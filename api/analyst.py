"""Analyst view: segment-level hardship rates over SYNTHETIC households only.

Everything here comes from `analytics.cohorts.generate` (invented households; no real user, account or
transaction is read) run through the same `forecast` engine and rolled up with `segment_rates`, which
omits segments under 20 households. The view reports household counts and a share per segment, nothing
per household. It is support-outreach information, never a credit signal.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any

import pandas as pd

from analytics import cohorts
from analytics.forecast import forecast

N_HOUSEHOLDS = 200
SEED = 42
MIN_SEGMENT_SIZE = 20  # enforced again here, whatever the analytics module returns
SEGMENT_LABELS = {
    "student": "Students",
    "early_career": "Early career",
    "gig_worker": "Gig workers",
    "retiree": "Retirees",
}


def _start_balance(rows: list[dict[str, Any]]) -> int:
    balance = 0
    for r in rows:
        balance += r["amount_cents"] if r["kind"] == "deposit" else -r["amount_cents"]
    return balance


@lru_cache(maxsize=4)
def _segments(n: int, seed: int) -> tuple[tuple[str, int, float], ...]:
    data = cohorts.generate(n=n, seed=seed)
    txns = pd.DataFrame(data["transactions"])
    sched = pd.DataFrame(data["scheduled"])
    results: dict[str, dict] = {}
    start = dt.date.fromisoformat(max(t["date"] for t in data["transactions"]))
    for h in data["households"]:
        user = f"{h['household_id']}_u1"
        mine = txns[txns["user_id"] == user]
        results[h["household_id"]] = forecast(
            mine,
            sched[sched["user_id"] == user],
            _start_balance(mine.to_dict("records")),
            start.isoformat(),
            horizon_days=30,
            seed=SEED,
        )
    rows = cohorts.segment_rates(results, pd.DataFrame(data["households"]))
    return tuple((r["segment"], int(r["households"]), float(r["share_at_risk"])) for r in rows)


def segments() -> dict[str, Any]:
    rows = [
        {
            "segment": seg,
            "label": SEGMENT_LABELS.get(seg, seg.replace("_", " ").title()),
            "households": count,
            "share_at_risk": share,
        }
        for seg, count, share in _segments(N_HOUSEHOLDS, SEED)
        if count >= MIN_SEGMENT_SIZE
    ]
    return {
        "synthetic": True,
        "total_households": N_HOUSEHOLDS,
        "min_segment_size": MIN_SEGMENT_SIZE,
        "segments": rows,
        "note": (
            "Invented households only. Share of households with better than even odds of a shortfall "
            "in the next 30 days. Used to offer support early, never for credit decisions."
        ),
    }
