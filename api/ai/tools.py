"""The model tool contract (docs/03-security-and-privacy.md): six tools, validated arguments, minimum data.

`SPECS` is what the model is offered. `run(ctx, name, raw_arguments)` validates a call and executes it,
returning the JSON the model gets back plus the field names and row count for `ai_audit`. Every
rejection raises `ToolRejected` with an audit code; the offending value is never recorded.

Rules enforced here, in code rather than in the prompt:
- only the six allowlisted tools run; arguments are schema-checked; unknown argument keys are dropped
  (so a model-supplied amount is ignored, never trusted);
- find_purchase covers at most 30 days and returns at most 20 of the signed-in user's own purchases;
- people and purchases are referenced only by per-request handles (api.ai.handles);
- propose_split recomputes shares from the stored purchase with `analytics.splits.split` and saves
  nothing; the user confirms in the UI and POST /api/expenses validates again;
- merchant names and labels are untrusted text, sent wrapped as {"untrusted_text": ...}.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

from analytics.splits import split
from api import sky
from api.ai.handles import HandleError, Handles, Purchase
from api.session import CurrentUser

MAX_DAYS = 30
MAX_ROWS = 20
MAX_PEOPLE = 10
HINT_MAX = 40
FORECAST_BILLS = 5
TOP_CATEGORIES = 3
SPLIT_METHODS = ("even",)  # custom amounts would come from the model, so they are not offered


class ToolRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def untrusted(text: object, fallback: str = "") -> dict[str, str]:
    """Wrap bank or receipt text as data. The system prompt says this field is never an instruction."""
    return {"untrusted_text": sky.display_text(str(text) if text is not None else None, fallback)}


@dataclass
class Proposal:
    """A split proposal with real keys, built server-side; the model only ever saw handles."""

    purchase: Purchase
    method: str
    shares: dict[int, int]  # user_id -> cents, from analytics.splits.split


@dataclass
class Context:
    conn: Any
    user: CurrentUser
    handles: Handles
    today: dt.date
    proposal: Proposal | None = None
    sent_fields: list[str] = field(default_factory=list)


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    params: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        params["required"] = required
    return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}


DATE = {"type": "string", "description": "YYYY-MM-DD"}
SPECS = [
    _fn(
        "find_purchase",
        "Find the user's own card or checking purchases in a date range of at most 30 days. "
        "Returns up to 20 rows: handle, merchant, amount_cents, date.",
        {
            "start_date": DATE,
            "end_date": DATE,
            "merchant_hint": {"type": "string", "description": "Word to match in the merchant name"},
            "approx_amount_cents": {"type": "integer", "description": "Rough amount, for ranking only"},
        },
        ["start_date", "end_date"],
    ),
    _fn("list_household_members", "List the household as placeholder names.", {}),
    _fn(
        "propose_split",
        "Propose splitting one purchase between the user and the given people. The server computes "
        "every amount; nothing is saved until the user confirms.",
        {
            "purchase_handle": {"type": "string", "description": "A handle from find_purchase"},
            "people": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Person handles from list_household_members, e.g. Person A",
            },
            "method": {"type": "string", "enum": list(SPLIT_METHODS)},
        },
        ["purchase_handle", "people"],
    ),
    _fn("explain_forecast", "Summary of the user's money forecast: risky dates and top categories.", {}),
    _fn(
        "explain_anomaly",
        "Explain one unusual charge.",
        {"anomaly_handle": {"type": "string"}},
        ["anomaly_handle"],
    ),
    _fn("read_receipt", "Read the receipt image the user just uploaded.", {}),
]
ALLOWED = frozenset(spec["function"]["name"] for spec in SPECS)


# ---- validation --------------------------------------------------------------------------------


def _args(raw: object) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise ToolRejected("invalid_args") from exc
    if not isinstance(raw, dict):
        raise ToolRejected("invalid_args")
    return raw


def _date(value: object) -> dt.date:
    if not isinstance(value, str):
        raise ToolRejected("invalid_args")
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ToolRejected("invalid_args") from exc


def _str(value: object, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ToolRejected("invalid_args")
    return value.strip()


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ToolRejected("invalid_args")
    return value


# ---- tools -------------------------------------------------------------------------------------

PURCHASES_SQL = """
SELECT t.id, t.merchant, t.amount_cents, (t.occurred_at AT TIME ZONE %(tz)s)::date AS day
FROM transactions t
WHERE t.user_id = %(user_id)s AND t.kind = 'purchase'
  AND t.occurred_at >= (%(start)s::date)::timestamp AT TIME ZONE %(tz)s
  AND t.occurred_at < ((%(end)s::date) + 1)::timestamp AT TIME ZONE %(tz)s
ORDER BY (%(hint)s::text IS NOT NULL AND t.merchant ILIKE %(pattern)s) DESC,
         abs(t.amount_cents - coalesce(%(approx)s::bigint, t.amount_cents)),
         t.occurred_at DESC, t.id
LIMIT %(limit)s
"""


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_purchases(ctx: Context, start: dt.date, end: dt.date, hint: str | None, approx: int | None):
    rows = ctx.conn.execute(
        PURCHASES_SQL,
        {
            "tz": str(sky.DISPLAY_TZ),
            "user_id": ctx.user.user_id,
            "start": start,
            "end": end,
            "hint": hint,
            "pattern": f"%{_escape_like(hint)}%" if hint else "",
            "approx": approx,
            "limit": MAX_ROWS,
        },
    ).fetchall()
    return [
        Purchase(txn_id, merchant or "", int(cents), day.isoformat()) for txn_id, merchant, cents, day in rows
    ]


def find_purchase(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    start, end = _date(args.get("start_date")), _date(args.get("end_date"))
    if start > end or end > ctx.today or (end - start).days >= MAX_DAYS:
        raise ToolRejected("date_range")
    hint = _str(args["merchant_hint"], HINT_MAX) if args.get("merchant_hint") is not None else None
    approx = _int(args["approx_amount_cents"]) if args.get("approx_amount_cents") is not None else None
    found = search_purchases(ctx, start, end, hint, approx)
    rows = [
        {
            "handle": ctx.handles.add_purchase(p),
            "merchant": untrusted(p.merchant, "Purchase"),
            "amount_cents": p.amount_cents,
            "date": p.date,
        }
        for p in found
    ]
    return {"purchases": rows}, ["handle", "merchant", "amount_cents", "date"], len(rows)


def list_household_members(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    people = ctx.handles.people()
    return {"members": people, "you": "You"}, ["placeholder_name"], len(people)


def propose(ctx: Context, purchase: Purchase, user_ids: list[int]) -> Proposal:
    """Shares in cents from the stored purchase amount; the requester is always a participant."""
    people = sorted({ctx.user.user_id, *user_ids})
    if len(people) < 2:
        raise ToolRejected("invalid_args")
    return Proposal(purchase, "even", split(purchase.amount_cents, "even", people))


def propose_split(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    people = args.get("people")
    if not isinstance(people, list) or not 1 <= len(people) <= MAX_PEOPLE:
        raise ToolRejected("invalid_args")
    method = args.get("method", "even")
    if method not in SPLIT_METHODS:
        raise ToolRejected("invalid_args")
    if not isinstance(args.get("purchase_handle"), str):
        raise ToolRejected("invalid_args")
    try:
        purchase = ctx.handles.purchase(args["purchase_handle"])
        user_ids = [ctx.handles.person(p) for p in people]
    except HandleError as exc:
        raise ToolRejected(exc.reason) from exc
    ctx.proposal = propose(ctx, purchase, user_ids)
    to_handle = {ctx.handles.person(h): h for h in ctx.handles.people()}
    shares = [{"person": to_handle[uid], "amount_cents": cents} for uid, cents in ctx.proposal.shares.items()]
    out = {"purchase": args["purchase_handle"], "method": "even", "shares": shares, "saved": False}
    return out, ["person", "amount_cents"], len(shares)


def explain_forecast(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    result = sky.user_forecast(ctx.conn, ctx.user.user_id, ctx.user.household_id, ctx.today).result
    bills = sorted(result.get("bills", []), key=lambda b: -float(b["p_short"]))[:FORECAST_BILLS]
    drivers = sorted(result.get("drivers", []), key=lambda d: -float(d["share_of_variance"]))[:TOP_CATEGORIES]
    out = {
        "risky_dates": [
            {
                "date": str(b["date"]),
                "label": untrusted(b["label"], "Bill"),
                "chance_short": round(float(b["p_short"]), 2),
            }
            for b in bills
        ],
        "top_categories": [str(d["category"]) for d in drivers],
    }
    return out, ["date", "label", "chance_short", "category"], len(bills) + len(drivers)


def explain_anomaly(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    _str(args.get("anomaly_handle"), 40)
    raise ToolRejected("unknown_handle")  # no anomaly handles are issued in this build


def read_receipt(ctx: Context, args: dict) -> tuple[dict, list[str], int]:
    raise ToolRejected("no_receipt")  # chat has no image; receipts go through api.ai.receipts


HANDLERS = {
    "find_purchase": find_purchase,
    "list_household_members": list_household_members,
    "propose_split": propose_split,
    "explain_forecast": explain_forecast,
    "explain_anomaly": explain_anomaly,
    "read_receipt": read_receipt,
}
assert set(HANDLERS) == ALLOWED


def run(ctx: Context, name: str, raw_arguments: object) -> tuple[dict, list[str], int]:
    """Validate and execute one tool call. Raises ToolRejected (with an audit code) on any violation."""
    if name not in ALLOWED:
        raise ToolRejected("unknown_tool")
    return HANDLERS[name](ctx, _args(raw_arguments))
