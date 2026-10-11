"""Future view: labelled hypothetical, visible adjustable assumptions, exact integer-cent series."""

from __future__ import annotations

from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_api_contract import login


def test_requires_session(client):  # noqa: F811
    assert client.get("/api/future").status_code == 401


def test_default_projection_is_labelled_and_shows_assumptions(client):  # noqa: F811
    login(client)
    body = client.get("/api/future").json()
    assert body["label"] == "Hypothetical, not investment advice"
    assert body["assumptions"] == {"low": 0.03, "mid": 0.06, "high": 0.08}
    assert len(body["series"]) == 10 and body["from_history"] is True
    assert all(isinstance(v, int) for row in body["series"] for v in row.values())
    assert body["monthly_surplus_cents"] >= 0


def test_what_if_amount_and_rates_are_applied(client):  # noqa: F811
    login(client)
    body = client.get("/api/future", params={"monthly_cents": 10000, "low": 0, "mid": 0, "high": 0.1}).json()
    assert body["from_history"] is False and body["monthly_surplus_cents"] == 10000
    assert body["series"][0]["low_cents"] == 120000  # 12 months at 0%
    assert body["series"][-1]["low_cents"] == 1200000
    assert body["series"][-1]["high_cents"] > body["series"][-1]["mid_cents"]


def test_bad_inputs_are_rejected(client):  # noqa: F811
    login(client)
    for params in (
        {"low": 0.5},
        {"low": 0.09, "mid": 0.06},
        {"high": -0.01},
        {"monthly_cents": -1},
        {"monthly_cents": 10**9},
    ):
        assert client.get("/api/future", params=params).status_code == 422, params
