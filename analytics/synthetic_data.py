"""Synthetic roommate household (Maya, Jake, Priya).

Contract (docs/02-technical-spec.md, Analytics contracts):

    generate(seed=42, days=60) -> {"users", "transactions", "scheduled", "receipts"}

Deterministic for a given seed. Money is integer cents and always positive;
direction comes from ``kind`` (deposit = money in; purchase, bill, transfer = money out).
History ends on ANCHOR_DATE; ``scheduled`` covers the 30 days after it.

Planted cases: a duplicate household subscription (Maya and Jake both pay
Spotify), one anomalous grocery charge (Jake), and a tight week before rent (Priya).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import random
from typing import Any

ANCHOR_DATE = dt.date(2026, 10, 10)
SCHEDULE_DAYS = 30

USERS = [
    # user_id, name, paycheck cents, first payday offset (days after start), opening checking cents
    ("u_maya", "Maya", 182_000, 3, 310_000),
    ("u_jake", "Jake", 141_000, 10, 145_000),
    ("u_priya", "Priya", 118_000, 6, 62_000),
]

ACCOUNT_TYPES = [
    ("checking", "Everyday Checking", 1),
    ("savings", "Rainy Day Savings", 3),
    ("credit_card", "Rewards Card", 0),
]

SUBSCRIPTIONS = {
    "u_maya": [("Spotify", 1199, 4), ("Netflix", 1549, 12), ("iCloud", 299, 20)],
    "u_jake": [("Spotify", 1199, 7), ("Xbox Game Pass", 1699, 15), ("Hulu", 999, 25)],
    "u_priya": [("Duolingo", 699, 2), ("Disney Plus", 1399, 18), ("NYT Cooking", 500, 22)],
}

RENT_CENTS = 240_000
INTERNET_CENTS = 7_000


def _account_id(user_id: str, kind: str) -> str:
    return f"{user_id}_{kind}"


def _dates(days: int) -> list[dt.date]:
    start = ANCHOR_DATE - dt.timedelta(days=days - 1)
    return [start + dt.timedelta(days=i) for i in range(days)]


def generate(seed: int = 42, days: int = 60) -> dict[str, Any]:
    rng = random.Random(seed)
    users: list[dict[str, Any]] = []
    for user_id, name, _pay, _offset, opening in USERS:
        accounts = []
        for kind, nickname, mult in ACCOUNT_TYPES:
            balance = opening * mult if kind != "credit_card" else 0
            if kind == "savings":
                balance = opening // 2 + rng.randrange(0, 50_000, 100)
            accounts.append(
                {
                    "account_id": _account_id(user_id, kind),
                    "type": kind,
                    "nickname": nickname,
                    "opening_balance_cents": balance,
                }
            )
        users.append({"user_id": user_id, "name": name, "accounts": accounts})

    rows: list[dict[str, Any]] = []

    def add(user_id: str, acct: str, day: dt.date, cents: int, kind: str, cat: str, merch: str):
        rows.append(
            {
                "user_id": user_id,
                "account_id": _account_id(user_id, acct),
                "date": day.isoformat(),
                "amount_cents": int(cents),
                "kind": kind,
                "category": cat,
                "merchant": merch,
            }
        )

    calendar = _dates(days)
    start = calendar[0]
    for user_id, _name, pay, offset, _opening in USERS:
        for day in calendar:
            idx = (day - start).days
            if idx >= offset and (idx - offset) % 14 == 0:
                add(
                    user_id,
                    "checking",
                    day,
                    pay + rng.randrange(-1500, 1500, 100),
                    "deposit",
                    "income",
                    "Payroll Direct Deposit",
                )
            for merch, cents, dom in SUBSCRIPTIONS[user_id]:
                if day.day == dom:
                    add(user_id, "credit_card", day, cents, "purchase", "subscriptions", merch)
            if day.weekday() in (1, 5) or rng.random() < 0.08:
                store = "Harris Teeter" if rng.random() < 0.6 else "Food Lion"
                add(user_id, "checking", day, rng.randrange(2800, 7800), "purchase", "groceries", store)
            if rng.random() < 0.22:
                place = rng.choice(["Cosmic Cantina", "Bojangles", "Med Deli", "Sup Dogs"])
                add(user_id, "credit_card", day, rng.randrange(900, 3600), "purchase", "dining", place)
            if rng.random() < 0.12:
                add(user_id, "credit_card", day, rng.randrange(800, 2600), "purchase", "rideshare", "Uber")
            if rng.random() < 0.04:
                add(
                    user_id,
                    "credit_card",
                    day,
                    rng.randrange(1500, 9000),
                    "purchase",
                    "shopping",
                    rng.choice(["Target", "Amazon"]),
                )
            if user_id == "u_priya" and 24 <= day.day <= 30 and rng.random() < 0.5:
                # Planted tight week: extra spending right before rent.
                add(user_id, "checking", day, rng.randrange(4000, 9000), "purchase", "shopping", "Target")

    for day in calendar:
        if day.day == 1:
            add("u_maya", "checking", day, RENT_CENTS, "bill", "rent", "Franklin St Apartments")
        if day.day == 15:
            electric = 9_000 + rng.randrange(0, 6_000, 25)
            add("u_maya", "checking", day, electric, "bill", "utilities", "Duke Energy")
        if day.day == 20:
            add("u_maya", "checking", day, INTERNET_CENTS, "bill", "internet", "Spectrum")
        if day.day == 3:
            # Roommates pay Maya back their rent share.
            for user_id in ("u_jake", "u_priya"):
                add(user_id, "checking", day, RENT_CENTS // 3, "transfer", "transfer", "Maya")

    # Planted anomaly: one oversized grocery charge for Jake, 10 days before the anchor.
    add(
        "u_jake",
        "checking",
        ANCHOR_DATE - dt.timedelta(days=10),
        21_840,
        "purchase",
        "groceries",
        "Harris Teeter",
    )

    rows.sort(key=lambda r: (r["date"], r["user_id"], r["kind"], r["merchant"], r["amount_cents"]))
    pending_from = (ANCHOR_DATE - dt.timedelta(days=1)).isoformat()
    transactions = []
    for n, row in enumerate(rows, start=1):
        status = "pending" if row["date"] >= pending_from and row["kind"] == "purchase" else "posted"
        transactions.append({"transaction_id": f"t{n:05d}", **row, "status": status})

    return {
        "users": users,
        "transactions": transactions,
        "scheduled": _scheduled(rng),
        "receipts": _receipts(),
    }


def _scheduled(rng: random.Random) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    first = ANCHOR_DATE + dt.timedelta(days=1)
    window = [first + dt.timedelta(days=i) for i in range(SCHEDULE_DAYS)]
    # Next paydays continue each user's biweekly rhythm.
    next_pay = {"u_maya": 2, "u_jake": 9, "u_priya": 5}
    for user_id, _name, pay, _offset, _opening in USERS:
        for day in window:
            idx = (day - first).days
            if idx >= next_pay[user_id] and (idx - next_pay[user_id]) % 14 == 0:
                out.append(
                    {
                        "user_id": user_id,
                        "account_id": _account_id(user_id, "checking"),
                        "date": day.isoformat(),
                        "amount_cents": pay,
                        "kind": "income",
                        "label": "Paycheck",
                        "cadence": "biweekly",
                    }
                )
            for merch, cents, dom in SUBSCRIPTIONS[user_id]:
                if day.day == dom:
                    out.append(
                        {
                            "user_id": user_id,
                            "account_id": _account_id(user_id, "credit_card"),
                            "date": day.isoformat(),
                            "amount_cents": cents,
                            "kind": "bill",
                            "label": merch,
                            "cadence": "monthly",
                        }
                    )
            if day.day == 1:
                share = RENT_CENTS if user_id == "u_maya" else RENT_CENTS // 3
                label = "Rent" if user_id == "u_maya" else "Rent share"
                out.append(
                    {
                        "user_id": user_id,
                        "account_id": _account_id(user_id, "checking"),
                        "date": day.isoformat(),
                        "amount_cents": share,
                        "kind": "bill",
                        "label": label,
                        "cadence": "monthly",
                    }
                )
    for day in window:
        if day.day == 15:
            out.append(
                {
                    "user_id": "u_maya",
                    "account_id": _account_id("u_maya", "checking"),
                    "date": day.isoformat(),
                    "amount_cents": 11_500 + rng.randrange(0, 2000, 25),
                    "kind": "bill",
                    "label": "Electric",
                    "cadence": "monthly",
                }
            )
        if day.day == 20:
            out.append(
                {
                    "user_id": "u_maya",
                    "account_id": _account_id("u_maya", "checking"),
                    "date": day.isoformat(),
                    "amount_cents": INTERNET_CENTS,
                    "kind": "bill",
                    "label": "Internet",
                    "cadence": "monthly",
                }
            )
    out.sort(key=lambda r: (r["date"], r["user_id"], r["label"]))
    return out


def _receipts() -> list[dict[str, Any]]:
    def item(label: str, qty: int, unit: str, price: int) -> dict[str, Any]:
        return {"raw_label": label, "quantity": qty, "unit": unit, "unit_price_cents": price}

    return [
        {
            "receipt_id": "r001",
            "user_id": "u_maya",
            "merchant": "Harris Teeter",
            "date": "2026-09-15",
            "items": [
                item("ORG WHL MLK 1GAL", 1, "gal", 649),
                item("BNLS CHKN BRST", 2, "lb", 499),
                item("BANANAS", 3, "lb", 69),
            ],
        },
        {
            "receipt_id": "r002",
            "user_id": "u_jake",
            "merchant": "Food Lion",
            "date": "2026-09-22",
            "items": [
                item("Organic Whole Milk 1 gal", 1, "gal", 579),
                item("Boneless Chicken Breast", 3, "lb", 429),
                item("Paper Towels 6pk", 1, "each", 899),
            ],
        },
        {
            "receipt_id": "r003",
            "user_id": "u_priya",
            "merchant": "Harris Teeter",
            "date": "2026-10-02",
            "items": [
                item("ORG WHL MLK 1GAL", 1, "gal", 669),
                item("BANANAS", 2, "lb", 72),
                item("PPR TWL 6PK", 1, "each", 1049),
            ],
        },
        {
            "receipt_id": "r004",
            "user_id": "u_maya",
            "merchant": "Food Lion",
            "date": "2026-10-08",
            "items": [item("Bananas", 3, "lb", 59), item("Boneless Chicken Breast", 2, "lb", 449)],
        },
    ]


def save_seed(path: str | Path = "seed_data.json", seed: int = 42, days: int = 60) -> str:
    """Generate the synthetic dataset and save it to JSON."""
    data = generate(seed=seed, days=days)
    target = Path(path)
    with target.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(target)


if __name__ == "__main__":
    out_path = save_seed()
    print(f"Saved seed data to {out_path}")

