"""Phase 1 read endpoints. Identity comes only from the session cookie (`current_user`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import sky
from api.db import get_conn
from api.session import CurrentUser, current_user

router = APIRouter()


@router.get("/api/accounts")
def accounts(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"accounts": sky.list_accounts(conn, user.user_id)}


@router.get("/api/sky")
def get_sky(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return sky.build_sky(conn, user)


@router.get("/api/household/status")
def household_status(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    # TODO(phase 2): also accept the Clearday Home device token once the devices table lands.
    return sky.household_status(conn, user)
