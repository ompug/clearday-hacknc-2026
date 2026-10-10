"""STUB: needs-vs-wants tagging and income detection.

Contract (docs/02-technical-spec.md, Analytics contracts):

    tag_needs(transactions) -> transactions with added column "necessity" ("need"|"want")
    detect_income(transactions) -> {"cadence": "weekly"|"biweekly"|"monthly"|"irregular",
      "typical_amount_cents", "variability_cents", "next_expected_date"}

Uses a fixed category map and simple gap heuristics. The real module replaces it.
"""

from __future__ import annotations

import datetime as dt

from analytics._common import iso, median_int, parse_date, records

NEED_CATEGORIES = {
    "rent",
    "utilities",
    "internet",
    "groceries",
    "insurance",
    "health",
    "transfer",
    "income",
    "transport",
}


def _necessity(category) -> str:
    return "need" if str(category or "").lower() in NEED_CATEGORIES else "want"


def tag_needs(transactions):
    """Return a copy of ``transactions`` with a "necessity" column.

    Accepts a pandas DataFrame (returns a DataFrame) or a list of dicts (returns a list).
    """
    if hasattr(transactions, "assign"):
        return transactions.assign(necessity=[_necessity(c) for c in transactions["category"]])
    return [{**row, "necessity": _necessity(row.get("category"))} for row in records(transactions)]


def detect_income(transactions):
    deposits = sorted(
        (parse_date(r["date"]), int(r["amount_cents"]))
        for r in records(transactions)
        if r.get("kind") == "deposit"
    )
    if len(deposits) < 2:
        amount = deposits[0][1] if deposits else 0
        return {
            "cadence": "irregular",
            "typical_amount_cents": amount,
            "variability_cents": 0,
            "next_expected_date": None,
        }
    gaps = [(b[0] - a[0]).days for a, b in zip(deposits, deposits[1:], strict=False)]
    gap = median_int(gaps)
    if 6 <= gap <= 8:
        cadence = "weekly"
    elif 13 <= gap <= 15:
        cadence = "biweekly"
    elif 28 <= gap <= 31:
        cadence = "monthly"
    else:
        cadence = "irregular"
    amounts = [a for _, a in deposits]
    return {
        "cadence": cadence,
        "typical_amount_cents": median_int(amounts),
        "variability_cents": (max(amounts) - min(amounts)) // 2,
        "next_expected_date": iso(deposits[-1][0] + dt.timedelta(days=gap)),
    }
