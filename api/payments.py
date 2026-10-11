"""Pop-to-pay: pay one bubble from the sky, then mirror it to Nessie.

Shared bubble (`exp_N`): the user's share of a household expense is paid to the expense payer through
`api.ledger` (picked share first). The money also lands in our transactions (a transfer out of the
paying account, a deposit into the payee's checking) so displayed balances move to the cent.
Personal bill (`bill_N`): the pending bill transaction is posted.

Ledger rows are written in one DB transaction and commit even if Nessie is down. The mirror runs
afterwards (`mirror_payment`): payer-side transfer plus payee-side deposit in whole dollars (the
difference is `nessie_rounding_diff_cents`), or the Nessie bill marked completed. A failed mirror is
marked and retried by sync (`retry_mirrors`). Sync leaves ledger-owned Nessie records alone
(`ledger_owned_nessie_ids`) so their exact cents survive.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

import httpx
from psycopg.types.json import Jsonb

from api import ids, ledger
from api.nessie.client import NessieClient, NessieError
from api.realtime import Emit, device_room, household_room, user_room
from api.session import CurrentUser

log = logging.getLogger("clearday.payments")

FILL_PLACES = 4


class PaymentError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class PopOutcome:
    payment_id: int
    result: dict
    replay: bool = False
    events: list[Emit] = field(default_factory=list)


class _Replayed(Exception):
    def __init__(self, lp: ledger.LedgerPayment) -> None:
        self.lp = lp


def nessie_amount(cents: int) -> tuple[int, int]:
    """(whole-dollar amount in cents sent to Nessie, ledger cents minus that). Rounds half up."""
    dollars, rem = divmod(cents, 100)
    if rem >= 50:
        dollars += 1
    sent = dollars * 100
    return sent, cents - sent


def mirror_description(label: str) -> str:
    return f"Clearday: {label} share"


def _noon_utc(day: dt.date) -> dt.datetime:
    # Same convention as api.nessie.sync.occurred_at, so the mirrored record keys line up.
    return dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.UTC)


def _user_account(conn, user_id: int, account_id: str) -> int:
    pk = ids.decode(ids.ACCOUNT, account_id)
    row = conn.execute("SELECT id FROM accounts WHERE id = %s AND user_id = %s", (pk, user_id)).fetchone()
    if pk is None or row is None:
        raise PaymentError(404, "Account not found")
    return row[0]


def _replay(conn, user: CurrentUser, key: str, bubble_id: str) -> PopOutcome | None:
    try:
        lp = ledger.find_replay(conn, key, user.user_id)
    except ledger.IdempotencyConflict as exc:
        raise PaymentError(409, "Idempotency key already used") from exc
    if lp is None:
        return None
    if not lp.result or lp.result.get("bubble_id") != bubble_id:
        raise PaymentError(409, "Idempotency key already used")
    return PopOutcome(lp.payment_id, lp.result, replay=True)


def expense_progress(conn, expense_id: int) -> tuple[int, int, int, int]:
    """(paid_cents, total_cents, paid_count, participants) for one expense."""
    return conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN s.status = 'paid' THEN s.amount_cents
                               ELSE LEAST(s.amount_cents, COALESCE(a.cents, 0)) END), 0)::BIGINT,
                  e.total_cents, COUNT(*) FILTER (WHERE s.status = 'paid'), COUNT(*)
           FROM expenses e JOIN shares s ON s.expense_id = e.id
           LEFT JOIN (SELECT share_id, SUM(amount_cents) AS cents FROM allocations GROUP BY share_id) a
                  ON a.share_id = s.id
           WHERE e.id = %s GROUP BY e.total_cents""",
        (expense_id,),
    ).fetchone()


def _pop_shared(
    conn, user: CurrentUser, key: str, bubble_id: str, account_id: str, amount: int
) -> PopOutcome:
    expense_id = ids.decode(ids.EXPENSE, bubble_id)
    with conn.transaction():
        row = conn.execute(
            """SELECT e.label, e.payer_id, s.id, s.amount_cents - COALESCE(
                          (SELECT SUM(a.amount_cents) FROM allocations a WHERE a.share_id = s.id), 0)::BIGINT,
                      s.status
               FROM expenses e JOIN shares s ON s.expense_id = e.id AND s.user_id = %s
               WHERE e.id = %s AND e.household_id = %s
               FOR UPDATE OF s""",
            (user.user_id, expense_id, user.household_id),
        ).fetchone()
        if row is None:
            raise PaymentError(404, "Bubble not found")
        label, payee_id, share_id, owed, status = row
        if payee_id == user.user_id or status in ("paid", "disputed") or owed <= 0:
            raise PaymentError(409, "Nothing left to pay")
        if amount != owed:
            raise PaymentError(409, "Amount changed")
        paying_account = _user_account(conn, user.user_id, account_id)
        payee_account = conn.execute(
            "SELECT id FROM accounts WHERE user_id = %s AND type = 'checking' ORDER BY id LIMIT 1",
            (payee_id,),
        ).fetchone()
        if payee_account is None:
            raise PaymentError(409, "Payee has no checking account")

        when = _noon_utc(dt.datetime.now(dt.UTC).date())
        description = mirror_description(label)
        txn_sql = """INSERT INTO transactions
                         (user_id, account_id, kind, amount_cents, merchant, category, status, occurred_at)
                     VALUES (%s, %s, %s, %s, %s, 'transfer', 'posted', %s) RETURNING id"""
        payer_txn = conn.execute(
            txn_sql, (user.user_id, paying_account, "transfer", amount, description, when)
        )
        payee_txn = conn.execute(txn_sql, (payee_id, payee_account[0], "deposit", amount, description, when))
        lp = ledger.record_share_payment(
            conn,
            payer_id=user.user_id,
            payee_id=payee_id,
            account_id=paying_account,
            amount_cents=amount,
            idempotency_key=key,
            picked_share_ids=[share_id],
            extra_columns={
                "expense_id": expense_id,
                "payer_txn_id": payer_txn.fetchone()[0],
                "payee_txn_id": payee_txn.fetchone()[0],
            },
        )
        if lp.replay:  # a concurrent request with this key won: undo our transactions
            raise _Replayed(lp)

        new_status = conn.execute("SELECT status FROM shares WHERE id = %s", (share_id,)).fetchone()[0]
        paid_cents, total, paid_count, participants = expense_progress(conn, expense_id)
        fill = round(paid_cents / total, FILL_PLACES)  # display ratio, not money
        popped = paid_count == participants
        result = {
            "payment_id": f"pay_{lp.payment_id}",
            "bubble_id": bubble_id,
            "status": new_status,
            "fill_fraction": fill,
            "paid_count": paid_count,
            "popped": popped,
        }
        conn.execute("UPDATE payments SET result = %s WHERE id = %s", (Jsonb(result), lp.payment_id))
        feed_type = "bubble_popped" if popped else "share_paid"
        conn.execute(
            "INSERT INTO feed_events (household_id, type, actor_id, subject_label) VALUES (%s, %s, %s, %s)",
            (user.household_id, feed_type, user.user_id, label),
        )

    hh, dev = household_room(user.household_id), device_room(user.household_id)
    events = [
        Emit(
            "share.updated",
            {
                "expense_id": bubble_id,
                "share_id": ids.encode(ids.SHARE, share_id),
                "status": new_status,
                "fill_fraction": fill,
            },
            (hh, dev),
        ),  # fmt: skip
        Emit(
            "feed.created",
            {"type": feed_type, "actor_display_name": user.display_name, "subject_label": label},
            (hh,),  # members only: the device room never gets names
        ),
    ]
    if popped:
        events.insert(1, Emit("bubble.popped", {"expense_id": bubble_id, "label": label}, (hh, dev)))
    return PopOutcome(lp.payment_id, result, events=events)


def _pop_bill(conn, user: CurrentUser, key: str, bubble_id: str, account_id: str, amount: int) -> PopOutcome:
    txn_id = ids.decode(ids.BILL, bubble_id)
    with conn.transaction():
        row = conn.execute(
            """SELECT t.amount_cents, t.merchant FROM transactions t
               WHERE t.id = %s AND t.user_id = %s AND t.kind = 'bill' AND t.status = 'pending'
                 AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.source_txn_id = t.id)
               FOR UPDATE""",
            (txn_id, user.user_id),
        ).fetchone()
        if row is None:
            raise PaymentError(409, "Nothing left to pay")
        if amount != row[0]:
            raise PaymentError(409, "Amount changed")
        paying_account = _user_account(conn, user.user_id, account_id)
        payment_id = ledger.insert_payment(
            conn,
            idempotency_key=key,
            from_user=user.user_id,
            to_user=None,
            account_id=paying_account,
            amount_cents=amount,
            bill_txn_id=txn_id,
        )
        if payment_id is None:
            raise _Replayed(ledger.find_replay(conn, key, user.user_id))
        conn.execute("UPDATE transactions SET status = 'posted' WHERE id = %s", (txn_id,))
        result = {
            "payment_id": f"pay_{payment_id}",
            "bubble_id": bubble_id,
            "status": "paid",
            "fill_fraction": 1.0,
            "paid_count": 1,
            "popped": True,
        }
        conn.execute("UPDATE payments SET result = %s WHERE id = %s", (Jsonb(result), payment_id))
    label = (row[1] or "Bill").strip()[:80] or "Bill"
    # A personal bill is private: only the user's own sessions hear about it.
    events = [Emit("bubble.popped", {"expense_id": bubble_id, "label": label}, (user_room(user.user_id),))]
    return PopOutcome(payment_id, result, events=events)


def pop_bubble(
    conn, user: CurrentUser, *, idempotency_key: str, bubble_id: str, account_id: str, amount_cents: int
) -> PopOutcome:
    """Pay one bubble for the signed-in user. Identity is `user` (from the cookie), never the body."""
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents <= 0:
        raise PaymentError(422, "amount_cents must be positive integer cents")
    if replay := _replay(conn, user, idempotency_key, bubble_id):
        return replay
    if ids.decode(ids.EXPENSE, bubble_id) is not None:
        pop = _pop_shared
    elif ids.decode(ids.BILL, bubble_id) is not None:
        pop = _pop_bill
    elif ids.decode(ids.SUBSCRIPTION, bubble_id) is not None:
        raise PaymentError(409, "Subscriptions renew automatically; there is nothing to pay here")
    else:
        raise PaymentError(404, "Bubble not found")
    try:
        outcome = pop(conn, user, idempotency_key, bubble_id, account_id, amount_cents)
    except _Replayed:
        conn.rollback()
        return _replay(conn, user, idempotency_key, bubble_id)
    except ledger.IdempotencyConflict as exc:
        conn.rollback()
        raise PaymentError(409, "Idempotency key already used") from exc
    except BaseException:
        conn.rollback()
        raise
    conn.commit()  # the ledger is final before anything is emitted or mirrored
    return outcome


# ---- Nessie mirror -------------------------------------------------------------------------------

MIRROR_LOCK = 0x0C1EA4DB  # pg advisory lock class: one mirror per payment at a time

MIRROR_ROW_SQL = """
SELECT p.amount_cents, p.created_at::date, p.mirror_status, p.nessie_transfer_id, p.nessie_deposit_id,
       p.bill_txn_id, p.payer_txn_id, p.payee_txn_id, e.label, pa.nessie_account_id,
       (SELECT a.nessie_account_id FROM transactions t JOIN accounts a ON a.id = t.account_id
         WHERE t.id = p.payee_txn_id),
       (SELECT t.nessie_id FROM transactions t WHERE t.id = p.bill_txn_id)
FROM payments p
LEFT JOIN expenses e ON e.id = p.expense_id
LEFT JOIN accounts pa ON pa.id = p.account_id
WHERE p.id = %s
"""


def mirror_payment(conn, client: NessieClient, payment_id: int) -> str:
    """Mirror one committed payment to Nessie and return its mirror_status. Commits on `conn` after
    each Nessie write, so a retry after a partial failure never creates a duplicate record."""
    conn.commit()
    if not conn.execute("SELECT pg_try_advisory_lock(%s, %s)", (MIRROR_LOCK, payment_id)).fetchone()[0]:
        conn.commit()
        return "pending"  # another worker is mirroring it right now
    try:
        row = conn.execute(MIRROR_ROW_SQL, (payment_id,)).fetchone()
        if row is None:
            raise ValueError(f"no payment {payment_id}")
        (cents, day, status, transfer_id, deposit_id, bill_txn, payer_txn, payee_txn, label,
         payer_nessie, payee_nessie, bill_nessie) = row  # fmt: skip
        if status == "mirrored":
            return status
        try:
            if bill_txn is not None:
                if bill_nessie:
                    client.set_bill_status(bill_nessie, "completed")
            else:
                sent, diff = nessie_amount(cents)
                conn.execute(
                    "UPDATE payments SET nessie_rounding_diff_cents = %s WHERE id = %s", (diff, payment_id)
                )
                conn.commit()
                desc = mirror_description(label or "Household")
                if sent > 0 and payer_nessie and transfer_id is None:
                    transfer_id = client.create_transfer(payer_nessie, sent, day, "completed", desc)["id"]
                    _link(conn, payment_id, "nessie_transfer_id", transfer_id, payer_txn)
                if sent > 0 and payee_nessie and deposit_id is None:
                    deposit_id = client.create_deposit(payee_nessie, sent, day, "completed", desc)["id"]
                    _link(conn, payment_id, "nessie_deposit_id", deposit_id, payee_txn)
        except (NessieError, httpx.HTTPError) as exc:
            log.warning(
                "Nessie mirror for payment %s failed (%s); sync will retry", payment_id, type(exc).__name__
            )
            status = "failed"
        else:
            status = "mirrored"
        conn.execute(
            "UPDATE payments SET mirror_status = %s, mirror_attempts = mirror_attempts + 1 WHERE id = %s",
            (status, payment_id),
        )
        conn.commit()
        return status
    finally:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(%s, %s)", (MIRROR_LOCK, payment_id))
        conn.commit()


_LINK_SQL = {
    "nessie_transfer_id": "UPDATE payments SET nessie_transfer_id = %s WHERE id = %s",
    "nessie_deposit_id": "UPDATE payments SET nessie_deposit_id = %s WHERE id = %s",
}


def _link(conn, payment_id: int, column: str, nessie_id: str, txn_id: int | None) -> None:
    conn.execute(_LINK_SQL[column], (nessie_id, payment_id))
    if txn_id is not None:
        conn.execute("UPDATE transactions SET nessie_id = %s WHERE id = %s", (nessie_id, txn_id))
    conn.commit()


def retry_mirrors(conn, client: NessieClient) -> dict[str, int]:
    """Mirror every payment that isn't mirrored yet (called at the start of a sync)."""
    pending = conn.execute("SELECT id FROM payments WHERE mirror_status <> 'mirrored' ORDER BY id").fetchall()
    counts: dict[str, int] = {}
    for (pid,) in pending:
        status = mirror_payment(conn, client, pid)
        counts[status] = counts.get(status, 0) + 1
    return counts


def ledger_owned_nessie_ids(conn) -> set[str]:
    """Nessie records our ledger wrote or settled. Sync must not overwrite them (Nessie holds whole
    dollars and may lag a failed mirror), so the ledger's exact cents and statuses stand."""
    rows = conn.execute(
        """SELECT nessie_transfer_id FROM payments WHERE nessie_transfer_id IS NOT NULL
           UNION SELECT nessie_deposit_id FROM payments WHERE nessie_deposit_id IS NOT NULL
           UNION SELECT t.nessie_id FROM payments p JOIN transactions t ON t.id = p.bill_txn_id
                 WHERE t.nessie_id IS NOT NULL"""
    ).fetchall()
    return {r[0] for r in rows}
