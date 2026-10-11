"""Reset the Apartment 4B demo to its seeded start state, so every judge sees a fresh run.

Usage (from the repo root; the DB is the one api.config points at, e.g. DATABASE_URL_LOCAL):
    uv run python -m scripts.reset_demo --dry-run   # count what would change, change nothing
    uv run python -m scripts.reset_demo             # Nessie first, then our DB
    uv run python -m scripts.reset_demo --db-only   # offline: our DB only, Nessie untouched

Our DB: deletes Clearday-created payments, their allocations (credits are allocations with no share),
the ledger transactions pop-to-pay wrote, the household feed, and every expense the seed didn't create
(app-created ones, e.g. an E2E "Pizza night", with their shares); puts every share back to its seeded
status (the payer's own share paid, the rest open) and every seeded bill back to its seeded status.

Nessie: only inside the seeded accounts of our 3 customers (zz-probe records and anything else are
never read for writing). Deletes transfers and deposits whose id is on a payment row or whose
description starts with "Clearday:", and puts bills that pop marked completed back to their seeded
status. Afterwards it re-lists the touched accounts so nessie_cache matches Nessie again.

Idempotent: a second run changes nothing. Output is counts only: no secrets, no Nessie ids.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field

import httpx
import psycopg

from api.nessie.client import NessieClient, NessieError
from scripts.seed_nessie import ACCOUNTS, HOUSEHOLD, PEOPLE, Plan, _first_by, build_plan

MIRROR_PREFIX = "Clearday:"  # api.payments.mirror_description
_DB_STATUS = {"completed": "posted", "pending": "pending", "recurring": "pending"}  # as api.nessie.sync


@dataclass
class Household:
    id: int
    users: dict[str, int]  # person key -> user id
    account_ids: list[int]


@dataclass
class PaymentRefs:
    """Nessie ids recorded on our payment rows (kept in memory only, never printed)."""

    transfers: set[str] = field(default_factory=set)
    deposits: set[str] = field(default_factory=set)
    bills: set[str] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.transfers) + len(self.deposits) + len(self.bills)


def find_household(conn) -> Household | None:
    row = conn.execute(
        "SELECT id FROM households WHERE name = %s ORDER BY id LIMIT 1", (HOUSEHOLD,)
    ).fetchone()
    if row is None:
        return None
    members = dict(
        conn.execute(
            """SELECT u.display_name, u.id FROM household_members m JOIN users u ON u.id = m.user_id
               WHERE m.household_id = %s""",
            (row[0],),
        ).fetchall()
    )
    users = {p.key: members[p.first] for p in PEOPLE if p.first in members}
    accounts = conn.execute(
        "SELECT id FROM accounts WHERE user_id = ANY(%s) ORDER BY id", (list(members.values()),)
    ).fetchall()
    return Household(row[0], users, [a[0] for a in accounts])


def payment_refs(conn, hh: Household) -> PaymentRefs:
    refs = PaymentRefs()
    rows = conn.execute(
        """SELECT p.nessie_transfer_id, p.nessie_deposit_id, t.nessie_id
           FROM payments p LEFT JOIN transactions t ON t.id = p.bill_txn_id
           WHERE p.from_user = ANY(%s)""",
        (list(hh.users.values()),),
    ).fetchall()
    for transfer, deposit, bill in rows:
        refs.transfers.update([transfer] if transfer else [])
        refs.deposits.update([deposit] if deposit else [])
        refs.bills.update([bill] if bill else [])
    return refs


# ---- Nessie ------------------------------------------------------------------------------------


def seeded_accounts(client: NessieClient) -> dict[tuple[str, str], str]:
    """(person, account type) -> Nessie account id, for our 3 customers' seeded accounts only.
    Same lookup as the seed: exact name, zz-probe skipped, duplicates resolve stably by id."""
    customers = _first_by(client.list_customers(), lambda c: (c["first_name"], c["last_name"]))
    out: dict[tuple[str, str], str] = {}
    for p in PEOPLE:
        cid = customers.get((p.first, p.last))
        if cid is None:
            continue
        have = _first_by(client.list_accounts(cid), lambda a: (a["type"], a["nickname"]))
        for kind, nickname in ACCOUNTS:
            if (kind, nickname) in have:
                out[(p.key, kind)] = have[(kind, nickname)]
    return out


def reset_nessie(client: NessieClient, plan: Plan, refs: PaymentRefs, dry_run: bool) -> Counter:
    counts: Counter = Counter()
    seeded_bills = {(b.person, b.account, b.nickname, b.date.isoformat()): b.status for b in plan.bills}
    touched: list[str] = []
    for (person, kind), aid in seeded_accounts(client).items():
        changed = False
        for name, rows, ours, delete in (
            ("transfer", client.list_transfers(aid), refs.transfers, client.delete_transfer),
            ("deposit", client.list_deposits(aid), refs.deposits, client.delete_deposit),
        ):
            for x in rows:
                if x["id"] in ours or (x["description"] or "").startswith(MIRROR_PREFIX):
                    counts[f"{name}s deleted"] += 1
                    changed = True
                    if not dry_run:
                        delete(x["id"])
        for b in client.list_bills(aid):
            want = seeded_bills.get((person, kind, b["nickname"], b["date"]))
            if want is None and b["id"] in refs.bills:
                want = "pending"  # pop only pays pending bills
            if want is not None and b["status"] != want:
                counts["bills reopened"] += 1
                changed = True
                if not dry_run:
                    client.set_bill_status(b["id"], want)
        if changed:
            touched.append(aid)
    if not dry_run:
        for aid in touched:  # refresh nessie_cache so an offline sync can't bring the records back
            client.list_transfers(aid)
            client.list_deposits(aid)
            client.list_bills(aid)
    return counts


# ---- our database ------------------------------------------------------------------------------


def _noon_utc(day: dt.date) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.UTC)


def reset_db(conn, hh: Household, plan: Plan) -> Counter:
    """Runs inside the caller's transaction. Returns rows changed per kind."""
    counts: Counter = Counter()
    user_ids = list(hh.users.values())
    pay = conn.execute(
        "SELECT id, payer_txn_id, payee_txn_id, bill_txn_id FROM payments WHERE from_user = ANY(%s)",
        (user_ids,),
    ).fetchall()
    payment_ids = [r[0] for r in pay]
    ledger_txns = [t for r in pay for t in r[1:3] if t is not None]
    bill_txns = [r[3] for r in pay if r[3] is not None]

    counts["credits deleted"] = conn.execute(
        "SELECT count(*) FROM allocations WHERE payment_id = ANY(%s) AND share_id IS NULL", (payment_ids,)
    ).fetchone()[0]
    counts["allocations deleted"] = conn.execute(
        "DELETE FROM allocations WHERE payment_id = ANY(%s)", (payment_ids,)
    ).rowcount
    counts["payments deleted"] = conn.execute(
        "DELETE FROM payments WHERE id = ANY(%s)", (payment_ids,)
    ).rowcount
    # The transfer/deposit rows pop wrote, plus any "Clearday:" mirror a sync imported later.
    counts["ledger transactions deleted"] = conn.execute(
        """DELETE FROM transactions
           WHERE account_id = ANY(%s)
             AND (id = ANY(%s) OR (kind IN ('transfer', 'deposit') AND merchant LIKE %s))""",
        (hh.account_ids, ledger_txns, MIRROR_PREFIX + "%"),
    ).rowcount
    reopened = conn.execute(
        """UPDATE transactions SET status = 'pending'
           WHERE id = ANY(%s) AND account_id = ANY(%s) AND kind = 'bill' AND status <> 'pending'""",
        (bill_txns, hh.account_ids),
    ).rowcount
    for b in plan.bills:  # every seeded bill back to its seeded status
        if b.person not in hh.users:
            continue
        reopened += conn.execute(
            """UPDATE transactions SET status = %s
               WHERE user_id = %s AND kind = 'bill' AND merchant = %s AND occurred_at = %s
                 AND status <> %s""",
            (_DB_STATUS[b.status], hh.users[b.person], b.payee, _noon_utc(b.date), _DB_STATUS[b.status]),
        ).rowcount
    counts["bills reopened"] = reopened
    counts["feed events deleted"] = conn.execute(
        "DELETE FROM feed_events WHERE household_id = %s", (hh.id,)
    ).rowcount
    # Expenses the seed didn't create: app-created ones carry an idempotency key; seeded ones match the
    # plan. Their payments and allocations are gone above, so the no-silent-edits trigger (UPDATE only)
    # doesn't apply and nothing else references them.
    seeded = [(e.label, e.total_cents, e.due_on) for e in plan.expenses]
    extra = [
        r[0]
        for r in conn.execute(
            "SELECT id, idempotency_key, label, total_cents, due_on FROM expenses WHERE household_id = %s",
            (hh.id,),
        ).fetchall()
        if r[1] is not None or (r[2], r[3], r[4]) not in seeded
    ]
    conn.execute(
        "DELETE FROM allocations WHERE share_id IN (SELECT id FROM shares WHERE expense_id = ANY(%s))",
        (extra,),
    )
    conn.execute("DELETE FROM shares WHERE expense_id = ANY(%s)", (extra,))
    counts["expenses deleted"] = conn.execute("DELETE FROM expenses WHERE id = ANY(%s)", (extra,)).rowcount
    counts["shares reset"] = conn.execute(
        """UPDATE shares s
           SET status = CASE WHEN s.user_id = e.payer_id THEN 'paid' ELSE 'open' END
           FROM expenses e
           WHERE e.id = s.expense_id AND e.household_id = %s
             AND s.status <> CASE WHEN s.user_id = e.payer_id THEN 'paid' ELSE 'open' END""",
        (hh.id,),
    ).rowcount
    return counts


# ---- entry point -------------------------------------------------------------------------------


@dataclass
class ResetResult:
    nessie: Counter | None  # None when Nessie was skipped
    db: Counter
    nessie_left: int = 0  # mirror records a --db-only run left in Nessie


def reset(
    conn, client: NessieClient | None, *, dry_run: bool = False, plan: Plan | None = None
) -> ResetResult:
    """Nessie first (it needs the ids on our payment rows), then our DB in one transaction. A Nessie
    failure raises before the DB is touched; re-running finishes the job."""
    plan = plan or build_plan()
    hh = find_household(conn)
    if hh is None:
        return ResetResult(None if client is None else Counter(), Counter())
    refs = payment_refs(conn, hh)
    conn.commit()
    nessie = None if client is None else reset_nessie(client, plan, refs, dry_run)
    with conn.transaction() as tx:
        db = reset_db(conn, hh, plan)
        if dry_run:
            raise psycopg.Rollback(tx)
    conn.commit()
    return ResetResult(nessie, db, nessie_left=len(refs) if client is None else 0)


def _line(title: str, counts: Counter | None) -> str:
    if counts is None:
        return f"{title}: skipped"
    shown = {k: v for k, v in sorted(counts.items()) if v}
    return f"{title}: " + (", ".join(f"{v} {k}" for k, v in shown.items()) if shown else "already clean")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="count what would change; change nothing")
    parser.add_argument("--db-only", action="store_true", help="skip Nessie (offline); reset our DB only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    from api.db import connect
    from api.nessie.cache import MemoryCache, PgCache

    with connect(autocommit=True) as cache_conn, connect() as conn:
        print(f"{'Dry run: ' if args.dry_run else ''}resetting database {conn.info.dbname!r}")
        try:
            if args.db_only:
                result = reset(conn, None, dry_run=args.dry_run)
            else:
                cache = MemoryCache() if args.dry_run else PgCache(cache_conn)
                with NessieClient.from_settings(cache=cache) as client:
                    result = reset(conn, client, dry_run=args.dry_run)
        except (NessieError, httpx.HTTPError) as exc:
            conn.rollback()
            print(
                f"Nessie failed ({type(exc).__name__}); our DB is unchanged. "
                "Re-run, or use --db-only offline.",
                file=sys.stderr,
            )
            return 1
    verb = "would change" if args.dry_run else "changed"
    print(_line(f"Nessie {verb}", result.nessie))
    print(_line(f"DB {verb}", result.db))
    if result.nessie_left:
        print(
            f"Note: Nessie still holds {result.nessie_left} pop mirror records (sync ignores them). "
            "Run without --db-only once online to clean them up."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
