"""Household insights built on analytics contracts: duplicate subscriptions and the forecast backtest.

`duplicate_subscriptions` sees one row per (member, subscription merchant) from the signed-in user's own
household only; `backtest.run` sees only the signed-in user's own history. Merchant names are untrusted
text: they are only ever keys into those rows and are cleaned with `sky.display_text` for display.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from analytics import backtest
from analytics.detection import duplicate_subscriptions
from api import ids, sky
from api.session import CurrentUser

HOLDOUT_DAYS = 30
SUBSCRIPTION_WINDOW_DAYS = 62  # long enough to see a monthly charge twice

HOUSEHOLD_SUBS_SQL = """
SELECT DISTINCT ON (t.user_id, t.merchant)
       t.id, t.user_id, t.account_id, to_char(t.occurred_at, 'YYYY-MM-DD'), t.amount_cents, t.kind,
       t.category, t.merchant, t.status
FROM transactions t
JOIN household_members m ON m.user_id = t.user_id AND m.household_id = %s AND m.left_at IS NULL
WHERE t.kind = 'purchase' AND t.category = 'subscriptions'
  AND t.merchant IS NOT NULL AND t.merchant <> ''
  AND t.occurred_at::date BETWEEN %s AND %s
ORDER BY t.user_id, t.merchant, t.occurred_at DESC, t.id DESC
"""


def duplicate_subscription_cards(conn, user: CurrentUser) -> list[dict[str, Any]]:
    today = sky.today()
    rows = conn.execute(
        HOUSEHOLD_SUBS_SQL, (user.household_id, today - dt.timedelta(days=SUBSCRIPTION_WINDOW_DAYS), today)
    ).fetchall()
    found = duplicate_subscriptions(pd.DataFrame(rows, columns=sky.TXN_COLUMNS))
    names = dict(
        conn.execute(
            "SELECT u.id, u.display_name FROM users u JOIN household_members m ON m.user_id = u.id"
            " WHERE m.household_id = %s AND m.left_at IS NULL",
            (user.household_id,),
        ).fetchall()
    )
    cards = []
    for d in found:
        members = [
            {
                "user_id": ids.encode(ids.USER, int(u)),
                "display_name": sky.display_text(names[int(u)], "Roommate"),
            }
            for u in d["user_ids"]
            if int(u) in names
        ]
        if len(members) < 2:
            continue
        cards.append(
            {
                "merchant": sky.display_text(d["merchant"], "Subscription"),
                "members": members,
                "monthly_cost_cents": int(d["monthly_cost_cents"]),
                "possible_savings_cents": int(d["possible_savings_cents"]),
            }
        )
    return cards


def backtest_summary(conn, user: CurrentUser) -> dict[str, Any]:
    """`backtest.run` over the user's own history. `is_preview` is true while the module is the stub
    (it sets `IS_STUB`); the teammate's real module doesn't, so the UI then drops the caveat."""
    today = sky.today()
    txns = pd.DataFrame(
        conn.execute(
            """SELECT t.id, t.user_id, t.account_id, to_char(t.occurred_at, 'YYYY-MM-DD'), t.amount_cents,
                      t.kind, COALESCE(t.category, 'other'), COALESCE(t.merchant, ''), t.status
               FROM transactions t WHERE t.user_id = %s AND t.occurred_at::date <= %s
                 AND NOT (t.kind = 'bill' AND t.status = 'pending')
               ORDER BY t.occurred_at, t.id""",
            (user.user_id, today),
        ).fetchall(),
        columns=sky.TXN_COLUMNS,
    )
    scheduled = pd.DataFrame(
        [
            {
                "user_id": user.user_id,
                "account_id": b.account_id,
                "date": b.due_on.isoformat(),
                "amount_cents": b.amount_cents,
                "kind": "bill",
                "label": b.label,
                "cadence": None,
            }
            for b in sky.personal_bills(conn, user.user_id)
        ],
        columns=sky.SCHEDULED_COLUMNS,
    )
    out = backtest.run(txns, scheduled, holdout_days=HOLDOUT_DAYS, seed=user.user_id)
    return {
        "coverage": min(max(float(out["coverage"]), 0.0), 1.0),
        "median_abs_error_cents": int(out["median_abs_error_cents"]),
        "holdout_days": HOLDOUT_DAYS,
        "is_preview": bool(getattr(backtest, "IS_STUB", False)),
    }
