"""GET /api/forecast (web/lib/api/types.ts ForecastResponse). Identity comes only from the session cookie."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import forecast
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/forecast")
def get_forecast(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return forecast.build_forecast(conn, user)
