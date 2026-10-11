"""Spoken household announcement: template text from household-level data, ElevenLabs audio, cached.

The text carries no amounts, no names and no bill labels (labels are user-typed text). Audio is cached on
disk by a hash of voice, model and text, so a repeated demo never bills twice. Any ElevenLabs failure
(timeout, HTTP error, missing key) returns no audio, and the web shows the transcript alone.
Keys come from api/.env through `get_settings()` and are never logged.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from api.config import get_settings

log = logging.getLogger("clearday.voice")

CACHE_DIR = Path(__file__).resolve().parents[1] / "logs" / "voice_cache"  # logs/ is gitignored
TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
TIMEOUT_S = 8.0
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_lock = threading.Lock()


@dataclass(frozen=True)
class Announcement:
    text: str
    audio_hash: str | None  # None: text only
    source: str  # "elevenlabs" (fresh), "cache" or "text"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def announcement_text(status: dict[str, Any]) -> str:
    """The template fallback for 'a shared bill just cleared', from `sky.household_status` counts only."""
    sky_line = f"Skies look {'tight' if status.get('weather') == 'tight' else 'clear'} this week."
    open_bills = int(status.get("open_bills", 0))
    if open_bills == 0:
        return f"A shared bill just cleared. Every shared bill is covered. {sky_line}"
    paid, total = int(status.get("shares_paid", 0)), int(status.get("shares_total", 0))
    return (
        f"A shared bill just cleared. {_plural(open_bills, 'shared bill')} still open, "
        f"{paid} of {_plural(total, 'share')} paid. {sky_line}"
    )


def _key(text: str) -> str:
    s = get_settings()
    return hashlib.sha256(f"{s.elevenlabs_voice_id}\n{s.elevenlabs_model_id}\n{text}".encode()).hexdigest()


def cached_audio_path(audio_hash: str) -> Path | None:
    if not HASH_RE.match(audio_hash):
        return None
    path = CACHE_DIR / f"{audio_hash}.mp3"
    return path if path.is_file() else None


def synthesize(text: str, transport: httpx.BaseTransport | None = None) -> Announcement:
    """Audio for `text`: from the cache, else one ElevenLabs call. Never raises."""
    s = get_settings()
    key = _key(text)
    with _lock:  # two roommates' browsers ask at once: one call, one bill
        if cached_audio_path(key):
            return Announcement(text, key, "cache")
        api_key = s.elevenlabs_api_key.get_secret_value()
        if not (api_key and s.elevenlabs_voice_id):
            return Announcement(text, None, "text")
        try:
            with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
                res = client.post(
                    TTS_URL.format(voice_id=s.elevenlabs_voice_id),
                    headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
                    json={"text": text, "model_id": s.elevenlabs_model_id or "eleven_multilingual_v2"},
                )
            res.raise_for_status()
            if not res.content:
                raise ValueError("empty audio")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = CACHE_DIR / f"{key}.tmp"
            tmp.write_bytes(res.content)
            tmp.replace(CACHE_DIR / f"{key}.mp3")
        except (httpx.HTTPError, ValueError, OSError) as exc:
            log.warning("ElevenLabs unavailable, text only: %s", type(exc).__name__)  # never the key or URL
            return Announcement(text, None, "text")
    return Announcement(text, key, "elevenlabs")
