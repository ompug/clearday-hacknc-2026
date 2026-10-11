"""Contract tests: every Phase 1 endpoint's JSON matches web/lib/api/types.ts (key sets and types are
written out by hand below), identity comes only from the signed cookie, and no Nessie ID or account
number appears in any response."""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest
from fastapi.testclient import TestClient

from api import sky
from api.db import connect, get_conn
from api.main import app, fastapi_app
from api.migrate import migrate
from api.session import COOKIE_NAME, sign

# ---- expected shapes (mirror web/lib/api/types.ts) ---------------------------------------------

STR, INT, NUM, NULL = "str", "int", "num", "null"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DEMO_PERSONA = {"user_id": {STR}, "display_name": {STR}, "tagline": {STR}}
ME = {"user": {"user_id": {STR}, "display_name": {STR}}, "household": {"household_id": {STR}, "name": {STR}}}
ACCOUNT = {"account_id": {STR}, "type": {STR}, "nickname": {STR}, "last4": {STR}, "balance_cents": {INT}}
SKY_BUBBLE = {
    "bubble_id": {STR},
    "kind": {STR},
    "label": {STR},
    "due_date": {STR},
    "your_share_cents": {INT},
    "total_cents": {INT},
    "status": {STR},
    "fill_fraction": {NUM},
    "paid_count": {INT},
    "participant_count": {INT},
    "p_short": {NUM},
    "weather": {STR},
    "necessity": {STR},
    "expense_id": {STR, NULL},
    "share_id": {STR, NULL},
    "default_account_id": {STR, NULL},
    "cluster_id": {STR, NULL},
    "payable": {"bool"},
}
SKY_CLUSTER = {"cluster_id": {STR}, "label": {STR}, "bubble_ids": {"list"}}
SKY = {
    "as_of": {STR},
    "bubbles": {"list"},
    "clusters": {"list"},
    "safe_to_spend_cents": {INT},
    "next_payday": {STR},
}
# Not in types.ts: the spec says only "household-only summary"; this is the shape Clearday Home parses
# (device/clearday_home/payloads.py). Counts only, no amounts or names.
HOUSEHOLD_STATUS = {
    "weather": {STR},
    "open_bills": {INT},
    "due_soon_bills": {INT},
    "shares_paid": {INT},
    "shares_total": {INT},
}
ENUMS = {
    "type": {"checking", "savings", "credit_card"},
    "kind": {"bill", "shared"},
    "status": {"open", "partial", "paid", "disputed"},
    "weather": {"clear", "watch", "tight"},
    "necessity": {"need", "want"},
}


def _kind(value) -> str:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return INT
    if isinstance(value, float):
        return NUM
    if isinstance(value, str):
        return STR
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def assert_shape(obj: dict, shape: dict, where: str = "") -> None:
    assert isinstance(obj, dict), where
    assert set(obj) == set(shape), f"{where}: keys {sorted(obj)} != {sorted(shape)}"
    for key, allowed in shape.items():
        if isinstance(allowed, dict):
            assert_shape(obj[key], allowed, f"{where}.{key}")
            continue
        kind = _kind(obj[key])
        ok = kind in allowed or (kind == INT and NUM in allowed)  # JSON 0 for a number is fine
        assert ok, f"{where}.{key}: {kind} not in {allowed}"


# ---- fixture household -------------------------------------------------------------------------

NESSIE = {
    "cust": ["5f0c0ffee0000000000000a1", "5f0c0ffee0000000000000a2", "5f0c0ffee0000000000000a3"],
    "acct": ["66aa00000000000000000001", "66aa00000000000000000002", "66aa00000000000000000003"],
    "txn": ["77bb00000000000000000001", "77bb00000000000000000002", "77bb00000000000000000003"],
}


@pytest.fixture
def client(scratch_dsn):
    """App wired to a migrated scratch DB holding one three-person household."""
    today = sky.today()
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        hh = conn.execute("INSERT INTO households (name) VALUES ('Test Flat') RETURNING id").fetchone()[0]
        users = []
        for name, cust in zip(["Ana", "Ben", "Cal"], NESSIE["cust"], strict=True):
            uid = conn.execute(
                "INSERT INTO users (display_name, nessie_customer_id) VALUES (%s, %s) RETURNING id",
                (name, cust),
            ).fetchone()[0]
            conn.execute("INSERT INTO household_members (household_id, user_id) VALUES (%s, %s)", (hh, uid))
            users.append(uid)
        ana = users[0]
        chk = conn.execute(
            """INSERT INTO accounts (user_id, nessie_account_id, type, nickname, last4, opening_balance_cents)
               VALUES (%s, %s, 'checking', 'Everyday Checking', '4321', 100000) RETURNING id""",
            (ana, NESSIE["acct"][0]),
        ).fetchone()[0]
        card = conn.execute(
            """INSERT INTO accounts (user_id, nessie_account_id, type, nickname, last4, opening_balance_cents)
               VALUES (%s, %s, 'credit_card', 'Rewards Card', '8765', 0) RETURNING id""",
            (ana, NESSIE["acct"][1]),
        ).fetchone()[0]
        noon = dt.datetime(today.year, today.month, today.day, 12, tzinfo=dt.UTC)
        txn = """INSERT INTO transactions (user_id, account_id, nessie_id, kind, amount_cents, merchant,
                     category, status, occurred_at)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"""
        rows = [
            (chk, 0, "deposit", 50000, "Payroll", "income", "posted", -3),
            (card, 1, "purchase", 2500, "Cafe", "dining", "posted", -1),
            (chk, 2, "bill", 9000, "Phone Co", "bills", "pending", 5),  # personal bill, due in 5 days
        ]
        txn_ids = [
            conn.execute(
                txn, (ana, acct, NESSIE["txn"][i], kind, cents, merchant, cat, status,
                      noon + dt.timedelta(days=offset)),
            ).fetchone()[0]
            for acct, i, kind, cents, merchant, cat, status, offset in rows
        ]  # fmt: skip
        bill_txn = txn_ids[2]
        exp = conn.execute(
            """INSERT INTO expenses (household_id, payer_id, label, total_cents, split_method, due_on)
               VALUES (%s, %s, 'Rent', 10000, 'even', %s) RETURNING id""",
            (hh, ana, today + dt.timedelta(days=2)),
        ).fetchone()[0]
        for uid, cents, status in zip(users, [3334, 3333, 3333], ["paid", "open", "open"], strict=True):
            conn.execute(
                "INSERT INTO shares (expense_id, user_id, amount_cents, status) VALUES (%s, %s, %s, %s)",
                (exp, uid, cents, status),
            )
        conn.commit()

    def scratch_conn():
        with connect(scratch_dsn) as conn:
            yield conn

    sky.invalidate_forecasts()
    fastapi_app.dependency_overrides[get_conn] = scratch_conn
    try:
        with TestClient(app) as c:
            c.ids = {"users": users, "bill_txn": bill_txn, "expense": exp, "checking": chk, "card": card}
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_conn, None)
        sky.invalidate_forecasts()


def login(client, index: int = 0) -> dict:
    res = client.post("/api/dev/login", json={"user_id": f"u_{client.ids['users'][index]}"})
    assert res.status_code == 200, res.text
    return res.json()


# ---- session -----------------------------------------------------------------------------------


def test_personas_shape(client):
    res = client.get("/api/dev/personas")
    assert res.status_code == 200
    personas = res.json()
    assert [p["display_name"] for p in personas] == ["Ana", "Ben", "Cal"]
    for p in personas:
        assert_shape(p, DEMO_PERSONA, "DemoPersona")


def test_login_sets_httponly_cookie_and_returns_me(client):
    body = login(client)
    assert_shape(body, ME, "Me")
    assert body["user"] == {"user_id": f"u_{client.ids['users'][0]}", "display_name": "Ana"}
    cookie = client.cookies.get(COOKIE_NAME)
    assert cookie
    assert client.get("/api/me").json() == body


def test_login_cookie_flags(client):
    res = client.post("/api/dev/login", json={"user_id": f"u_{client.ids['users'][0]}"})
    header = res.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header


@pytest.mark.parametrize("user_id", ["u_999999", "999", "acct_1", "", "u_1; drop"])
def test_login_rejects_unknown_persona(client, user_id):
    assert client.post("/api/dev/login", json={"user_id": user_id}).status_code == 404


def test_login_rejects_extra_fields(client):
    res = client.post(
        "/api/dev/login", json={"user_id": f"u_{client.ids['users'][0]}", "household_id": "hh_9"}
    )
    assert res.status_code == 422


@pytest.mark.parametrize("path", ["/api/me", "/api/sky", "/api/accounts", "/api/household/status"])
def test_requires_session(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", ["/api/me", "/api/sky", "/api/accounts"])
def test_tampered_or_forged_cookie_is_rejected(client, path):
    login(client)
    good = client.cookies.get(COOKIE_NAME)
    user_part, issued, nonce, sig = good.split(".")
    other = client.ids["users"][1]
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, f"{other}.{issued}.{nonce}.{sig}")
    assert client.get(path).status_code == 401
    client.cookies.set(COOKIE_NAME, sign(int(user_part), issued_at=0))  # expired
    assert client.get(path).status_code == 401


def test_query_params_do_not_change_identity(client):
    login(client, 0)
    ben = f"u_{client.ids['users'][1]}"
    assert client.get(f"/api/me?user_id={ben}").json()["user"]["display_name"] == "Ana"


def test_logout_clears_session(client):
    login(client)
    res = client.post("/api/session/logout")
    assert res.status_code == 204
    assert client.get("/api/me").status_code == 401


def test_dev_routes_can_be_disabled(client, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "enable_dev_routes", False)
    assert client.get("/api/dev/personas").status_code == 404
    assert client.post("/api/dev/login", json={"user_id": "u_1"}).status_code == 404


# ---- reads -------------------------------------------------------------------------------------


def test_accounts_shape_and_balances(client):
    login(client)
    body = client.get("/api/accounts").json()
    assert set(body) == {"accounts"}
    for a in body["accounts"]:
        assert_shape(a, ACCOUNT, "Account")
        assert a["type"] in ENUMS["type"]
        assert re.fullmatch(r"\d{4}", a["last4"])
    by_type = {a["type"]: a for a in body["accounts"]}
    # Opening balance plus stored transactions; the pending bill doesn't count yet.
    assert by_type["checking"]["balance_cents"] == 100000 + 50000
    assert by_type["credit_card"]["balance_cents"] == 2500  # amount owed
    assert by_type["checking"]["last4"] == "4321"


def test_accounts_are_only_mine(client):
    login(client, 1)  # Ben has no accounts
    assert client.get("/api/accounts").json() == {"accounts": []}


def test_sky_shape(client):
    login(client)
    body = client.get("/api/sky").json()
    assert_shape(body, SKY, "SkyResponse")
    assert ISO_DATE.match(body["next_payday"])
    assert body["bubbles"], "fixture has a shared bubble and a personal bill"
    for b in body["bubbles"]:
        assert_shape(b, SKY_BUBBLE, f"SkyBubble {b['bubble_id']}")
        for key in ("kind", "status", "weather", "necessity"):
            assert b[key] in ENUMS[key], (key, b[key])
        assert ISO_DATE.match(b["due_date"])
        assert 0 <= b["fill_fraction"] <= 1 and 0 <= b["p_short"] <= 1
    for cl in body["clusters"]:
        assert_shape(cl, SKY_CLUSTER, "SkyCluster")


def test_sky_bubbles_reconcile_with_ledger(client):
    login(client, 1)  # Ben: owes a Rent share, no personal bills
    bubbles = client.get("/api/sky").json()["bubbles"]
    assert len(bubbles) == 1
    rent = bubbles[0]
    assert rent["kind"] == "shared" and rent["label"] == "Rent"
    assert rent["your_share_cents"] == 3333 and rent["total_cents"] == 10000
    assert rent["status"] == "open" and rent["paid_count"] == 1 and rent["participant_count"] == 3
    assert rent["fill_fraction"] == pytest.approx(0.3334)
    assert rent["expense_id"] == rent["bubble_id"] == f"exp_{client.ids['expense']}"

    client.cookies.clear()
    login(client, 0)  # Ana: paid her Rent share; has a personal pending bill
    by_kind = {b["kind"]: b for b in client.get("/api/sky").json()["bubbles"]}
    assert by_kind["shared"]["status"] == "paid" and by_kind["shared"]["weather"] == "clear"
    bill = by_kind["bill"]
    assert bill["bubble_id"] == f"bill_{client.ids['bill_txn']}"
    assert bill["your_share_cents"] == bill["total_cents"] == 9000
    assert bill["default_account_id"] == f"acct_{client.ids['checking']}"


def test_household_status_shape_has_no_amounts_or_names(client):
    login(client)
    body = client.get("/api/household/status").json()
    assert_shape(body, HOUSEHOLD_STATUS, "HouseholdStatus")
    assert body["weather"] in {"clear", "tight"}
    assert body == {**body, "open_bills": 1, "due_soon_bills": 1, "shares_paid": 1, "shares_total": 3}
    text = str(body)
    for name in ("Ana", "Ben", "Cal", "Rent", "3333", "10000"):
        assert name not in text


# ---- leak scan ---------------------------------------------------------------------------------


def test_no_nessie_ids_or_account_numbers_in_any_response(client):
    bodies = [client.get("/api/dev/personas").text]
    for i in range(3):
        client.cookies.clear()
        bodies.append(client.post("/api/dev/login", json={"user_id": f"u_{client.ids['users'][i]}"}).text)
        for path in ("/api/me", "/api/sky", "/api/accounts", "/api/household/status"):
            res = client.get(path)
            assert res.status_code == 200, path
            bodies.append(res.text)
    secrets = [v for group in NESSIE.values() for v in group]
    for text in bodies:
        for value in secrets:
            assert value not in text
        assert "nessie" not in text.lower()
        assert "account_number" not in text
        assert not re.search(r"\d{9,}", text), "long digit run looks like an account number"


# ---- sky: labels, subscription clusters, necessity ---------------------------------------------


def _cache_bill(dsn: str, nickname: str) -> None:
    """A cached Nessie bill list holding the fixture's personal bill, as the client stores it."""
    body = [{"_id": NESSIE["txn"][2], "payee": "Phone Co", "nickname": nickname, "status": "pending"}]
    with connect(dsn) as conn:
        conn.execute(
            """INSERT INTO nessie_cache (cache_key, method, path, status_code, response_body)
               VALUES (%s, 'GET', %s, 200, %s::jsonb)""",
            ("a" * 64, f"/accounts/{NESSIE['acct'][0]}/bills", json.dumps(body)),
        )
        conn.commit()


def _bill_bubble(client) -> dict:
    return next(b for b in client.get("/api/sky").json()["bubbles"] if b["bubble_id"].startswith("bill_"))


def test_sky_personal_bill_uses_nickname_not_payee(client, scratch_dsn):
    login(client)
    assert _bill_bubble(client)["label"] == "Bill"  # no cached nickname: generic, never the payee
    _cache_bill(scratch_dsn, "Phone")
    sky.invalidate_forecasts()
    bill = _bill_bubble(client)
    assert bill["label"] == "Phone"
    assert "Phone Co" not in client.get("/api/sky").text


def test_sky_labels_are_cleaned_untrusted_text(client, scratch_dsn):
    _cache_bill(scratch_dsn, "  Ph‮one\n\t<b>x</b>" + "z" * 200)
    login(client)
    label = _bill_bubble(client)["label"]
    assert label.startswith("Ph one <b>x</b>") and len(label) == sky.LABEL_MAX
    assert sky.display_text("\x07​ \n", "Bill") == "Bill"


def _add_card_charges(dsn: str, user_id: int, card: int, charges: list[tuple[str, str, int, int]]) -> None:
    today = sky.today()
    noon = dt.datetime(today.year, today.month, today.day, 12, tzinfo=dt.UTC)
    with connect(dsn) as conn:
        for merchant, category, cents, days_ago in charges:
            conn.execute(
                """INSERT INTO transactions (user_id, account_id, kind, amount_cents, merchant, category,
                       status, occurred_at)
                   VALUES (%s, %s, 'purchase', %s, %s, %s, 'posted', %s)""",
                (user_id, card, cents, merchant, category, noon - dt.timedelta(days=days_ago)),
            )
        conn.commit()


def test_sky_clusters_recurring_subscriptions(client, scratch_dsn):
    ana, card = client.ids["users"][0], client.ids["card"]
    _add_card_charges(
        scratch_dsn,
        ana,
        card,
        [
            ("StreamCo", "subscriptions", 1500, 50),
            ("StreamCo", "subscriptions", 1500, 20),  # next charge in 10 days
            ("TuneCo", "subscriptions", 1200, 45),
            ("TuneCo", "subscriptions", 1200, 15),  # next charge in 15 days
            ("GymCo", "health", 4000, 40),
            ("GymCo", "health", 4000, 10),  # recurring, but not a subscription
        ],
    )
    login(client)
    body = client.get("/api/sky").json()
    assert len(body["clusters"]) == 1
    cluster = body["clusters"][0]
    assert_shape(cluster, SKY_CLUSTER, "SkyCluster")
    assert cluster["label"] == "Subscriptions"
    members = [b for b in body["bubbles"] if b["cluster_id"] == cluster["cluster_id"]]
    assert sorted(b["bubble_id"] for b in members) == sorted(cluster["bubble_ids"])
    by_label = {b["label"]: b for b in members}
    assert set(by_label) == {"StreamCo", "TuneCo"}
    today = sky.today()
    assert by_label["StreamCo"]["due_date"] == (today + dt.timedelta(days=10)).isoformat()
    for b in members:
        assert_shape(b, SKY_BUBBLE, b["bubble_id"])
        assert b["kind"] == "bill" and b["bubble_id"].startswith("sub_")
        assert b["default_account_id"] == f"acct_{card}"
        assert b["necessity"] == "want"
    assert by_label["TuneCo"]["your_share_cents"] == 1200
    assert all(b["label"] != "GymCo" for b in body["bubbles"])

    client.cookies.clear()
    login(client, 1)  # Ben's sky never shows Ana's subscriptions
    assert client.get("/api/sky").json()["clusters"] == []


def test_subscription_bubbles_are_not_payable(client, scratch_dsn):
    """Spec: subscriptions are predicted renewals (recurring-charge detection), not bills to pay."""
    _add_card_charges(
        scratch_dsn,
        client.ids["users"][0],
        client.ids["card"],
        [("StreamCo", "subscriptions", 1500, 50), ("StreamCo", "subscriptions", 1500, 20)],
    )
    login(client)
    by_prefix = {b["bubble_id"].split("_")[0]: b for b in client.get("/api/sky").json()["bubbles"]}
    assert by_prefix["sub"]["payable"] is False
    assert by_prefix["bill"]["payable"] is True
    res = client.post(
        "/api/payments",
        json={
            "idempotency_key": "sub-pop-0000001",
            "bubble_id": by_prefix["sub"]["bubble_id"],
            "account_id": f"acct_{client.ids['card']}",
            "amount_cents": 1500,
        },
    )
    assert res.status_code == 409
    assert "automatically" in res.json()["detail"]


def test_sky_single_subscription_is_not_clustered(client, scratch_dsn):
    _add_card_charges(
        scratch_dsn,
        client.ids["users"][0],
        client.ids["card"],
        [("StreamCo", "subscriptions", 1500, 50), ("StreamCo", "subscriptions", 1500, 20)],
    )
    login(client)
    body = client.get("/api/sky").json()
    assert body["clusters"] == []
    assert [b["cluster_id"] for b in body["bubbles"] if b["label"] == "StreamCo"] == [None]


def test_sky_necessity_comes_from_tag_needs(client, monkeypatch):
    login(client)
    by_kind = {b["kind"]: b for b in client.get("/api/sky").json()["bubbles"]}
    assert by_kind["bill"]["necessity"] == "need"  # a Nessie bill reads as a utility to the contract

    seen = []

    def fake_tag_needs(transactions):
        seen.extend(transactions["category"].tolist())
        return transactions.assign(necessity=["want"] * len(transactions))

    monkeypatch.setattr(sky, "tag_needs", fake_tag_needs)
    bubbles = client.get("/api/sky").json()["bubbles"]
    assert {b["necessity"] for b in bubbles} == {"want"}
    assert "utilities" in seen and "bills" not in seen
