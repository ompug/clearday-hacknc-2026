"""Mirror Nessie activity into our transactions hypertable. Idempotent: re-running changes nothing.

Every GET goes through the client, so a sync also refreshes nessie_cache. Records are keyed by
Nessie id; a record whose date moved is re-keyed, one that vanished from Nessie (or was cancelled)
is removed, and an unchanged record is left alone.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from api.nessie.client import NessieClient

log = logging.getLogger("clearday.nessie.sync")

# Nessie status -> ours. None means "don't mirror" (cancelled).
_STATUS = {"completed": "posted", "pending": "pending", "recurring": "pending", "cancelled": None}


@dataclass
class SyncStats:
    accounts: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    skipped: list[str] = field(default_factory=list)  # Nessie ids we couldn't read

    @property
    def changed(self) -> int:
        return self.inserted + self.updated + self.removed


def occurred_at(date_text: str) -> dt.datetime:
    """Nessie dates are YYYY-MM-DD; pin them to noon UTC so no timezone shifts the day."""
    day = dt.date.fromisoformat(date_text[:10])
    return dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.UTC)


def _rows_for_account(client: NessieClient, nessie_account_id: str, merchants: dict, stats: SyncStats):
    """Yield normalised rows (nessie_id, kind, amount_cents, merchant, category, status, occurred_at)."""
    sources = (
        ("purchase", client.list_purchases),
        ("deposit", client.list_deposits),
        ("transfer", client.list_transfers),
        ("bill", client.list_bills),
    )
    for kind, fetch in sources:
        for rec in fetch(nessie_account_id):
            try:
                status = _STATUS[rec["status"]]
                when = occurred_at(rec["date"])
            except (KeyError, TypeError, ValueError):
                stats.skipped.append(rec["id"])
                continue
            if status is None:
                continue
            if kind == "purchase":
                name, category = merchants.get(rec["merchant_id"], (None, None))
            elif kind == "bill":
                name, category = rec["payee"], "bills"
            elif kind == "transfer":
                name, category = rec["description"], "transfer"
            else:
                name, category = rec["description"], "income"
            yield rec["id"], kind, rec["amount_cents"], name, category, status, when


def sync_accounts(conn, client: NessieClient) -> SyncStats:
    """Refresh every Nessie-backed account in our DB. Runs in one DB transaction."""
    from api.payments import ledger_owned_nessie_ids, retry_mirrors  # noqa: PLC0415 (avoids an import cycle)

    retry_mirrors(conn, client)  # before fetching, so new mirror records are recognised below
    owned = ledger_owned_nessie_ids(conn)
    stats = SyncStats()
    merchants = {m["id"]: (m["name"], m["category"]) for m in client.list_merchants()}
    accounts = conn.execute(
        "SELECT id, user_id, nessie_account_id FROM accounts WHERE nessie_account_id IS NOT NULL ORDER BY id"
    ).fetchall()
    # Fetch everything before writing, so a Nessie failure leaves the DB untouched.
    fetched = [(a, list(_rows_for_account(client, a[2], merchants, stats))) for a in accounts]
    with conn.transaction():
        for (account_id, user_id, _), rows in fetched:
            stats.accounts += 1
            seen = []
            for nessie_id, kind, cents, merchant, category, status, when in rows:
                seen.append(nessie_id)
                if nessie_id in owned:  # the ledger holds exact cents and status for these
                    stats.unchanged += 1
                    continue
                moved = conn.execute(
                    "DELETE FROM transactions WHERE nessie_id = %s AND occurred_at <> %s", (nessie_id, when)
                ).rowcount
                result = conn.execute(
                    """
                    INSERT INTO transactions
                        (user_id, account_id, nessie_id, kind, amount_cents, merchant, category, status,
                         occurred_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (nessie_id, occurred_at) DO UPDATE SET
                        user_id = EXCLUDED.user_id, account_id = EXCLUDED.account_id, kind = EXCLUDED.kind,
                        amount_cents = EXCLUDED.amount_cents, merchant = EXCLUDED.merchant,
                        category = EXCLUDED.category, status = EXCLUDED.status
                    WHERE (transactions.user_id, transactions.account_id, transactions.kind,
                           transactions.amount_cents, transactions.merchant, transactions.category,
                           transactions.status)
                       IS DISTINCT FROM (EXCLUDED.user_id, EXCLUDED.account_id, EXCLUDED.kind,
                           EXCLUDED.amount_cents, EXCLUDED.merchant, EXCLUDED.category, EXCLUDED.status)
                    RETURNING (xmax = 0) AS inserted
                    """,
                    (user_id, account_id, nessie_id, kind, cents, merchant, category, status, when),
                ).fetchone()
                if result is None:
                    stats.unchanged += 1
                elif result[0] and not moved:
                    stats.inserted += 1
                else:
                    stats.updated += 1
            stats.removed += conn.execute(
                "DELETE FROM transactions WHERE account_id = %s AND nessie_id IS NOT NULL"
                " AND NOT (nessie_id = ANY(%s::text[]))",
                (account_id, seen),
            ).rowcount
    if stats.skipped:
        log.warning("Nessie sync skipped %d unreadable records", len(stats.skipped))
    return stats
