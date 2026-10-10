"""Ledger and pop-to-pay, tested at two seams: `api.ledger.record_share_payment` (allocation, credit,
idempotency) and `POST /api/payments` (identity from the cookie, replay, Nessie mirror, rounding)."""

from __future__ import annotations

import datetime as dt

import pytest

from api import ledger
from api.db import connect
from api.migrate import migrate

TODAY = dt.date(2026, 10, 10)


@pytest.fixture
def household(scratch_dsn):
    """Ana pays the household bills; Ben and Cal owe her shares of Electric (older) and Rent."""
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        hh = conn.execute("INSERT INTO households (name) VALUES ('Test Flat') RETURNING id").fetchone()[0]
        users = {}
        for name in ["Ana", "Ben", "Cal"]:
            uid = conn.execute(
                "INSERT INTO users (display_name) VALUES (%s) RETURNING id", (name,)
            ).fetchone()[0]
            conn.execute("INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)", (hh, uid))
            users[name] = uid
        accounts = {}
        for i, (name, nessie) in enumerate([("Ana", "nes-acct-ana"), ("Ben", "nes-acct-ben"), ("Cal", None)]):
            accounts[name] = conn.execute(
                """INSERT INTO accounts
                       (user_id, nessie_account_id, type, nickname, last4, opening_balance_cents)
                   VALUES (%s, %s, 'checking', 'Everyday Checking', %s, 100000) RETURNING id""",
                (users[name], nessie, f"000{i}"),
            ).fetchone()[0]
        expenses, shares = {}, {}
        for label, total, split_cents, due in [
            ("Electric", 12600, [4200, 4200, 4200], TODAY + dt.timedelta(days=1)),
            ("Rent", 10000, [3334, 3333, 3333], TODAY + dt.timedelta(days=2)),
        ]:
            exp = conn.execute(
                """INSERT INTO expenses (household_id, payer_id, label, total_cents, split_method, due_on)
                   VALUES (%s, %s, %s, %s, 'even', %s) RETURNING id""",
                (hh, users["Ana"], label, total, due),
            ).fetchone()[0]
            expenses[label] = exp
            for name, cents in zip(["Ana", "Ben", "Cal"], split_cents, strict=True):
                shares[(label, name)] = conn.execute(
                    "INSERT INTO shares (expense_id, user_id, amount_cents, status) VALUES (%s, %s, %s, %s)"
                    " RETURNING id",
                    (exp, users[name], cents, "paid" if name == "Ana" else "open"),
                ).fetchone()[0]
        conn.commit()
    return {"dsn": scratch_dsn, "hh": hh, "users": users, "accounts": accounts, "expenses": expenses,
            "shares": shares}  # fmt: skip


def share_state(dsn, share_id):
    with connect(dsn) as conn:
        return conn.execute(
            """SELECT s.status, COALESCE(SUM(a.amount_cents), 0)::BIGINT
               FROM shares s LEFT JOIN allocations a ON a.share_id = s.id
               WHERE s.id = %s GROUP BY s.status""",
            (share_id,),
        ).fetchone()


def pay(h, payer, amount, key, picked=()):
    with connect(h["dsn"]) as conn:
        return ledger.record_share_payment(
            conn,
            payer_id=h["users"][payer],
            payee_id=h["users"]["Ana"],
            account_id=h["accounts"][payer],
            amount_cents=amount,
            idempotency_key=key,
            picked_share_ids=picked,
        )


# ---- ledger seam -------------------------------------------------------------------------------


def test_partial_payment_goes_to_oldest_share_and_leaves_it_partial(household):
    h = household
    result = pay(h, "Ben", 2000, "key-partial-0001")
    assert result.allocations == [{"share_id": h["shares"][("Electric", "Ben")], "amount_cents": 2000}]
    assert result.credit_cents == 0
    assert share_state(h["dsn"], h["shares"][("Electric", "Ben")]) == ("partial", 2000)
    assert share_state(h["dsn"], h["shares"][("Rent", "Ben")]) == ("open", 0)


def test_overpayment_covers_all_shares_oldest_first_and_the_rest_is_credit(household):
    h = household
    result = pay(h, "Ben", 8000, "key-over-00001")  # owes 4200 + 3333 = 7533
    assert result.allocations == [
        {"share_id": h["shares"][("Electric", "Ben")], "amount_cents": 4200},
        {"share_id": h["shares"][("Rent", "Ben")], "amount_cents": 3333},
    ]
    assert result.credit_cents == 467
    assert share_state(h["dsn"], h["shares"][("Electric", "Ben")]) == ("paid", 4200)
    assert share_state(h["dsn"], h["shares"][("Rent", "Ben")]) == ("paid", 3333)
    with connect(h["dsn"]) as conn:
        credit = conn.execute("SELECT amount_cents FROM allocations WHERE share_id IS NULL").fetchall()
    assert credit == [(467,)]


def test_picked_share_is_paid_before_older_ones(household):
    h = household
    result = pay(h, "Ben", 3333, "key-picked-001", picked=[h["shares"][("Rent", "Ben")]])
    assert result.allocations == [{"share_id": h["shares"][("Rent", "Ben")], "amount_cents": 3333}]
    assert share_state(h["dsn"], h["shares"][("Electric", "Ben")]) == ("open", 0)


def test_replayed_key_returns_the_original_payment_and_writes_nothing(household):
    h = household
    first = pay(h, "Ben", 2000, "key-replay-001")
    again = pay(h, "Ben", 2000, "key-replay-001")
    assert again.replay and again.payment_id == first.payment_id
    assert again.allocations == first.allocations
    assert share_state(h["dsn"], h["shares"][("Electric", "Ben")]) == ("partial", 2000)
    with connect(h["dsn"]) as conn:
        assert conn.execute("SELECT count(*) FROM payments").fetchone()[0] == 1


def test_key_reused_by_someone_else_is_rejected(household):
    h = household
    pay(h, "Ben", 2000, "key-shared-001")
    with pytest.raises(ledger.IdempotencyConflict):
        pay(h, "Cal", 2000, "key-shared-001")


# ---- HTTP seam: POST /api/payments ----------------------------------------------------------------

import json  # noqa: E402

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import payments  # noqa: E402
from api.db import get_conn  # noqa: E402
from api.main import app, fastapi_app  # noqa: E402
from api.nessie.client import NessieClient  # noqa: E402
from api.nessie.sync import sync_accounts  # noqa: E402
from api.routes.payments import get_mirror_runner  # noqa: E402
from api.session import COOKIE_NAME, load_member, sign  # noqa: E402
from api.tests.fake_nessie import KEY, FakeNessie  # noqa: E402


class BillFakeNessie(FakeNessie):
    """FakeNessie plus PUT /bills/{id} (how a bill is marked paid)."""

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.startswith("/bills/") and not self.down:
            self.requests.append(request)
            bill = self.children["bills"][request.url.path.rsplit("/", 1)[1]]
            bill.update(json.loads(request.content))
            return httpx.Response(202, json={"code": 202, "message": "Accepted"})
        return super().handle(request)


@pytest.fixture
def api(household):
    h = household
    fake = BillFakeNessie()
    nessie = NessieClient(KEY, "https://nessie.test", transport=fake.transport())
    # Ben's personal phone bill, mirrored from Nessie as a pending bill transaction.
    bill = nessie.create_bill(
        "nes-acct-ben", "Phone Co", "Phone", 4518, TODAY + dt.timedelta(days=5), 15, "pending"
    )
    with connect(h["dsn"]) as conn:
        h["bill_txn"] = conn.execute(
            """INSERT INTO transactions
               (user_id, account_id, nessie_id, kind, amount_cents, merchant, category, status, occurred_at)
               VALUES (%s, %s, %s, 'bill', 4518, 'Phone Co', 'bills', 'pending', %s) RETURNING id""",
            (
                h["users"]["Ben"],
                h["accounts"]["Ben"],
                bill["id"],
                payments._noon_utc(TODAY + dt.timedelta(days=5)),
            ),
        ).fetchone()[0]

    def scratch_conn():
        with connect(h["dsn"]) as conn:
            yield conn

    def mirror(payment_id):
        with connect(h["dsn"]) as conn:
            return payments.mirror_payment(conn, nessie, payment_id)

    fastapi_app.dependency_overrides[get_conn] = scratch_conn
    fastapi_app.dependency_overrides[get_mirror_runner] = lambda: mirror
    try:
        with TestClient(app) as c:
            c.h, c.fake, c.nessie = h, fake, nessie
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_conn, None)
        fastapi_app.dependency_overrides.pop(get_mirror_runner, None)


def as_user(c, name):
    c.cookies.set(COOKIE_NAME, sign(c.h["users"][name]))


def body(c, payer, bubble, amount, key="pop-key-00000001", **extra):
    return {"idempotency_key": key, "bubble_id": bubble, "account_id": f"acct_{c.h['accounts'][payer]}",
            "amount_cents": amount, **extra}  # fmt: skip


def balance(c, name):
    as_user(c, name)
    return c.get("/api/accounts").json()["accounts"][0]["balance_cents"]


def test_pop_without_a_session_is_rejected(api):
    res = api.post("/api/payments", json=body(api, "Ben", f"exp_{api.h['expenses']['Rent']}", 3333))
    assert res.status_code == 401


def test_body_user_id_is_ignored_identity_comes_from_the_cookie(api):
    h = api.h
    as_user(api, "Ben")
    res = api.post(
        "/api/payments",
        json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333, user_id=f"u_{h['users']['Cal']}"),
    )
    assert res.status_code == 200, res.text
    assert share_state(h["dsn"], h["shares"][("Rent", "Ben")]) == ("paid", 3333)
    assert share_state(h["dsn"], h["shares"][("Rent", "Cal")]) == ("open", 0)


def test_pop_shared_share_returns_payment_result_and_moves_balances_to_the_cent(api):
    h = api.h
    as_user(api, "Ben")
    res = api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333))
    assert res.status_code == 200, res.text
    result = res.json()
    assert set(result) == {"payment_id", "bubble_id", "status", "fill_fraction", "paid_count", "popped"}
    assert result["status"] == "paid" and result["paid_count"] == 2 and result["popped"] is False
    assert result["fill_fraction"] == pytest.approx(0.6667)
    assert balance(api, "Ben") == 100000 - 3333
    assert balance(api, "Ana") == 100000 + 3333


def test_nessie_mirror_is_whole_dollars_with_the_rounding_difference_on_the_payment(api):
    h = api.h
    as_user(api, "Ben")
    api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333))
    [transfer] = api.fake.children["transfers"].values()
    [deposit] = api.fake.children["deposits"].values()
    assert (transfer["account_id"], transfer["amount"], transfer["description"]) == (
        "nes-acct-ben",
        33,
        "Clearday: Rent share",
    )
    assert (deposit["account_id"], deposit["amount"], deposit["description"]) == (
        "nes-acct-ana",
        33,
        "Clearday: Rent share",
    )
    with connect(h["dsn"]) as conn:
        row = conn.execute(
            "SELECT nessie_transfer_id, nessie_deposit_id, nessie_rounding_diff_cents, mirror_status"
            " FROM payments"
        ).fetchone()
    assert row == (transfer["_id"], deposit["_id"], 33, "mirrored")


def test_nessie_amount_rounds_to_the_nearest_dollar():
    assert payments.nessie_amount(80000) == (80000, 0)
    assert payments.nessie_amount(3333) == (3300, 33)
    assert payments.nessie_amount(3350) == (3400, -50)
    assert payments.nessie_amount(49) == (0, 49)


def test_replayed_pop_returns_the_original_result_and_pays_once(api):
    h = api.h
    as_user(api, "Ben")
    first = api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333))
    again = api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333))
    assert again.status_code == 200 and again.json() == first.json()
    assert len(api.fake.children["transfers"]) == 1
    assert balance(api, "Ben") == 100000 - 3333


def test_amount_that_disagrees_with_the_ledger_is_rejected(api):
    as_user(api, "Ben")
    res = api.post("/api/payments", json=body(api, "Ben", f"exp_{api.h['expenses']['Rent']}", 3000))
    assert res.status_code == 409


def test_last_share_pops_the_bubble(api):
    h = api.h
    for name, key in [("Ben", "pop-key-ben-0001"), ("Cal", "pop-key-cal-0001")]:
        as_user(api, name)
        res = api.post("/api/payments", json=body(api, name, f"exp_{h['expenses']['Rent']}", 3333, key=key))
    assert res.json()["popped"] is True and res.json()["fill_fraction"] == 1.0


def test_ledger_commits_when_nessie_is_down_and_sync_retries_the_mirror(api):
    h = api.h
    api.fake.down = True
    as_user(api, "Ben")
    res = api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses']['Rent']}", 3333))
    assert res.status_code == 200
    with connect(h["dsn"]) as conn:
        assert conn.execute("SELECT mirror_status FROM payments").fetchone() == ("failed",)
    assert balance(api, "Ben") == 100000 - 3333

    api.fake.down = False
    with connect(h["dsn"]) as conn:
        sync_accounts(conn, api.nessie)
        assert conn.execute("SELECT mirror_status FROM payments").fetchone() == ("mirrored",)
    assert len(api.fake.children["transfers"]) == 1
    # Nessie holds $33; the ledger's exact 3333 cents survive the sync.
    assert balance(api, "Ben") == 100000 - 3333
    assert balance(api, "Ana") == 100000 + 3333


def test_popping_a_personal_bill_marks_the_nessie_bill_completed(api):
    h = api.h
    as_user(api, "Ben")
    res = api.post("/api/payments", json=body(api, "Ben", f"bill_{h['bill_txn']}", 4518))
    assert res.status_code == 200, res.text
    assert res.json()["popped"] is True
    [bill] = api.fake.children["bills"].values()
    assert bill["status"] == "completed"
    assert balance(api, "Ben") == 100000 - 4518


def test_someone_elses_bill_cannot_be_popped(api):
    as_user(api, "Cal")
    res = api.post("/api/payments", json=body(api, "Cal", f"bill_{api.h['bill_txn']}", 4518))
    assert res.status_code == 409


# ---- Socket.IO auth seam ---------------------------------------------------------------------------

from api import realtime  # noqa: E402


def test_socket_with_session_cookie_joins_household_and_user_rooms(household):
    h = household
    environ = {"HTTP_COOKIE": f"{COOKIE_NAME}={sign(h['users']['Ben'])}"}
    rooms = realtime.resolve_rooms(environ, None, h["dsn"])
    assert rooms == [f"hh:{h['hh']}", f"user:{h['users']['Ben']}"]


def test_socket_with_device_token_joins_only_the_device_room(household):
    h = household
    token = "device-token-abcdef-123456"
    with connect(h["dsn"]) as conn:
        conn.execute(
            "INSERT INTO devices (household_id, token_hash) VALUES (%s, %s)",
            (h["hh"], realtime.hash_device_token(token)),
        )
    assert realtime.resolve_rooms({}, {"token": token}, h["dsn"]) == [f"hh:{h['hh']}:device"]


@pytest.mark.parametrize(
    "environ, auth",
    [({}, None), ({"HTTP_COOKIE": f"{COOKIE_NAME}=1.2.forged"}, None), ({}, {"token": "x" * 32})],
)
def test_socket_without_valid_credentials_is_refused(household, environ, auth):
    assert realtime.resolve_rooms(environ, auth, household["dsn"]) is None


def test_device_room_never_receives_names_or_amounts(api):
    h = api.h
    as_user(api, "Ben")
    with connect(h["dsn"]) as conn:
        user = load_member(conn, h["users"]["Ben"])
        outcome = payments.pop_bubble(
            conn, user, idempotency_key="pop-key-dev-0001", bubble_id=f"exp_{h['expenses']['Rent']}",
            account_id=f"acct_{h['accounts']['Ben']}", amount_cents=3333,
        )  # fmt: skip
    device = realtime.device_room(h["hh"])
    for e in outcome.events:
        if device in e.rooms:
            assert e.event in {"share.updated", "bubble.popped"}
            assert not any("cents" in k or "name" in k for k in e.payload)
    assert any(e.event == "feed.created" and device not in e.rooms for e in outcome.events)
