"""Create a shared expense with an even or custom split (web/lib/api/types.ts CreateExpenseRequest).

The payer is the signed-in user. Amounts come from `analytics.splits.split` (integer cents, largest
remainder, ties by user ID), so shares always sum to the total. The payer's own share is created
`paid`; everyone else's is `open`. Ledger only: no Nessie write and no money moves until someone pops
their share (`api.payments`).

Idempotency: `expenses.idempotency_key` is unique. A replayed key (same user) returns the original
result and writes nothing; a key used by someone else is a 409.

Events (amount-free): `share.updated` per share to the household and device rooms, and
`feed.created` ("expense_created") to the household room only. The route emits them after commit.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import psycopg

from analytics.splits import split
from api import ids, sky
from api.payments import FILL_PLACES, expense_progress
from api.realtime import Emit, device_room, household_room
from api.session import CurrentUser

SPLIT_METHODS = ("even", "custom")
FEED_TYPE = "expense_created"
ALREADY_SPLIT = "That purchase is already split"


class ExpenseError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Raced(Exception):
    """A concurrent request with the same idempotency key committed first."""


@dataclass
class ExpenseOutcome:
    expense_id: int
    result: dict
    replay: bool = False
    events: list[Emit] = field(default_factory=list)
    # Everyone whose sky or forecast changed: the post-commit hook (forecast refresh) targets them.
    affected_user_ids: list[int] = field(default_factory=list)


def _member_ids(conn, household_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT user_id FROM household_members WHERE household_id = %s AND left_at IS NULL", (household_id,)
    ).fetchall()
    return {r[0] for r in rows}


def _result(conn, expense_id: int) -> dict:
    label, total, method, due_on, payer = conn.execute(
        "SELECT label, total_cents, split_method, due_on, payer_id FROM expenses WHERE id = %s", (expense_id,)
    ).fetchone()
    shares = conn.execute(
        "SELECT id, user_id, amount_cents, status FROM shares WHERE expense_id = %s ORDER BY user_id",
        (expense_id,),
    ).fetchall()
    return {
        "expense_id": ids.encode(ids.EXPENSE, expense_id),
        "label": label,
        "total_cents": total,
        "split_method": method,
        "due_date": due_on.isoformat(),
        "payer_id": ids.encode(ids.USER, payer),
        "shares": [
            {
                "share_id": ids.encode(ids.SHARE, sid),
                "user_id": ids.encode(ids.USER, uid),
                "amount_cents": cents,
                "status": status,
            }
            for sid, uid, cents, status in shares
        ],
    }


def _replay(conn, user: CurrentUser, key: str) -> ExpenseOutcome | None:
    row = conn.execute("SELECT id, payer_id FROM expenses WHERE idempotency_key = %s", (key,)).fetchone()
    if row is None:
        return None
    if row[1] != user.user_id:
        raise ExpenseError(409, "Idempotency key already used")
    return ExpenseOutcome(row[0], _result(conn, row[0]), replay=True)


def already_split(conn, household_id: int, txn_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM expenses WHERE household_id = %s AND source_txn_id = %s", (household_id, txn_id)
        ).fetchone()
        is not None
    )


def _source_txn(conn, user: CurrentUser, source_txn: str | None, total_cents: int) -> int | None:
    """The purchase this expense splits, or None. It must be a current member's purchase whose stored
    amount is the total (the server's ledger, not the client, decides), and not already split."""
    if source_txn is None:
        return None
    txn_id = ids.decode(ids.TRANSACTION, source_txn)
    if txn_id is None:
        raise ExpenseError(422, "Unknown source purchase")
    row = conn.execute(
        """SELECT t.amount_cents FROM transactions t
           JOIN household_members m ON m.user_id = t.user_id AND m.left_at IS NULL
           WHERE t.id = %s AND t.kind = 'purchase' AND m.household_id = %s LIMIT 1""",
        (txn_id, user.household_id),
    ).fetchone()
    if row is None or row[0] != total_cents:
        raise ExpenseError(422, "Source purchase does not match this expense")
    if already_split(conn, user.household_id, txn_id):
        raise ExpenseError(409, ALREADY_SPLIT)
    return txn_id


def _shares(user: CurrentUser, members: set[int], total_cents: int, method: str, participants: list[dict]):
    """{user_id: cents} for the request, or ExpenseError(422)."""
    if method not in SPLIT_METHODS:
        raise ExpenseError(422, "split_method must be even or custom")
    people: list[int] = []
    for p in participants:
        user_id = ids.decode(ids.USER, p.get("user_id"))
        if user_id is None or user_id not in members:
            raise ExpenseError(422, "Participants must be household members")
        people.append(user_id)
    if len(set(people)) != len(people):
        raise ExpenseError(422, "Participants must be unique")
    if not any(u != user.user_id for u in people):
        raise ExpenseError(422, "Add at least one roommate besides you")
    weights = None
    if method == "custom":
        weights = {u: p.get("amount_cents") for u, p in zip(people, participants, strict=True)}
    try:
        return split(total_cents, method, people, weights=weights)
    except ValueError as exc:
        raise ExpenseError(422, "Custom amounts must be integer cents that add up to the total") from exc


def create_expense(
    conn,
    user: CurrentUser,
    *,
    idempotency_key: str,
    label: str,
    total_cents: int,
    split_method: str,
    participants: list[dict],
    due_on: dt.date | None = None,
    source_txn: str | None = None,
) -> ExpenseOutcome:
    """Create the expense and its shares for the signed-in `user` (from the cookie, never the body)."""
    if isinstance(total_cents, bool) or not isinstance(total_cents, int) or total_cents <= 0:
        raise ExpenseError(422, "total_cents must be positive integer cents")
    clean_label = sky.display_text(label, "")
    if not clean_label:
        raise ExpenseError(422, "label must not be empty")
    if replay := _replay(conn, user, idempotency_key):
        return replay
    source_id = _source_txn(conn, user, source_txn, total_cents)
    amounts = _shares(user, _member_ids(conn, user.household_id), total_cents, split_method, participants)
    due = due_on or sky.today()
    try:
        with conn.transaction():
            row = conn.execute(
                """INSERT INTO expenses (household_id, payer_id, label, total_cents, status, split_method,
                                         due_on, idempotency_key, source_txn_id)
                   VALUES (%s, %s, %s, %s, 'final', %s, %s, %s, %s)
                   ON CONFLICT (idempotency_key) DO NOTHING RETURNING id""",
                (
                    user.household_id,
                    user.user_id,
                    clean_label,
                    total_cents,
                    split_method,
                    due,
                    idempotency_key,
                    source_id,
                ),
            ).fetchone()
            if row is None:  # lost a race with the same key
                raise _Raced
            expense_id = row[0]
            for user_id, cents in amounts.items():
                conn.execute(
                    "INSERT INTO shares (expense_id, user_id, amount_cents, status) VALUES (%s, %s, %s, %s)",
                    (expense_id, user_id, cents, "paid" if user_id == user.user_id else "open"),
                )
            conn.execute(
                """INSERT INTO feed_events (household_id, type, actor_id, subject_label)
                   VALUES (%s, %s, %s, %s)""",
                (user.household_id, FEED_TYPE, user.user_id, clean_label),
            )
            result = _result(conn, expense_id)
            paid_cents, total, _, _ = expense_progress(conn, expense_id)
    except psycopg.errors.UniqueViolation as exc:  # the same source purchase, raced past the check
        conn.rollback()
        raise ExpenseError(409, ALREADY_SPLIT) from exc
    except _Raced:
        conn.rollback()
        return _replay(conn, user, idempotency_key)
    except BaseException:
        conn.rollback()
        raise
    conn.commit()  # the ledger is final before anything is emitted

    fill = round(paid_cents / total, FILL_PLACES)  # display ratio, not money
    hh, dev = household_room(user.household_id), device_room(user.household_id)
    events = [
        Emit(
            "share.updated",
            {
                "expense_id": result["expense_id"],
                "share_id": s["share_id"],
                "status": s["status"],
                "fill_fraction": fill,
            },
            (hh, dev),
        )  # fmt: skip
        for s in result["shares"]
    ]
    events.append(
        Emit(
            "feed.created",
            {"type": FEED_TYPE, "actor_display_name": user.display_name, "subject_label": clean_label},
            (hh,),  # members only: the device room never gets names
        )
    )
    return ExpenseOutcome(expense_id, result, events=events, affected_user_ids=sorted(amounts))


def household_members(conn, user: CurrentUser) -> list[dict]:
    """Current members of the user's household: app ID and display name only."""
    rows = conn.execute(
        """SELECT u.id, u.display_name FROM household_members m JOIN users u ON u.id = m.user_id
           WHERE m.household_id = %s AND m.left_at IS NULL ORDER BY u.id""",
        (user.household_id,),
    ).fetchall()
    return [{"user_id": ids.encode(ids.USER, uid), "display_name": name} for uid, name in rows]
