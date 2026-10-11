"""Money weather for one user: the `GET /api/forecast` body and the debounced `forecast.updated` event.

The forecast itself is `analytics.forecast.forecast` through its contract, run by `api.sky.user_forecast`
(the same inputs and cache the sky uses), so the stub and the teammate's real module are interchangeable.
This module only maps the contract output to `ForecastResponse` (web/lib/api/types.ts): each bill gets
its bubble link and weather, and labels are cleaned untrusted text.

`forecast.updated` goes to each affected user's private room only, and carries only that user's own
bubbles and safe-to-spend (`ForecastUpdatedEvent`). Writers call `request_update(user_ids)` (or
`request_payment_update(payment_id)`) after their transaction commits; calls inside `DEBOUNCE_S` of each
other coalesce into one recompute per user, run off the event loop after the response.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

import anyio.from_thread
from fastapi.concurrency import run_in_threadpool

from api import sky
from api.db import get_conn
from api.realtime import sio, user_room
from api.session import CurrentUser, load_member

log = logging.getLogger("clearday.forecast")

EVENT = "forecast.updated"
DEBOUNCE_S = 0.75  # quiet period before recomputing
MAX_WAIT_S = 3.0  # a steady stream of writes still gets an update this often


# ---- GET /api/forecast -------------------------------------------------------------------------


def _bill_row(row: dict[str, Any], fc: sky.UserForecast, with_amount: bool) -> dict[str, Any]:
    label, date = str(row["label"]), str(row["date"])
    p = float(row["p_short"])
    out: dict[str, Any] = {"label": sky.display_text(label, "Bill"), "date": date}
    if with_amount:
        out["amount_cents"] = int(row["amount_cents"])
    out.update(p_short=p, bubble_id=fc.bubble_by_bill.get((label, date)), weather=sky.weather_for(p))
    return out


def build_forecast(conn, user: CurrentUser) -> dict[str, Any]:
    """`ForecastResponse` for the signed-in user (their own accounts, bills and shares only)."""
    fc = sky.user_forecast(conn, user.user_id, user.household_id, sky.today())
    r = fc.result
    trimmed = r.get("wants_trimmed") or {}
    return {
        "as_of": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "threshold_cents": sky.THRESHOLD_CENTS,
        "days": [
            {
                "date": str(d["date"]),
                "p10_cents": int(d["p10_cents"]),
                "p50_cents": int(d["p50_cents"]),
                "p90_cents": int(d["p90_cents"]),
            }
            for d in r.get("days", [])
        ],
        "bills": [_bill_row(b, fc, with_amount=True) for b in r.get("bills", [])],
        "safe_to_spend_cents": int(r.get("safe_to_spend_cents") or 0),
        "next_payday": r.get("next_payday"),
        "drivers": [
            {"category": str(d["category"]), "share_of_variance": float(d["share_of_variance"])}
            for d in r.get("drivers", [])
        ],
        "wants_trimmed": {
            "safe_to_spend_cents": int(trimmed.get("safe_to_spend_cents") or 0),
            "bills": [_bill_row(b, fc, with_amount=False) for b in trimmed.get("bills", [])],
        },
    }


# ---- forecast.updated --------------------------------------------------------------------------


def event_payload(conn, user: CurrentUser) -> dict[str, Any]:
    """`ForecastUpdatedEvent`: the user's own sky bubble colours and safe-to-spend, nothing else."""
    s = sky.build_sky(conn, user)
    return {
        "bubbles": [
            {"bubble_id": b["bubble_id"], "weather": b["weather"], "p_short": b["p_short"]}
            for b in s["bubbles"]
        ],
        "safe_to_spend_cents": s["safe_to_spend_cents"],
    }


@contextmanager
def open_conn() -> Iterator[Any]:
    """A connection from the same provider requests use, so a test's `get_conn` override (a scratch
    database) also covers this after-response work."""
    from api.main import fastapi_app  # late: api.main imports the routes that import this module

    provider = fastapi_app.dependency_overrides.get(get_conn, get_conn)
    gen = provider()
    try:
        yield next(gen)
    finally:
        gen.close()


def _payloads(user_ids: list[int]) -> list[tuple[int, dict[str, Any]]]:
    sky.invalidate_forecasts()  # writers may not have invalidated; never emit a stale colour
    out = []
    with open_conn() as conn:
        for uid in user_ids:
            user = load_member(conn, uid)
            if user is not None:
                out.append((uid, event_payload(conn, user)))
    return out


def _payment_user_ids(payment_id: int) -> list[int]:
    with open_conn() as conn:
        row = conn.execute("SELECT from_user, to_user FROM payments WHERE id = %s", (payment_id,)).fetchone()
    return [u for u in (row or ()) if u is not None]


class Debouncer:
    """Trailing-edge debounce of per-user recomputes, on the event loop that first schedules one."""

    def __init__(self, delay_s: float = DEBOUNCE_S, max_wait_s: float = MAX_WAIT_S) -> None:
        self.delay_s = delay_s
        self.max_wait_s = max_wait_s
        self._pending: set[int] = set()
        self._payment_ids: set[int] = set()
        self._timer: asyncio.TimerHandle | None = None
        self._first_at: float | None = None
        self._tasks: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def add(self, user_ids: Iterable[int] = (), payment_ids: Iterable[int] = ()) -> None:
        """Must run on the event loop."""
        loop = asyncio.get_running_loop()
        if loop is not self._loop:  # a new loop (restart, test client): drop the old loop's timer
            self._loop, self._timer, self._first_at = loop, None, None
            self._pending.clear()
            self._payment_ids.clear()
        self._pending.update(int(u) for u in user_ids)
        self._payment_ids.update(int(p) for p in payment_ids)
        if not self._pending and not self._payment_ids:
            return
        now = loop.time()
        if self._first_at is None:
            self._first_at = now
        if self._timer is not None:
            self._timer.cancel()
        delay = min(self.delay_s, max(0.0, self._first_at + self.max_wait_s - now))
        self._timer = loop.call_later(delay, self._fire)

    def _fire(self) -> None:
        user_ids, payment_ids = sorted(self._pending), sorted(self._payment_ids)
        self._pending.clear()
        self._payment_ids.clear()
        self._timer = None
        self._first_at = None
        task = asyncio.get_running_loop().create_task(self.flush(user_ids, payment_ids))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self, user_ids: Iterable[int], payment_ids: Iterable[int] = ()) -> None:
        try:
            ids = set(user_ids)
            for pid in payment_ids:
                ids.update(await run_in_threadpool(_payment_user_ids, pid))
            for uid, payload in await run_in_threadpool(_payloads, sorted(ids)):
                await sio.emit(EVENT, payload, room=user_room(uid))
        except Exception as exc:  # the write already succeeded; the next poll or update catches up
            log.warning("forecast.updated not sent (%s)", type(exc).__name__)

    async def drain(self) -> None:
        """Fire anything pending now and wait for it (tests and shutdown)."""
        if self._timer is not None:
            self._timer.cancel()
            self._fire()
        if self._tasks:
            await asyncio.gather(*list(self._tasks))


debouncer = Debouncer()


def _schedule(user_ids: Iterable[int], payment_ids: Iterable[int]) -> None:
    user_ids, payment_ids = list(user_ids), list(payment_ids)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:  # a sync handler or background task in FastAPI's threadpool
            anyio.from_thread.run_sync(debouncer.add, user_ids, payment_ids)
        except RuntimeError:
            log.warning("forecast.updated skipped: no event loop to schedule on")
        return
    debouncer.add(user_ids, payment_ids)


def request_update(user_ids: Iterable[int]) -> None:
    """Post-commit hook: these users' forecasts changed. Safe from async code or a threadpool thread."""
    _schedule(user_ids, ())


def request_payment_update(payment_id: int) -> None:
    """Post-commit hook for a payment: updates both its payer and its payee."""
    _schedule((), (payment_id,))
