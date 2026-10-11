"""Weekly recap: a two-host script built from household-level counts only.

Inputs are `sky.household_status` and counts of this week's feed events by type. No amounts, no names,
no bill labels (labels are user-typed text), no news or outside claims. The transcript is always returned;
audio is the same text through `voice.synthesize` (one voice; text only if ElevenLabs is unavailable).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from api import sky, voice

WEEK_DAYS = 7


def _n(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def week_counts(conn, household_id: int, today: dt.date) -> dict[str, int]:
    since = today - dt.timedelta(days=WEEK_DAYS - 1)
    rows = conn.execute(
        """SELECT type, count(*) FROM feed_events
           WHERE household_id = %s AND (created_at AT TIME ZONE 'America/New_York')::date >= %s
           GROUP BY type""",
        (household_id, since),
    ).fetchall()
    return {t: int(c) for t, c in rows}


def build_script(status: dict[str, Any], counts: dict[str, int]) -> list[dict[str, str]]:
    """Alternating host lines. Pure: counts in, text out."""
    cleared = counts.get("bubble_popped", 0)
    paid = counts.get("share_paid", 0) + cleared
    added = counts.get("expense_created", 0)
    open_bills = int(status.get("open_bills", 0))
    tight = status.get("weather") == "tight"
    lines = [
        ("A", "Welcome to your Clearday week in review, for your household."),
        (
            "B",
            f"This week the household cleared {_n(cleared, 'shared bill')} and paid {_n(paid, 'share')}."
            if cleared or paid
            else "It was a quiet week: no shared bills were cleared.",
        ),
    ]
    if added:
        lines.append(("A", f"Your household also added {_n(added, 'new shared expense')}."))
    lines.append(
        (
            "B",
            "Every shared bill is covered right now."
            if open_bills == 0
            else f"{_n(open_bills, 'shared bill')} still open, {int(status.get('shares_paid', 0))} of "
            f"{_n(int(status.get('shares_total', 0)), 'share')} paid.",
        )
    )
    lines.append(
        (
            "A",
            "Skies look tight ahead, so check your forecast and talk it over together."
            if tight
            else "Skies look clear ahead. Nice work, everyone.",
        )
    )
    return [{"speaker": s, "text": t} for s, t in lines]


def latest(conn, household_id: int) -> dict[str, Any]:
    today = sky.today()
    lines = build_script(sky.household_status(conn, household_id), week_counts(conn, household_id, today))
    transcript = " ".join(line["text"] for line in lines)
    result = voice.synthesize(transcript)
    return {
        "week_start": (today - dt.timedelta(days=WEEK_DAYS - 1)).isoformat(),
        "lines": lines,
        "transcript": transcript,
        "audio_url": f"/api/voice/audio/{result.audio_hash}" if result.audio_hash else None,
        "source": result.source,
    }
