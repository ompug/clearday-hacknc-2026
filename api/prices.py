"""Price memory via the `analytics.prices` contract (normalize, compare).

History is the signed-in user's own confirmed receipt items. Receipt text is untrusted: labels and
merchants are cleaned with `sky.display_text` and only ever used as data (stored, normalized, compared);
no code path branches on what they say.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from analytics import prices
from api import sky
from api.session import CurrentUser

MAX_ITEMS = 40
HISTORY_DAYS = 120
HISTORY_ROWS = 500

HISTORY_SQL = """
SELECT r.merchant, r.purchased_at, i.unit_price_cents, i.normalized_name
FROM receipt_items i JOIN receipts r ON r.id = i.receipt_id
WHERE r.user_id = %s AND i.normalized_name = %s AND r.purchased_at >= %s
ORDER BY r.purchased_at DESC, r.id DESC
LIMIT %s
"""


def _clean(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "label": sky.display_text(i["label"], "Item"),
            "normalized": prices.normalize(sky.display_text(i["label"], "Item"))[:80] or "item",
            "amount_cents": int(i["amount_cents"]),
        }
        for i in items
    ]


def history(conn, user: CurrentUser, normalized: str) -> list[dict[str, Any]]:
    since = sky.today() - dt.timedelta(days=HISTORY_DAYS)
    rows = conn.execute(HISTORY_SQL, (user.user_id, normalized, since, HISTORY_ROWS)).fetchall()
    return [
        {"merchant": m, "date": d.isoformat(), "unit_price_cents": int(c), "normalized_name": n}
        for m, d, c, n in rows
    ]


def compare(conn, user: CurrentUser, item: str, extra: list[dict[str, Any]] | None = None) -> dict:
    """`prices.compare` over remembered history plus any rows not saved yet."""
    normalized = prices.normalize(item)
    return prices.compare(normalized, [*(extra or []), *history(conn, user, normalized)])


def tips(conn, user: CurrentUser, merchant: str, date: dt.date, items: list[dict[str, Any]]) -> list[dict]:
    """For each item on the receipt in hand, where it was cheaper before. Saves nothing."""
    merchant = sky.display_text(merchant, "Store")
    out = []
    for item in _clean(items):
        here = {
            "merchant": merchant,
            "date": date.isoformat(),
            "unit_price_cents": item["amount_cents"],
            "normalized_name": item["normalized"],
        }
        found = prices.compare(item["normalized"], [here, *history(conn, user, item["normalized"])])
        if found["best"] and found["savings_cents_per_unit"] > 0:
            out.append(
                {
                    "label": item["label"],
                    "item": found["item"],
                    "best": found["best"],
                    "latest": found["latest"],
                    "savings_cents_per_unit": int(found["savings_cents_per_unit"]),
                }
            )
    return out


def remember(conn, user: CurrentUser, merchant: str, date: dt.date, items: list[dict[str, Any]]) -> None:
    """Keep a confirmed receipt's items. The same receipt sent twice is stored once."""
    clean = _clean(items)
    if not clean:
        return
    row = conn.execute(
        """INSERT INTO receipts (user_id, merchant, purchased_at, total_cents) VALUES (%s, %s, %s, %s)
           ON CONFLICT (user_id, merchant, purchased_at, total_cents) DO NOTHING RETURNING id""",
        (user.user_id, sky.display_text(merchant, "Store"), date, sum(i["amount_cents"] for i in clean)),
    ).fetchone()
    if row is None:
        return
    for i in clean:
        conn.execute(
            """INSERT INTO receipt_items (receipt_id, raw_label, normalized_name, unit_price_cents)
               VALUES (%s, %s, %s, %s)""",
            (row[0], i["label"], i["normalized"], i["amount_cents"]),
        )
    conn.commit()
