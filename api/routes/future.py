"""GET /api/future: educational projection for the signed-in user. Rates and a what-if monthly amount are
query parameters; identity comes only from the session cookie."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api import future
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/future")
def get_future(
    low: float | None = None,
    mid: float | None = None,
    high: float | None = None,
    monthly_cents: int | None = None,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
) -> dict:
    try:
        return future.projection(conn, user.user_id, future.rates_from(low, mid, high), monthly_cents)
    except future.FutureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
