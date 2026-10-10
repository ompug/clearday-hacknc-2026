"""Small helpers shared by the analytics stubs (stdlib only).

Real modules may use or ignore these; calling code never imports them.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

TRANSACTION_COLUMNS = (
    "transaction_id",
    "user_id",
    "account_id",
    "date",
    "amount_cents",
    "kind",
    "category",
    "merchant",
    "status",
)


def records(data: Any) -> list[dict[str, Any]]:
    """Return rows as plain dicts from a pandas DataFrame or a list of dicts.

    numpy scalars are converted to Python ints/floats so outputs stay JSON-serializable.
    """
    if data is None:
        return []
    rows = data.to_dict("records") if hasattr(data, "to_dict") else list(data)
    out = []
    for row in rows:
        clean = {}
        for key, value in dict(row).items():
            if hasattr(value, "item") and not isinstance(value, str):
                value = value.item()
            clean[key] = value
        out.append(clean)
    return out


def parse_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def iso(value: dt.date) -> str:
    return value.isoformat()


def median_int(values: list[int]) -> int:
    """Median of integers, rounded down to an integer (no floats)."""
    if not values:
        return 0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) // 2
