"""Clearday Home's HTTP seam: a hashed household device token (`api.devices.issue_token`) read through
`GET /api/household/status` and `GET /api/device/summary` with `Authorization: Bearer`. Payloads are
household-level counts and bill labels only; the fixture salts names and amounts so a leak is visible."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from api import devices, realtime, sky
from api.db import connect, get_conn
from api.main import app, fastapi_app
from api.migrate import migrate
from api.session import COOKIE_NAME, sign

# Salted values: none of these may ever appear in a device payload.
NAMES = ["Zelphira", "Quillon", "Marvex"]
TOTAL = 98765
SPLIT = [32923, 32921, 32921]
SALT = [*NAMES, str(TOTAL), *map(str, SPLIT), "987.65", "329.2", "Vexcorp Utilities", "4242"]


@pytest.fixture
def device(scratch_dsn):
    today = sky.today()
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        hh = conn.execute("INSERT INTO households (name) VALUES ('Salt Flat') RETURNING id").fetchone()[0]
        other = conn.execute("INSERT INTO households (name) VALUES ('Next Door') RETURNING id").fetchone()[0]
        users = []
        for name in NAMES:
            uid = conn.execute(
                "INSERT INTO users (display_name) VALUES (%s) RETURNING id", (name,)
            ).fetchone()[0]
            conn.execute("INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)", (hh, uid))
            conn.execute(
                """INSERT INTO accounts (user_id, type, nickname, last4, opening_balance_cents)
                   VALUES (%s, 'checking', 'Everyday Checking', '4242', 500000)""",
                (uid,),
            )
            users.append(uid)
        exp = conn.execute(
            """INSERT INTO expenses (household_id, payer_id, label, total_cents, split_method, due_on)
               VALUES (%s, %s, 'Electric', %s, 'even', %s) RETURNING id""",
            (hh, users[0], TOTAL, today + dt.timedelta(days=2)),
        ).fetchone()[0]
        for uid, cents, status in zip(users, SPLIT, ["paid", "open", "open"], strict=True):
            conn.execute(
                "INSERT INTO shares (expense_id, user_id, amount_cents, status) VALUES (%s, %s, %s, %s)",
                (exp, uid, cents, status),
            )
        token = devices.issue_token(conn, hh)
        other_token = devices.issue_token(conn, other)
        conn.commit()

    def scratch_conn():
        with connect(scratch_dsn) as conn:
            yield conn

    sky.invalidate_forecasts()
    fastapi_app.dependency_overrides[get_conn] = scratch_conn
    try:
        with TestClient(app) as c:
            c.dsn, c.hh, c.users, c.token, c.other_token = scratch_dsn, hh, users, token, other_token
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_conn, None)
        sky.invalidate_forecasts()


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def assert_no_salt(body: dict) -> None:
    text = json.dumps(body)
    for salt in SALT:
        assert salt not in text, salt
    assert not any("cents" in key or "name" in key for key in _keys(body))


def _keys(obj) -> list[str]:
    if isinstance(obj, dict):
        return [*obj, *(k for v in obj.values() for k in _keys(v))]
    if isinstance(obj, list):
        return [k for v in obj for k in _keys(v)]
    return []


def test_token_is_stored_only_as_its_hash(device):
    with connect(device.dsn) as conn:
        hashes = [r[0] for r in conn.execute("SELECT token_hash FROM devices ORDER BY id").fetchall()]
    assert hashes == [
        realtime.hash_device_token(device.token),
        realtime.hash_device_token(device.other_token),
    ]
    assert device.token not in hashes and len(device.token) >= 32


def test_household_status_with_device_token_is_counts_only(device):
    res = device.get("/api/household/status", headers=bearer(device.token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {"weather": body["weather"], "open_bills": 1, "due_soon_bills": 1, "shares_paid": 1,
                    "shares_total": 3}  # fmt: skip
    assert body["weather"] in {"clear", "tight"}
    assert_no_salt(body)


def test_device_summary_is_household_level_with_no_amounts_or_names(device):
    res = device.get("/api/device/summary", headers=bearer(device.token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body == {
        "weather": body["weather"],
        "open_bills": 1,
        "bills": [{"label": "Shared bill", "shares_paid": 1, "shares_total": 3, "due_in_days": 2}],
    }
    assert_no_salt(body)


def test_device_token_sees_only_its_own_household(device):
    body = device.get("/api/device/summary", headers=bearer(device.other_token)).json()
    assert body["open_bills"] == 0 and body["bills"] == []


@pytest.mark.parametrize("path", ["/api/household/status", "/api/device/summary"])
@pytest.mark.parametrize(
    "header", [None, "Bearer " + "x" * 43, "Bearer ", "Basic abc", "token-without-scheme"]
)
def test_missing_or_unknown_token_is_rejected(device, path, header):
    res = device.get(path, headers={"Authorization": header} if header else {})
    assert res.status_code == 401


@pytest.mark.parametrize("path", ["/api/household/status", "/api/device/summary"])
def test_revoked_token_is_rejected(device, path):
    with connect(device.dsn) as conn:
        conn.execute("UPDATE devices SET revoked_at = now()")
        conn.commit()
    assert device.get(path, headers=bearer(device.token)).status_code == 401


def test_device_summary_needs_the_device_token_not_a_member_cookie(device):
    device.cookies.set(COOKIE_NAME, sign(device.users[1]))
    assert device.get("/api/device/summary").status_code == 401
    # The cookie still reads the status, as before.
    assert device.get("/api/household/status").status_code == 200


def test_device_token_cannot_read_member_endpoints(device):
    for path in ["/api/sky", "/api/accounts", "/api/me"]:
        assert device.get(path, headers=bearer(device.token)).status_code == 401


def test_socket_with_issued_token_joins_the_household_device_room(device):
    assert realtime.resolve_rooms({}, {"token": device.token}, device.dsn) == [f"hh:{device.hh}:device"]


def test_issue_device_token_script_prints_a_working_token_once_and_stores_its_hash(device, capsys):
    from scripts import issue_device_token  # noqa: PLC0415

    assert issue_device_token.main(["--household-id", str(device.hh)], dsn=device.dsn) == 0
    out = capsys.readouterr().out
    [token] = [
        line.split("=", 1)[1] for line in out.splitlines() if line.startswith("CLEARDAY_DEVICE_TOKEN=")
    ]
    with connect(device.dsn) as conn:
        stored = [r[0] for r in conn.execute("SELECT token_hash FROM devices").fetchall()]
    assert realtime.hash_device_token(token) in stored and token not in stored
    assert device.get("/api/device/summary", headers=bearer(token)).status_code == 200


def test_issue_device_token_script_needs_a_household_when_there_are_several(device, capsys):
    from scripts import issue_device_token  # noqa: PLC0415

    assert issue_device_token.main([], dsn=device.dsn) == 2
    assert "CLEARDAY_DEVICE_TOKEN" not in capsys.readouterr().out


def test_device_summary_never_carries_user_typed_labels(device):
    """Expense labels are free text ("Priya owes $40", a merchant). The device speaks them aloud, so it
    gets a generic server-derived category instead."""
    salted = "Maya owes Priya $40.25 for Jake's birthday"
    with connect(device.dsn) as conn:
        conn.execute("UPDATE expenses SET label = %s", (salted,))
        conn.commit()
    body = device.get("/api/device/summary", headers=bearer(device.token)).json()
    assert [b["label"] for b in body["bills"]] == ["Shared bill"]
    for fragment in ("Maya", "Priya", "Jake", "40", "birthday"):
        assert fragment not in json.dumps(body)
