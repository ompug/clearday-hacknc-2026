"""GET /api/recap/latest: this week's recap script, transcript and audio URL for the signed-in household."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import recap
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/recap/latest")
def get_latest(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return recap.latest(conn, user.household_id)
