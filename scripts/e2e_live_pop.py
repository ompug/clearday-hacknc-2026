"""Live end to end: Maya and Jake in two browser sessions. Jake pops his Rent share and Maya's sky
updates over Socket.IO without a reload; then Maya splits a new expense with Jake and his sky gains
the new shared bubble live. Screenshots land in logs/e2e/.

Needs the API and web running against a seeded DB. Before the browsers start, it runs
scripts/reset_demo.py on the DB that api.config points at (set DATABASE_URL_LOCAL to the same DB as
the API), so every run starts from the seeded state. --reset-db-only skips Nessie; --no-reset skips it.
For example (Playwright is a dev dependency; once per machine: uv run playwright install chromium):
    bash scripts/dev.sh up --e2e     # API :8001 + web :3002 on the clearday_e2e DB
    bash scripts/dev.sh e2e          # runs this script against that stack
or by hand against any running stack:
    uv run python scripts/e2e_live_pop.py --web http://localhost:3001

Exits non-zero if Jake's Rent share isn't open, the pop fails, the split fails, or the other
person's view doesn't update within the timeout.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / "e2e"
LIVE_TIMEOUT_MS = 5000


def login(page, web: str, name: str) -> None:
    page.goto(f"{web}/login")
    page.get_by_role("button", name=re.compile(rf"^{name}\b")).click()
    page.wait_for_url(re.compile(r"/sky"))
    page.get_by_role("button", name=re.compile(r"^Rent\b")).first.wait_for()


def shot(page, focus, name: str) -> None:
    """Viewport screenshot with the Rent bubble in view."""
    focus.scroll_into_view_if_needed()
    page.wait_for_timeout(400)  # let the fill animation settle
    page.screenshot(path=OUT / name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:3001")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--chromium", help="path to a Chromium binary (else Playwright's own)")
    reset = parser.add_mutually_exclusive_group()
    reset.add_argument("--no-reset", action="store_true", help="don't reset the demo first")
    reset.add_argument("--reset-db-only", action="store_true", help="reset our DB only (offline)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not args.no_reset:
        cmd = [sys.executable, "-m", "scripts.reset_demo", *(["--db-only"] if args.reset_db_only else [])]
        if subprocess.run(cmd, cwd=ROOT, check=False).returncode != 0:  # noqa: S603 (fixed argv)
            print("Demo reset failed; not running the E2E.", file=sys.stderr)
            return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, executable_path=args.chromium)
        size = {"width": 1280, "height": 860}
        maya = browser.new_context(viewport=size).new_page()  # separate contexts = separate cookies
        jake = browser.new_context(viewport=size).new_page()
        login(maya, args.web, "Maya")
        login(jake, args.web, "Jake")

        maya_rent = maya.get_by_role("button", name=re.compile(r"^Rent\b")).first
        before = maya_rent.inner_text()
        jake_rent = jake.get_by_role("button", name=re.compile(r"^Rent\b")).first
        jake_before = jake_rent.inner_text()
        shot(maya, maya_rent, "1-maya-before.png")
        shot(jake, jake_rent, "2-jake-before.png")

        jake_rent.click()
        pop = jake.get_by_role("button", name=re.compile(r"^Pop it: pay"))
        try:
            pop.wait_for(timeout=LIVE_TIMEOUT_MS)
        except PlaywrightTimeout:
            print("Jake's Rent share is not open (paid already?). Reset the demo, re-run.", file=sys.stderr)
            return 1
        pop.click()
        expect(jake_rent).not_to_have_text(jake_before, timeout=LIVE_TIMEOUT_MS)
        shot(jake, jake_rent, "3-jake-after-pop.png")

        # Maya never reloads: her Rent bubble must change from the share.updated push alone.
        expect(maya_rent).not_to_have_text(before, timeout=LIVE_TIMEOUT_MS)
        after = maya_rent.inner_text()
        shot(maya, maya_rent, "4-maya-after-live-update.png")
        print(f"Maya before: {before!r}\nMaya after:  {after!r}")

        # Maya splits a new expense with Jake; Jake's sky must gain the bubble without a reload.
        label = f"Pizza night {int(time.time()) % 100000}"
        jake_new = jake.get_by_role("button", name=re.compile(rf"^{re.escape(label)}\b"))
        expect(jake_new).to_have_count(0)
        maya.get_by_role("button", name="New shared expense").click()
        dialog = maya.get_by_role("dialog", name="New shared expense")
        dialog.get_by_label("What was it for?").fill(label)
        dialog.get_by_label("Total you paid").fill("30.00")
        dialog.get_by_label(re.compile(r"Priya")).uncheck()
        shot(maya, dialog, "5-maya-split-dialog.png")
        dialog.get_by_role("button", name=re.compile(r"^Split with 1 roommate")).click()
        expect(dialog).to_be_hidden(timeout=LIVE_TIMEOUT_MS)
        expect(jake_new.first).to_be_visible(timeout=LIVE_TIMEOUT_MS)
        shot(jake, jake_new.first, "6-jake-after-live-split.png")
        print(f"Jake's sky gained {jake_new.first.inner_text().splitlines()[:2]!r}\nScreenshots: {OUT}")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
