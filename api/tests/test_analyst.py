"""Analyst view: synthetic households only, segments under 20 hidden, session required."""

from __future__ import annotations

from api import analyst
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_api_contract import login


def test_requires_session(client):  # noqa: F811
    assert client.get("/api/analyst/segments").status_code == 401


def test_segments_are_synthetic_with_shares_in_range(client):  # noqa: F811
    login(client)
    body = client.get("/api/analyst/segments").json()
    assert body["synthetic"] is True and body["total_households"] == 200
    assert body["segments"], "expected visible segments"
    for s in body["segments"]:
        assert s["households"] >= 20
        assert 0.0 <= s["share_at_risk"] <= 1.0
        assert set(s) == {"segment", "label", "households", "share_at_risk"}  # nothing per household


def test_segments_under_20_households_are_hidden(monkeypatch):
    monkeypatch.setattr(analyst, "N_HOUSEHOLDS", 60)
    shown = analyst.segments()["segments"]
    assert shown and all(s["households"] >= 20 for s in shown)
    assert {"gig_worker", "retiree"}.isdisjoint(s["segment"] for s in shown)  # 12 and 6 households


def test_reads_no_real_data():
    import inspect

    assert "conn" not in inspect.signature(analyst.segments).parameters
