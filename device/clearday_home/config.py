"""Device configuration from environment variables (optionally a local env file).

Only the household device token lives here: hashed and revocable on the
server, read-only scope. No Nessie, Gemini or ElevenLabs keys on the device.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    api_url: str
    device_token: str
    bulb: str = "fake"
    bulb_ip: str | None = None
    matrix: str = "log"
    audio: bool = True
    keypad_device: str | None = None
    briefing_key: str = "KEY_KPENTER"
    log_dir: Path = Path("logs")
    poll_interval: float = 2.0

    def __repr__(self) -> str:  # never print the token
        return f"Config(api_url={self.api_url!r}, bulb={self.bulb!r}, matrix={self.matrix!r})"


def load_env_file(path: Path) -> None:
    """Minimal KEY=VALUE reader; existing environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def from_env(env: dict[str, str] | None = None) -> Config:
    env = dict(os.environ if env is None else env)
    token = env.get("CLEARDAY_DEVICE_TOKEN", "").strip()
    if not token:
        raise SystemExit("CLEARDAY_DEVICE_TOKEN is not set (see device/README.md)")
    return Config(
        api_url=env.get("CLEARDAY_API_URL", "http://localhost:8000").rstrip("/"),
        device_token=token,
        bulb=env.get("CLEARDAY_BULB", "fake"),
        bulb_ip=env.get("CLEARDAY_BULB_IP") or None,
        matrix=env.get("CLEARDAY_MATRIX", "log"),
        audio=env.get("CLEARDAY_AUDIO", "1") not in ("0", "false", "off"),
        keypad_device=env.get("CLEARDAY_KEYPAD_DEVICE") or None,
        briefing_key=env.get("CLEARDAY_BRIEFING_KEY", "KEY_KPENTER"),
        log_dir=Path(env.get("CLEARDAY_LOG_DIR", "logs")),
        poll_interval=float(env.get("CLEARDAY_POLL_SECONDS", "2")),
    )
