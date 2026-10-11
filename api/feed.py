"""Private household feed: celebrations without amounts.

Reads `feed_events` (which stores no amounts) for the signed-in user's own household only. Each event has
a type, the actor's display name, the user-typed subject label (cleaned with `sky.display_text`) and a
timestamp. Names appear here, in the members-only app, and never on Clearday Home.
"""

from __future__ import annotations

from typing import Any

from api import sky

LIMIT = 30
TYPES = {"share_paid", "bubble_popped", "expense_created"}

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
            "subject_label": sky.display_text(label, "a bill"),
            "created_at": created.isoformat().replace("+00:00", "Z"),
        }
        for kind, name, label, created in conn.execute(FEED_SQL, (household_id, LIMIT)).fetchall()
        if kind in TYPES
    ]
