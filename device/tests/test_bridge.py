"""Bridge against an in-process fake API: auth, event mapping, fallbacks, privacy."""

from __future__ import annotations

import logging
import time

import pytest

from clearday_home.api_client import ApiClient
from clearday_home.bridge import Bridge
from clearday_home.bulb import FakeBulb
from clearday_home.controller import Controller
from clearday_home.lights import LightPlayer
from clearday_home.matrix import LogMatrix
from clearday_home.state import DeviceMachine, Durations, State
from tests.fake_server import TOKEN, FakeApi

SECRETS = ("45000", "Alex Rivera", "Jordan", "Groceries at Hidden Mart", "9911")


class RecordingAudio:
    def __init__(self) -> None:
        self.chimes = 0
        self.played = []

    def chime(self) -> None:
        self.chimes += 1

    def play(self, path, delete=True, on_done=None) -> None:
        self.played.append(path.read_bytes())
        path.unlink(missing_ok=True)
        if on_done:
            on_done()


def wait_for(cond, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


@pytest.fixture
def api():
    server = FakeApi().start()
    yield server
    server.stop()


def make_device(api_url, token=TOKEN):
    bulb, matrix, audio = FakeBulb(), LogMatrix(), RecordingAudio()
    controller = Controller(
        DeviceMachine(Durations(share_paid=0.3, popped=0.5)),
        LightPlayer(bulb),
        matrix,
        audio,
        ApiClient(api_url, token),
    )
    bridge = Bridge(controller, api_url, token, poll_interval=0.1, transports=["polling"], connect_timeout=1)
    controller.start()
    bridge.start()
    return controller, bridge, bulb, matrix, audio


@pytest.fixture
def device(api):
    controller, bridge, bulb, matrix, audio = make_device(api.url)
    yield controller, bulb, matrix, audio
    bridge.stop()
    controller.stop()


def test_connects_with_token_and_loads_status(api, device):
    controller, _bulb, matrix, _audio = device
    assert api.connected.wait(5)
    wait_for(lambda: controller.machine.state is State.DUE_SOON)
    assert matrix.sent[0] == "matrix:dash"
    assert matrix.sent[-1] == "matrix:count:1"
    assert ("/api/household/status", f"Bearer {TOKEN}") in api.requests


def test_bubble_popped_bursts_then_settles_clear(api, device):
    """Acceptance test path: last share paid -> burst, chime, sun, then calm blue."""
    controller, bulb, matrix, audio = device
    assert api.connected.wait(5)
    wait_for(lambda: controller.machine.state is State.DUE_SOON)
    api.status = {
        "weather": "clear",
        "open_bills": 0,
        "due_soon_bills": 0,
        "shares_paid": 3,
        "shares_total": 3,
    }
    api.emit("bubble.popped", {"expense_id": 7, "label": "Groceries at Hidden Mart"})
    wait_for(lambda: controller.machine.state is State.POPPED)
    wait_for(lambda: ("celebrate", None) in bulb.commands)
    assert audio.chimes == 1
    assert matrix.sent[-1] == "matrix:sun"
    wait_for(lambda: controller.machine.state is State.CLEAR)


def test_share_updated_sparkles_and_refreshes_count(api, device):
    controller, _bulb, matrix, audio = device
    assert api.connected.wait(5)
    wait_for(lambda: controller.machine.state is State.DUE_SOON)
    api.status = {**api.status, "open_bills": 2, "shares_paid": 3, "shares_total": 4}
    api.emit("share.updated", {"expense_id": 7, "share_id": 3, "status": "paid", "fill_fraction": 0.75})
    wait_for(lambda: audio.chimes == 1)
    wait_for(lambda: matrix.sent[-1] == "matrix:count:2")


def test_announce_downloads_from_our_api_only(api, device):
    _controller, _bulb, _matrix, audio = device
    assert api.connected.wait(5)
    api.emit("device.announce", {"audio_url": "https://elsewhere.example/a.mp3", "light_pattern": "burst"})
    api.emit("device.announce", {"audio_url": "/api/device/audio/1.wav", "light_pattern": "burst"})
    wait_for(lambda: len(audio.played) == 1)
    assert not any("elsewhere" in path for path, _ in api.requests)


def test_bad_token_is_rejected_and_shows_offline(api):
    controller, bridge, _bulb, matrix, _audio = make_device(api.url, token="wrong")  # noqa: S106
    try:
        time.sleep(0.5)
        assert not api.connected.is_set()
        assert controller.machine.state is State.OFFLINE
        assert set(matrix.sent) == {"matrix:dash"}
    finally:
        bridge.stop()
        controller.stop()


def test_polls_status_when_socket_fails_and_infers_pop(api):
    api.socket_up = False
    controller, bridge, _bulb, _matrix, audio = make_device(api.url)
    try:
        wait_for(lambda: controller.machine.state is State.DUE_SOON)
        api.status = {
            "weather": "clear",
            "open_bills": 0,
            "due_soon_bills": 0,
            "shares_paid": 3,
            "shares_total": 3,
        }
        wait_for(lambda: audio.chimes == 1)
        wait_for(lambda: controller.machine.state is State.CLEAR)
        api.http_up = False
        wait_for(lambda: controller.machine.state is State.OFFLINE)
    finally:
        bridge.stop()
        controller.stop()


def test_never_handles_amounts_or_names(api, device, caplog):
    """Salted payloads: no amount or name reaches state, outputs or logs."""
    caplog.set_level(logging.DEBUG, logger="clearday_home")
    controller, bulb, matrix, _audio = device
    assert api.connected.wait(5)
    api.status = {
        "weather": "tight",
        "open_bills": 1,
        "due_soon_bills": 0,
        "shares_paid": 1,
        "shares_total": 2,
        "total_cents": 45000,
        "members": ["Alex Rivera", "Jordan"],
        "last4": "9911",
    }
    api.emit("share.updated", {"expense_id": 7, "amount_cents": 45000, "actor": "Jordan"})
    api.emit("bubble.popped", {"expense_id": 7, "label": "Groceries at Hidden Mart"})
    api.emit("forecast.updated", {"safe_to_spend_cents": 45000, "user": "Alex Rivera"})
    wait_for(lambda: controller.machine.status is not None and controller.machine.status.weather == "tight")
    time.sleep(0.6)
    observed = " ".join(
        [
            repr(vars(controller.machine)),
            " ".join(matrix.sent),
            repr(bulb.commands),
            caplog.text,
        ]
    )
    for secret in SECRETS:
        assert secret not in observed
