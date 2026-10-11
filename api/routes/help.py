"""GET /api/help: the signed-in user's private help panel (empty unless one of their own triggers fires)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from api import help as help_panel
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/help")
def get_help(
    response: Response,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    return help_panel.panel(conn, user)
