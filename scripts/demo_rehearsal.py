"""Pre-demo rehearsal: walks every beat of docs/06's demo script in a real browser, times each beat and
saves one screenshot per beat to logs/rehearsal/. Exits non-zero at the first beat that breaks.

Run it with `bash scripts/dev.sh rehearse`, which cold-starts the stack (down, up) and resets the demo
first. Against a stack that is already running and freshly reset:
    uv run python scripts/demo_rehearsal.py --web http://localhost:3001
Playwright is a dev dependency; once per machine: uv run playwright install chromium.

Beats: personas and the sky, Priya's tight-week forecast, Jake and Priya pop rent (Maya updates live,
voice announcement with transcript), Maya splits last night's pizza with words, receipt scan with
itemized split and price hint, duplicate subscriptions + anomaly + backtest, then list view,
reduced-motion toggle and 200% text size. Needs a model for the receipt scan; if the reader is
unavailable the beat falls back to typing items and says so (the beat still passes, marked MANUAL).
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / "rehearsal"
LIVE_MS = 8000  # a live Socket.IO update should land well inside this
SIZE = {"width": 1280, "height": 860}
PIZZA_PROMPT = "split last night's pizza with Jake and Priya"

RECEIPT_HTML = """<body style="margin:0;background:#fff"><div id=r style="width:360px;padding:20px;
font:20px monospace;background:#fff;color:#000"><div style="text-align:center;font-weight:bold">
FOOD LION</div><div style="text-align:center">{date}</div><hr>
<div>Organic Eggs ......... 4.40</div><div>Sandwich Bread ........ 3.10</div><hr>
<div>Subtotal ............. 7.50</div><div>Tax ................... 0.53</div>
<div>Tip ................... 0.00</div><div style="font-weight:bold">TOTAL ................. 8.03</div>
</div></body>"""

timings: list[tuple[str, float, str]] = []


def login(page: Page, web: str, name: str) -> None:
    page.goto(f"{web}/login")
    page.get_by_role("button", name=re.compile(rf"^{name}\b")).click()
    page.wait_for_url(re.compile(r"/sky"))
    page.get_by_role("heading", name="Upcoming bills").wait_for()  # Rent may already be popped


def set_view(page: Page, view: str) -> None:
    page.get_by_role("group", name="View").get_by_role("button", name=view).click()
    expect(page.get_by_role("group", name="View").get_by_role("button", name=view)).to_have_attribute(
        "aria-pressed", "true"
    )


def snap(page: Page, name: str, full: bool = False) -> None:
    page.wait_for_timeout(400)  # let fills and fades settle
    page.screenshot(path=OUT / f"{name}.png", full_page=full)


class Rehearsal:
    def __init__(self, web: str, headed: bool) -> None:
        self.web = web
        self.headed = headed

    def beat(self, name: str, fn: Callable[[], str | None]) -> None:
        start = time.perf_counter()
        try:
            note = fn() or ""
        except Exception as exc:
            took = time.perf_counter() - start
            timings.append((name, took, f"FAILED: {type(exc).__name__}"))
            raise
        took = time.perf_counter() - start
        timings.append((name, took, note))
        print(f"  {took:5.1f}s  {name}  {note}", flush=True)


def run(args: argparse.Namespace) -> None:
    web = args.web
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    r = Rehearsal(web, args.headed)
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch(headless=not args.headed, executable_path=args.chromium)

        def new_page(size=SIZE, **kw) -> Page:  # separate contexts = separate cookies
            return browser.new_context(viewport=size, **kw).new_page()

        maya, jake, priya = new_page(), new_page(), new_page()
        state: dict[str, str] = {}

        # 1. Personas and the sky ---------------------------------------------------------------
        def personas() -> str:
            for page, who in ((maya, "Maya"), (jake, "Jake"), (priya, "Priya")):
                login(page, web, who)
            set_view(maya, "Sky")
            expect(maya.get_by_text("Likely safe to spend until payday")).to_be_visible()
            snap(maya, "01-maya-sky")
            return "Maya, Jake, Priya signed in"

        r.beat("1 persona logins and the sky", personas)

        # 2. Priya's tight week -------------------------------------------------------------------
        def forecast() -> str:
            set_view(priya, "Sky")
            tight = priya.get_by_role("button", name=re.compile(r"^Rent\b.*likely short", re.S | re.I))
            expect(tight.first).to_be_visible()  # rent bubble in storm colors, with its text label
            priya.get_by_role("link", name="See your 30-day forecast").click()
            expect(priya.get_by_role("heading", name="Your money weather, next 30 days")).to_be_visible()
            bills = priya.get_by_role("region", name="Bills ahead")
            expect(bills).to_contain_text(re.compile(r"likely to leave you short"))
            line = (
                bills.get_by_role("listitem")
                .filter(has_text=re.compile(r"^Rent"))
                .get_by_text(re.compile(r"in 10 chance|Almost certain"))
            )
            expect(line).to_be_visible()
            state["chance"] = line.inner_text()
            snap(priya, "02-priya-forecast", full=True)
            priya.goto(f"{web}/sky")
            priya.get_by_role("button", name=re.compile(r"^Rent\b")).first.wait_for()
            return f"Priya sees: {state['chance']!r}"

        r.beat("2 Priya's tight-week forecast", forecast)

        # 3. Jake pops rent; Maya updates live ----------------------------------------------------
        def pop() -> str:
            maya_rent = maya.get_by_role("button", name=re.compile(r"^Rent\b")).first
            jake_rent = jake.get_by_role("button", name=re.compile(r"^Rent\b")).first
            maya_before, jake_before = maya_rent.inner_text(), jake_rent.inner_text()
            jake_rent.click()
            jake.get_by_role("button", name=re.compile(r"^Pop it: pay")).click()
            expect(jake_rent).not_to_have_text(jake_before, timeout=LIVE_MS)
            expect(maya_rent).not_to_have_text(maya_before, timeout=LIVE_MS)  # no reload on Maya's side
            snap(jake, "03a-jake-popped-his-share")
            snap(maya, "03b-maya-live-update")
            # Priya covers the last share: the bubble pops for everyone and the household is told.
            priya_rent = priya.get_by_role("button", name=re.compile(r"^Rent\b")).first
            priya_rent.click(force=True)  # sky bubbles float, so skip the "stable" wait
            priya.get_by_role("button", name=re.compile(r"^Pop it: pay")).click()
            voice = maya.get_by_role("region", name="Clearday Home announcement")
            expect(voice).to_contain_text("Transcript:", timeout=LIVE_MS * 2)
            transcript = voice.locator("p", has_text="Transcript:").inner_text()
            assert not re.search(r"\$|\d+\.\d\d", transcript), f"amount in the announcement: {transcript!r}"
            play = voice.get_by_role("button", name=re.compile(r"announcement", re.I))
            mode = "voice + transcript" if play.count() else "text only (voice unavailable)"
            snap(maya, "03c-maya-announcement")
            return f"{mode}: {transcript!r}"

        r.beat("3 Jake pops rent, Maya live, announcement", pop)

        # 4. The assistant splits last night's pizza -----------------------------------------------
        def pizza() -> str:
            set_view(maya, "List")
            box = maya.get_by_label("What should we split?")
            box.fill(PIZZA_PROMPT)
            maya.get_by_role("button", name="Find it").click()
            proposal = maya.get_by_role("group", name=re.compile(r"Proposed split"))
            expect(proposal).to_be_visible(timeout=45000)
            shares = proposal.get_by_role("list", name="Shares")
            for who in ("Maya", "Jake", "Priya"):
                expect(shares).to_contain_text(who)
            how = proposal.get_by_text(re.compile(r"Found by Gemma|Quick match")).inner_text()
            how = "model" if "Gemma" in how else "template fallback"
            if how != "model" and not os.environ.get("REHEARSAL_ALLOW_TEMPLATE"):
                raise AssertionError("the pizza reply came from the template fallback, not the model")
            snap(maya, "04a-maya-proposal")
            proposal.get_by_role("button", name="Confirm split").click()
            jake_new = jake.get_by_role("button", name=re.compile(r"^Franklin Street Pizza"))
            expect(jake_new.first).to_be_visible(timeout=LIVE_MS)  # Jake's sky gains it live
            snap(jake, "04b-jake-pizza-bubble")
            return f"proposal via {how}; Jake got the request bubble live"

        r.beat("4 Maya splits last night's pizza (assistant)", pizza)

        # 5. Receipt scan -------------------------------------------------------------------------
        def receipt() -> str:
            png = Path(tmp) / "receipt.png"
            page = browser.new_page()
            page.set_content(RECEIPT_HTML.format(date=dt.date.today().isoformat()))
            page.locator("#r").screenshot(path=png)
            page.close()
            set_view(maya, "Sky")
            maya.get_by_role("button", name=re.compile(r"^New shared expense")).click()
            dialog = maya.get_by_role("dialog", name="New shared expense")
            dialog.get_by_label("By item").check()
            dialog.get_by_label("Scan a receipt (optional)").set_input_files(png)
            memory = dialog.get_by_role("region", name="Price memory")
            mode = "scan"
            try:
                expect(dialog.get_by_text(re.compile(r"Read \d+ items"))).to_be_visible(timeout=60000)
                expect(memory).to_contain_text("cheaper at Harris Teeter", timeout=10000)
            except AssertionError:
                if "reader" not in dialog.inner_text().lower():
                    raise
                mode = "MANUAL (reader unavailable)"
                dialog.get_by_label("What was it for?").fill("Groceries")
                dialog.get_by_label("Item 1 name").fill("Organic Eggs")
                dialog.get_by_label("Item 1 price in dollars").fill("4.40")
                dialog.get_by_label("Tax", exact=True).fill("0.53")
            hint = memory.inner_text().replace("\n", " ") if memory.count() else "no price hint"
            first = dialog.get_by_role("group", name="Who shared item 1")
            first.get_by_label(re.compile(r"^Priya")).uncheck()  # itemized: Priya skips the eggs
            maya.keyboard.press("Tab")
            snap(maya, "05-receipt-itemized-split")
            dialog.get_by_role("button", name=re.compile(r"^Split with")).click()
            expect(dialog).to_be_hidden(timeout=10000)
            return f"{mode}; hint: {hint!r}"

        r.beat("5 receipt scan, itemized split, price hint", receipt)

        # 6. Insights: duplicates, anomaly, backtest ----------------------------------------------
        def insights() -> str:
            jake.goto(f"{web}/forecast")
            subs = jake.get_by_role("region", name="Subscriptions you may be doubling up on")
            expect(subs).to_contain_text("Spotify")
            odd = jake.get_by_role("region", name="Charges that look unusual")
            expect(odd).to_contain_text("Harris Teeter")
            expect(odd).to_contain_text("$218.00")
            back = jake.get_by_role("region", name="How the forecast has done")
            pct = back.locator("p").nth(0).inner_text()
            assert re.fullmatch(r"\d+%", pct), pct
            snap(jake, "06-insights", full=True)
            return f"Spotify duplicate, Harris Teeter $218.00, backtest {pct}"

        r.beat("6 duplicate subscriptions, anomaly, backtest", insights)

        # 7. Accessibility: list view, reduced motion, 200% text ----------------------------------
        def access() -> str:
            set_view(maya, "List")
            expect(maya.get_by_role("list", name="Bills, soonest due first")).to_be_visible()
            snap(maya, "07a-list-view")
            maya.get_by_role("button", name="Display").click()
            switch = maya.get_by_role("switch", name="Still bubbles")
            if switch.get_attribute("aria-checked") != "true":
                switch.click()
            expect(switch).to_have_attribute("aria-checked", "true")
            snap(maya, "07b-reduced-motion")
            # 200% zoom is half the CSS pixels at the same device pixels; the largest text size on top.
            zoomed = new_page({"width": 640, "height": 430}, device_scale_factor=2)
            login(zoomed, web, "Maya")
            zoomed.get_by_role("button", name="Display").click()
            zoomed.get_by_label("Largest").check()
            zoomed.keyboard.press("Escape")
            overflow = zoomed.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow <= 1, f"horizontal scroll at 200% zoom + largest text ({overflow}px)"
            expect(zoomed.get_by_role("button", name="New shared expense")).to_be_visible()
            snap(zoomed, "07c-200-percent-zoom")
            return "list view, still bubbles on, 200% zoom + Largest text without sideways scroll"

        r.beat("7 list view, reduced motion, 200% text", access)
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:3001")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--chromium", help="path to a Chromium binary (else Playwright's own)")
    args = parser.parse_args()
    print(f"Rehearsal against {args.web}", flush=True)
    start = time.perf_counter()
    try:
        run(args)
    except Exception as exc:  # noqa: BLE001 (report which beat broke, then fail)
        print(
            f"\nREHEARSAL FAILED at beat {len(timings)}: {type(exc).__name__}: {str(exc)[:600]}",
            file=sys.stderr,
        )
        return 1
    print(f"\nREHEARSAL PASSED in {time.perf_counter() - start:.0f}s; screenshots in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
