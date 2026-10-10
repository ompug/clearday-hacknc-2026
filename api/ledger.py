"""The household ledger: record a payment against shares, in integer cents, in one DB transaction.

A payment from payer to payee covers the payer's open shares of the payee's expenses: the shares the
user picked first, then the rest oldest first (due date, then expense id). Any overflow is a credit
(an allocation with share_id NULL). A share's status follows what has been allocated to it: paid when
covered, partial when part-covered. The math is `analytics.splits.allocate_payment`.

Idempotency: the client key is unique in `payments`. A replayed key returns the original payment and
writes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from analytics.splits import allocate_payment


class LedgerError(ValueError):
    """The payment can't be recorded as asked."""


class IdempotencyConflict(LedgerError):
    """The key was already used for a different payment."""


@dataclass
class LedgerPayment:
    payment_id: int
    allocations: list[dict] = field(default_factory=list)
    credit_cents: int = 0
    replay: bool = False
    result: dict | None = None  # the stored PaymentResult, set on replay


OPEN_SHARES_SQL = """
SELECT s.id, s.amount_cents - COALESCE(
           (SELECT SUM(a.amount_cents) FROM allocations a WHERE a.share_id = s.id), 0)::BIGINT AS owed
FROM shares s JOIN expenses e ON e.id = s.expense_id
WHERE s.user_id = %s AND e.payer_id = %s AND s.status IN ('open', 'partial')
ORDER BY e.due_on NULLS LAST, e.id
FOR UPDATE OF s
"""


def _check_cents(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LedgerError("amount must be positive integer cents")
    return value


def find_replay(conn, idempotency_key: str, payer_id: int) -> LedgerPayment | None:
    """The payment already recorded under this key (by this payer), or None."""
    row = conn.execute(
        "SELECT id, from_user, result FROM payments WHERE idempotency_key = %s", (idempotency_key,)
    ).fetchone()
    if row is None:
        return None
    if row[1] != payer_id:
        raise IdempotencyConflict("idempotency key already used")
    allocs = conn.execute(
        "SELECT share_id, amount_cents FROM allocations WHERE payment_id = %s ORDER BY id", (row[0],)
    ).fetchall()
    return LedgerPayment(
        payment_id=row[0],
        allocations=[{"share_id": s, "amount_cents": c} for s, c in allocs if s is not None],
        credit_cents=sum(c for s, c in allocs if s is None),
        replay=True,
        result=row[2],
    )


PAYMENT_COLUMNS = {
    "from_user",
    "to_user",
    "account_id",
    "amount_cents",
    "expense_id",
    "bill_txn_id",
    "payer_txn_id",
    "payee_txn_id",
}


def insert_payment(conn, *, idempotency_key: str, **columns) -> int | None:
    """Insert the payments row; None if the key already exists (a concurrent double tap)."""
    unknown = set(columns) - PAYMENT_COLUMNS
    if unknown:
        raise LedgerError(f"unknown payments columns: {sorted(unknown)}")
    names = ["idempotency_key", *columns]
    # Column names come from the PAYMENT_COLUMNS allowlist.
    sql = (
        f"INSERT INTO payments ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))})"  # noqa: S608
        " ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
    )
    row = conn.execute(sql, (idempotency_key, *columns.values())).fetchone()
    return row[0] if row else None


def refresh_share_statuses(conn, share_ids: Sequence[int]) -> None:
    conn.execute(
        """UPDATE shares s SET status = CASE WHEN a.cents >= s.amount_cents THEN 'paid' ELSE 'partial' END
           FROM (SELECT share_id, SUM(amount_cents) AS cents FROM allocations
                 WHERE share_id = ANY(%s) GROUP BY share_id) a
           WHERE a.share_id = s.id AND s.status <> 'disputed'""",
        (list(share_ids),),
    )


def record_share_payment(
    conn,
    *,
    payer_id: int,
    payee_id: int,
    account_id: int,
    amount_cents: int,
    idempotency_key: str,
    picked_share_ids: Sequence[int] = (),
    extra_columns: dict | None = None,
) -> LedgerPayment:
    """Record payer -> payee in one transaction and allocate it. Commits unless the caller already
    holds a transaction, in which case it joins it."""
    _check_cents(amount_cents)
    if payer_id == payee_id:
        raise LedgerError("payer and payee must differ")
    with conn.transaction():
        if replay := find_replay(conn, idempotency_key, payer_id):
            return replay
        payment_id = insert_payment(
            conn,
            idempotency_key=idempotency_key,
            from_user=payer_id,
            to_user=payee_id,
            account_id=account_id,
            amount_cents=amount_cents,
            **(extra_columns or {}),
        )
        if payment_id is None:  # lost a race with the same key: return the winner's payment
            return find_replay(conn, idempotency_key, payer_id)

        owed = conn.execute(OPEN_SHARES_SQL, (payer_id, payee_id)).fetchall()
        picked = [sid for sid in picked_share_ids if any(sid == s for s, _ in owed)]
        order = picked + [s for s, _ in owed if s not in picked]
        owed_by_id = dict(owed)
        plan = allocate_payment(amount_cents, [{"share_id": s, "amount_cents": owed_by_id[s]} for s in order])
        for a in plan["allocations"]:
            conn.execute(
                "INSERT INTO allocations (payment_id, share_id, amount_cents) VALUES (%s, %s, %s)",
                (payment_id, a["share_id"], a["amount_cents"]),
            )
        if plan["credit_cents"]:
            conn.execute(
                "INSERT INTO allocations (payment_id, share_id, amount_cents) VALUES (%s, NULL, %s)",
                (payment_id, plan["credit_cents"]),
            )
        refresh_share_statuses(conn, [a["share_id"] for a in plan["allocations"]])
    return LedgerPayment(payment_id, plan["allocations"], plan["credit_cents"])
