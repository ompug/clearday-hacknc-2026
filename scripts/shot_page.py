"""Screenshot one app page at 100%, 200% zoom and phone width, with the axe and AA-contrast checks.

    uv run python -m scripts.shot_page /analyst "Analyst view" [--user Maya] [--web http://localhost:3001]

Saves logs/stretch/<name>-<view>.png; exits non-zero on a critical axe violation or text below AA.
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from scripts import ui_audit

OUT = ui_audit.ROOT / "logs" / "stretch"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path")
    ap.add_argument("heading")
    ap.add_argument("--user", default="Maya")
    ap.add_argument("--web", default="http://localhost:3001")
    ap.add_argument("--wait", default=None, help="text that must be visible before the shot")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    name = args.path.strip("/").replace("/", "-")
    bad = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for view, viewport, scale in ui_audit.VIEWS:
            page = browser.new_context(viewport=viewport, device_scale_factor=scale).new_page()
            ui_audit.login(page, args.web, args.user)
            page.goto(f"{args.web}{args.path}")
            page.get_by_role("heading", name=args.heading, level=1).wait_for()
            if args.wait:
                page.get_by_text(args.wait).first.wait_for()
            page.wait_for_timeout(600)
            label = f"{name}-{view}"
            page.screenshot(path=OUT / f"{label}.png", full_page=True)
            bad += ui_audit.axe(page, label, {})
            bad += ui_audit.contrast(page, label, {})
            page.context.close()
        browser.close()
    print(f"{args.path}: {'FAIL' if bad else 'ok'}; shots in {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
