"""Smart bulb drivers. The brand is TBD (WiZ first choice, Kasa second).

`BulbDriver` is everything the light patterns need. Only `FakeBulb` is
implemented; it logs each command. To add a real bulb, fill in `WizBulb` or
`KasaBulb`, add its library to device/pyproject.toml (pywizlight or
python-kasa, after team sign-off), and set CLEARDAY_BULB=wiz|kasa plus
CLEARDAY_BULB_IP.
"""

from __future__ import annotations

import logging
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


class WizBulb:
    """Slot for a WiZ bulb via pywizlight (not installed yet).

    pywizlight is asyncio: run one event loop in a background thread and use
    `PilotBuilder(rgb=..., brightness=...)`; `celebrate` can use a party scene.
    """

    def __init__(self, ip: str) -> None:
        raise NotImplementedError("WizBulb is not implemented yet; use CLEARDAY_BULB=fake")


class KasaBulb:
    """Slot for a TP-Link Kasa bulb via python-kasa (not installed yet).

    python-kasa is asyncio: `Device.connect(host=ip)`, then the light module's
    `set_hsv` / `set_brightness`; `celebrate` can be a short HSV sweep.
    """

    def __init__(self, ip: str) -> None:
        raise NotImplementedError("KasaBulb is not implemented yet; use CLEARDAY_BULB=fake")


def make_bulb(kind: str, ip: str | None) -> BulbDriver:
    """Pick the driver from config. Falls back to FakeBulb (matrix-only demo) if the real one fails."""
    kind = kind.lower()
    try:
        if kind == "wiz":
            return WizBulb(_need_ip(ip))
        if kind == "kasa":
            return KasaBulb(_need_ip(ip))
    except Exception as exc:  # noqa: BLE001 - any driver failure falls back per the hardware doc
        log.warning("bulb driver %r unavailable (%s); using FakeBulb", kind, exc)
        return FakeBulb()
    if kind != "fake":
        log.warning("unknown CLEARDAY_BULB %r; using FakeBulb", kind)
    return FakeBulb()


def _need_ip(ip: str | None) -> str:
    if not ip:
        raise ValueError("CLEARDAY_BULB_IP is not set")
    return ip
