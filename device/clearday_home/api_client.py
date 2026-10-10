"""HTTP calls to the Clearday API, authenticated with the device token.

The device only ever calls our own API, never Nessie, Gemini or ElevenLabs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import requests

from clearday_home.payloads import HouseholdStatus, HouseholdSummary, parse_status, parse_summary

TIMEOUT = 3.0
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class ApiClient:
    def __init__(self, base_url: str, token: str, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = session or requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"

    def household_status(self) -> HouseholdStatus:
        resp = self._session.get(f"{self.base_url}/api/household/status", timeout=TIMEOUT)
        resp.raise_for_status()
        return parse_status(resp.json())

    def device_summary(self) -> HouseholdSummary:
        resp = self._session.get(f"{self.base_url}/api/device/summary", timeout=TIMEOUT)
        resp.raise_for_status()
        return parse_summary(resp.json())

    def briefing_audio(self) -> Path:
        """POST /api/device/briefing; returns a temp file with the audio."""
        resp = self._session.post(f"{self.base_url}/api/device/briefing", timeout=15)
        resp.raise_for_status()
        return self._save(resp)

    def download_audio(self, api_path: str) -> Path:
        """Fetch announcement audio from a path on our own API (validated in payloads)."""
        resp = self._session.get(f"{self.base_url}{api_path}", timeout=10)
        resp.raise_for_status()
        return self._save(resp)

    @staticmethod
    def _save(resp: requests.Response) -> Path:
        if len(resp.content) > MAX_AUDIO_BYTES:
            raise ValueError("audio too large")
        suffix = ".wav" if "wav" in resp.headers.get("Content-Type", "") else ".mp3"
        with tempfile.NamedTemporaryFile(prefix="clearday-", suffix=suffix, delete=False) as f:
            f.write(resp.content)
        return Path(f.name)
