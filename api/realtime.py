"""Socket.IO: authenticated connections and room fan-out.

A browser connects with the session cookie (sent by socket.io-client `withCredentials`) and joins its
household room and its private user room. Clearday Home connects with `auth={"token": ...}` and joins
only the household's device room, which never receives names (no `feed.created`). Anything else is
refused. Payloads never carry amounts. Logout disconnects that session's sockets, and
`recheck_sockets` (run periodically by the API) drops any socket whose session or device token no
longer resolves to the same rooms (logged out, expired, left the household, revoked).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from http.cookies import SimpleCookie

import socketio

from api.config import get_settings
from api.db import connect
from api.session import COOKIE_NAME, session_member

log = logging.getLogger("clearday.realtime")

sio = socketio.AsyncServer(
    async_mode="asgi", cors_allowed_origins=get_settings().web_origins, cors_credentials=True
)


def household_room(household_id: int) -> str:
    return f"hh:{household_id}"


def device_room(household_id: int) -> str:
    return f"hh:{household_id}:device"


def user_room(user_id: int) -> str:
    return f"user:{user_id}"


@dataclass(frozen=True)
class Emit:
    event: str
    payload: dict
    rooms: tuple[str, ...]


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _cookie_token(environ: dict) -> str | None:
    jar = SimpleCookie()
    try:
        jar.load(environ.get("HTTP_COOKIE", ""))
    except Exception:  # malformed header: treat as no cookie
        return None
    morsel = jar.get(COOKIE_NAME)
    return morsel.value if morsel else None


def resolve_rooms(environ: dict, auth: object, dsn: str | None = None) -> list[str] | None:
    """The rooms this connection may join, or None to refuse it. Runs DB lookups (call off-loop)."""
    token = auth.get("token") if isinstance(auth, dict) else None
    with connect(dsn) as conn:
        if isinstance(token, str) and 16 <= len(token) <= 256:
            row = conn.execute(
                "SELECT household_id FROM devices WHERE token_hash = %s AND revoked_at IS NULL",
                (hash_device_token(token),),
            ).fetchone()
            return [device_room(row[0])] if row else None
        user = session_member(conn, _cookie_token(environ))
        if user is None:
            return None
        return [household_room(user.household_id), user_room(user.user_id)]


@dataclass(frozen=True)
class _Credentials:
    """What a socket connected with, kept so it can be re-checked and found again at logout."""

    environ: dict
    auth: object
    rooms: tuple[str, ...]
    cookie: str | None


# sid -> credentials, for this process's connected sockets.
_connected: dict[str, _Credentials] = {}


async def on_connect(sid, environ, auth=None):
    try:
        rooms = await asyncio.to_thread(resolve_rooms, environ, auth)
    except Exception as exc:  # DB down or bad config: refuse rather than crash the handshake
        log.warning("socket connect check failed (%s)", type(exc).__name__)
        rooms = None
    if not rooms:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    cookie_only = {"HTTP_COOKIE": environ.get("HTTP_COOKIE", "")}
    token = None if isinstance(auth, dict) and auth.get("token") else _cookie_token(environ)
    _connected[sid] = _Credentials(cookie_only, auth, tuple(rooms), token)
    for room in rooms:
        await sio.enter_room(sid, room)


async def on_disconnect(sid, *_reason):
    _connected.pop(sid, None)


sio.on("connect", on_connect)
sio.on("disconnect", on_disconnect)


async def disconnect_session(cookie: str | None) -> int:
    """Disconnect every socket that connected with this session cookie (logout)."""
    sids = [sid for sid, c in list(_connected.items()) if cookie and c.cookie == cookie]
    for sid in sids:
        await sio.disconnect(sid)
    return len(sids)


def _stale(creds: list[tuple[str, _Credentials]], dsn: str | None) -> list[str]:
    return [sid for sid, c in creds if tuple(resolve_rooms(c.environ, c.auth, dsn) or ()) != c.rooms]


async def recheck_sockets(dsn: str | None = None) -> int:
    """Disconnect sockets whose credentials no longer give the rooms they joined with."""
    creds = list(_connected.items())
    if not creds:
        return 0
    try:
        stale = await asyncio.to_thread(_stale, creds, dsn)
    except Exception as exc:  # DB down: keep sockets until the next check
        log.warning("socket re-check failed (%s)", type(exc).__name__)
        return 0
    for sid in stale:
        await sio.disconnect(sid)
    return len(stale)


async def emit_all(events: list[Emit]) -> None:
    for e in events:
        for room in e.rooms:
            await sio.emit(e.event, e.payload, room=room)
