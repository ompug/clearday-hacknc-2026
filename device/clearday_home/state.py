"""Device state machine, per docs/04-clearday-home-hardware.md "Device states and behaviors".

Pure Python: no I/O, no clock. Callers pass `now` (monotonic seconds) and
apply the returned effects. Every state pairs a light pattern with a matrix
icon or a sound so status never depends on color alone.

Base states come from the latest household status:
    Offline > Bill due soon > Tight week ahead > Clear skies
Transient states play over the base and then fall back to it:
    Share paid (sparkle), Bubble popped (burst), Briefing (until audio ends),
    Listening (while the key is held; stretch).
Going offline cancels any transient immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from clearday_home.payloads import HouseholdStatus


class State(StrEnum):
    CLEAR = "clear_skies"
    TIGHT = "tight_week"
    DUE_SOON = "bill_due_soon"
    SHARE_PAID = "share_paid"
    POPPED = "bubble_popped"
    BRIEFING = "briefing"
    LISTENING = "listening"
    OFFLINE = "offline"


class Light(StrEnum):
    BREATHE_BLUE = "breathe_blue"  # Clear skies: slow calm blue breathing
    AMBER = "amber"  # Tight week ahead: soft amber
    PULSE = "pulse"  # Bill due soon: gentle pulse
    SPARKLE = "sparkle"  # Share paid: brief sparkle
    BURST = "burst"  # Bubble popped: burst, then blue
    SHIMMER = "shimmer"  # Briefing: rotating shimmer while speaking
    WHITE = "white"  # Listening: steady white
    DIM_GRAY = "dim_gray"  # Offline: dim slow gray


class Sound(StrEnum):
    CHIME = "chime"


@dataclass(frozen=True)
class SetLight:
    pattern: Light


@dataclass(frozen=True)
class SetMatrix:
    command: str  # bridge string, e.g. "matrix:sun"


@dataclass(frozen=True)
class PlaySound:
    sound: Sound


Effect = SetLight | SetMatrix | PlaySound

MATRIX_SUN = "matrix:sun"
MATRIX_CLOUD = "matrix:cloud"
MATRIX_DASH = "matrix:dash"
MATRIX_MIC = "matrix:mic"  # Listening (stretch); the sketch draws it too


def matrix_count(n: int) -> str:
    return f"matrix:count:{max(0, min(n, 99))}"


@dataclass(frozen=True)
class Durations:
    share_paid: float = 2.5
    popped: float = 4.0
    briefing_max: float = 60.0  # safety net if the audio never reports done


class DeviceMachine:
    def __init__(self, durations: Durations | None = None) -> None:
        self.durations = durations or Durations()
        self.online = False
        self.status: HouseholdStatus | None = None
        self._transient: State | None = None
        self._until = 0.0
        self._light: Light | None = None
        self._matrix: str | None = None

    # ---- queries -------------------------------------------------------

    @property
    def base_state(self) -> State:
        if not self.online or self.status is None:
            return State.OFFLINE
        if self.status.due_soon_bills > 0:
            return State.DUE_SOON
        if self.status.weather == "tight":
            return State.TIGHT
        return State.CLEAR

    @property
    def state(self) -> State:
        return self._transient or self.base_state

    # ---- inputs ----------------------------------------------------------

    def start(self) -> list[Effect]:
        """Initial effects at boot: Offline until the backend answers."""
        return self._render()

    def on_online(self, now: float) -> list[Effect]:
        self.online = True
        return self.tick(now)

    def on_offline(self, now: float) -> list[Effect]:
        self.online = False
        self._transient = None
        return self._render()

    def on_status(self, status: HouseholdStatus, now: float, infer_events: bool = False) -> list[Effect]:
        """New status. With `infer_events` (polling fallback, no Socket.IO events),
        a drop in open bills plays the pop and a rise in paid shares plays the sparkle."""
        previous = self.status
        self.status = status
        self.online = True
        if infer_events and previous is not None:
            if status.open_bills < previous.open_bills:
                return self.on_bubble_popped(now)
            if status.shares_paid > previous.shares_paid:
                return self.on_share_updated(now)
        return self.tick(now)

    def on_share_updated(self, now: float) -> list[Effect]:
        if not self.online:
            return []
        if self._transient in (State.POPPED, State.BRIEFING, State.LISTENING):
            return self.tick(now)  # don't interrupt a bigger moment; count still updates
        return self._enter(State.SHARE_PAID, now + self.durations.share_paid, sound=True)

    def on_bubble_popped(self, now: float) -> list[Effect]:
        if not self.online:
            return []
        return self._enter(State.POPPED, now + self.durations.popped, sound=True)

    def on_briefing_start(self, now: float) -> list[Effect]:
        if not self.online:
            return []
        return self._enter(State.BRIEFING, now + self.durations.briefing_max, sound=False)

    def on_briefing_end(self, now: float) -> list[Effect]:
        if self._transient is State.BRIEFING:
            self._transient = None
        return self.tick(now)

    def on_key_held(self, now: float) -> list[Effect]:
        if not self.online:
            return []
        return self._enter(State.LISTENING, float("inf"), sound=False)

    def on_key_released(self, now: float) -> list[Effect]:
        if self._transient is State.LISTENING:
            self._transient = None
        return self.tick(now)

    def tick(self, now: float) -> list[Effect]:
        if self._transient is not None and now >= self._until:
            self._transient = None
        return self._render()

    # ---- internals ---------------------------------------------------------

    def _enter(self, state: State, until: float, sound: bool) -> list[Effect]:
        self._transient = state
        self._until = until
        self._light = None  # restart the animation even if the same pattern is running
        effects = self._render()
        if sound:
            effects.append(PlaySound(Sound.CHIME))
        return effects

    def _weather_icon(self) -> str:
        return MATRIX_CLOUD if self.status is not None and self.status.weather == "tight" else MATRIX_SUN

    def _open_count(self) -> str:
        return matrix_count(self.status.open_bills if self.status else 0)

    def _look(self, state: State) -> tuple[Light, str]:
        match state:
            case State.CLEAR:
                return Light.BREATHE_BLUE, MATRIX_SUN
            case State.TIGHT:
                return Light.AMBER, MATRIX_CLOUD
            case State.DUE_SOON:
                return Light.PULSE, self._open_count()
            case State.SHARE_PAID:
                return Light.SPARKLE, self._open_count()
            case State.POPPED:
                return Light.BURST, MATRIX_SUN
            case State.BRIEFING:
                return Light.SHIMMER, self._weather_icon()
            case State.LISTENING:
                return Light.WHITE, MATRIX_MIC
            case State.OFFLINE:
                return Light.DIM_GRAY, MATRIX_DASH

    def _render(self) -> list[Effect]:
        light, matrix = self._look(self.state)
        effects: list[Effect] = []
        if light != self._light:
            self._light = light
            effects.append(SetLight(light))
        if matrix != self._matrix:
            self._matrix = matrix
            effects.append(SetMatrix(matrix))
        return effects
