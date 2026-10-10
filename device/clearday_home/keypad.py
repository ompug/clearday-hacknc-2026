"""USB numeric keypad via evdev (Linux only; `uv sync --group keypad`).

The Briefing key (default KEY_KPENTER; change with CLEARDAY_BRIEFING_KEY)
calls POST /api/device/briefing and plays the result. Holding it for
HOLD_SECONDS enters Listening (stretch); releasing returns to the base state.
"""

from __future__ import annotations

import logging
import threading
import time

from clearday_home.controller import Controller

log = logging.getLogger("clearday_home.keypad")

HOLD_SECONDS = 0.8
KEY_DOWN, KEY_UP, KEY_HOLD = 1, 0, 2


class KeyTracker:
    """Turns key down/up into press (short) or hold (long). Pure, for tests."""

    def __init__(self, hold_seconds: float = HOLD_SECONDS) -> None:
        self.hold_seconds = hold_seconds
        self._down_at: float | None = None
        self._holding = False

    def down(self, now: float) -> None:
        self._down_at = now
        self._holding = False

    def poll(self, now: float) -> str | None:
        if self._down_at is not None and not self._holding and now - self._down_at >= self.hold_seconds:
            self._holding = True
            return "hold"
        return None

    def up(self, now: float) -> str | None:
        if self._down_at is None:
            return None
        was_holding = self._holding or now - self._down_at >= self.hold_seconds
        self._down_at = None
        self._holding = False
        return "release" if was_holding else "press"


def start_keypad(controller: Controller, device_path: str | None, key_name: str) -> threading.Thread | None:
    try:
        import evdev  # type: ignore[import-not-found]  # optional "keypad" group
    except ImportError:
        log.info("evdev not installed; keypad disabled (uv sync --group keypad)")
        return None

    def find_device():
        if device_path:
            return evdev.InputDevice(device_path)
        for path in evdev.list_devices():
            dev = evdev.InputDevice(path)
            if evdev.ecodes.EV_KEY in dev.capabilities() and "key" in dev.name.lower():
                return dev
        return None

    code = evdev.ecodes.ecodes.get(key_name)
    if code is None:
        log.warning("unknown key %r; keypad disabled", key_name)
        return None

    def run() -> None:
        dev = find_device()
        if dev is None:
            log.warning("no keypad found; set CLEARDAY_KEYPAD_DEVICE=/dev/input/eventN")
            return
        log.info("keypad ready on %s", dev.path)
        tracker = KeyTracker()
        for event in dev.read_loop():
            if event.type != evdev.ecodes.EV_KEY or event.code != code:
                continue
            now = time.monotonic()
            if event.value == KEY_DOWN:
                tracker.down(now)
            elif event.value == KEY_HOLD and tracker.poll(now) == "hold":
                controller.key_held()
            elif event.value == KEY_UP:
                action = tracker.up(now)
                if action == "press":
                    threading.Thread(target=controller.briefing, daemon=True).start()
                elif action == "release":
                    controller.key_released()

    thread = threading.Thread(target=run, name="keypad", daemon=True)
    thread.start()
    return thread
