"""Allowlist parsers for everything the device reads from the backend.

The device consumes only `/api/household/status` and `/api/device/summary`
(docs/03-security-and-privacy.md, "Clearday Home device rules"). Each parser
copies the few household-level fields it knows and drops everything else, so a
stray amount or person's name in a payload never reaches device state, logs,
the bulb or the matrix. Socket.IO event payloads are treated as triggers only;
see `bridge.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

Weather = Literal["clear", "tight"]

MAX_COUNT = 99
MAX_LABEL_CHARS = 40


class PayloadError(ValueError):
    """The payload is missing a required field or has the wrong type."""


@dataclass(frozen=True)
class HouseholdStatus:
    """GET /api/household/status, reduced to what the globe needs. Counts only."""

    weather: Weather
    open_bills: int
    due_soon_bills: int
    shares_paid: int
    shares_total: int


@dataclass(frozen=True)
class BillSummary:
    """One shared bill in the narrator summary: a label and share progress."""

    label: str
    shares_paid: int
    shares_total: int
    due_in_days: int


@dataclass(frozen=True)
class HouseholdSummary:
    """GET /api/device/summary, for the narrator. Household-level only."""

    weather: Weather
    open_bills: int
    bills: tuple[BillSummary, ...]


@dataclass(frozen=True)
class Announcement:
    """device.announce: where to fetch the audio (our API only) and a light pattern name."""

    audio_path: str
    light_pattern: str | None


def _count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PayloadError(f"{key} must be a non-negative integer")
    return min(value, MAX_COUNT)


def _weather(data: dict[str, Any]) -> Weather:
    value = data.get("weather")
    if value not in ("clear", "tight"):
        raise PayloadError("weather must be 'clear' or 'tight'")
    return value


def _require_dict(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PayloadError("payload must be a JSON object")
    return data


def parse_status(data: Any) -> HouseholdStatus:
    data = _require_dict(data)
    status = HouseholdStatus(
        weather=_weather(data),
        open_bills=_count(data, "open_bills"),
        due_soon_bills=_count(data, "due_soon_bills"),
        shares_paid=_count(data, "shares_paid"),
        shares_total=_count(data, "shares_total"),
    )
    if status.shares_paid > status.shares_total:
        raise PayloadError("shares_paid exceeds shares_total")
    return status


def parse_summary(data: Any) -> HouseholdSummary:
    data = _require_dict(data)
    raw_bills = data.get("bills", [])
    if not isinstance(raw_bills, list):
        raise PayloadError("bills must be a list")
    bills = []
    for raw in raw_bills[:MAX_COUNT]:
        raw = _require_dict(raw)
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip():
            raise PayloadError("bill label must be a non-empty string")
        bills.append(
            BillSummary(
                label=label.strip()[:MAX_LABEL_CHARS],
                shares_paid=_count(raw, "shares_paid"),
                shares_total=_count(raw, "shares_total"),
                due_in_days=_count(raw, "due_in_days"),
            )
        )
    return HouseholdSummary(weather=_weather(data), open_bills=_count(data, "open_bills"), bills=tuple(bills))


def parse_announcement(data: Any) -> Announcement:
    """Accept only a relative path on our own API, never an external URL."""
    data = _require_dict(data)
    url = data.get("audio_url")
    if not isinstance(url, str):
        raise PayloadError("audio_url must be a string")
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path.startswith("/api/") or ".." in parts.path:
        raise PayloadError("audio_url must be a path on the Clearday API")
    pattern = data.get("light_pattern")
    return Announcement(
        audio_path=parts.path + (f"?{parts.query}" if parts.query else ""),
        light_pattern=pattern if isinstance(pattern, str) else None,
    )
