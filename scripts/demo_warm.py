"""Warm the demo before recording (run after reset_demo): `bash scripts/dev.sh warm`.

1. Caches the ElevenLabs announcement audio for the demo's pop (both weather outcomes), via the same
   `voice.synthesize` the live pop uses, so the cached hash is hit during the video.
2. Computes the forecast for every persona (imports, caches, DB pages warm).
3. Calls the assistant once with the exact demo prompt as Maya, so the model connection is warm.
   The video's live call still happens; nothing is stubbed or stored (only the normal audit rows).
Needs the API running (default http://localhost:8000).
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

from api import ids, sky, voice
from api.db import connect

PIZZA_PROMPT = "split last night's pizza with Jake and Priya"


def warm_voice(conn, household_id: int) -> list[str]:
    """Cache audio for the announcement after the rent bubble fully pops (rent leaves the open list)."""
    shares = sky.open_household_shares(conn, household_id)
    rent = {s.expense_id: s for s in shares if s.label.lower().startswith("rent")}
    status = sky.household_status(conn, household_id)
    for s in rent.values():
        status["open_bills"] -= 1
        status["shares_paid"] -= s.paid_count
        status["shares_total"] -= s.participants
    out = []
    for weather in ("clear", "tight"):
        text = voice.announcement_text({**status, "weather": weather})
        res = voice.synthesize(text)
        out.append(f"{weather}: {res.source}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()
    with connect() as conn:
        rows = conn.execute(
            "SELECT u.id, u.display_name, m.household_id FROM users u "
            "JOIN household_members m ON m.user_id = u.id ORDER BY u.id"
        ).fetchall()
        people = {name: (pk, hh) for pk, name, hh in rows}
        t = time.perf_counter()
        print("voice:", ", ".join(warm_voice(conn, people["Maya"][1])), f"({time.perf_counter() - t:.1f}s)")
    with httpx.Client(base_url=args.api, timeout=60) as http:
        for name in ("Priya", "Jake", "Maya"):
            http.post(
                "/api/dev/login", json={"user_id": ids.encode(ids.USER, people[name][0])}
            ).raise_for_status()
            t = time.perf_counter()
            http.get("/api/sky").raise_for_status()
            http.get("/api/forecast").raise_for_status()
            print(f"forecast {name}: {time.perf_counter() - t:.1f}s")
        t = time.perf_counter()  # the session is Maya's now
        res = http.post("/api/assistant", json={"message": PIZZA_PROMPT})
        res.raise_for_status()
        print(f"assistant: {time.perf_counter() - t:.1f}s via {res.json().get('source')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
