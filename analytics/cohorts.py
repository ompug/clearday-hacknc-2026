"""STUB: synthetic cohort households for the analyst view.

Contract (docs/02-technical-spec.md, Analytics contracts):

    generate(n=200, seed=42) -> {"households": [...], "transactions": [...], "scheduled": [...]}
    segment_rates(forecasts_by_household, households) -> [{"segment", "households", "share_at_risk"}]
      # segments with fewer than 20 households are omitted

Every household is synthetic. ``forecasts_by_household`` maps household_id to a
forecast() result; a household is "at risk" when any bill has p_short > 0.5.
"""

from __future__ import annotations

import datetime as dt
import random

from analytics._common import records

SEGMENTS = [
    # segment, weight, income cents per biweekly paycheck, rent cents
    ("student", 35, 62_000, 70_000),
    ("early_career", 35, 135_000, 120_000),
    ("gig_worker", 20, 88_000, 90_000),
    ("retiree", 10, 110_000, 80_000),
]
ANCHOR = dt.date(2026, 10, 10)
MIN_SEGMENT_SIZE = 20


def generate(n=200, seed=42):
    rng = random.Random(seed)
    households, transactions, scheduled = [], [], []
    total_weight = sum(w for _, w, _, _ in SEGMENTS)
    plan = []
    for segment, weight, pay, rent in SEGMENTS:
        plan += [(segment, pay, rent)] * (n * weight // total_weight)
    while len(plan) < n:
        plan.append(SEGMENTS[0][0:1] + SEGMENTS[0][2:4])
    txn_no = 0
    for i, (segment, pay, rent) in enumerate(plan[:n], start=1):
        hid = f"h{i:04d}"
        size = rng.randint(1, 4)
        households.append({"household_id": hid, "segment": segment, "size": size, "synthetic": True})
        user_id, account_id = f"{hid}_u1", f"{hid}_u1_checking"
        income = pay + rng.randrange(-pay // 5, pay // 5, 100)
        for d in range(30):
            day = ANCHOR - dt.timedelta(days=29 - d)
            rows = []
            if d % 14 == 4:
                rows.append((income, "deposit", "income", "Payroll Direct Deposit"))
            if day.day == 1:
                rows.append((rent, "bill", "rent", "Landlord"))
            if rng.random() < 0.5:
                rows.append(
                    (
                        rng.randrange(800, 6000),
                        "purchase",
                        rng.choice(["groceries", "dining", "shopping"]),
                        "Store",
                    )
                )
            for cents, kind, cat, merchant in rows:
                txn_no += 1
                transactions.append(
                    {
                        "transaction_id": f"c{txn_no:07d}",
                        "user_id": user_id,
                        "account_id": account_id,
                        "date": day.isoformat(),
                        "amount_cents": cents,
                        "kind": kind,
                        "category": cat,
                        "merchant": merchant,
                        "status": "posted",
                    }
                )
        next_rent = dt.date(2026, 11, 1).isoformat()
        scheduled.append(
            {
                "user_id": user_id,
                "account_id": account_id,
                "date": next_rent,
                "amount_cents": rent,
                "kind": "bill",
                "label": "Rent",
                "cadence": "monthly",
            }
        )
        scheduled.append(
            {
                "user_id": user_id,
                "account_id": account_id,
                "date": (ANCHOR + dt.timedelta(days=8)).isoformat(),
                "amount_cents": income,
                "kind": "income",
                "label": "Paycheck",
                "cadence": "biweekly",
            }
        )
    return {"households": households, "transactions": transactions, "scheduled": scheduled}


def segment_rates(forecasts_by_household, households):
    counts, at_risk = {}, {}
    for h in records(households):
        seg, hid = str(h["segment"]), h["household_id"]
        counts[seg] = counts.get(seg, 0) + 1
        result = forecasts_by_household.get(hid) or {}
        risky = any(b.get("p_short", 0) > 0.5 for b in result.get("bills", []))
        at_risk[seg] = at_risk.get(seg, 0) + int(risky)
    return [
        {"segment": seg, "households": counts[seg], "share_at_risk": round(at_risk[seg] / counts[seg], 3)}
        for seg in sorted(counts)
        if counts[seg] >= MIN_SEGMENT_SIZE
    ]
