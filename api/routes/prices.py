"""Price memory endpoints. Identity comes only from the session cookie; history is the user's own.

POST /api/prices/tips      items of a receipt just read -> where each was cheaper before (saves nothing)
POST /api/prices/remember  the confirmed items of a receipt, kept for later comparisons
GET  /api/prices?item=     price history summary of one normalized item (analytics.prices.compare)
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from api import prices, sky
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


class Item(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: str = Field(min_length=1, max_length=200)
    amount_cents: StrictInt = Field(gt=0, le=100_000_00)


class ReceiptItems(BaseModel):
    model_config = ConfigDict(extra="ignore")  # a body user_id is dropped, never read
    merchant: str = Field(min_length=1, max_length=200)
    date: dt.date
    items: list[Item] = Field(max_length=prices.MAX_ITEMS)


def _checked(body: ReceiptItems) -> list[dict]:
    if body.date > sky.today():
        raise HTTPException(422, "date is in the future")
    return [i.model_dump() for i in body.items]


@router.post("/api/prices/tips")
def price_tips(body: ReceiptItems, user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"tips": prices.tips(conn, user, body.merchant, body.date, _checked(body))}


@router.post("/api/prices/remember")
def remember_prices(
    body: ReceiptItems,
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
) -> dict:
    prices.remember(conn, user, body.merchant, body.date, _checked(body))
    return {"saved": True}


@router.get("/api/prices")
def price_history(
    item: str = Query(min_length=1, max_length=80),
    user: CurrentUser = Depends(current_user),  # noqa: B008
    conn=Depends(get_conn),  # noqa: B008
) -> dict:
    return prices.compare(conn, user, item)
