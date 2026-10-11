"""Render thumbnail.html to ../devpost-thumbnail.png (1200x800)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

here = Path(__file__).resolve().parent
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 800}, device_scale_factor=1)
    pg.goto((here / "thumbnail.html").as_uri())
    pg.screenshot(path=str(here.parent / "devpost-thumbnail.png"))
    b.close()
