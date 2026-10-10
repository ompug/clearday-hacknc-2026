"""Logging to stdout and <log_dir>/device.log. Log names of things, never payload values."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger("clearday_home")
    root.setLevel(level)
    root.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / "device.log")):
        handler.setFormatter(fmt)
        root.addHandler(handler)
