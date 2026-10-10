"""STUB: recurring charges, anomalies, and duplicate subscriptions.

Contract (docs/02-technical-spec.md, Analytics contracts):

    detect_recurring(transactions) -> [{"merchant", "amount_cents", "cadence",
      "next_expected_date", "confidence"}]
    detect_anomalies(transactions) -> [{"transaction_id", "merchant", "amount_cents",
      "typical_low_cents", "typical_high_cents", "score"}]
    duplicate_subscriptions(household_transactions) -> [{"merchant", "user_ids",
      "monthly_cost_cents", "possible_savings_cents"}]

Simple deterministic heuristics; the real module replaces this file.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from analytics._common import iso, median_int, parse_date, records


def _purchases(transactions):
    return [r for r in records(transactions) if r.get("kind") in ("purchase", "bill")]


def detect_recurring(transactions):
    by_merchant = defaultdict(list)
    for r in _purchases(transactions):
        by_merchant[str(r["merchant"])].append((parse_date(r["date"]), int(r["amount_cents"])))
    out = []
    for merchant in sorted(by_merchant):
        rows = sorted(by_merchant[merchant])
        if len(rows) < 2:
            continue
        amounts = [a for _, a in rows]
        typical = median_int(amounts)
        if max(amounts) - min(amounts) > typical // 10:
            continue  # amounts not within ~10%
        gap = median_int([(b[0] - a[0]).days for a, b in zip(rows, rows[1:], strict=False)])
        cadence = {7: "weekly", 14: "biweekly"}.get(gap, "monthly" if 28 <= gap <= 31 else None)
        if cadence is None:
            continue
        out.append(
            {
                "merchant": merchant,
                "amount_cents": typical,
                "cadence": cadence,
                "next_expected_date": iso(rows[-1][0] + dt.timedelta(days=gap)),
                "confidence": 0.9 if len(rows) >= 3 else 0.7,
            }
        )
    return out


def detect_anomalies(transactions):
    by_merchant = defaultdict(list)
    for r in _purchases(transactions):
        by_merchant[str(r["merchant"])].append(r)
    out = []
    for merchant in sorted(by_merchant):
        rows = by_merchant[merchant]
        if len(rows) < 4:
            continue
        amounts = sorted(int(r["amount_cents"]) for r in rows)
        low, high = amounts[len(amounts) // 10], amounts[(len(amounts) * 9) // 10 - 1]
        typical = median_int(amounts)
        for r in rows:
            cents = int(r["amount_cents"])
            if cents > 2 * high and cents > typical * 3:
                out.append(
                    {
                        "transaction_id": str(r["transaction_id"]),
                        "merchant": merchant,
                        "amount_cents": cents,
                        "typical_low_cents": low,
                        "typical_high_cents": high,
                        "score": round(min(cents / max(high, 1) / 4, 1.0), 2),
                    }
                )
    return sorted(out, key=lambda a: (-a["score"], a["transaction_id"]))


def duplicate_subscriptions(household_transactions):
    per_merchant = defaultdict(dict)
    for r in records(household_transactions):
        if r.get("category") != "subscriptions":
            continue
        per_merchant[str(r["merchant"])][str(r["user_id"])] = int(r["amount_cents"])
    out = []
    for merchant in sorted(per_merchant):
        users = per_merchant[merchant]
        if len(users) < 2:
            continue
        monthly = sum(users.values())
        out.append(
            {
                "merchant": merchant,
                "user_ids": sorted(users),
                "monthly_cost_cents": monthly,
                "possible_savings_cents": monthly - max(users.values()),
            }
        )
    return out
