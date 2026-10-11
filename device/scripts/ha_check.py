"""Cycle the bulb through every state's colour (about 10 seconds).

    cd device && BULB_DRIVER=homeassistant HA_URL=... HA_TOKEN=... HA_LIGHT_ENTITY=light.x \
        uv run python scripts/ha_check.py

Reads device/.env too (real environment variables win).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clearday_home.bulb import FakeBulb, make_bulb  # noqa: E402
from clearday_home.config import load_env_file  # noqa: E402
from clearday_home.lights import AMBER, CALM_BLUE, GRAY, SKY_BLUE, WHITE  # noqa: E402

STEPS = [
    ("Clear skies (calm blue)", CALM_BLUE, 80),
    ("Tight week (amber)", AMBER, 55),
    ("Bill due soon (sky blue)", SKY_BLUE, 85),
    ("Listening (white)", WHITE, 80),
    ("Offline (dim gray)", GRAY, 12),
]


def main() -> int:
    load_env_file(ROOT / ".env")
    import os

    bulb = make_bulb(os.environ.get("BULB_DRIVER", "fake"))
    if isinstance(bulb, FakeBulb):
        print("Using the fake bulb: set BULB_DRIVER=homeassistant, HA_URL, HA_TOKEN, HA_LIGHT_ENTITY.")
    for label, rgb, brightness in STEPS:
        print(label)
        bulb.set_color(rgb)
        bulb.set_brightness(brightness)
        time.sleep(1.5)
    print("Celebration")
    bulb.celebrate()
    time.sleep(2.5)
    bulb.set_color(CALM_BLUE)
    bulb.set_brightness(60)
    time.sleep(1)
    bulb.off()
    print("Done. Watch the bulb for each colour; errors (if any) are logged above.")
    return 0


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
