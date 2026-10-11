"""Private household feed: celebrations without amounts.

Reads `feed_events` (which stores no amounts) for the signed-in user's own household only. Each event has
a type, the actor's display name, the subject label and a timestamp. Labels are user-typed, so `label`
replaces any that could carry an amount or a link with "a bill" (`api.safe_text`), here and in the
realtime `feed.created` emit. Names appear here, in the members-only app, and never on Clearday Home.
"""

from __future__ import annotations

from typing import Any

from api import safe_text, sky

LIMIT = 30
TYPES = {"share_paid", "bubble_popped", "expense_created"}
FALLBACK_LABEL = "a bill"


def label(text: str | None) -> str:
    """A feed label that can't carry an amount or a link."""
    return safe_text.safe_label(text, FALLBACK_LABEL, sky.LABEL_MAX)


FEED_SQL = """
SELECT f.type, u.display_name, f.subject_label, f.created_at
FROM feed_events f JOIN users u ON u.id = f.actor_id
WHERE f.household_id = %s
ORDER BY f.created_at DESC, f.id DESC
LIMIT %s
"""


def recent(conn, household_id: int) -> list[dict[str, Any]]:
    return [
        {
            "type": kind,
            "actor_display_name": sky.display_text(name, "A roommate"),
            "subject_label": label(subject),
            "created_at": created.isoformat().replace("+00:00", "Z"),
        }
        for kind, name, subject, created in conn.execute(FEED_SQL, (household_id, LIMIT)).fetchall()
        if kind in TYPES
    ]
