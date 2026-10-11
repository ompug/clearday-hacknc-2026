"""Private feed: household-scoped, newest first, no amounts."""

from __future__ import annotations

import re

from api.db import connect
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_api_contract import login

INSERT = "INSERT INTO feed_events (household_id, type, actor_id, subject_label) VALUES (%s, %s, %s, %s)"


def test_requires_session(client):  # noqa: F811
    assert client.get("/api/feed").status_code == 401


def test_feed_lists_own_household_newest_first_without_amounts(client, scratch_dsn):  # noqa: F811
    ana = client.ids["users"][0]
    with connect(scratch_dsn) as conn:
        hh = conn.execute("SELECT household_id FROM household_members WHERE user_id = %s", (ana,)).fetchone()[
            0
        ]
        other = conn.execute("INSERT INTO households (name) VALUES ('Elsewhere') RETURNING id").fetchone()[0]
        conn.execute(INSERT, (hh, "expense_created", ana, "Pizza night"))
        conn.execute(INSERT, (hh, "bubble_popped", ana, "Rent"))
        conn.execute(INSERT, (other, "bubble_popped", ana, "Not ours"))
        conn.commit()
    login(client)
    events = client.get("/api/feed").json()["events"]
    assert [e["subject_label"] for e in events] == ["Rent", "Pizza night"]
    assert set(events[0]) == {"type", "actor_display_name", "subject_label", "created_at"}
    assert events[0]["actor_display_name"] == "Ana"
    assert not re.search(r"[$€£]|amount|cents", str(events))


def test_empty_feed(client):  # noqa: F811
    login(client)
    assert client.get("/api/feed").json() == {"events": []}
