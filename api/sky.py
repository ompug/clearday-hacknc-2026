"""The sky: a user's bubbles (personal bills plus their shares of household expenses), coloured by the
money-weather forecast, and the household-only status the app and Clearday Home poll.

Bubbles are a view over the ledger. Balances come only from `api.balances`. The forecast is the
analytics contract (`analytics.forecast.forecast`); this module only assembles its inputs and maps
its per-bill output back to bubbles by (label, date).
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from analytics.categorize import detect_income
from analytics.forecast import forecast
from api import ids
from api.balances import account_balances_cents
from api.session import CurrentUser

DISPLAY_TZ = ZoneInfo("America/New_York")
HORIZON_DAYS = 30
THRESHOLD_CENTS = 5_000  # spec default safety buffer ($50)
TIGHT_P = 0.5
WATCH_P = 0.2
DEFAULT_P_SHORT = 0.05  # outside the forecast horizon (or overdue): no signal either way
DUE_SOON_DAYS = 3  # Clearday Home "Bill due soon"
FORECAST_TTL_S = 15.0
LABEL_MAX = 80
CADENCE_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30}
TXN_COLUMNS = [
    "transaction_id",
    "user_id",
    "account_id",
    "date",
    "amount_cents",
    "kind",
    "category",
    "merchant",
    "status",
]
SCHEDULED_COLUMNS = ["user_id", "account_id", "date", "amount_cents", "kind", "label", "cadence"]


def today() -> dt.date:
    """Today in the display timezone (due dates are America/New_York)."""
    return dt.datetime.now(DISPLAY_TZ).date()


def weather_for(p_short: float) -> str:
    if p_short >= TIGHT_P:
        return "tight"
    if p_short >= WATCH_P:
        return "watch"
    return "clear"


# ---- ledger reads ------------------------------------------------------------------------------

SHARED_SQL = """
WITH alloc AS (
    SELECT share_id, SUM(amount_cents) AS cents FROM allocations WHERE share_id IS NOT NULL GROUP BY share_id
), progress AS (
    SELECT s.expense_id,
           COUNT(*) AS participants,
           COUNT(*) FILTER (WHERE s.status = 'paid') AS paid_count,
           SUM(CASE WHEN s.status = 'paid' THEN s.amount_cents
                    ELSE LEAST(s.amount_cents, COALESCE(a.cents, 0)) END)::BIGINT AS paid_cents
    FROM shares s LEFT JOIN alloc a ON a.share_id = s.id
    GROUP BY s.expense_id
)
SELECT e.id, e.label, COALESCE(e.due_on, e.created_at::date), e.total_cents, e.payer_id, e.source_txn_id,
       s.id, s.user_id, s.amount_cents, s.status,
       LEAST(s.amount_cents, COALESCE(a.cents, 0))::BIGINT,
       p.participants, p.paid_count, p.paid_cents
FROM expenses e
JOIN shares s ON s.expense_id = e.id
LEFT JOIN alloc a ON a.share_id = s.id
JOIN progress p ON p.expense_id = e.id
WHERE e.household_id = %s AND p.paid_count < p.participants
ORDER BY e.due_on NULLS LAST, e.id, s.user_id
"""


@dataclass(frozen=True)
class ShareRow:
    expense_id: int
    label: str
    due_on: dt.date
    total_cents: int
    payer_id: int
    source_txn_id: int | None
    share_id: int
    user_id: int
    amount_cents: int
    status: str
    allocated_cents: int
    participants: int
    paid_count: int
    paid_cents: int


def open_household_shares(conn, household_id: int) -> list[ShareRow]:
    """Every share of every household expense that isn't fully paid yet."""
    return [ShareRow(*r) for r in conn.execute(SHARED_SQL, (household_id,)).fetchall()]


PERSONAL_BILLS_SQL = """
SELECT t.id, t.merchant, t.occurred_at::date, t.amount_cents
FROM transactions t
WHERE t.user_id = %s AND t.kind = 'bill' AND t.status = 'pending'
  AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.source_txn_id = t.id)
ORDER BY t.occurred_at, t.id
"""

ACCOUNTS_SQL = """
SELECT id, type, nickname, last4 FROM accounts WHERE user_id = %s
ORDER BY CASE type WHEN 'checking' THEN 0 WHEN 'savings' THEN 1 ELSE 2 END, id
"""


def list_accounts(conn, user_id: int) -> list[dict[str, Any]]:
    """Nickname and last 4 only, with the balance from the one balance function."""
    balances = account_balances_cents(conn, user_id)
    return [
        {
            "account_id": ids.encode(ids.ACCOUNT, pk),
            "type": kind,
            "nickname": nickname,
            "last4": last4,
            "balance_cents": balances.get(pk, 0),
        }
        for pk, kind, nickname, last4 in conn.execute(ACCOUNTS_SQL, (user_id,)).fetchall()
    ]


def _checking(conn, user_id: int) -> tuple[int | None, int]:
    """(first checking account id, total checking balance in cents)."""
    rows = conn.execute(ACCOUNTS_SQL, (user_id,)).fetchall()
    checking = [r[0] for r in rows if r[1] == "checking"]
    balances = account_balances_cents(conn, user_id)
    return (checking[0] if checking else None), sum(balances.get(a, 0) for a in checking)


# ---- forecast ----------------------------------------------------------------------------------


@dataclass
class UserForecast:
    """Forecast output plus the (label, date) -> bubble_id map for its bills."""

    result: dict[str, Any]
    bubble_by_bill: dict[tuple[str, str], str] = field(default_factory=dict)

    def p_short(self, bubble_id: str) -> float:
        for row in self.result.get("bills", []):
            if self.bubble_by_bill.get((str(row["label"]), str(row["date"]))) == bubble_id:
                return float(row["p_short"])
        return DEFAULT_P_SHORT


_cache: dict[int, tuple[float, dt.date, UserForecast]] = {}
_cache_lock = threading.Lock()


def invalidate_forecasts() -> None:
    """Call after anything that changes balances or shares (payments, sync)."""
    with _cache_lock:
        _cache.clear()


def _label(text: str | None) -> str:
    return (text or "Bill").strip()[:LABEL_MAX] or "Bill"


def _income_schedule(checking_deposits: pd.DataFrame, start: dt.date, end: dt.date) -> list[dict]:
    income = detect_income(checking_deposits)
    step = CADENCE_DAYS.get(income.get("cadence", ""))
    nxt = income.get("next_expected_date")
    amount = int(income.get("typical_amount_cents") or 0)
    if not step or not nxt or amount <= 0:
        return []
    day = dt.date.fromisoformat(str(nxt)[:10])
    while day < start:
        day += dt.timedelta(days=step)
    rows = []
    while day <= end:
        rows.append({"date": day.isoformat(), "amount_cents": amount, "kind": "income", "label": "Paycheck"})
        day += dt.timedelta(days=step)
    return rows


def _compute_forecast(conn, user_id: int, household_id: int, start: dt.date) -> UserForecast:
    end = start + dt.timedelta(days=HORIZON_DAYS - 1)
    checking_id, start_balance = _checking(conn, user_id)
    txn_rows = conn.execute(
        """SELECT t.id, t.user_id, t.account_id, to_char(t.occurred_at, 'YYYY-MM-DD'), t.amount_cents,
                  t.kind, COALESCE(t.category, 'other'), COALESCE(t.merchant, ''), t.status
           FROM transactions t
           WHERE t.user_id = %s AND t.occurred_at::date <= %s
             AND NOT (t.kind = 'bill' AND t.status = 'pending')
           ORDER BY t.occurred_at, t.id""",
        (user_id, start),
    ).fetchall()
    txns = pd.DataFrame(txn_rows, columns=TXN_COLUMNS)
    deposits = txns[(txns["kind"] == "deposit") & (txns["account_id"] == checking_id)]

    scheduled: list[dict] = _income_schedule(deposits, start, end)
    bubble_by_bill: dict[tuple[str, str], str] = {}

    def add_bill(label: str, day: dt.date, cents: int, bubble_id: str) -> None:
        if cents <= 0:
            return
        scheduled.append({"date": day.isoformat(), "amount_cents": cents, "kind": "bill", "label": label})
        bubble_by_bill[(label, day.isoformat())] = bubble_id

    for txn_id, merchant, due, cents in conn.execute(PERSONAL_BILLS_SQL, (user_id,)).fetchall():
        add_bill(_label(merchant), due, cents, ids.encode(ids.BILL, txn_id))
    for s in open_household_shares(conn, household_id):
        bubble_id = ids.encode(ids.EXPENSE, s.expense_id)
        if s.payer_id == user_id and s.source_txn_id is not None:
            # The payer's account carries the whole bill; roommates repay them later.
            if s.user_id == user_id:
                add_bill(s.label, s.due_on, s.total_cents, bubble_id)
        elif s.user_id == user_id and s.status != "paid":
            add_bill(s.label, s.due_on, s.amount_cents - s.allocated_cents, bubble_id)

    for row in scheduled:
        row.update(user_id=user_id, account_id=checking_id, cadence=None)
    result = forecast(
        txns,
        pd.DataFrame(scheduled, columns=SCHEDULED_COLUMNS),
        start_balance,
        start.isoformat(),
        horizon_days=HORIZON_DAYS,
        threshold_cents=THRESHOLD_CENTS,
        seed=user_id,
    )
    return UserForecast(result=result, bubble_by_bill=bubble_by_bill)


def user_forecast(conn, user_id: int, household_id: int, start: dt.date) -> UserForecast:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(user_id)
        if hit and hit[0] > now and hit[1] == start:
            return hit[2]
    fc = _compute_forecast(conn, user_id, household_id, start)
    with _cache_lock:
        _cache[user_id] = (now + FORECAST_TTL_S, start, fc)
    return fc


# ---- responses ---------------------------------------------------------------------------------


def build_sky(conn, user: CurrentUser) -> dict[str, Any]:
    start = today()
    fc = user_forecast(conn, user.user_id, user.household_id, start)
    checking_id, _ = _checking(conn, user.user_id)
    default_account = ids.encode(ids.ACCOUNT, checking_id) if checking_id is not None else None
    bubbles: list[dict[str, Any]] = []

    for s in open_household_shares(conn, user.household_id):
        if s.user_id != user.user_id:
            continue
        bubble_id = ids.encode(ids.EXPENSE, s.expense_id)
        p = 0.0 if s.status == "paid" else fc.p_short(bubble_id)
        bubbles.append(
            {
                "bubble_id": bubble_id,
                "kind": "shared",
                "label": s.label,
                "due_date": s.due_on.isoformat(),
                "your_share_cents": s.amount_cents,
                "total_cents": s.total_cents,
                "status": s.status,
                "fill_fraction": round(s.paid_cents / s.total_cents, 4),  # display ratio, not money
                "paid_count": s.paid_count,
                "participant_count": s.participants,
                "p_short": p,
                "weather": weather_for(p),
                "necessity": "need",  # shared household bills (rent, utilities)
                "expense_id": bubble_id,
                "share_id": ids.encode(ids.SHARE, s.share_id),
                "default_account_id": default_account,
                "cluster_id": None,
            }
        )

    for txn_id, merchant, due, cents in conn.execute(PERSONAL_BILLS_SQL, (user.user_id,)).fetchall():
        bubble_id = ids.encode(ids.BILL, txn_id)
        p = fc.p_short(bubble_id)
        bubbles.append(
            {
                "bubble_id": bubble_id,
                "kind": "bill",
                "label": _label(merchant),
                "due_date": due.isoformat(),
                "your_share_cents": cents,
                "total_cents": cents,
                "status": "open",
                "fill_fraction": 0.0,
                "paid_count": 0,
                "participant_count": 1,
                "p_short": p,
                "weather": weather_for(p),
                "necessity": "need",  # Nessie bills are recurring obligations
                "expense_id": None,
                "share_id": None,
                "default_account_id": default_account,
                "cluster_id": None,
            }
        )

    bubbles.sort(key=lambda b: (b["due_date"], b["bubble_id"]))
    horizon_end = start + dt.timedelta(days=HORIZON_DAYS - 1)
    return {
        "as_of": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "bubbles": bubbles,
        "clusters": [],
        "safe_to_spend_cents": int(fc.result.get("safe_to_spend_cents") or 0),
        "next_payday": fc.result.get("next_payday") or horizon_end.isoformat(),
    }


def household_status(conn, user: CurrentUser) -> dict[str, Any]:
    """Household-level counts only: no amounts, no names, no per-person data (Clearday Home reads this)."""
    start = today()
    shares = open_household_shares(conn, user.household_id)
    expenses: dict[int, ShareRow] = {s.expense_id: s for s in shares}
    tight = False
    for s in shares:
        if s.status == "paid" or tight:
            continue
        member_fc = user_forecast(conn, s.user_id, user.household_id, start)
        tight = member_fc.p_short(ids.encode(ids.EXPENSE, s.expense_id)) >= TIGHT_P
    soon = start + dt.timedelta(days=DUE_SOON_DAYS)
    return {
        "weather": "tight" if tight else "clear",
        "open_bills": len(expenses),
        "due_soon_bills": sum(1 for e in expenses.values() if e.due_on <= soon),
        "shares_paid": sum(e.paid_count for e in expenses.values()),
        "shares_total": sum(e.participants for e in expenses.values()),
    }
