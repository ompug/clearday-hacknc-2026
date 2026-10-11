"""GET /api/feed: this household's recent events, no amounts. Household comes from the session only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import feed
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/feed")
def get_feed(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"events": feed.recent(conn, user.household_id)}
