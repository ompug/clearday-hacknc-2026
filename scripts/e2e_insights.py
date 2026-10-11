"""Live end to end: insight cards on the forecast page (unusual charges, price memory).

Jake opens the forecast and must see the planted unusual Harris Teeter charge; screenshots land in
logs/e2e/. Needs the API and web running against a seeded DB:
    uv run python scripts/e2e_insights.py --web http://localhost:3001
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path(__file__).resolve().parent.parent / "logs" / "e2e"

RECEIPT_HTML = """<body style="margin:0;background:#fff"><div id=r style="width:360px;padding:20px;
font:20px monospace;background:#fff;color:#000"><div style="text-align:center;font-weight:bold">
FOOD LION</div><div style="text-align:center">{date}</div><hr>
<div>Organic Eggs ......... 4.40</div><div>Sandwich Bread ........ 3.10</div><hr>
<div>Subtotal ............. 7.50</div><div>Tax ................... 0.53</div>
<div>Tip ................... 0.00</div><div style="font-weight:bold">TOTAL ................. 8.03</div>
</div></body>"""


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
        # Price memory: Maya scans a Food Lion receipt; eggs were cheaper at Harris Teeter last week.
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.png"
            shot = browser.new_page()
            shot.set_content(RECEIPT_HTML.format(date=dt.date.today().isoformat()))
            shot.locator("#r").screenshot(path=receipt)
            maya = browser.new_context(viewport={"width": 1100, "height": 1500}).new_page()
            maya.goto(f"{args.web}/login")
            maya.get_by_role("button", name=re.compile(r"^Maya\b")).click()
            maya.wait_for_url(re.compile(r"/sky"))
            maya.get_by_role("button", name=re.compile(r"^New shared expense")).click()
            dialog = maya.get_by_role("dialog", name="New shared expense")
            dialog.get_by_label("By item").check()
            dialog.get_by_label("Scan a receipt (optional)").set_input_files(receipt)
            memory = dialog.get_by_role("region", name="Price memory")
            expect(memory).to_contain_text("cheaper at Harris Teeter", timeout=60000)
            expect(memory).to_contain_text("$0.60")
            dialog.screenshot(path=OUT / "insights_price_memory.png")
        browser.close()
    print("insights e2e ok; screenshots in logs/e2e/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
