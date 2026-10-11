"""Smart bulb drivers: `FakeBulb` (default, logs) and `HomeAssistantBulb`.

The bulb is an EcoSmart bulb controlled through Home Assistant's REST API
(stdlib urllib only, no extra dependency). Pick the driver with
BULB_DRIVER=homeassistant|fake; HomeAssistantBulb reads HA_URL, HA_TOKEN and
HA_LIGHT_ENTITY. Only colours, brightness and on/off ever reach the bulb.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

log = logging.getLogger("clearday_home.bulb")

RGB = tuple[int, int, int]


@runtime_checkable
class BulbDriver(Protocol):
    def set_color(self, rgb: RGB) -> None:
        """Set the color, each channel 0 to 255."""

    def set_brightness(self, percent: int) -> None:
        """Set brightness, 1 to 100."""

    def celebrate(self) -> None:
        """Start the bulb's own party/celebration effect, or the closest built-in scene."""

    def off(self) -> None:
        """Turn the bulb off."""


class FakeBulb:
    """Logs commands instead of talking to hardware. Default driver."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, object]] = []

    def _record(self, op: str, value: object) -> None:
        self.commands.append((op, value))
        log.info("bulb %s %s", op, value)

    def set_color(self, rgb: RGB) -> None:
        self._record("color", tuple(rgb))

    def set_brightness(self, percent: int) -> None:
        self._record("brightness", max(1, min(100, int(percent))))

    def celebrate(self) -> None:
        self._record("celebrate", None)

    def off(self) -> None:
        self._record("off", None)


CELEBRATION_COLORS: tuple[RGB, ...] = (
    (255, 255, 255),
    (110, 190, 255),
    (40, 120, 255),
    (255, 255, 255),
    (90, 220, 255),
    (110, 190, 255),
)
CELEBRATION_STEP = 0.3  # seconds per colour: a few updates per second at most


class HomeAssistantBulb:
    """Drives a light entity through Home Assistant's REST API.

    Every request is `POST {url}/api/services/light/turn_on|turn_off` with a
    Bearer token. Failures are logged (error type only, never the token) and
    swallowed, so the state machine and LED matrix keep running; after a
    failure further requests are skipped for `retry_after` seconds so a dead
    HA does not stall the light thread on repeated timeouts.
    """

    def __init__(
        self,
        url: str,
        token: str,
        entity_id: str,
        *,
        timeout: float = 2.0,
        retry_after: float = 5.0,
        celebration_step: float = CELEBRATION_STEP,
    ) -> None:
        if not (url and token and entity_id):
            raise ValueError("HA_URL, HA_TOKEN and HA_LIGHT_ENTITY must all be set")
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("HA_URL must start with http:// or https://")
        self._url = url.rstrip("/")
        self._token = token
        self._entity = entity_id
        self._timeout = timeout
        self._retry_after = retry_after
        self._step = celebration_step
        self._rgb: RGB = (255, 255, 255)
        self._brightness = 255
        self._lock = threading.Lock()  # serialises requests and guards _generation
        self._generation = 0
        self._down_until = 0.0
        self._failing = False

    def __repr__(self) -> str:  # never print the token
        return f"HomeAssistantBulb(url={self._url!r}, entity={self._entity!r})"

    def set_color(self, rgb: RGB) -> None:
        self._rgb = _clamp_rgb(rgb)
        self._command(self._turn_on_payload(1.0))

    def set_brightness(self, percent: int) -> None:
        self._brightness = round(max(1, min(100, int(percent))) * 255 / 100)
        self._command(self._turn_on_payload(1.0))

    def off(self) -> None:
        self._command({"entity_id": self._entity, "transition": 1}, service="turn_off")

    def celebrate(self) -> None:
        """Short colour sequence on a background thread; any newer command cancels it."""
        with self._lock:
            self._generation += 1
            generation = self._generation
        threading.Thread(
            target=self._celebrate, args=(generation,), name="bulb-celebrate", daemon=True
        ).start()

    def _celebrate(self, generation: int) -> None:
        for rgb in CELEBRATION_COLORS:
            payload = {
                "entity_id": self._entity,
                "rgb_color": list(rgb),
                "brightness": 255,
                "transition": 0.2,
            }
            if not self._post("turn_on", payload, only_generation=generation):
                return
            time.sleep(self._step)

    def _turn_on_payload(self, transition: float) -> dict[str, object]:
        return {
            "entity_id": self._entity,
            "rgb_color": list(self._rgb),
            "brightness": self._brightness,
            "transition": transition,
        }

    def _command(self, payload: dict[str, object], service: str = "turn_on") -> None:
        with self._lock:
            self._generation += 1  # cancels a running celebration
        self._post(service, payload)

    def _post(self, service: str, payload: dict[str, object], only_generation: int | None = None) -> bool:
        """Send one request. Returns False if cancelled by a newer command."""
        with self._lock:
            if only_generation is not None and only_generation != self._generation:
                return False
            if time.monotonic() < self._down_until:
                return True
            request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
                f"{self._url}/api/services/light/{service}",
                data=json.dumps(payload).encode(),
                method="POST",
                headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                    response.read()
                if self._failing:
                    log.info("home assistant reachable again")
                self._failing = False
            except Exception as exc:  # noqa: BLE001 - bulb trouble must never stop the state machine
                if not self._failing:
                    log.warning(
                        "home assistant bulb call failed (%s); continuing without the bulb",
                        type(exc).__name__,
                    )
                self._failing = True
                self._down_until = time.monotonic() + self._retry_after
        return True


def _clamp_rgb(rgb: RGB) -> RGB:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    return (r, g, b)


def make_bulb(kind: str, env: Mapping[str, str] | None = None) -> BulbDriver:
    """Pick the driver from BULB_DRIVER. Falls back to FakeBulb (matrix-only demo) if the real one fails."""
    env = os.environ if env is None else env
    kind = kind.lower()
    if kind == "homeassistant":
        try:
            return HomeAssistantBulb(
                env.get("HA_URL", "").strip(),
                env.get("HA_TOKEN", "").strip(),
                env.get("HA_LIGHT_ENTITY", "").strip(),
            )
        except Exception as exc:  # noqa: BLE001 - any driver failure falls back per the hardware doc
            log.warning("bulb driver %r unavailable (%s); using FakeBulb", kind, exc)
            return FakeBulb()
    if kind != "fake":
        log.warning("unknown BULB_DRIVER %r; using FakeBulb", kind)
    return FakeBulb()
