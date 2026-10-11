"""GET /api/insights/subscriptions and /api/insights/backtest. Identity comes only from the session cookie."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import insights
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/insights/subscriptions")
def get_duplicate_subscriptions(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"duplicates": insights.duplicate_subscription_cards(conn, user)}


@router.get("/api/insights/backtest")
def get_backtest(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return insights.backtest_summary(conn, user)
