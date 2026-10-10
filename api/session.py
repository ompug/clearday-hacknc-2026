"""Signed session cookie (stdlib hmac) and the `current_user` dependency.

Identity comes only from this cookie: handlers take `CurrentUser` from `current_user`, never a user or
household ID from the body, query or model output. The cookie holds `<user_id>.<issued_unix>.<sig>`,
where sig is HMAC-SHA256 over the first two parts with SESSION_SECRET. Every request also re-checks
that the user is still a current household member.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response

from api.config import get_settings
from api.db import get_conn

COOKIE_NAME = "clearday_session"
MAX_AGE_S = 7 * 24 * 3600


class SessionConfigError(RuntimeError):
    """SESSION_SECRET is missing or too short to sign with."""


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    display_name: str
    household_id: int
    household_name: str


def _secret() -> bytes:
    secret = get_settings().session_secret.get_secret_value()
    if len(secret) < 16:
        raise SessionConfigError("SESSION_SECRET must be set in api/.env (16+ characters)")
    return secret.encode()


def _sig(body: str) -> str:
    digest = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def sign(user_id: int, issued_at: int | None = None) -> str:
    body = f"{user_id}.{int(time.time()) if issued_at is None else issued_at}"
    return f"{body}.{_sig(body)}"


def verify(token: str | None, now: int | None = None) -> int | None:
    """The user ID in a valid, unexpired token, else None."""
    if not token or token.count(".") != 2:
        return None
    user_part, issued_part, sig = token.split(".")
    if not (user_part.isdigit() and issued_part.isdigit() and len(user_part) <= 18):
        return None
    if not hmac.compare_digest(sig, _sig(f"{user_part}.{issued_part}")):
        return None
    age = (int(time.time()) if now is None else now) - int(issued_part)
    if not 0 <= age <= MAX_AGE_S:
        return None
    return int(user_part)


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        COOKIE_NAME,
        sign(user_id),
        max_age=MAX_AGE_S,
        httponly=True,
        samesite="lax",
        secure=get_settings().session_cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")


MEMBER_SQL = """
SELECT u.id, u.display_name, h.id, h.name
FROM users u
JOIN household_members m ON m.user_id = u.id AND m.left_at IS NULL
JOIN households h ON h.id = m.household_id
WHERE u.id = %s
ORDER BY m.joined_at DESC
LIMIT 1
"""


def load_member(conn, user_id: int) -> CurrentUser | None:
    row = conn.execute(MEMBER_SQL, (user_id,)).fetchone()
    return CurrentUser(*row) if row else None


def current_user(request: Request, conn=Depends(get_conn)) -> CurrentUser:  # noqa: B008
    user_id = verify(request.cookies.get(COOKIE_NAME))
    user = load_member(conn, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user
