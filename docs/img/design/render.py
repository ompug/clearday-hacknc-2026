"""Render every docs/img/design/*.html to a 1600x900 PNG next to it."""
from pathlib import Path

from playwright.sync_api import sync_playwright

here = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    for f in sorted(here.glob("*.html")):
        pg.goto(f.as_uri())
        pg.screenshot(path=str(f.with_suffix(".png")))
    b.close()
