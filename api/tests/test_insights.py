"""Household insights: the duplicate-subscription card and the forecast backtest number.

Both go through their analytics contracts (`detection.duplicate_subscriptions`, `backtest.run`), so the
stub and the teammate's real module are interchangeable.
"""

from __future__ import annotations

from api.db import connect
from api.tests.test_api_contract import STR, _add_card_charges, assert_shape, login
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)

INT = "int"
DUPLICATE = {
    "merchant": {STR},
    "members": {"list"},
    "monthly_cost_cents": {INT},
    "possible_savings_cents": {INT},
}
MEMBER = {"user_id": {STR}, "display_name": {STR}}


def test_insights_require_session(client):  # noqa: F811
    assert client.get("/api/insights/subscriptions").status_code == 401
    assert client.get("/api/insights/backtest").status_code == 401


def test_duplicate_subscription_is_surfaced_with_names_and_savings(client, scratch_dsn):  # noqa: F811
    ana, ben = client.ids["users"][0], client.ids["users"][1]
    card = client.ids["card"]
    _add_card_charges(
        scratch_dsn, ana, card, [("TuneCo", "subscriptions", 1200, 10), ("OnlyAna", "subscriptions", 500, 9)]
    )
    with connect(scratch_dsn) as conn:
        bcard = conn.execute(
            "INSERT INTO accounts (user_id, type, nickname, last4, opening_balance_cents)"
            " VALUES (%s, 'credit_card', 'Card', '1111', 0) RETURNING id",
            (ben,),
        ).fetchone()[0]
        conn.commit()
    _add_card_charges(scratch_dsn, ben, bcard, [("TuneCo", "subscriptions", 1200, 7)])
    login(client)
    res = client.get("/api/insights/subscriptions")
    assert res.status_code == 200, res.text
    dups = res.json()["duplicates"]
    assert [d["merchant"] for d in dups] == ["TuneCo"]  # OnlyAna has one payer
    d = dups[0]
    assert_shape(d, DUPLICATE, "DuplicateSubscription")
    assert d["monthly_cost_cents"] == 2400 and d["possible_savings_cents"] == 1200
    assert sorted(m["display_name"] for m in d["members"]) == ["Ana", "Ben"]
    for m in d["members"]:
        assert_shape(m, MEMBER, "DuplicateMember")
        assert m["user_id"].startswith("u_")


def test_no_duplicates_means_empty_list(client):  # noqa: F811
    login(client)
    assert client.get("/api/insights/subscriptions").json() == {"duplicates": []}


def test_backtest_reports_contract_numbers_and_flags_the_stub(client):  # noqa: F811
    login(client)
    res = client.get("/api/insights/backtest")
    assert res.status_code == 200, res.text
    b = res.json()
    assert set(b) == {"coverage", "median_abs_error_cents", "holdout_days", "is_preview"}
    assert 0 <= b["coverage"] <= 1 and isinstance(b["median_abs_error_cents"], int)
    assert b["holdout_days"] == 30
    assert b["is_preview"] is True  # the stub marks itself; a real module carries no flag
