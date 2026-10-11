"""Live end to end: insight cards on the forecast page (unusual charges, price memory).

Jake opens the forecast and must see the planted unusual Harris Teeter charge; screenshots land in
logs/e2e/. Needs the API and web running against a seeded DB:
    uv run python scripts/e2e_insights.py --web http://localhost:3001
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parent.parent / "logs" / "e2e"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:3001")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": 1100, "height": 1500}).new_page()
        page.goto(f"{args.web}/login")
        page.get_by_role("button", name=re.compile(r"^Jake\b")).click()
        page.wait_for_url(re.compile(r"/sky"))
        page.goto(f"{args.web}/forecast")
        section = page.get_by_role("region", name="Charges that look unusual")
        expect(section).to_contain_text("Harris Teeter")
        expect(section).to_contain_text("$218.00")
        section.scroll_into_view_if_needed()
        section.screenshot(path=OUT / "insights_anomaly.png")
        page.screenshot(path=OUT / "insights_forecast_full.png", full_page=True)
        browser.close()
    print("insights e2e ok; screenshots in logs/e2e/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
