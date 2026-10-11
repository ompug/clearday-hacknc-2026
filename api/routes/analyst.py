"""GET /api/analyst/segments: synthetic-household hardship rates. Needs a session; reads no user data."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import analyst
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/analyst/segments")
def get_segments(user: CurrentUser = Depends(current_user)) -> dict:  # noqa: ARG001, B008
    return analyst.segments()
