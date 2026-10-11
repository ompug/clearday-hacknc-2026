"""Weekly recap: household data only (no amounts, names or labels), transcript always present."""

from __future__ import annotations

import re

from api import recap
from api.db import connect
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_api_contract import login

STATUS = {"weather": "clear", "open_bills": 2, "shares_paid": 1, "shares_total": 4}


def test_requires_session(client):  # noqa: F811
    assert client.get("/api/recap/latest").status_code == 401


def test_script_uses_counts_only():
    lines = recap.build_script(STATUS, {"bubble_popped": 1, "share_paid": 2, "expense_created": 3})
    text = " ".join(line["text"] for line in lines)
    assert "cleared 1 shared bill and paid 3 shares" in text
    assert "2 shared bills still open, 1 of 4 shares paid" in text
    assert "$" not in text and {line["speaker"] for line in lines} == {"A", "B"}


def test_quiet_week_and_tight_weather():
    text = " ".join(
        x["text"] for x in recap.build_script({**STATUS, "weather": "tight", "open_bills": 0}, {})
    )
    assert "quiet week" in text and "tight" in text and "Every shared bill is covered" in text


def test_latest_has_transcript_and_leaks_no_names_labels_or_amounts(client, scratch_dsn):  # noqa: F811
    ana = client.ids["users"][0]
    with connect(scratch_dsn) as conn:
        hh = conn.execute("SELECT household_id FROM household_members WHERE user_id = %s", (ana,)).fetchone()[
            0
        ]
        conn.execute(
            "INSERT INTO feed_events (household_id, type, actor_id, subject_label)"
            " VALUES (%s, 'bubble_popped', %s, %s)",
            (hh, ana, "Secret Rent Label"),
        )
        conn.commit()
    login(client)
    body = client.get("/api/recap/latest").json()
    assert body["transcript"] and body["lines"]
    assert "cleared 1 shared bill" in body["transcript"]
    blob = str(body)
    assert "Secret Rent Label" not in blob and "Ana" not in blob and "Ben" not in blob
    assert not re.search(r"[$€£]", body["transcript"])
    assert body["source"] in {"elevenlabs", "cache", "text"}
