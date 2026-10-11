"""Future view: an educational 10-year projection of the user's steady monthly surplus.

The surplus is the median of the user's last three 30-day net cash flows (deposits minus posted
purchases and bills), floored at zero. `analytics.future.project` does the compounding. Return rates are
visible, adjustable placeholders for a generic broad index fund: no securities, no advice. Every
response carries the label "Hypothetical, not investment advice".
"""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

from analytics import future
from api import sky

LABEL = "Hypothetical, not investment advice"
DEFAULT_RATES = {"low": 0.03, "mid": 0.06, "high": 0.08}
MAX_RATE = 0.15
WINDOWS = 3
WINDOW_DAYS = 30
MAX_SURPLUS_CENTS = 10_000_000  # $100,000 a month: a sanity cap on what-if input


class FutureError(ValueError):
    """A bad rate or surplus from the query string (the route answers 422)."""


def monthly_surplus_cents(conn, user_id: int) -> int:
    today = sky.today()
    flows = []
    for i in range(WINDOWS):
        end = today - dt.timedelta(days=i * WINDOW_DAYS)
        start = end - dt.timedelta(days=WINDOW_DAYS)
        (net,) = conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN kind = 'deposit' THEN amount_cents
                                        WHEN kind IN ('purchase', 'bill') THEN -amount_cents ELSE 0 END), 0)
               FROM transactions
               WHERE user_id = %s AND status = 'posted'
                 AND occurred_at::date > %s AND occurred_at::date <= %s""",
            (user_id, start, end),
        ).fetchone()
        flows.append(int(net))
    return max(0, int(statistics.median(flows)))


def rates_from(low: float | None, mid: float | None, high: float | None) -> dict[str, float]:
    rates = {
        "low": DEFAULT_RATES["low"] if low is None else low,
        "mid": DEFAULT_RATES["mid"] if mid is None else mid,
        "high": DEFAULT_RATES["high"] if high is None else high,
    }
    if any(not 0 <= r <= MAX_RATE for r in rates.values()):
        raise FutureError(f"Rates must be between 0 and {MAX_RATE}")
    if not rates["low"] <= rates["mid"] <= rates["high"]:
        raise FutureError("Rates must run low to high")
    return rates


def projection(
    conn, user_id: int, rates: dict[str, float], surplus_cents: int | None = None
) -> dict[str, Any]:
    if surplus_cents is not None and not 0 <= surplus_cents <= MAX_SURPLUS_CENTS:
        raise FutureError("Monthly amount is out of range")
    surplus = monthly_surplus_cents(conn, user_id) if surplus_cents is None else surplus_cents
    out = future.project(surplus, years=10, rates=rates)
    return {
        "label": LABEL,
        "monthly_surplus_cents": surplus,
        "from_history": surplus_cents is None,
        "assumptions": {k: float(v) for k, v in out["assumptions"].items()},
        "years": 10,
        "series": [{k: int(v) for k, v in row.items()} for row in out["series"]],
        "note": (
            "An educational range for a generic broad index fund, not a prediction and not about any "
            "specific investment. Real returns vary and can be negative."
        ),
    }
