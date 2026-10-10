"""STUB: Monte Carlo "money weather" forecast.

Contract (docs/02-technical-spec.md, Analytics contracts):

    forecast(transactions, scheduled, start_balance_cents, start_date, horizon_days=30,
             n_paths=1000, threshold_cents=5000, seed=0) -> {
      "days": [{"date", "p10_cents", "p50_cents", "p90_cents"}],
      "bills": [{"label", "date", "amount_cents", "p_short"}],
      "safe_to_spend_cents", "next_payday",
      "drivers": [{"category", "share_of_variance"}],
      "wants_trimmed": {"safe_to_spend_cents", "bills": [{"label", "date", "p_short"}]}
    }

This stub does NOT simulate. It places scheduled events on a straight-line
burn derived from history and widens the band with time, deterministically.
The real module replaces it file for file.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from typing import Any

from analytics._common import iso, parse_date, records

WANT_CATEGORIES = {"dining", "rideshare", "shopping", "subscriptions", "entertainment"}
OUTFLOW_KINDS = {"purchase"}


def _daily_burn(txns: list[dict[str, Any]]) -> tuple[int, dict[str, int]]:
    by_cat: dict[str, int] = defaultdict(int)
    dates = set()
    for t in txns:
        dates.add(str(t["date"])[:10])
        if t.get("kind") in OUTFLOW_KINDS:
            by_cat[str(t.get("category") or "other")] += int(t["amount_cents"])
    span = max(len(dates), 1)
    total = sum(by_cat.values())
    return (total // span if total else 2_500), dict(by_cat)


def _p_short(p10: int, p50: int, threshold: int) -> float:
    if p50 <= threshold:
        return 0.95
    if p10 >= threshold:
        return 0.03
    # Linear between p10 and p50 (p10 is the 10th percentile).
    frac = (threshold - p10) / max(p50 - p10, 1)
    return round(0.1 + 0.4 * frac, 2)


def forecast(
    transactions,
    scheduled,
    start_balance_cents,
    start_date,
    horizon_days=30,
    n_paths=1000,
    threshold_cents=5000,
    seed=0,
):
    txns = records(transactions)
    sched = records(scheduled)
    start = parse_date(start_date)
    end = start + dt.timedelta(days=horizon_days - 1)
    burn, by_cat = _daily_burn(txns)
    want_burn = sum(v for k, v in by_cat.items() if k in WANT_CATEGORIES)
    total_spend = sum(by_cat.values()) or 1
    want_share_burn = burn * want_burn // total_spend

    events: dict[dt.date, int] = defaultdict(int)
    bill_events = []
    next_payday = None
    for s in sorted(sched, key=lambda r: (str(r["date"]), str(r.get("label")))):
        day = parse_date(s["date"])
        if not start <= day <= end:
            continue
        cents = int(s["amount_cents"])
        if s["kind"] == "income":
            events[day] += cents
            if next_payday is None:
                next_payday = iso(day)
        else:
            events[day] -= cents
            bill_events.append((day, str(s["label"]), cents))

    def run(daily_burn: int) -> tuple[list[dict[str, Any]], dict[dt.date, tuple[int, int]]]:
        days, bands = [], {}
        balance = int(start_balance_cents)
        for i in range(horizon_days):
            day = start + dt.timedelta(days=i)
            balance += events.get(day, 0) - daily_burn
            spread = int(daily_burn * 0.9 * math.sqrt(i + 1)) + (seed % 7) * 10
            p10, p50, p90 = balance - spread, balance, balance + spread
            bands[day] = (p10, p50)
            days.append({"date": iso(day), "p10_cents": p10, "p50_cents": p50, "p90_cents": p90})
        return days, bands

    def safe(days: list[dict[str, Any]]) -> int:
        horizon = next_payday or iso(end)
        lows = [d["p10_cents"] for d in days if d["date"] <= horizon]
        return max(0, min(lows, default=0) - int(threshold_cents))

    days, bands = run(burn)
    trimmed_days, trimmed_bands = run(burn - want_share_burn // 4)

    def bill_rows(b: dict[dt.date, tuple[int, int]], with_amount: bool) -> list[dict[str, Any]]:
        rows = []
        for day, label, cents in bill_events:
            p10, p50 = b[day]
            row: dict[str, Any] = {"label": label, "date": iso(day)}
            if with_amount:
                row["amount_cents"] = cents
            row["p_short"] = _p_short(p10, p50, int(threshold_cents))
            rows.append(row)
        return rows

    ranked = sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    ranked_total = sum(v for _, v in ranked) or 1
    drivers = [{"category": c, "share_of_variance": round(v / ranked_total, 2)} for c, v in ranked]

    return {
        "days": days,
        "bills": bill_rows(bands, with_amount=True),
        "safe_to_spend_cents": safe(days),
        "next_payday": next_payday,
        "drivers": drivers,
        "wants_trimmed": {
            "safe_to_spend_cents": safe(trimmed_days),
            "bills": bill_rows(trimmed_bands, with_amount=False),
        },
    }
