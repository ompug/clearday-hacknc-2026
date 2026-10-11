"""Session security: persona login only from this computer, logout ends the session server-side and
drops that session's sockets, and connected sockets are re-checked against the session."""

from __future__ import annotations

import asyncio
import itertools

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api import realtime
from api.config import get_settings
from api.db import connect
from api.main import app
from api.migrate import migrate
from api.session import COOKIE_NAME

LOOPBACK = ("127.0.0.1", 50000)
_eio_ids = itertools.count(1)


@pytest.fixture
def flat(scratch_dsn, monkeypatch):
    """A migrated scratch DB with a two-person household; the whole app (HTTP and sockets) uses it."""
    with connect(scratch_dsn) as conn:
        migrate(conn)
        hh = conn.execute("INSERT INTO households (name) VALUES ('Flat') RETURNING id").fetchone()[0]
        users = {}
        for name in ("Ana", "Ben"):
            uid = conn.execute(
                "INSERT INTO users (display_name) VALUES (%s) RETURNING id", (name,)
            ).fetchone()[0]
            conn.execute("INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)", (hh, uid))
            users[name] = uid
    monkeypatch.setattr(get_settings(), "db_target", "local")
    monkeypatch.setattr(get_settings(), "database_url_local", SecretStr(scratch_dsn))
    return {"dsn": scratch_dsn, "hh": hh, "users": users}


def login(client: TestClient, uid: int):
    return client.post("/api/dev/login", json={"user_id": f"u_{uid}"})


@pytest.fixture
def sockets(monkeypatch):
    """Registers sockets with the real Socket.IO manager and records server-side disconnects."""
    dropped: list[str] = []

    async def record_disconnect(sid, namespace=None, ignore_queue=False):
        dropped.append(sid)
        await realtime.on_disconnect(sid)
        realtime.sio.manager.basic_disconnect(sid, "/")

    monkeypatch.setattr(realtime.sio, "disconnect", record_disconnect)
    opened: list[str] = []

    async def connect_socket(cookie: str) -> str:
        sid = await realtime.sio.manager.connect(f"eio-{next(_eio_ids)}", "/")
        await realtime.on_connect(sid, {"HTTP_COOKIE": f"{COOKIE_NAME}={cookie}"})
        return sid

    def open_socket(cookie: str) -> str:
        sid = asyncio.run(connect_socket(cookie))
        opened.append(sid)
        return sid

    yield open_socket, dropped
    for sid in opened:
        if sid not in dropped:
            asyncio.run(realtime.on_disconnect(sid))
            realtime.sio.manager.basic_disconnect(sid, "/")


# ---- persona login from loopback only ----------------------------------------------------------------


@pytest.mark.parametrize("host", ["192.168.1.50", "10.0.0.7", "2001:db8::5"])
def test_persona_login_from_a_non_loopback_client_is_rejected(flat, host):
    with TestClient(app, client=(host, 50000)) as client:
        res = login(client, flat["users"]["Ana"])
        assert res.status_code == 403
        assert "set-cookie" not in res.headers
        assert client.get("/api/dev/personas").status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_persona_login_from_loopback_works(flat, host):
    with TestClient(app, client=(host, 50000)) as client:
        assert login(client, flat["users"]["Ana"]).status_code == 200
        assert client.get("/api/me").json()["user"]["display_name"] == "Ana"


# ---- logout ends the session server-side --------------------------------------------------------------


def test_a_copied_cookie_stops_working_after_logout(flat):
    with TestClient(app, client=LOOPBACK) as client:
        login(client, flat["users"]["Ana"])
        copied = client.cookies.get(COOKIE_NAME)
        assert client.post("/api/session/logout").status_code == 204
    with TestClient(app, client=LOOPBACK, cookies={COOKIE_NAME: copied}) as thief:
        assert thief.get("/api/me").status_code == 401
    assert realtime.resolve_rooms({"HTTP_COOKIE": f"{COOKIE_NAME}={copied}"}, None) is None


def test_logout_ends_only_that_session(flat):
    with TestClient(app, client=LOOPBACK) as laptop, TestClient(app, client=LOOPBACK) as phone:
        login(laptop, flat["users"]["Ana"])
        login(phone, flat["users"]["Ana"])
        assert laptop.cookies.get(COOKIE_NAME) != phone.cookies.get(COOKIE_NAME)
        laptop.post("/api/session/logout")
        assert phone.get("/api/me").status_code == 200


def test_logout_disconnects_that_sessions_sockets(flat, sockets):
    open_socket, dropped = sockets
    with TestClient(app, client=LOOPBACK) as ana, TestClient(app, client=LOOPBACK) as ana_phone:
        login(ana, flat["users"]["Ana"])
        login(ana_phone, flat["users"]["Ana"])
        mine = open_socket(ana.cookies.get(COOKIE_NAME))
        other_session = open_socket(ana_phone.cookies.get(COOKIE_NAME))
        ana.post("/api/session/logout")
    assert dropped == [mine]
    assert other_session not in dropped


# ---- sockets re-check the session ---------------------------------------------------------------------


def test_recheck_drops_sockets_whose_member_left_and_keeps_the_rest(flat, sockets):
    open_socket, dropped = sockets
    with TestClient(app, client=LOOPBACK) as ana, TestClient(app, client=LOOPBACK) as ben:
        login(ana, flat["users"]["Ana"])
        login(ben, flat["users"]["Ben"])
        ana_sid = open_socket(ana.cookies.get(COOKIE_NAME))
        ben_sid = open_socket(ben.cookies.get(COOKIE_NAME))
    with connect(flat["dsn"]) as conn:
        conn.execute(
            "UPDATE household_members SET left_at = now() WHERE user_id = %s", (flat["users"]["Ben"],)
        )
    asyncio.run(realtime.recheck_sockets())
    assert dropped == [ben_sid]
    assert ana_sid not in dropped


def test_the_api_rechecks_sockets_periodically(monkeypatch):
    import time  # noqa: PLC0415

    calls = []

    async def counting_recheck(dsn=None):
        calls.append(1)
        return 0

    monkeypatch.setattr(realtime, "recheck_sockets", counting_recheck)
    monkeypatch.setattr(get_settings(), "socket_recheck_interval_s", 0.05)
    with TestClient(app):
        deadline = time.monotonic() + 3
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
    assert len(calls) >= 2
