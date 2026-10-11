"""Unusual charges: GET /api/insights/anomalies and the explain_anomaly tool.

Both go through `analytics.detection.detect_anomalies`, so the stub and the teammate's module are
interchangeable. The model is only ever sent an anomaly handle, never a transaction ID.
"""

from __future__ import annotations

import datetime as dt

from api import sky
from api.db import connect
from api.tests.test_ai_gateway import ask, audit_rows, login
from api.tests.test_ai_gateway import client as client  # noqa: F401  (fixture)

BIG = 21800
USUAL = 5000


def _charges(client, name: str, merchant: str, amounts: list[int]) -> None:
    noon = dt.datetime.combine(sky.today(), dt.time(12), sky.DISPLAY_TZ)
    with connect(client.dsn) as conn:
        uid = client.users[name]
        card = conn.execute("SELECT id FROM accounts WHERE user_id = %s", (uid,)).fetchone()[0]
        for i, cents in enumerate(amounts):
            conn.execute(
                """INSERT INTO transactions (user_id, account_id, kind, amount_cents, merchant, category,
                       status, occurred_at)
                   VALUES (%s, %s, 'purchase', %s, %s, 'groceries', 'posted', %s)""",
                (uid, card, cents, merchant, noon - dt.timedelta(days=5 + i * 6)),
            )
        conn.commit()


def _plant(client, name: str) -> None:
    _charges(client, name, "Fresh Mart", [USUAL, USUAL, USUAL, USUAL, USUAL, BIG])


def test_anomalies_require_session(client):  # noqa: F811
    assert client.get("/api/insights/anomalies").status_code == 401


def test_no_anomalies_means_empty_list(client):  # noqa: F811
    login(client, "Ana")
    assert client.get("/api/insights/anomalies").json() == {"anomalies": []}


def test_own_anomaly_is_listed_with_typical_range_and_nobody_elses(client):  # noqa: F811
    _plant(client, "Ana")
    _charges(client, "Ben", "Gadget Hub", [900, 900, 900, 900, 900, 40000])
    login(client, "Ana")
    res = client.get("/api/insights/anomalies")
    assert res.status_code == 200, res.text
    found = res.json()["anomalies"]
    assert len(found) == 1
    a = found[0]
    assert set(a) == {
        "anomaly_id",
        "merchant",
        "date",
        "amount_cents",
        "typical_low_cents",
        "typical_high_cents",
    }
    assert (a["merchant"], a["amount_cents"]) == ("Fresh Mart", BIG)
    assert a["typical_low_cents"] <= a["typical_high_cents"] < BIG
    assert a["anomaly_id"].startswith("txn_")
    assert dt.date.fromisoformat(a["date"])
    assert "Gadget Hub" not in res.text


def test_explain_anomaly_returns_the_one_item_for_an_issued_handle(client):  # noqa: F811
    _plant(client, "Ana")
    login(client, "Ana")
    res = ask(
        client,
        "why is that Fresh Mart charge so big?",
        script=[[("explain_anomaly", {"anomaly_handle": "anomaly_1"})], "Fresh Mart was far above usual."],
    )
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "model"
    assert "anomaly_1" in client.fake.requests[0]["messages"][0]["content"]
    tool = client.fake.tool_text
    assert '"untrusted_text": "Fresh Mart"' in tool and str(BIG) in tool and str(USUAL) in tool
    audits = [r for r in audit_rows(client) if r["event"] == "tool"]
    assert (audits[0]["tool"], audits[0]["outcome"], audits[0]["row_count"]) == ("explain_anomaly", "ok", 1)
    assert "Fresh Mart" not in str(audit_rows(client)) and str(BIG) not in str(audit_rows(client))


def test_explain_anomaly_rejects_raw_ids_and_unissued_handles(client):  # noqa: F811
    _plant(client, "Ana")
    login(client, "Ana")
    with connect(client.dsn) as conn:
        txn_id = conn.execute("SELECT id FROM transactions WHERE amount_cents = %s", (BIG,)).fetchone()[0]
    script = [
        [("explain_anomaly", {"anomaly_handle": f"txn_{txn_id}"})],
        [("explain_anomaly", {"anomaly_handle": "anomaly_2"})],
        "I could not find that.",
    ]
    ask(client, "explain it", script=script)
    reasons = [r["reason"] for r in audit_rows(client) if r["event"] == "tool"]
    assert reasons == ["raw_id", "unknown_handle"]
    assert f"txn_{txn_id}" not in client.fake.requests[0]["messages"][0]["content"] + client.fake.tool_text


def test_no_anomaly_handles_are_mentioned_when_there_are_none(client):  # noqa: F811
    login(client, "Ana")
    ask(client, "split last night's pizza with Ben", script=[])
    assert "anomaly_1" not in client.fake.requests[0]["messages"][0]["content"]
