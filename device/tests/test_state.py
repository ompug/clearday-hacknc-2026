"""Device state machine, per docs/04-clearday-home-hardware.md "Device states and behaviors"."""

from clearday_home.payloads import HouseholdStatus
from clearday_home.state import (
    MATRIX_CLOUD,
    MATRIX_DASH,
    MATRIX_MIC,
    MATRIX_SUN,
    DeviceMachine,
    Durations,
    Light,
    PlaySound,
    SetLight,
    SetMatrix,
    Sound,
    State,
)


def status(weather="clear", open_bills=2, due_soon=0, paid=1, total=4):
    return HouseholdStatus(weather, open_bills, due_soon, paid, total)


def online(st=None):
    m = DeviceMachine(Durations(share_paid=2, popped=4, briefing_max=60))
    m.start()
    m.on_status(st or status(), 0)
    return m


def test_boots_offline_with_dim_gray_and_dash():
    m = DeviceMachine()
    assert m.start() == [SetLight(Light.DIM_GRAY), SetMatrix(MATRIX_DASH)]
    assert m.state is State.OFFLINE


def test_connected_without_status_stays_offline():
    m = DeviceMachine()
    m.start()
    assert m.on_online(0) == []
    assert m.state is State.OFFLINE


def test_clear_skies():
    m = DeviceMachine()
    m.start()
    assert m.on_status(status(), 0) == [SetLight(Light.BREATHE_BLUE), SetMatrix(MATRIX_SUN)]
    assert m.state is State.CLEAR


def test_tight_week():
    m = DeviceMachine()
    m.start()
    assert m.on_status(status(weather="tight"), 0) == [SetLight(Light.AMBER), SetMatrix(MATRIX_CLOUD)]
    assert m.state is State.TIGHT


def test_due_soon_shows_open_bill_count_and_beats_tight():
    m = DeviceMachine()
    m.start()
    effects = m.on_status(status(weather="tight", open_bills=3, due_soon=1), 0)
    assert effects == [SetLight(Light.PULSE), SetMatrix("matrix:count:3")]
    assert m.state is State.DUE_SOON


def test_unchanged_status_emits_nothing():
    m = online()
    assert m.on_status(status(), 1) == []


def test_share_paid_sparkles_chimes_then_returns():
    m = online(status(due_soon=1, open_bills=2))
    effects = m.on_share_updated(1)
    assert SetLight(Light.SPARKLE) in effects and PlaySound(Sound.CHIME) in effects
    assert m.state is State.SHARE_PAID
    # count updates while sparkling
    assert m.on_status(status(due_soon=1, open_bills=1), 1.5) == [SetMatrix("matrix:count:1")]
    assert m.tick(2.9) == []
    assert m.tick(3.0) == [SetLight(Light.PULSE)]
    assert m.state is State.DUE_SOON


def test_repeated_share_paid_restarts_sparkle():
    m = online()
    m.on_share_updated(1)
    assert SetLight(Light.SPARKLE) in m.on_share_updated(1.5)


def test_bubble_popped_bursts_sun_chime_then_calm_blue():
    """Acceptance test: last share paid -> burst, then calm blue and the sun icon."""
    m = online(status(due_soon=1, open_bills=1, paid=2, total=3))
    effects = m.on_bubble_popped(1)
    assert effects == [SetLight(Light.BURST), SetMatrix(MATRIX_SUN), PlaySound(Sound.CHIME)]
    assert m.state is State.POPPED
    m.on_status(status(open_bills=0, due_soon=0, paid=3, total=3), 1.2)
    assert m.state is State.POPPED
    assert m.tick(5.0) == [SetLight(Light.BREATHE_BLUE)]
    assert m.state is State.CLEAR


def test_share_update_does_not_interrupt_pop():
    m = online()
    m.on_bubble_popped(1)
    m.on_share_updated(1.1)
    assert m.state is State.POPPED


def test_briefing_shimmers_with_weather_icon_until_audio_ends():
    m = online(status(weather="tight"))
    assert m.on_briefing_start(1) == [SetLight(Light.SHIMMER)]  # cloud icon already showing
    assert m.state is State.BRIEFING
    assert m.on_briefing_end(10) == [SetLight(Light.AMBER)]
    m2 = online(status(due_soon=1))
    assert m2.on_briefing_start(1) == [SetLight(Light.SHIMMER), SetMatrix(MATRIX_SUN)]


def test_briefing_times_out():
    m = online()
    m.on_briefing_start(0)
    m.tick(61)
    assert m.state is State.CLEAR


def test_listening_while_held():
    m = online()
    assert m.on_key_held(1) == [SetLight(Light.WHITE), SetMatrix(MATRIX_MIC)]
    assert m.tick(1000) == []
    assert m.on_key_released(1001) == [SetLight(Light.BREATHE_BLUE), SetMatrix(MATRIX_SUN)]


def test_offline_cancels_transient_and_ignores_events():
    m = online()
    m.on_bubble_popped(1)
    assert m.on_offline(1.5) == [SetLight(Light.DIM_GRAY), SetMatrix(MATRIX_DASH)]
    assert m.state is State.OFFLINE
    assert m.on_bubble_popped(2) == []
    assert m.on_share_updated(2) == []
    assert m.on_briefing_start(2) == []


def test_reconnect_restores_base_from_last_status():
    m = online(status(weather="tight"))
    m.on_offline(1)
    assert m.on_online(2) == [SetLight(Light.AMBER), SetMatrix(MATRIX_CLOUD)]


def test_polling_fallback_infers_pop_and_share_paid():
    m = online(status(open_bills=2, paid=1, total=4))
    effects = m.on_status(status(open_bills=2, paid=2, total=4), 1, infer_events=True)
    assert SetLight(Light.SPARKLE) in effects
    effects = m.on_status(status(open_bills=1, paid=4, total=4), 5, infer_events=True)
    assert SetLight(Light.BURST) in effects


def test_socket_mode_does_not_infer():
    m = online(status(open_bills=2))
    m.on_status(status(open_bills=1), 1)
    assert m.state is State.CLEAR


def test_count_is_capped_for_the_matrix():
    m = DeviceMachine()
    m.start()
    effects = m.on_status(status(open_bills=150, due_soon=1), 0)
    assert SetMatrix("matrix:count:99") in effects
