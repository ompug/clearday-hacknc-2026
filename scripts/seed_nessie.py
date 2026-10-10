"""Seed the Apartment 4B demo household into Nessie, then mirror it into our database.

Usage (from the repo root):
    uv run python -m scripts.seed_nessie --dry-run   # reads Nessie, prints the plan, writes nothing
    uv run python -m scripts.seed_nessie             # creates what's missing, then writes our DB

Idempotent. Nessie can't delete customers or merchants, so they're looked up by exact name and
reused. Accounts match on (type, nickname); activity matches on a natural key per account. A re-run
creates nothing in Nessie and changes nothing in our DB. Leftover ``zz-probe`` records are ignored.

Nessie truncates purchase, deposit and transfer amounts to whole dollars, so those are whole dollars
here; bills keep cents. Shared totals are multiples of $3 so every share is whole dollars.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import random
import sys
from collections import Counter
from dataclasses import dataclass, field

from analytics.splits import split
from api.nessie.client import NessieClient

log = logging.getLogger("clearday.seed")

ANCHOR = dt.date(2026, 10, 10)  # last day of history; matches analytics.synthetic_data
DAYS = 60
HOUSEHOLD = "Apartment 4B"
PROBE_PREFIX = "zz-probe"
NEW = "<new>"  # placeholder id in a dry run

HOME = {
    "street_number": "412",
    "street_name": "W Franklin St Apt 4B",
    "city": "Chapel Hill",
    "state": "NC",
    "zip": "27516",
}


@dataclass(frozen=True)
class Person:
    key: str
    first: str
    last: str
    employer: str
    pay_dollars: int
    payday_offset: int  # days after the first day of history
    monthly_savings_dollars: int
    openings: dict  # account type -> opening balance in cents (whole dollars)


PEOPLE = [
    Person(
        "maya",
        "Maya",
        "Okafor",
        "UNC Health",
        1240,
        3,
        300,
        {"checking": 210_000, "savings": 185_000, "credit_card": 0},
    ),
    Person(
        "jake",
        "Jake",
        "Morales",
        "UNC Graduate School",
        1080,
        10,
        200,
        {"checking": 145_000, "savings": 260_000, "credit_card": 0},
    ),
    Person(
        "priya",
        "Priya",
        "Raman",
        "Bright Pixel Studio",
        880,
        6,
        0,
        {"checking": 72_000, "savings": 40_000, "credit_card": 0},
    ),
]
STATEMENT_DAY = 5
PAYER = "maya"  # pays the landlord and utilities; Jake and Priya owe shares
ACCOUNTS = [
    ("checking", "Everyday Checking"),
    ("savings", "Rainy Day Savings"),
    ("credit_card", "Rewards Card"),
]

MERCHANTS = {
    "Harris Teeter": "groceries",
    "Food Lion": "groceries",
    "Cosmic Cantina": "dining",
    "Bojangles": "dining",
    "Med Deli": "dining",
    "Sup Dogs": "dining",
    "Uber": "rideshare",
    "Target": "shopping",
    "Amazon": "shopping",
    "Spotify": "subscriptions",
    "Netflix": "subscriptions",
    "iCloud": "subscriptions",
    "Xbox Game Pass": "subscriptions",
    "Hulu": "subscriptions",
    "Duolingo": "subscriptions",
    "Disney Plus": "subscriptions",
    "NYT Cooking": "subscriptions",
}
DINING = ["Cosmic Cantina", "Bojangles", "Med Deli", "Sup Dogs"]

# (merchant, whole dollars, day of month). Maya and Jake both pay Spotify: the planted duplicate.
SUBSCRIPTIONS = {
    "maya": [("Spotify", 12, 4), ("Netflix", 15, 12), ("iCloud", 3, 20)],
    "jake": [("Spotify", 12, 7), ("Xbox Game Pass", 17, 15), ("Hulu", 10, 25)],
    "priya": [("Duolingo", 7, 2), ("Disney Plus", 14, 18), ("NYT Cooking", 5, 22)],
}

# Shared bills on Maya's checking: (label, payee, day of month, [(due date, cents, status)]).
# Every total is a multiple of 300 cents, so three even shares are whole dollars.
SHARED_BILLS = [
    (
        "Rent",
        "Franklin St Apartments",
        1,
        [
            (dt.date(2026, 9, 1), 240_000, "completed"),
            (dt.date(2026, 10, 1), 240_000, "completed"),
            (dt.date(2026, 11, 1), 240_000, "pending"),
        ],
    ),
    (
        "Electric",
        "Duke Energy",
        15,
        [
            (dt.date(2026, 8, 15), 13_800, "completed"),
            (dt.date(2026, 9, 15), 11_700, "completed"),
            (dt.date(2026, 10, 15), 12_600, "pending"),
        ],
    ),
    (
        "Internet",
        "Spectrum",
        20,
        [
            (dt.date(2026, 8, 20), 7_500, "completed"),
            (dt.date(2026, 9, 20), 7_500, "completed"),
            (dt.date(2026, 10, 20), 7_500, "pending"),
        ],
    ),
]

# Personal bills on each checking account (cents survive on bills).
PERSONAL_BILLS = {
    "maya": ("Car insurance", "Tar Heel Auto Insurance", 11_240, 25),
    "jake": ("Phone", "Carolina Wireless", 4_518, 18),
    "priya": ("Student loan", "Federal Loan Servicer", 8_437, 28),
}


# ---- the plan ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Purchase:
    person: str
    account: str
    merchant: str
    amount_cents: int
    date: dt.date
    status: str
    description: str


@dataclass(frozen=True)
class Movement:  # a deposit or a transfer
    person: str
    account: str
    amount_cents: int
    date: dt.date
    status: str
    description: str


@dataclass(frozen=True)
class Bill:
    person: str
    account: str
    payee: str
    nickname: str
    amount_cents: int
    date: dt.date
    recurring_date: int
    status: str


@dataclass(frozen=True)
class SharedExpense:
    label: str
    payee: str
    total_cents: int
    due_on: dt.date


@dataclass
class Plan:
    purchases: list[Purchase] = field(default_factory=list)
    deposits: list[Movement] = field(default_factory=list)
    transfers: list[Movement] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)
    expenses: list[SharedExpense] = field(default_factory=list)


def build_plan(anchor: dt.date = ANCHOR, days: int = DAYS, seed: int = 42) -> Plan:
    """Deterministic 60 days of history plus the upcoming bills. Pure: no I/O."""
    rng = random.Random(seed)
    start = anchor - dt.timedelta(days=days - 1)
    calendar = [start + dt.timedelta(days=i) for i in range(days)]
    plan = Plan()
    used: set[tuple] = set()

    def buy(person: str, account: str, merchant: str, dollars: int, day: dt.date, description: str):
        while (person, account, merchant, day, dollars) in used:  # keep natural keys unique
            dollars += 1
        used.add((person, account, merchant, day, dollars))
        status = "pending" if day >= anchor else "completed"
        plan.purchases.append(Purchase(person, account, merchant, dollars * 100, day, status, description))

    for p in PEOPLE:
        for i, day in enumerate(calendar):
            if i >= p.payday_offset and (i - p.payday_offset) % 14 == 0:
                pay = (p.pay_dollars + rng.randrange(-15, 16)) * 100
                plan.deposits.append(
                    Movement(p.key, "checking", pay, day, "completed", f"Payroll: {p.employer}")
                )
            for merchant, dollars, dom in SUBSCRIPTIONS[p.key]:
                if day.day == dom:
                    buy(p.key, "credit_card", merchant, dollars, day, "Subscription")
            if day.weekday() in (1, 5) or rng.random() < 0.08:
                store = "Harris Teeter" if rng.random() < 0.6 else "Food Lion"
                buy(p.key, "checking", store, rng.randrange(28, 79), day, "Groceries")
            if rng.random() < 0.22:
                buy(p.key, "credit_card", rng.choice(DINING), rng.randrange(9, 37), day, "Dining out")
            if rng.random() < 0.12:
                buy(p.key, "credit_card", "Uber", rng.randrange(8, 27), day, "Ride")
            if rng.random() < 0.04:
                buy(
                    p.key,
                    "credit_card",
                    rng.choice(["Target", "Amazon"]),
                    rng.randrange(15, 91),
                    day,
                    "Shopping",
                )
            if p.key == "priya" and 24 <= day.day <= 30 and rng.random() < 0.5:
                buy(p.key, "checking", "Target", rng.randrange(40, 91), day, "Shopping")  # tight week
    buy("jake", "checking", "Harris Teeter", 218, anchor - dt.timedelta(days=10), "Groceries")  # anomaly

    payees = [p.key for p in PEOPLE if p.key != PAYER]
    names = {p.key: p.first for p in PEOPLE}
    utilities: Counter = Counter()
    for label, payee, dom, schedule in SHARED_BILLS:
        for due, cents, status in schedule:
            if due < start:
                continue
            plan.bills.append(Bill(PAYER, "checking", payee, label, cents, due, dom, status))
            if status == "pending":
                plan.expenses.append(SharedExpense(label, payee, cents, due))
            elif label == "Rent":
                repay = (due + dt.timedelta(days=2), cents // len(PEOPLE), "Rent share")
                _repay(plan, payees, names, *repay)
            else:
                utilities[due.replace(day=22)] += cents
    for day, cents in sorted(utilities.items()):
        _repay(plan, payees, names, day, cents // len(PEOPLE), "Utilities share")

    for p in PEOPLE:
        nickname, payee, cents, dom = PERSONAL_BILLS[p.key]
        for month in (8, 9, 10):
            due = dt.date(anchor.year, month, dom)
            status = "completed" if due <= anchor else "pending"
            plan.bills.append(Bill(p.key, "checking", payee, nickname, cents, due, dom, status))

    # On the 5th: pay off the card statement and move savings, each as a transfer out of checking
    # plus the matching deposit on the other account (Nessie transfers have no payee).
    paid: Counter = Counter()
    for day in (d for d in calendar if d.day == STATEMENT_DAY):
        for p in PEOPLE:
            owed = sum(
                x.amount_cents
                for x in plan.purchases
                if (x.person, x.account) == (p.key, "credit_card") and x.date < day
            )
            moves = [
                (owed - paid[p.key], "credit_card", "Card payment"),
                (p.monthly_savings_dollars * 100, "savings", "Savings transfer"),
            ]
            for cents, account, what in moves:
                if cents <= 0:
                    continue
                plan.transfers.append(Movement(p.key, "checking", cents, day, "completed", what))
                plan.deposits.append(Movement(p.key, account, cents, day, "completed", f"{what} received"))
            paid[p.key] = owed
    return plan


def _repay(plan: Plan, payers: list[str], names: dict, day: dt.date, cents: int, what: str) -> None:
    """Past repayments to Maya: a transfer out of each roommate plus the matching deposit (no payee field)."""
    for who in payers:
        plan.transfers.append(Movement(who, "checking", cents, day, "completed", f"{what} to {names[PAYER]}"))
        plan.deposits.append(
            Movement(PAYER, "checking", cents, day, "completed", f"{what} from {names[who]}")
        )


def projected_balances(plan: Plan) -> dict[tuple[str, str], tuple[int, int]]:
    """{(person, account): (end cents, lowest cents)}, same rules as api.balances (cards: owed)."""
    events: dict[tuple[str, str], list[tuple[dt.date, int]]] = {}
    for x in plan.deposits:
        events.setdefault((x.person, x.account), []).append((x.date, x.amount_cents))
    for x in [*plan.purchases, *plan.transfers]:
        events.setdefault((x.person, x.account), []).append((x.date, -x.amount_cents))
    for b in plan.bills:
        if b.status == "completed":
            events.setdefault((b.person, b.account), []).append((b.date, -b.amount_cents))
    out = {}
    for p in PEOPLE:
        for kind, _ in ACCOUNTS:
            sign = -1 if kind == "credit_card" else 1
            balance = low = p.openings[kind]
            for _, delta in sorted(events.get((p.key, kind), [])):
                balance += sign * delta
                low = min(low, balance)
            out[(p.key, kind)] = (balance, low)
    return out


# ---- Nessie ------------------------------------------------------------------------------------


@dataclass
class Seeded:
    customers: dict[str, str] = field(default_factory=dict)  # person -> Nessie id
    accounts: dict[tuple[str, str], str] = field(default_factory=dict)  # (person, type) -> Nessie id
    merchants: dict[str, str] = field(default_factory=dict)  # name -> Nessie id
    created: Counter = field(default_factory=Counter)
    reused: Counter = field(default_factory=Counter)


def _first_by(rows: list[dict], key) -> dict:
    """Map key(row) (a tuple) -> id. Duplicates resolve stably by id; zz-probe leftovers are skipped."""
    out: dict = {}
    for row in sorted(rows, key=lambda r: r["id"]):
        k = key(row)
        if not any(str(part).startswith(PROBE_PREFIX) for part in k):
            out.setdefault(k, row["id"])
    return out


def seed_nessie(client: NessieClient, plan: Plan, dry_run: bool) -> Seeded:
    s = Seeded()

    def make(kind: str, fn, *args, **kwargs) -> str:
        s.created[kind] += 1
        return NEW if dry_run else fn(*args, **kwargs)["id"]

    existing = _first_by(client.list_customers(), lambda c: (c["first_name"], c["last_name"]))
    for p in PEOPLE:
        if (p.first, p.last) in existing:
            s.customers[p.key] = existing[(p.first, p.last)]
            s.reused["customer"] += 1
        else:
            s.customers[p.key] = make("customer", client.create_customer, p.first, p.last, HOME)

    existing = _first_by(client.list_merchants(), lambda m: (m["name"],))
    for n, (name, category) in enumerate(MERCHANTS.items()):
        if (name,) in existing:
            s.merchants[name] = existing[(name,)]
            s.reused["merchant"] += 1
        else:
            address = {**HOME, "street_number": str(100 + 10 * n), "street_name": "E Franklin St"}
            s.merchants[name] = make(
                "merchant",
                client.create_merchant,
                name,
                category,
                address,
                35.9132 + n / 10_000,
                -79.0558 - n / 10_000,
            )

    for p in PEOPLE:
        cid = s.customers[p.key]
        have = (
            {} if cid == NEW else _first_by(client.list_accounts(cid), lambda a: (a["type"], a["nickname"]))
        )
        for kind, nickname in ACCOUNTS:
            if (kind, nickname) in have:
                s.accounts[(p.key, kind)] = have[(kind, nickname)]
                s.reused["account"] += 1
            else:
                s.accounts[(p.key, kind)] = make(
                    "account", client.create_account, cid, kind, nickname, p.openings[kind]
                )

    for (person, kind), aid in s.accounts.items():
        new = aid == NEW
        have_p = (
            set()
            if new
            else {(x["merchant_id"], x["date"], x["amount_cents"]) for x in client.list_purchases(aid)}
        )
        have_d = (
            set()
            if new
            else {(x["date"], x["amount_cents"], x["description"]) for x in client.list_deposits(aid)}
        )
        have_t = (
            set()
            if new
            else {(x["date"], x["amount_cents"], x["description"]) for x in client.list_transfers(aid)}
        )
        have_b = set() if new else {(x["nickname"], x["date"]) for x in client.list_bills(aid)}
        for x in plan.purchases:
            if (x.person, x.account) != (person, kind):
                continue
            mid = s.merchants[x.merchant]
            if (mid, x.date.isoformat(), x.amount_cents) in have_p:
                s.reused["purchase"] += 1
            else:
                make(
                    "purchase",
                    client.create_purchase,
                    aid,
                    mid,
                    x.amount_cents,
                    x.date,
                    x.status,
                    x.description,
                )
        for rows, have, kind_name, fn in (
            (plan.deposits, have_d, "deposit", client.create_deposit),
            (plan.transfers, have_t, "transfer", client.create_transfer),
        ):
            for x in rows:
                if (x.person, x.account) != (person, kind):
                    continue
                if (x.date.isoformat(), x.amount_cents, x.description) in have:
                    s.reused[kind_name] += 1
                else:
                    make(kind_name, fn, aid, x.amount_cents, x.date, x.status, x.description)
        for b in plan.bills:
            if (b.person, b.account) != (person, kind):
                continue
            if (b.nickname, b.date.isoformat()) in have_b:
                s.reused["bill"] += 1
            else:
                make(
                    "bill",
                    client.create_bill,
                    aid,
                    b.payee,
                    b.nickname,
                    b.amount_cents,
                    b.date,
                    b.recurring_date,
                    b.status,
                )
    return s


# ---- our database ------------------------------------------------------------------------------


def write_db(conn, client: NessieClient, plan: Plan, s: Seeded) -> dict:
    """Upsert household, users, accounts; sync transactions; add the open shared expenses."""
    from api.nessie.sync import sync_accounts

    counts: Counter = Counter()
    with conn.transaction():
        row = conn.execute(
            "SELECT id FROM households WHERE name = %s ORDER BY id LIMIT 1", (HOUSEHOLD,)
        ).fetchone()
        household_id = (
            row[0]
            if row
            else conn.execute(
                "INSERT INTO households (name) VALUES (%s) RETURNING id", (HOUSEHOLD,)
            ).fetchone()[0]
        )
        users: dict[str, int] = {}
        for p in PEOPLE:
            users[p.key] = conn.execute(
                """INSERT INTO users (display_name, nessie_customer_id) VALUES (%s, %s)
                   ON CONFLICT (nessie_customer_id) DO UPDATE SET display_name = EXCLUDED.display_name
                   RETURNING id""",
                (p.first, s.customers[p.key]),
            ).fetchone()[0]
            counts["member"] += conn.execute(
                """INSERT INTO household_members (household_id, user_id)
                   SELECT %s, %s WHERE NOT EXISTS (
                       SELECT 1 FROM household_members WHERE household_id = %s AND user_id = %s)""",
                (household_id, users[p.key], household_id, users[p.key]),
            ).rowcount
            for acct in client.list_accounts(s.customers[p.key]):
                if s.accounts.get((p.key, acct["type"])) != acct["id"]:  # only the accounts we seeded
                    continue
                counts["account"] += conn.execute(
                    """INSERT INTO accounts
                           (user_id, nessie_account_id, type, nickname, last4, opening_balance_cents)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (nessie_account_id) DO UPDATE SET
                           user_id = EXCLUDED.user_id, type = EXCLUDED.type, nickname = EXCLUDED.nickname,
                           last4 = EXCLUDED.last4, opening_balance_cents = EXCLUDED.opening_balance_cents
                       WHERE (accounts.user_id, accounts.type, accounts.nickname, accounts.last4,
                              accounts.opening_balance_cents)
                          IS DISTINCT FROM (EXCLUDED.user_id, EXCLUDED.type, EXCLUDED.nickname,
                              EXCLUDED.last4,
                              EXCLUDED.opening_balance_cents)""",
                    (
                        users[p.key],
                        acct["id"],
                        acct["type"],
                        acct["nickname"],
                        acct["account_number"][-4:],
                        acct["balance_cents"],
                    ),
                ).rowcount

    sync = sync_accounts(conn, client)

    participants = sorted(users.values())
    with conn.transaction():
        for e in plan.expenses:
            if conn.execute(
                "SELECT 1 FROM expenses WHERE household_id = %s AND label = %s AND due_on = %s",
                (household_id, e.label, e.due_on),
            ).fetchone():
                continue
            source = conn.execute(
                """SELECT t.id FROM transactions t JOIN accounts a ON a.id = t.account_id
                   WHERE a.user_id = %s AND t.kind = 'bill' AND t.merchant = %s
                     AND t.occurred_at::date = %s""",
                (users[PAYER], e.payee, e.due_on),
            ).fetchone()
            expense_id = conn.execute(
                """INSERT INTO expenses (household_id, payer_id, source_txn_id, label, total_cents, status,
                                         split_method, due_on)
                   VALUES (%s, %s, %s, %s, %s, 'final', 'even', %s) RETURNING id""",
                (household_id, users[PAYER], source[0] if source else None, e.label, e.total_cents, e.due_on),
            ).fetchone()[0]
            counts["expense"] += 1
            for user_id, cents in split(e.total_cents, "even", participants).items():
                status = "paid" if user_id == users[PAYER] else "open"  # the payer's own share is covered
                counts["share"] += conn.execute(
                    """INSERT INTO shares (expense_id, user_id, amount_cents, status) VALUES (%s, %s, %s, %s)
                       ON CONFLICT (expense_id, user_id) DO NOTHING""",
                    (expense_id, user_id, cents, status),
                ).rowcount
    return {"db_rows": dict(+counts), "sync": sync}  # +counts drops zeros


# ---- CLI ---------------------------------------------------------------------------------------


def _print_plan(plan: Plan, s: Seeded, dry_run: bool) -> None:
    verb = "Would create" if dry_run else "Created"
    print(f"{verb} in Nessie: {dict(sorted(s.created.items())) or 'nothing'}")
    print(f"Reused from Nessie: {dict(sorted(s.reused.items())) or 'nothing'}")
    print(
        f"Plan: {len(plan.purchases)} purchases, {len(plan.deposits)} deposits, "
        f"{len(plan.transfers)} transfers, {len(plan.bills)} bills, {len(plan.expenses)} open shared expenses"
    )
    for e in plan.expenses:
        shares = split(e.total_cents, "even", [p.key for p in PEOPLE])
        print(f"  {e.label} due {e.due_on}: {e.total_cents} cents paid by {PAYER}, shares {shares}")
    print("Projected balances (cents; credit cards show amount owed):")
    for (person, kind), (end, low) in projected_balances(plan).items():
        print(f"  {person:6} {kind:12} end {end:>9}  lowest {low:>9}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="read Nessie and print the plan; write nothing"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    plan = build_plan()
    if args.dry_run:
        from api.nessie.cache import MemoryCache

        with NessieClient.from_settings(cache=MemoryCache()) as client:
            _print_plan(plan, seed_nessie(client, plan, dry_run=True), dry_run=True)
        return 0

    from api.db import connect
    from api.nessie.cache import PgCache

    with connect(autocommit=True) as cache_conn, connect() as conn:
        with NessieClient.from_settings(cache=PgCache(cache_conn)) as client:
            seeded = seed_nessie(client, plan, dry_run=False)
            _print_plan(plan, seeded, dry_run=False)
            result = write_db(conn, client, plan, seeded)
        conn.commit()
    sync = result["sync"]
    print(f"DB rows written: {result['db_rows'] or 'none'}")
    print(
        f"Sync: {sync.accounts} accounts, {sync.inserted} inserted, {sync.updated} updated, "
        f"{sync.unchanged} unchanged, {sync.removed} removed, {len(sync.skipped)} skipped"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
