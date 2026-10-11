"""Read endpoints. Identity comes only from the session cookie (`current_user`) or, for Clearday Home,
the household device token sent as `Authorization: Bearer` (`device_household_id`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from api import sky
from api.db import get_conn
from api.devices import device_household
from api.session import COOKIE_NAME, CurrentUser, current_user, session_member

router = APIRouter()


@router.get("/api/accounts")
def accounts(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return {"accounts": sky.list_accounts(conn, user.user_id)}


@router.get("/api/sky")
def get_sky(user: CurrentUser = Depends(current_user), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return sky.build_sky(conn, user)


def _bearer(request: Request) -> str | None:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def device_household_id(request: Request, conn=Depends(get_conn)) -> int:  # noqa: B008
    """The household of an active device token (Bearer), else 401."""
    household_id = device_household(conn, _bearer(request))
    if household_id is None:
        raise HTTPException(status_code=401, detail="Unknown or revoked device token")
    return household_id


def household_reader(request: Request, conn=Depends(get_conn)) -> int:  # noqa: B008
    """The household a member's session cookie or a device token may read, else 401."""
    if (token := _bearer(request)) is not None:
        household_id = device_household(conn, token)
    else:
        user = session_member(conn, request.cookies.get(COOKIE_NAME))
        household_id = user.household_id if user else None
    if household_id is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return household_id


@router.get("/api/household/status")
def household_status(household_id: int = Depends(household_reader), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return sky.household_status(conn, household_id)


@router.get("/api/device/summary")
def device_summary(household_id: int = Depends(device_household_id), conn=Depends(get_conn)) -> dict:  # noqa: B008
    return sky.device_summary(conn, household_id)
