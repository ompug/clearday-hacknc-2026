"""POST /api/expenses: create a shared expense with an even or custom split (ledger only).

Seam: the HTTP endpoint (identity from the cookie, idempotency, events) plus /api/sky and
/api/household/members as the read side. Events are captured at `emit_all`."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api import sky
from api.db import connect, get_conn
from api.main import app, fastapi_app
from api.migrate import migrate
from api.routes import expenses as expense_routes
from api.routes.payments import get_mirror_runner


@pytest.fixture
def client(scratch_dsn, monkeypatch):
    """Ana, Ben and Cal share a flat; Zed lives elsewhere."""
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        hh = conn.execute("INSERT INTO households (name) VALUES ('Test Flat') RETURNING id").fetchone()[0]
        other = conn.execute("INSERT INTO households (name) VALUES ('Elsewhere') RETURNING id").fetchone()[0]
        users = {}
        for name, home in [("Ana", hh), ("Ben", hh), ("Cal", hh), ("Zed", other)]:
            uid = conn.execute(
                "INSERT INTO users (display_name) VALUES (%s) RETURNING id", (name,)
            ).fetchone()[0]
            conn.execute("INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)", (home, uid))
            conn.execute(
                """INSERT INTO accounts (user_id, type, nickname, last4, opening_balance_cents)
                   VALUES (%s, 'checking', 'Everyday Checking', '1234', 100000)""",
                (uid,),
            )
            users[name] = uid
        conn.commit()

    def scratch_conn():
        with connect(scratch_dsn) as conn:
            yield conn

    events: list = []

    async def capture(batch):
        events.extend(batch)

    monkeypatch.setattr(expense_routes, "emit_all", capture)
    sky.invalidate_forecasts()
    fastapi_app.dependency_overrides[get_conn] = scratch_conn
    fastapi_app.dependency_overrides[get_mirror_runner] = lambda: lambda payment_id: "pending"  # no Nessie
    try:
        with TestClient(app) as c:
            c.users = users
            c.events = events
            c.dsn = scratch_dsn
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_conn, None)
        fastapi_app.dependency_overrides.pop(get_mirror_runner, None)
        sky.invalidate_forecasts()


def login(client, name: str) -> None:
    res = client.post("/api/dev/login", json={"user_id": f"u_{client.users[name]}"})
    assert res.status_code == 200, res.text


def uid(client, name: str) -> str:
    return f"u_{client.users[name]}"


def create(client, *, key=None, label="Pizza night", total=1000, method="even", participants=None, **extra):
    body = {
        "idempotency_key": key or str(uuid.uuid4()),
        "label": label,
        "total_cents": total,
        "split_method": method,
        "participants": participants
        if participants is not None
        else [{"user_id": uid(client, n)} for n in ("Ana", "Ben", "Cal")],
        **extra,
    }
    return client.post("/api/expenses", json=body)


def test_even_split_of_ten_dollars_three_ways_reconciles_to_the_cent(client):
    login(client, "Ana")
    res = create(client, total=1000)
    assert res.status_code == 200, res.text
    body = res.json()
    by_user = {s["user_id"]: s for s in body["shares"]}
    # Largest remainder, ties by user ID: Ana has the lowest ID and gets the extra cent.
    assert [by_user[uid(client, n)]["amount_cents"] for n in ("Ana", "Ben", "Cal")] == [334, 333, 333]
    assert by_user[uid(client, "Ana")]["status"] == "paid"  # the payer's own share
    assert by_user[uid(client, "Ben")]["status"] == "open"
    assert body["payer_id"] == uid(client, "Ana")
    assert body["total_cents"] == 1000
    assert body["split_method"] == "even"


def count(client, sql: str) -> int:
    with connect(client.dsn) as conn:
        return conn.execute(sql).fetchone()[0]


def test_replayed_key_creates_one_expense_and_returns_the_same_result(client):
    login(client, "Ana")
    first = create(client, key="replay-key-0001")
    second = create(client, key="replay-key-0001", label="Something else", total=5000)
    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert count(client, "SELECT COUNT(*) FROM expenses") == 1
    assert count(client, "SELECT COUNT(*) FROM shares") == 3
    assert count(client, "SELECT COUNT(*) FROM feed_events") == 1


def test_events_are_amount_free_and_the_feed_never_reaches_the_device(client):
    login(client, "Ana")
    res = create(client, label="Concert tickets", total=98765)
    assert res.status_code == 200
    amounts = {str(s["amount_cents"]) for s in res.json()["shares"]} | {"98765", "987.65", "987"}

    events = {e.event: e for e in client.events}
    assert set(events) == {"share.updated", "feed.created"}
    assert [e.payload for e in client.events if e.event == "feed.created"] == [
        {"type": "expense_created", "actor_display_name": "Ana", "subject_label": "Concert tickets"}
    ]
    for e in client.events:
        assert not any("cents" in k or "amount" in k for k in e.payload), e
        assert not any(a in str(v) for a in amounts for v in e.payload.values()), e
    assert all(not r.endswith(":device") for r in events["feed.created"].rooms)
    updates = [e for e in client.events if e.event == "share.updated"]
    assert len(updates) == 3 and all(any(r.endswith(":device") for r in e.rooms) for e in updates)

    with connect(client.dsn) as conn:
        cols = [d.name for d in conn.execute("SELECT * FROM feed_events").description]
        row = conn.execute("SELECT * FROM feed_events").fetchone()
    assert not any("cents" in c or "amount" in c for c in cols)
    assert not any(a in str(v) for a in amounts for v in row)


def test_new_expense_appears_in_each_participants_sky(client):
    login(client, "Ana")
    expense_id = create(client, label="Pizza night", total=1000).json()["expense_id"]
    login(client, "Ben")
    bubble = next(b for b in client.get("/api/sky").json()["bubbles"] if b["bubble_id"] == expense_id)
    assert bubble["kind"] == "shared"
    assert bubble["label"] == "Pizza night"
    assert bubble["your_share_cents"] == 333
    assert bubble["total_cents"] == 1000
    assert bubble["status"] == "open"
    assert bubble["paid_count"] == 1 and bubble["participant_count"] == 3
    assert bubble["fill_fraction"] == pytest.approx(0.334)


def test_custom_split_uses_the_given_cents(client):
    login(client, "Ana")
    parts = [
        {"user_id": uid(client, "Ben"), "amount_cents": 700},
        {"user_id": uid(client, "Cal"), "amount_cents": 301},
    ]
    res = create(client, total=1001, method="custom", participants=parts, due_date="2026-10-20")
    assert res.status_code == 200, res.text
    body = res.json()
    assert {s["user_id"]: (s["amount_cents"], s["status"]) for s in body["shares"]} == {
        uid(client, "Ben"): (700, "open"),
        uid(client, "Cal"): (301, "open"),
    }
    assert body["due_date"] == "2026-10-20"


@pytest.mark.parametrize(
    ("total", "method", "parts", "why"),
    [
        (1000, "custom", [("Ben", 500), ("Cal", 400)], "custom amounts short of the total"),
        (1000, "custom", [("Ben", 500), ("Cal", None)], "custom amount missing"),
        (1000, "even", [("Ben", None), ("Zed", None)], "someone outside the household"),
        (1000, "even", [("Ben", None), ("Ben", None)], "duplicate participant"),
        (1000, "even", [("Ana", None)], "only the payer"),
        (0, "even", [("Ben", None)], "zero total"),
        (1000, "itemized", [("Ben", None)], "unsupported method"),
    ],
)
def test_invalid_requests_are_rejected_and_write_nothing(client, total, method, parts, why):
    login(client, "Ana")
    participants = [
        {"user_id": uid(client, n), **({} if c is None else {"amount_cents": c})} for n, c in parts
    ]
    res = create(client, total=total, method=method, participants=participants)
    assert res.status_code == 422, why
    assert count(client, "SELECT COUNT(*) FROM expenses") == 0


def test_float_cents_are_rejected(client):
    login(client, "Ana")
    assert create(client, total=10.5).status_code == 422


def test_payer_comes_from_the_cookie_not_the_body(client):
    login(client, "Ben")
    res = create(client, payer_id=uid(client, "Ana"), user_id=uid(client, "Ana"))
    assert res.status_code == 200
    assert res.json()["payer_id"] == uid(client, "Ben")


def test_requires_a_session(client):
    assert create(client).status_code == 401
    assert client.get("/api/household/members").status_code == 401


def test_key_reused_by_another_user_is_rejected(client):
    login(client, "Ana")
    assert create(client, key="shared-key-0001").status_code == 200
    login(client, "Ben")
    assert create(client, key="shared-key-0001").status_code == 409


def test_household_members_lists_only_my_household(client):
    login(client, "Ana")
    res = client.get("/api/household/members")
    assert res.status_code == 200
    assert res.json() == {
        "members": [{"user_id": uid(client, n), "display_name": n} for n in ("Ana", "Ben", "Cal")]
    }


def test_amounts_are_frozen_once_paid(client):
    """Ledger rule 10: no silent edits after a payment touches the expense."""
    login(client, "Ana")
    body = create(client, total=1000).json()
    login(client, "Ben")
    ben_share = next(s for s in body["shares"] if s["user_id"] == uid(client, "Ben"))
    acct = client.get("/api/accounts").json()["accounts"][0]["account_id"]
    paid = client.post(
        "/api/payments",
        json={"idempotency_key": str(uuid.uuid4()), "bubble_id": body["expense_id"], "account_id": acct,
              "amount_cents": ben_share["amount_cents"]},
    )  # fmt: skip
    assert paid.status_code == 200, paid.text
    with connect(client.dsn) as conn:
        with pytest.raises(Exception, match="adjustment"):
            conn.execute(
                "UPDATE shares SET amount_cents = 1 WHERE id = %s", (int(ben_share["share_id"][3:]),)
            )
        conn.rollback()
        with pytest.raises(Exception, match="adjustment"):
            conn.execute("UPDATE expenses SET total_cents = 1 WHERE id = %s", (int(body["expense_id"][4:]),))
