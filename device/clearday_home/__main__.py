"""Run Clearday Home: `uv run python -m clearday_home` (see device/README.md)."""

from __future__ import annotations

import logging
import signal
import threading
from pathlib import Path

from clearday_home import config as config_mod
from clearday_home import logs
from clearday_home.api_client import ApiClient
from clearday_home.audio import Audio
from clearday_home.bridge import Bridge
from clearday_home.bulb import make_bulb
from clearday_home.controller import Controller
from clearday_home.keypad import start_keypad
from clearday_home.lights import LightPlayer
from clearday_home.matrix import make_matrix
from clearday_home.state import DeviceMachine


def main() -> None:
    config_mod.load_env_file(Path(__file__).resolve().parent.parent / ".env")
    cfg = config_mod.from_env()
    logs.setup(cfg.log_dir)
    log = logging.getLogger("clearday_home")
    log.info("starting with %r", cfg)

    controller = Controller(
        machine=DeviceMachine(),
        lights=LightPlayer(make_bulb(cfg.bulb, cfg.bulb_ip)),
        matrix=make_matrix(cfg.matrix),
        audio=Audio(enabled=cfg.audio),
        api=ApiClient(cfg.api_url, cfg.device_token),
    )
    bridge = Bridge(controller, cfg.api_url, cfg.device_token, poll_interval=cfg.poll_interval)
    controller.start()
    bridge.start()
    start_keypad(controller, cfg.keypad_device, cfg.briefing_key)

    done = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: done.set())
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    done.wait()
    log.info("stopping")
    bridge.stop()
    controller.stop()


if __name__ == "__main__":
    main()
