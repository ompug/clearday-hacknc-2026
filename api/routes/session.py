"""Persona-picker login (dev only), logout and /api/me. Paths match web/lib/api/http.ts."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from api import ids, realtime
from api.config import get_settings
from api.db import get_conn
from api.session import (
    COOKIE_NAME,
    CurrentUser,
    clear_session_cookie,
    current_user,
    load_member,
    revoke_session,
    set_session_cookie,
)

router = APIRouter()

# Non-financial blurbs for the demo picker, keyed by display name. Anyone else gets the fallback.
TAGLINES = {
    "Maya": "Night-shift nurse, plans everything",
    "Jake": "Grad student, pays rent first",
    "Priya": "Designer, does the grocery runs",
}
FALLBACK_TAGLINE = "Roommate"

PERSONAS_SQL = """
SELECT DISTINCT u.id, u.display_name
FROM users u JOIN household_members m ON m.user_id = u.id AND m.left_at IS NULL
ORDER BY u.id
"""


def is_loopback(host: str | None) -> bool:
    """True for 127.0.0.0/8, ::1 and IPv4-mapped loopback. `host` is the TCP peer from the ASGI server;
    forwarded headers are never consulted here."""
    try:
        ip = ipaddress.ip_address(host or "")
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return ip.is_loopback or bool(mapped and mapped.is_loopback)


def require_dev_routes(request: Request) -> None:
    """The persona picker signs anyone in as anyone, so it only answers on this computer."""
    if not get_settings().enable_dev_routes:
        raise HTTPException(status_code=404, detail="Not found")
    if not is_loopback(request.client.host if request.client else None):
        raise HTTPException(status_code=403, detail="Persona login works only on this computer")


def me_payload(user: CurrentUser) -> dict:
    return {
        "user": {"user_id": ids.encode(ids.USER, user.user_id), "display_name": user.display_name},
        "household": {
            "household_id": ids.encode(ids.HOUSEHOLD, user.household_id),
            "name": user.household_name,
        },
    }


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(max_length=40)


@router.get("/api/dev/personas", dependencies=[Depends(require_dev_routes)])
def list_personas(conn=Depends(get_conn)) -> list[dict]:  # noqa: B008
    return [
        {
            "user_id": ids.encode(ids.USER, pk),
            "display_name": name,
            "tagline": TAGLINES.get(name, FALLBACK_TAGLINE),
        }
        for pk, name in conn.execute(PERSONAS_SQL).fetchall()
    ]


@router.post("/api/dev/login", dependencies=[Depends(require_dev_routes)])
def login_as_persona(body: LoginRequest, response: Response, conn=Depends(get_conn)) -> dict:  # noqa: B008
    # The one place a user ID arrives in a body: the dev persona picker, which IS the login.
    pk = ids.decode(ids.USER, body.user_id)
    user = load_member(conn, pk) if pk is not None else None
    if user is None:
        raise HTTPException(status_code=404, detail="Unknown persona")
    set_session_cookie(response, user.user_id)
    return me_payload(user)


@router.post("/api/session/logout", status_code=204)
async def logout(request: Request, response: Response, conn=Depends(get_conn)) -> Response:  # noqa: B008
    """End the session server-side (a copied cookie stops working) and drop its sockets."""
    token = request.cookies.get(COOKIE_NAME)
    await run_in_threadpool(revoke_session, conn, token)
    await realtime.disconnect_session(token)
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/api/me")
def me(user: CurrentUser = Depends(current_user)) -> dict:  # noqa: B008
    return me_payload(user)
