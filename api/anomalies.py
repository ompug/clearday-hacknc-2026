"""Unusual charges for the signed-in user, via `analytics.detection.detect_anomalies`.

Only the user's own recent purchases go in. Merchant names are untrusted text: they are only ever keys
into those rows and are cleaned with `sky.display_text` for display.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from analytics.detection import detect_anomalies
from api import ids, sky
from api.session import CurrentUser

WINDOW_DAYS = 90
MAX_ANOMALIES = 5

SQL = """
SELECT t.id, t.user_id, t.account_id, to_char(t.occurred_at AT TIME ZONE %s, 'YYYY-MM-DD'),
       t.amount_cents, t.kind, COALESCE(t.category, 'other'), COALESCE(t.merchant, ''), t.status
FROM transactions t
WHERE t.user_id = %s AND t.kind = 'purchase' AND t.merchant IS NOT NULL AND t.merchant <> ''
  AND t.occurred_at::date BETWEEN %s AND %s
ORDER BY t.occurred_at, t.id
"""


@dataclass(frozen=True)
class Anomaly:
    txn_id: int
    merchant: str
    date: str
    amount_cents: int
    typical_low_cents: int
    typical_high_cents: int


def find(conn, user: CurrentUser) -> list[Anomaly]:
    today = sky.today()
    rows = conn.execute(
        SQL, (str(sky.DISPLAY_TZ), user.user_id, today - dt.timedelta(days=WINDOW_DAYS), today)
    ).fetchall()
    dates = {str(r[0]): r[3] for r in rows}
    found = detect_anomalies(pd.DataFrame(rows, columns=sky.TXN_COLUMNS))
    out = []
    for a in found[:MAX_ANOMALIES]:
        txn = str(a["transaction_id"])
        if txn not in dates:
            continue
        out.append(
            Anomaly(
                int(txn),
                sky.display_text(a["merchant"], "Purchase"),
                dates[txn],
                int(a["amount_cents"]),
                int(a["typical_low_cents"]),
                int(a["typical_high_cents"]),
            )
        )
    return out


def cards(conn, user: CurrentUser) -> list[dict]:
    return [
        {
            "anomaly_id": ids.encode(ids.TRANSACTION, a.txn_id),
            "merchant": a.merchant,
            "date": a.date,
            "amount_cents": a.amount_cents,
            "typical_low_cents": a.typical_low_cents,
            "typical_high_cents": a.typical_high_cents,
        }
        for a in find(conn, user)
    ]
