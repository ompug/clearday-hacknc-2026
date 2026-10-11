"""Bulb drivers, light patterns, matrix commands, keypad, config and chime."""

import time
import wave

import pytest

from clearday_home import config
from clearday_home.audio import write_chime
from clearday_home.bulb import BulbDriver, FakeBulb, make_bulb
from clearday_home.keypad import KeyTracker
from clearday_home.lights import MIN_HOLD, PATTERNS, LightPlayer
from clearday_home.matrix import LogMatrix, validate
from clearday_home.state import Light


def test_fake_bulb_satisfies_protocol_and_logs(caplog):
    caplog.set_level("INFO", logger="clearday_home")
    bulb = FakeBulb()
    assert isinstance(bulb, BulbDriver)
    bulb.set_color((1, 2, 3))
    bulb.set_brightness(150)
    bulb.celebrate()
    bulb.off()
    assert bulb.commands == [("color", (1, 2, 3)), ("brightness", 100), ("celebrate", None), ("off", None)]
    assert "bulb celebrate" in caplog.text


@pytest.mark.parametrize("kind", ["fake", "wiz", "mystery", "homeassistant"])
def test_make_bulb_falls_back_to_fake(kind):
    assert isinstance(make_bulb(kind, {}), FakeBulb)


def test_every_state_light_has_a_pattern_with_safe_command_rate():
    assert set(PATTERNS) == set(Light)
    for pattern in PATTERNS.values():
        assert all(step.hold >= MIN_HOLD for step in pattern.steps)


class BrokenBulb(FakeBulb):
    def set_color(self, rgb):
        raise OSError("bulb unreachable")


def test_light_player_survives_a_broken_bulb():
    bulb = BrokenBulb()
    player = LightPlayer(bulb)
    player.start()
    player.play(Light.PULSE)
    time.sleep(0.2)
    player.play(Light.BURST)
    time.sleep(0.2)
    player.stop()
    assert ("celebrate", None) in bulb.commands
    assert bulb.commands[-1] == ("off", None)


def test_matrix_commands_follow_bridge_protocol():
    for ok in (
        "matrix:sun",
        "matrix:cloud",
        "matrix:dash",
        "matrix:mic",
        "matrix:count:3",
        "matrix:count:99",
    ):
        assert validate(ok) == ok
    for bad in ("matrix:count:100", "matrix:count:-1", "matrix:rent 450", "sun", "matrix:count:"):
        with pytest.raises(ValueError):
            LogMatrix().send(bad)


def test_key_press_vs_hold():
    k = KeyTracker(hold_seconds=0.8)
    k.down(0)
    assert k.up(0.2) == "press"
    k.down(1)
    assert k.poll(1.5) is None
    assert k.poll(1.9) == "hold"
    assert k.up(3) == "release"
    assert k.up(4) is None


def test_config_requires_token_and_hides_it():
    with pytest.raises(SystemExit):
        config.from_env({})
    cfg = config.from_env({"CLEARDAY_DEVICE_TOKEN": "s3cret-token", "CLEARDAY_API_URL": "http://h:8000/"})
    assert cfg.api_url == "http://h:8000"
    assert cfg.bulb == "fake" and cfg.matrix == "log"
    assert "s3cret" not in repr(cfg)


def test_chime_is_a_valid_wav(tmp_path):
    path = write_chime(tmp_path / "chime.wav")
    with wave.open(str(path)) as w:
        assert w.getnchannels() == 1 and w.getnframes() > 5000
