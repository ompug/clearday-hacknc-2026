"""POST /api/payments: pop-to-pay (web/lib/api/types.ts PaymentRequest -> PaymentResult).

Identity comes only from the session cookie. Unknown body fields (e.g. a user_id) are ignored. The
ledger commits before the response; Socket.IO events and the Nessie mirror run after it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api import payments, sky
from api.db import connect, get_conn
from api.nessie.cache import PgCache
from api.nessie.client import NessieClient
from api.realtime import Emit, emit_all
from api.session import CurrentUser, current_user

log = logging.getLogger("clearday.payments")

router = APIRouter()

MirrorRunner = Callable[[int], str]


def run_mirror(payment_id: int) -> str:
    """Mirror one payment with a fresh connection and the real Nessie client."""
    with connect() as conn:
        with NessieClient.from_settings(cache=PgCache(conn)) as client:
            return payments.mirror_payment(conn, client, payment_id)


def get_mirror_runner() -> MirrorRunner:
    """Dependency so tests can swap in a fake Nessie."""
    return run_mirror


class PaymentRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")  # a body user_id is dropped, never read
    idempotency_key: str = Field(min_length=8, max_length=128)
    bubble_id: str = Field(max_length=40)
    account_id: str = Field(max_length=40)
    amount_cents: StrictInt


async def _after_payment(events: list[Emit], payment_id: int, mirror: MirrorRunner) -> None:
    await emit_all(events)
    try:
        await run_in_threadpool(mirror, payment_id)
    except Exception as exc:  # the ledger is committed; sync retries the mirror
        log.warning("mirror of payment %s did not run (%s)", payment_id, type(exc).__name__)


@router.post("/api/payments")
def pay(
    body: PaymentRequest,
    background: BackgroundTasks,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
    mirror: MirrorRunner = Depends(get_mirror_runner),  # noqa: B008
) -> dict:
    try:
        outcome = payments.pop_bubble(
            conn,
            user,
            idempotency_key=body.idempotency_key,
            bubble_id=body.bubble_id,
            account_id=body.account_id,
            amount_cents=body.amount_cents,
        )
    except payments.PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not outcome.replay:
        sky.invalidate_forecasts()
        background.add_task(_after_payment, outcome.events, outcome.payment_id, mirror)
    return outcome.result
