"""Light patterns as short loops of bulb commands, and a thread that plays them.

Smart bulbs drop rapid commands, so every step holds for at least
MIN_HOLD seconds (a few updates per second at most). A failing bulb is logged
and skipped; the matrix keeps working (hardware doc, Fallbacks).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from clearday_home.bulb import RGB, BulbDriver
from clearday_home.state import Light

log = logging.getLogger("clearday_home.lights")

MIN_HOLD = 0.35

CALM_BLUE: RGB = (40, 120, 255)
SKY_BLUE: RGB = (110, 190, 255)
AMBER: RGB = (255, 150, 30)
WHITE: RGB = (255, 255, 255)
GRAY: RGB = (150, 150, 170)


@dataclass(frozen=True)
class Step:
    hold: float
    rgb: RGB | None = None
    brightness: int | None = None
    celebrate: bool = False


@dataclass(frozen=True)
class Pattern:
    steps: tuple[Step, ...]
    loop: bool
    then: Light | None = None  # pattern to continue with when a one-shot ends


def _breathe(rgb: RGB, low: int, high: int, hold: float) -> tuple[Step, ...]:
    return (
        Step(hold, rgb, high),
        Step(hold, rgb, (low + high) // 2),
        Step(hold, rgb, low),
        Step(hold, rgb, (low + high) // 2),
    )


PATTERNS: dict[Light, Pattern] = {
    Light.BREATHE_BLUE: Pattern(_breathe(CALM_BLUE, 35, 80, 1.5), loop=True),
    Light.AMBER: Pattern((Step(5.0, AMBER, 55),), loop=True),
    Light.PULSE: Pattern((Step(0.8, SKY_BLUE, 85), Step(0.8, SKY_BLUE, 40)), loop=True),
    Light.SPARKLE: Pattern(
        (Step(0.4, WHITE, 100), Step(0.4, SKY_BLUE, 70), Step(0.4, WHITE, 100), Step(0.6, CALM_BLUE, 70)),
        loop=False,
    ),
    Light.BURST: Pattern(
        (Step(1.5, celebrate=True), Step(0.5, WHITE, 100), Step(0.5, SKY_BLUE, 90), Step(0.6, CALM_BLUE, 75)),
        loop=False,
        then=Light.BREATHE_BLUE,
    ),
    Light.SHIMMER: Pattern(
        (Step(0.6, CALM_BLUE, 70), Step(0.6, SKY_BLUE, 80), Step(0.6, (90, 220, 255), 75)), loop=True
    ),
    Light.WHITE: Pattern((Step(5.0, WHITE, 80),), loop=True),
    Light.DIM_GRAY: Pattern((Step(2.5, GRAY, 12), Step(2.5, GRAY, 6)), loop=True),
}


class LightPlayer:
    """Plays one pattern at a time on a background thread; `play` replaces the current one."""

    def __init__(self, bulb: BulbDriver) -> None:
        self.bulb = bulb
        self._wake = threading.Condition()
        self._pattern: Light | None = None
        self._generation = 0
        self._stopped = False
        self._bulb_ok = True
        self._last_rgb: RGB | None = None
        self._thread = threading.Thread(target=self._run, name="lights", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def play(self, pattern: Light) -> None:
        with self._wake:
            self._pattern = pattern
            self._generation += 1
            self._wake.notify_all()

    def stop(self) -> None:
        with self._wake:
            self._stopped = True
            self._wake.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=2)
        self._send(lambda: self.bulb.off())

    def _send(self, command) -> None:
        try:
            command()
            if not self._bulb_ok:
                log.info("bulb reachable again")
            self._bulb_ok = True
        except Exception as exc:  # noqa: BLE001 - bulb trouble must never stop the matrix
            if self._bulb_ok:
                log.warning("bulb command failed (%s); continuing with matrix only", type(exc).__name__)
            self._bulb_ok = False

    def _run(self) -> None:
        while True:
            with self._wake:
                while self._pattern is None and not self._stopped:
                    self._wake.wait()
                if self._stopped:
                    return
                name, generation = self._pattern, self._generation
            self._play_once(name, generation)

    def _play_once(self, name: Light, generation: int) -> None:
        pattern = PATTERNS[name]
        for step in pattern.steps:
            if step.celebrate:
                self._last_rgb = None
                self._send(self.bulb.celebrate)
            else:
                if step.rgb is not None and step.rgb != self._last_rgb:
                    self._last_rgb = step.rgb
                    self._send(lambda rgb=step.rgb: self.bulb.set_color(rgb))
                if step.brightness is not None:
                    self._send(lambda b=step.brightness: self.bulb.set_brightness(b))
            with self._wake:
                if self._wake.wait_for(
                    lambda: self._stopped or self._generation != generation, timeout=max(step.hold, MIN_HOLD)
                ):
                    return  # replaced or stopped
        with self._wake:
            if self._generation != generation:
                return
            if not pattern.loop:
                # one-shot done: continue with its follow-up, or hold the last frame
                self._pattern = pattern.then
                if pattern.then is not None:
                    self._generation += 1
