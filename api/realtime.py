"""Socket.IO: authenticated connections and room fan-out.

A browser connects with the session cookie (sent by socket.io-client `withCredentials`) and joins its
household room and its private user room. Clearday Home connects with `auth={"token": ...}` and joins
only the household's device room, which never receives names (no `feed.created`). Anything else is
refused. Payloads never carry amounts.
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
from api.session import COOKIE_NAME, load_member, verify

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


def _cookie_user_id(environ: dict) -> int | None:
    jar = SimpleCookie()
    try:
        jar.load(environ.get("HTTP_COOKIE", ""))
    except Exception:  # malformed header: treat as no cookie
        return None
    morsel = jar.get(COOKIE_NAME)
    return verify(morsel.value) if morsel else None


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
        user_id = _cookie_user_id(environ)
        user = load_member(conn, user_id) if user_id is not None else None
        if user is None:
            return None
        return [household_room(user.household_id), user_room(user.user_id)]


async def _on_connect(sid, environ, auth=None):
    try:
        rooms = await asyncio.to_thread(resolve_rooms, environ, auth)
    except Exception as exc:  # DB down or bad config: refuse rather than crash the handshake
        log.warning("socket connect check failed (%s)", type(exc).__name__)
        rooms = None
    if not rooms:
        raise socketio.exceptions.ConnectionRefusedError("unauthorized")
    for room in rooms:
        await sio.enter_room(sid, room)


sio.on("connect", _on_connect)


async def emit_all(events: list[Emit]) -> None:
    for e in events:
        for room in e.rooms:
            await sio.emit(e.event, e.payload, room=room)
