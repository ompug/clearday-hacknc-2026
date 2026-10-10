"""Backend link: Socket.IO household room, with status polling as the fallback.

Auth: the device token goes in the Socket.IO `auth` payload as
`{"token": ...}` and in an `Authorization: Bearer` header for HTTP. The server
derives the household from the token; the device never names its household.

Events are triggers only. Their payloads (which may carry fill fractions,
labels or, for forecast.updated, safe-to-spend) are ignored; after each event
the device re-reads `/api/household/status`, which carries counts only.
The one exception is device.announce, whose audio path is validated to point
at our own API.

Supervisor loop (hardware doc, "Reconnect with backoff" and Fallbacks):
  - not connected: try Socket.IO, backing off 1 s -> 30 s between attempts;
  - between attempts, poll status every `poll_interval` s (events inferred
    from status changes); if polling fails too, show Offline.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import socketio

from clearday_home.controller import Controller
from clearday_home.payloads import PayloadError, parse_announcement

log = logging.getLogger("clearday_home.bridge")

HOUSEHOLD_EVENTS = ("share.updated", "bubble.popped", "forecast.updated", "device.announce")
BACKOFF_START = 1.0
BACKOFF_MAX = 30.0


class Bridge:
    def __init__(
        self,
        controller: Controller,
        api_url: str,
        token: str,
        poll_interval: float = 2.0,
        transports: list[str] | None = None,
        connect_timeout: float = 5.0,
    ) -> None:
        self.controller = controller
        self.api_url = api_url
        self._token = token
        self.poll_interval = poll_interval
        self.transports = transports
        self.connect_timeout = connect_timeout
        self.sio = socketio.Client(reconnection=False, logger=False, engineio_logger=False)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._register()

    # ---- Socket.IO handlers -------------------------------------------------

    def _register(self) -> None:
        sio = self.sio

        @sio.event
        def connect() -> None:
            self.controller.online()
            self._background(self.controller.refresh_status)

        @sio.event
        def connect_error(data: Any) -> None:
            log.warning("socket connect rejected")

        @sio.event
        def disconnect(*_reason: Any) -> None:
            log.info("socket disconnected")
            self.controller.offline()

        @sio.on("share.updated")
        def share_updated(_payload: Any = None) -> None:
            self.controller.share_updated()
            self._background(self.controller.refresh_status)

        @sio.on("bubble.popped")
        def bubble_popped(_payload: Any = None) -> None:
            self.controller.bubble_popped()
            self._background(self.controller.refresh_status)

        @sio.on("forecast.updated")
        def forecast_updated(_payload: Any = None) -> None:
            self._background(self.controller.refresh_status)

        @sio.on("device.announce")
        def device_announce(payload: Any = None) -> None:
            try:
                announcement = parse_announcement(payload)
            except PayloadError as exc:
                log.warning("ignored device.announce: %s", exc)
                return
            self._background(lambda: self.controller.announce(announcement))

    @staticmethod
    def _background(fn) -> None:
        threading.Thread(target=fn, daemon=True).start()

    # ---- supervisor ------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="bridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.sio.connected:
            self.sio.disconnect()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run(self) -> None:
        backoff = BACKOFF_START
        next_attempt = 0.0
        while not self._stop.is_set():
            if self.sio.connected:
                backoff = BACKOFF_START
                self._stop.wait(0.5)
                continue
            if time.monotonic() >= next_attempt and self._try_connect():
                continue
            if time.monotonic() >= next_attempt:
                next_attempt = time.monotonic() + backoff
                backoff = min(backoff * 2, BACKOFF_MAX)
            # Fallback: poll status while the socket is down.
            self.controller.refresh_status(infer_events=True)
            self._stop.wait(self.poll_interval)

    def _try_connect(self) -> bool:
        try:
            self.sio.connect(
                self.api_url,
                auth={"token": self._token},
                headers={"Authorization": f"Bearer {self._token}"},
                transports=self.transports,
                wait_timeout=self.connect_timeout,
            )
            return True
        except socketio.exceptions.ConnectionError as exc:
            log.info("socket connect failed (%s); polling status", type(exc).__name__)
            return False
