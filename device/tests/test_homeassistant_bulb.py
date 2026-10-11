"""HomeAssistantBulb against a local fake HTTP server."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from clearday_home.bulb import FakeBulb, HomeAssistantBulb, make_bulb
from clearday_home.lights import AMBER, CALM_BLUE, LightPlayer
from clearday_home.state import Light

TOKEN = "secret-token-123"
ENTITY = "light.ecosmart"


class FakeHA:
    def __init__(self, delay: float = 0.0, status: int = 200) -> None:
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append(
                    {"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(body)}
                )
                time.sleep(delay)
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"[]")
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ha():
    server = FakeHA()
    yield server
    server.close()


def test_requests_are_exact(ha):
    bulb = HomeAssistantBulb(ha.url, TOKEN, ENTITY)
    bulb.set_color(AMBER)
    bulb.set_brightness(50)
    bulb.off()
    assert [r["path"] for r in ha.requests] == [
        "/api/services/light/turn_on",
        "/api/services/light/turn_on",
        "/api/services/light/turn_off",
    ]
    assert all(r["auth"] == f"Bearer {TOKEN}" for r in ha.requests)
    assert ha.requests[0]["body"] == {
        "entity_id": ENTITY,
        "rgb_color": list(AMBER),
        "brightness": 255,
        "transition": 1.0,
    }
    assert ha.requests[1]["body"]["brightness"] == 128
    assert ha.requests[1]["body"]["rgb_color"] == list(AMBER)
    assert ha.requests[2]["body"] == {"entity_id": ENTITY, "transition": 1}


def test_state_pattern_reaches_bulb_with_only_allowed_fields(ha):
    player = LightPlayer(HomeAssistantBulb(ha.url, TOKEN, ENTITY))
    player.start()
    player.play(Light.AMBER)
    deadline = time.time() + 3
    while len(ha.requests) < 2 and time.time() < deadline:
        time.sleep(0.02)
    player.stop()
    assert ha.requests[0]["body"]["rgb_color"] == list(AMBER)
    for r in ha.requests:
        assert set(r["body"]) <= {"entity_id", "rgb_color", "brightness", "transition"}


def test_celebrate_runs_in_background_and_newer_command_cancels(ha):
    bulb = HomeAssistantBulb(ha.url, TOKEN, ENTITY, celebration_step=0.1)
    start = time.monotonic()
    bulb.celebrate()
    assert time.monotonic() - start < 0.1
    time.sleep(0.25)
    bulb.set_color(CALM_BLUE)
    sent = len(ha.requests)
    time.sleep(0.6)
    assert len(ha.requests) == sent  # celebration stopped, nothing after the new colour
    assert ha.requests[-1]["body"]["rgb_color"] == list(CALM_BLUE)
    assert sent >= 2


def test_celebration_completes_when_uninterrupted(ha):
    bulb = HomeAssistantBulb(ha.url, TOKEN, ENTITY, celebration_step=0.02)
    bulb.celebrate()
    time.sleep(0.5)
    assert len(ha.requests) == 6


def test_unreachable_server_degrades_and_never_leaks_token(caplog):
    bulb = HomeAssistantBulb("http://127.0.0.1:9", TOKEN, ENTITY)
    caplog.set_level("INFO")
    bulb.set_color(AMBER)  # must not raise
    bulb.set_brightness(10)
    bulb.off()
    assert "failed" in caplog.text
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(bulb)
    assert caplog.text.count("failed") == 1


def test_timeout_is_short_and_failures_back_off():
    slow = FakeHA(delay=1.0)
    try:
        bulb = HomeAssistantBulb(slow.url, TOKEN, ENTITY, timeout=0.2)
        start = time.monotonic()
        bulb.set_color(AMBER)
        assert time.monotonic() - start < 0.8
        start = time.monotonic()
        bulb.set_color(CALM_BLUE)  # skipped during back-off
        assert time.monotonic() - start < 0.1
        assert len(slow.requests) <= 1
    finally:
        time.sleep(1.0)
        slow.close()


def test_http_error_status_is_swallowed():
    server = FakeHA(status=401)
    try:
        HomeAssistantBulb(server.url, TOKEN, ENTITY).set_color(AMBER)
    finally:
        server.close()


def test_no_amounts_or_names_reach_the_bulb(ha):
    bulb = HomeAssistantBulb(ha.url, TOKEN, ENTITY)
    bulb.set_color((1, 2, 3))
    bulb.set_brightness(40)
    bulb.celebrate()
    time.sleep(0.2)
    bulb.off()
    for r in ha.requests:
        assert set(r["body"]) <= {"entity_id", "rgb_color", "brightness", "transition"}
        assert "$" not in json.dumps(r["body"])


def test_make_bulb_config():
    env = {"HA_URL": "http://x:8123", "HA_TOKEN": TOKEN, "HA_LIGHT_ENTITY": ENTITY}
    assert isinstance(make_bulb("homeassistant", env), HomeAssistantBulb)
    assert isinstance(make_bulb("homeassistant", {**env, "HA_TOKEN": ""}), FakeBulb)
    assert isinstance(make_bulb("fake", env), FakeBulb)
