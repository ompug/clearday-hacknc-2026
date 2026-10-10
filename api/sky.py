"""The sky: a user's bubbles (personal bills plus their shares of household expenses), coloured by the
money-weather forecast, and the household-only status the app and Clearday Home poll.

Bubbles are a view over the ledger. Balances come only from `api.balances`. The forecast is the
analytics contract (`analytics.forecast.forecast`); this module only assembles its inputs and maps
its per-bill output back to bubbles by (label, date). Necessity comes from `categorize.tag_needs`
and subscription bubbles from `detection.detect_recurring`, both through their contract signatures.

Payees, nicknames and merchant names are untrusted text: they are cleaned for display only and
never select code paths.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from analytics.categorize import detect_income, tag_needs
from analytics.detection import detect_recurring
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
# Nessie files every bill under "bills", which isn't a contract category; tag_needs sees a recurring
# household obligation instead.
NESSIE_BILL_CATEGORY = "bills"
CONTRACT_BILL_CATEGORY = "utilities"
SUBSCRIPTION_CATEGORY = "subscriptions"
SUBSCRIPTIONS_CLUSTER_ID = "cluster_subscriptions"
SUBSCRIPTIONS_CLUSTER_LABEL = "Subscriptions"
MIN_CLUSTER = 2
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


# The bill's nickname ("Phone") lives on the cached Nessie bill, not on the payee ("Carolina Wireless").
PERSONAL_BILLS_SQL = """
SELECT t.id, nb.nickname, t.occurred_at::date, t.amount_cents, COALESCE(t.category, 'other')
FROM transactions t
LEFT JOIN LATERAL (
    SELECT b ->> 'nickname' AS nickname
    FROM nessie_cache c,
         jsonb_array_elements(CASE WHEN jsonb_typeof(c.response_body) = 'array'
                                   THEN c.response_body ELSE '[]'::jsonb END) b
    WHERE c.method = 'GET' AND c.path LIKE '/accounts/%%/bills' AND b ->> '_id' = t.nessie_id
    ORDER BY c.fetched_at DESC
    LIMIT 1
) nb ON TRUE
WHERE t.user_id = %s AND t.kind = 'bill' AND t.status = 'pending'
  AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.source_txn_id = t.id)
ORDER BY t.occurred_at, t.id
"""


@dataclass(frozen=True)
class PersonalBill:
    txn_id: int
    nickname: str | None
    due_on: dt.date
    amount_cents: int
    category: str

    @property
    def label(self) -> str:
        return display_text(self.nickname, "Bill")


def personal_bills(conn, user_id: int) -> list[PersonalBill]:
    """Pending bills that aren't household expenses, labelled by their nickname, never the payee."""
    return [PersonalBill(*r) for r in conn.execute(PERSONAL_BILLS_SQL, (user_id,)).fetchall()]


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


def display_text(text: str | None, fallback: str) -> str:
    """Untrusted text made safe to show as a label: no control or format characters, single spaces,
    at most LABEL_MAX characters. The web renders it as text only."""
    cleaned = "".join(" " if unicodedata.category(ch)[0] in "CZ" else ch for ch in str(text or ""))
    return " ".join(cleaned.split())[:LABEL_MAX].strip() or fallback


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

    for b in personal_bills(conn, user_id):
        add_bill(b.label, b.due_on, b.amount_cents, ids.encode(ids.BILL, b.txn_id))
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


PURCHASES_SQL = """
SELECT t.id, t.user_id, t.account_id, to_char(t.occurred_at, 'YYYY-MM-DD'), t.amount_cents, t.kind,
       COALESCE(t.category, 'other'), t.merchant, t.status
FROM transactions t
WHERE t.user_id = %s AND t.kind = 'purchase' AND t.occurred_at::date <= %s
  AND t.merchant IS NOT NULL AND t.merchant <> ''
ORDER BY t.occurred_at, t.id
"""


@dataclass(frozen=True)
class Subscription:
    bubble_id: str
    label: str
    due_on: dt.date
    amount_cents: int
    account_id: int


def upcoming_subscriptions(conn, user_id: int, start: dt.date) -> list[Subscription]:
    """Recurring charges (detection.detect_recurring) in the subscriptions category, due within the
    horizon. A merchant name is only ever a key into the user's own rows here."""
    end = start + dt.timedelta(days=HORIZON_DAYS - 1)
    rows = conn.execute(PURCHASES_SQL, (user_id, start)).fetchall()
    latest: dict[str, tuple] = {}
    for row in rows:
        latest[str(row[7])] = row  # ordered by time, so the last write is the latest charge
    subs = []
    for rec in detect_recurring(pd.DataFrame(rows, columns=TXN_COLUMNS)):
        last = latest.get(str(rec.get("merchant")))
        nxt, cents = rec.get("next_expected_date"), int(rec.get("amount_cents") or 0)
        if last is None or last[6] != SUBSCRIPTION_CATEGORY or not nxt or cents <= 0:
            continue
        due = dt.date.fromisoformat(str(nxt)[:10])
        step = CADENCE_DAYS.get(str(rec.get("cadence")))
        while step and due < start:
            due += dt.timedelta(days=step)
        if start <= due <= end:
            label = display_text(last[7], "Subscription")
            subs.append(Subscription(ids.encode(ids.SUBSCRIPTION, last[0]), label, due, cents, last[2]))
    return subs


def _necessities(categories: list[str]) -> list[str]:
    """categorize.tag_needs over one row per bubble; unknown output reads as a need."""
    if not categories:
        return []
    rows = [
        {"transaction_id": str(i), "category": CONTRACT_BILL_CATEGORY if c == NESSIE_BILL_CATEGORY else c}
        for i, c in enumerate(categories)
    ]
    tagged = tag_needs(pd.DataFrame(rows, columns=TXN_COLUMNS))
    return [n if n in ("need", "want") else "need" for n in tagged["necessity"].tolist()]


def build_sky(conn, user: CurrentUser) -> dict[str, Any]:
    start = today()
    fc = user_forecast(conn, user.user_id, user.household_id, start)
    checking_id, _ = _checking(conn, user.user_id)
    default_account = ids.encode(ids.ACCOUNT, checking_id) if checking_id is not None else None
    bubbles: list[dict[str, Any]] = []
    categories: list[str] = []

    shares = [s for s in open_household_shares(conn, user.household_id) if s.user_id == user.user_id]
    source_ids = [s.source_txn_id for s in shares if s.source_txn_id is not None]
    source_category: dict[int, str] = (
        dict(
            conn.execute(
                "SELECT id, COALESCE(category, 'other') FROM transactions WHERE id = ANY(%s)", (source_ids,)
            ).fetchall()
        )
        if source_ids
        else {}
    )

    for s in shares:
        bubble_id = ids.encode(ids.EXPENSE, s.expense_id)
        p = 0.0 if s.status == "paid" else fc.p_short(bubble_id)
        categories.append(source_category.get(s.source_txn_id, "other"))
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
                "expense_id": bubble_id,
                "share_id": ids.encode(ids.SHARE, s.share_id),
                "default_account_id": default_account,
                "cluster_id": None,
            }
        )

    def solo(bubble_id: str, label: str, due: dt.date, cents: int, account: str | None) -> dict[str, Any]:
        p = fc.p_short(bubble_id)
        return {
            "bubble_id": bubble_id,
            "kind": "bill",
            "label": label,
            "due_date": due.isoformat(),
            "your_share_cents": cents,
            "total_cents": cents,
            "status": "open",
            "fill_fraction": 0.0,
            "paid_count": 0,
            "participant_count": 1,
            "p_short": p,
            "weather": weather_for(p),
            "expense_id": None,
            "share_id": None,
            "default_account_id": account,
            "cluster_id": None,
        }

    for b in personal_bills(conn, user.user_id):
        categories.append(b.category)
        bubbles.append(
            solo(ids.encode(ids.BILL, b.txn_id), b.label, b.due_on, b.amount_cents, default_account)
        )

    subs = upcoming_subscriptions(conn, user.user_id, start)
    in_cluster = len(subs) >= MIN_CLUSTER
    for sub in subs:
        categories.append(SUBSCRIPTION_CATEGORY)
        bubble = solo(
            sub.bubble_id, sub.label, sub.due_on, sub.amount_cents, ids.encode(ids.ACCOUNT, sub.account_id)
        )
        bubble["cluster_id"] = SUBSCRIPTIONS_CLUSTER_ID if in_cluster else None
        bubbles.append(bubble)

    for bubble, necessity in zip(bubbles, _necessities(categories), strict=True):
        bubble["necessity"] = necessity
    bubbles.sort(key=lambda b: (b["due_date"], b["bubble_id"]))
    clusters = []
    if in_cluster:
        members = [b["bubble_id"] for b in bubbles if b["cluster_id"] == SUBSCRIPTIONS_CLUSTER_ID]
        clusters.append(
            {
                "cluster_id": SUBSCRIPTIONS_CLUSTER_ID,
                "label": SUBSCRIPTIONS_CLUSTER_LABEL,
                "bubble_ids": members,
            }
        )
    horizon_end = start + dt.timedelta(days=HORIZON_DAYS - 1)
    return {
        "as_of": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "bubbles": bubbles,
        "clusters": clusters,
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
