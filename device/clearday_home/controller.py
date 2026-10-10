"""Glue between inputs (Socket.IO, polling, keypad) and outputs (bulb, matrix, audio).

All state lives in the pure `DeviceMachine`; this class serializes access with
a lock and applies the effects it returns.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from clearday_home.api_client import ApiClient
from clearday_home.audio import Audio
from clearday_home.lights import LightPlayer
from clearday_home.matrix import MatrixLink
from clearday_home.payloads import Announcement, HouseholdStatus
from clearday_home.state import DeviceMachine, Effect, PlaySound, SetLight, SetMatrix

log = logging.getLogger("clearday_home.controller")


class Controller:
    def __init__(
        self,
        machine: DeviceMachine,
        lights: LightPlayer,
        matrix: MatrixLink,
        audio: Audio,
        api: ApiClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.machine = machine
        self.lights = lights
        self.matrix = matrix
        self.audio = audio
        self.api = api
        self.clock = clock
        self._lock = threading.RLock()
        self._stop = threading.Event()

    # ---- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self.lights.start()
        self._apply(self.machine.start())
        threading.Thread(target=self._tick_loop, name="tick", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.lights.stop()

    def _tick_loop(self) -> None:
        while not self._stop.wait(0.25):
            self._step(lambda now: self.machine.tick(now))

    # ---- inputs ------------------------------------------------------------

    def online(self) -> None:
        log.info("backend connected")
        self._step(self.machine.on_online)

    def offline(self) -> None:
        if self.machine.online:
            log.info("backend unreachable; showing Offline")
        self._step(self.machine.on_offline)

    def status(self, status: HouseholdStatus, infer_events: bool = False) -> None:
        self._step(lambda now: self.machine.on_status(status, now, infer_events=infer_events))

    def refresh_status(self, infer_events: bool = False) -> bool:
        """Fetch /api/household/status. Returns False (and goes Offline) on failure."""
        try:
            status = self.api.household_status()
        except Exception as exc:  # noqa: BLE001 - any failure means we can't trust the status
            if self.machine.online:  # log the transition, not every poll
                log.warning("status fetch failed (%s)", type(exc).__name__)
            self.offline()
            return False
        self.status(status, infer_events=infer_events)
        return True

    def share_updated(self) -> None:
        log.info("event share.updated")
        self._step(self.machine.on_share_updated)

    def bubble_popped(self) -> None:
        log.info("event bubble.popped")
        self._step(self.machine.on_bubble_popped)

    def announce(self, announcement: Announcement) -> None:
        log.info("event device.announce")
        try:
            path = self.api.download_audio(announcement.audio_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("announcement download failed (%s)", type(exc).__name__)
            return
        self.audio.play(path)

    def briefing(self) -> None:
        """Briefing key: fetch household briefing audio and shimmer while it plays."""
        log.info("briefing requested")
        if not self.machine.online:
            return
        try:
            path = self.api.briefing_audio()
        except Exception as exc:  # noqa: BLE001
            log.warning("briefing fetch failed (%s)", type(exc).__name__)
            return
        self._step(self.machine.on_briefing_start)
        self.audio.play(path, on_done=lambda: self._step(self.machine.on_briefing_end))

    def key_held(self) -> None:
        self._step(self.machine.on_key_held)

    def key_released(self) -> None:
        self._step(self.machine.on_key_released)

    # ---- outputs -----------------------------------------------------------

    def _step(self, handler: Callable[[float], list[Effect]]) -> None:
        with self._lock:
            before = self.machine.state
            effects = handler(self.clock())
            if self.machine.state != before:
                log.info("state %s -> %s", before, self.machine.state)
            self._apply(effects)

    def _apply(self, effects: list[Effect]) -> None:
        for effect in effects:
            match effect:
                case SetLight(pattern):
                    self.lights.play(pattern)
                case SetMatrix(command):
                    self.matrix.send(command)
                case PlaySound():
                    self.audio.chime()
