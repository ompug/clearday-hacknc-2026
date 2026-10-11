"""Live end to end: itemized split from a receipt photo. Maya opens New shared expense, picks By
item, uploads a synthetic receipt image (generated here, no personal data), checks the items the
model read, assigns one item, and saves. Falls back to typing items by hand when the reader is
unavailable (that path is exercised too with --manual). Screenshots land in logs/e2e/.

Needs the API and web running against a seeded DB:
    uv run python scripts/e2e_receipt.py --web http://localhost:3001 [--manual]
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / "e2e"

RECEIPT_HTML = """<body style="margin:0;background:#fff"><div id=r style="width:360px;padding:20px;
font:20px monospace;background:#fff;color:#000"><div style="text-align:center;font-weight:bold">
SUNNY SLICE PIZZERIA</div><div style="text-align:center">2026-10-09</div><hr>
<div>Large Pepperoni ....... 18.50</div><div>Garden Salad .......... 7.25</div>
<div>Garlic Knots .......... 5.00</div><div>Lemonade x2 ........... 6.00</div><hr>
<div>Subtotal ............. 36.75</div><div>Tax ................... 2.57</div>
<div>Tip ................... 7.00</div><div style="font-weight:bold">TOTAL ................. 46.32</div>
</div></body>"""


def make_receipt(page, path: Path) -> None:
    page.set_content(RECEIPT_HTML)
    page.locator("#r").screenshot(path=path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:3001")
    parser.add_argument("--manual", action="store_true", help="skip the scan and type the items")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        receipt = Path(tmp) / "receipt.png"
        make_receipt(browser.new_page(), receipt)
        page = browser.new_context(viewport={"width": 1100, "height": 1500}).new_page()
        page.goto(f"{args.web}/login")
        page.get_by_role("button", name=re.compile(r"^Maya\b")).click()
        page.wait_for_url(re.compile(r"/sky"))
        page.get_by_role("button", name=re.compile(r"^New shared expense")).click()
        dialog = page.get_by_role("dialog", name="New shared expense")
        dialog.get_by_label("By item").check()
        if args.manual:
            dialog.get_by_label("What was it for?").fill("Pizza night")
            dialog.get_by_label("Item 1 name").fill("Pizza")
            dialog.get_by_label("Item 1 price in dollars").fill("18.50")
            dialog.get_by_label("Tax", exact=True).fill("1.50")
        else:
            dialog.get_by_label("Scan a receipt (optional)").set_input_files(receipt)
            expect(dialog.get_by_text(re.compile(r"Read \d+ items"))).to_be_visible(timeout=60000)
            expect(dialog.get_by_label("Item 1 name")).to_have_value(re.compile("Pepperoni", re.I))
        # Everyone shares everything by default; Jake alone ate item 1.
        first = dialog.get_by_role("group", name="Who shared item 1")
        for name in ("You", "Priya"):
            first.get_by_label(re.compile(rf"^{name}")).uncheck()
        page.keyboard.press("Tab")
        dialog.screenshot(path=OUT / ("receipt-manual.png" if args.manual else "receipt-scan.png"))
        dialog.get_by_role("button", name=re.compile(r"^Split with")).click()
        page.wait_for_url(re.compile(r"/sky"))
        expect(dialog).to_be_hidden(timeout=10000)
        print("itemized split saved")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
