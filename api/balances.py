"""Displayed account balances.

PENDING DECISION: Nessie balances never move, so for now a balance is computed from our DB as
opening_balance_cents plus the mirrored transactions. If that decision changes, change only this
function. Deposits add; purchases, transfers and posted bills subtract. Pending bills are upcoming
(not yet paid) and don't count. A credit card's balance is the amount owed, so the signs flip.
"""

from __future__ import annotations

BALANCE_SQL = """
SELECT a.id,
       a.opening_balance_cents + COALESCE(SUM(
           CASE
               WHEN t.id IS NULL OR (t.kind = 'bill' AND t.status = 'pending') THEN 0
               WHEN t.kind = 'deposit' THEN t.amount_cents
               ELSE -t.amount_cents
           END * CASE WHEN a.type = 'credit_card' THEN -1 ELSE 1 END
       ), 0)::BIGINT
FROM accounts a
LEFT JOIN transactions t ON t.account_id = a.id
WHERE a.user_id = %s
GROUP BY a.id
ORDER BY a.id
"""


def account_balances_cents(conn, user_id: int) -> dict[int, int]:
    """{account_id: balance in cents} for one user's accounts (credit cards: amount owed)."""
    return {row[0]: row[1] for row in conn.execute(BALANCE_SQL, (user_id,)).fetchall()}
