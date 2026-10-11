"""UI audit: screenshots of the sky, the split dialog and the forecast at 100% zoom, 200% zoom and
phone width, plus an axe-core scan of each. axe is injected from cdnjs at run time (it is not a
project dependency). axe can't judge text over glass (blur and gradients), so each view also gets a
pixel check: text is made transparent, the page is screenshotted, and every text element's colour is
compared against the worst background pixel behind it (WCAG AA: 4.5:1, 3:1 for large text).
Screenshots, axe-results.json and contrast-results.json land in logs/ui-audit/.

Works against the mock web app or a live stack, e.g.:
    NEXT_PUBLIC_USE_MOCKS=1 npm run dev            # in web/
    uv run python scripts/ui_audit.py --web http://localhost:3000

Exits non-zero if axe reports any critical violation or any text fails AA contrast.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "logs" / "ui-audit"
AXE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"

# name, viewport, device scale. "200%" zoom = half the CSS viewport at 2x pixels, which is what the
# browser's zoom does to layout (a 1280px window at 200% lays out at 640 CSS px).
VIEWS = [
    ("desktop-100", {"width": 1280, "height": 860}, 1),
    ("desktop-200", {"width": 640, "height": 430}, 2),
    ("phone", {"width": 390, "height": 844}, 3),
]


# The Next.js dev-mode badge floats over the page; it isn't part of the app.
HIDE_DEV_OVERLAY_JS = """
() => {
  const s = document.createElement('style');
  s.textContent = 'nextjs-portal { display: none !important; }';
  document.head.append(s);
}
"""


def login(page, web: str, name: str) -> None:
    page.add_init_script(f"addEventListener('DOMContentLoaded', {HIDE_DEV_OVERLAY_JS.strip()})")
    page.goto(f"{web}/login")
    page.get_by_role("button", name=re.compile(rf"^{name}\b")).click()
    page.wait_for_url(re.compile(r"/sky"))
    page.get_by_role("button", name="New shared expense").wait_for()


def axe(page, label: str, results: dict) -> int:
    page.add_script_tag(url=AXE_URL)
    report = page.evaluate(
        "async () => await axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21aa','best-practice']})"
    )
    found = [
        {
            "id": v["id"],
            "impact": v["impact"],
            "help": v["help"],
            "targets": [n["target"] for n in v["nodes"]][:5],
        }
        for v in report["violations"]
    ]
    results[label] = found
    critical = sum(1 for v in found if v["impact"] == "critical")
    summary = ", ".join(f"{v['id']}({v['impact']})" for v in found) or "none"
    print(f"  axe {label}: {summary}")
    return critical


# Text-bearing elements under `root`: rect, colour and whether WCAG counts the text as large.
COLLECT_TEXT_JS = """
([root, page]) => {
  const sx = page ? scrollX : 0, sy = page ? scrollY : 0;
  const scope = root ? document.querySelector(root) : document.body;
  const out = [];
  for (const el of scope.querySelectorAll('*')) {
    if (el.closest('svg, [aria-hidden="true"], .sr-only')) continue;
    const texts = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
    const field = el.tagName === 'INPUT' && /^(text|date|number|email|search|tel|url|)$/.test(el.type)
      && el.value;
    if (!texts.length && !field) continue;
    const vis = { opacityProperty: true, visibilityProperty: true, contentVisibilityAuto: true };
    if (!el.checkVisibility(vis)) continue;
    const cs = getComputedStyle(el);
    // Tight box: the text's own line boxes, or an input's content box, so padding, rounded corners
    // and neighbouring controls don't count as "background".
    let r;
    if (texts.length) {
      const range = document.createRange();
      range.setStartBefore(texts[0]);
      range.setEndAfter(texts[texts.length - 1]);
      r = range.getBoundingClientRect();
    } else {
      const b = el.getBoundingClientRect(), px = v => parseFloat(cs[v]);
      const left = px('paddingLeft') + px('borderLeftWidth'), top = px('paddingTop') + px('borderTopWidth');
      r = { left: b.left + left, top: b.top + top,
            width: b.width - left - px('paddingRight') - px('borderRightWidth'),
            height: b.height - top - px('paddingBottom') - px('borderBottomWidth') };
    }
    if (r.width < 2 || r.height < 2) continue;
    // Skip text scrolled out of a modal's view; a clipped line has no visible background to judge.
    const clip = root && scope.getBoundingClientRect();
    if (clip && (r.top < clip.top || r.top + r.height > clip.bottom)) continue;
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 700;
    out.push({
      text: (texts.length ? el.textContent : el.value).trim().slice(0, 40),
      color: cs.color,
      large: size >= 24 || (bold && size >= 18.66),
      x: r.left + sx, y: r.top + sy, w: r.width, h: r.height,
    });
  }
  return out;
}
"""

# Worst-case contrast of each element's colour against the pixels behind it in a text-free shot.
CONTRAST_JS = """
async ([png, items, cssWidth]) => {
  const img = new Image();
  img.src = 'data:image/png;base64,' + png;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const k = img.width / cssWidth;
  const lin = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  const lum = (r, g, b) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  return items.map(it => {
    const [r, g, b, a = 1] = it.color.match(/[\\d.]+/g).map(Number);
    const x0 = Math.max(0, Math.floor(it.x * k)), y0 = Math.max(0, Math.floor(it.y * k));
    const w = Math.min(c.width - x0, Math.ceil(it.w * k)), h = Math.min(c.height - y0, Math.ceil(it.h * k));
    if (w <= 0 || h <= 0) return { ...it, ratio: null };
    const px = ctx.getImageData(x0, y0, w, h).data;
    const ratios = [];
    const step = Math.max(1, Math.floor((w * h) / 4000));
    for (let i = 0; i < px.length; i += 4 * step) {
      // Blend translucent text over this pixel, as the browser would.
      const fr = r * a + px[i] * (1 - a), fg = g * a + px[i + 1] * (1 - a), fb = b * a + px[i + 2] * (1 - a);
      ratios.push(ratio(lum(fr, fg, fb), lum(px[i], px[i + 1], px[i + 2])));
    }
    ratios.sort((p, q) => p - q);
    // 2nd percentile: ignores a stray border or focus-ring pixel at the edge of the box.
    return { ...it, ratio: Math.round(ratios[Math.floor(ratios.length * 0.02)] * 100) / 100 };
  });
}
"""

HIDE_TEXT_CSS = (
    "*, *::placeholder { color: transparent !important; -webkit-text-fill-color: transparent !important;"
    " text-shadow: none !important; caret-color: transparent !important; }"
    " svg, input[type=checkbox], input[type=radio] { visibility: hidden !important; }"
)


def contrast(page, label: str, results: dict, root: str | None = None) -> int:
    full = root is None  # a modal is fixed to the viewport, so shoot just the viewport for it
    items = page.evaluate(COLLECT_TEXT_JS, [root, full])
    css_width = page.evaluate("document.documentElement.scrollWidth" if full else "innerWidth")
    style = page.add_style_tag(content=HIDE_TEXT_CSS)
    page.wait_for_timeout(100)
    png = base64.b64encode(page.screenshot(full_page=full, animations="disabled")).decode()
    style.evaluate("el => el.remove()")
    measured = page.evaluate(CONTRAST_JS, [png, items, css_width])
    failing = [
        {k: m[k] for k in ("text", "color", "large", "ratio")}
        for m in measured
        if m["ratio"] is not None and m["ratio"] < (3.0 if m["large"] else 4.5)
    ]
    worst = min((m["ratio"] for m in measured if m["ratio"] is not None), default=None)
    results[label] = {"checked": len(measured), "worst": worst, "failing": failing}
    print(f"  contrast {label}: {len(measured)} texts, worst {worst}:1, {len(failing)} below AA")
    for f in failing[:8]:
        print(f"    {f['ratio']}:1 {f['text']!r} ({f['color']})")
    return len(failing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--web", default="http://localhost:3001")
    parser.add_argument("--user", default="Maya")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    contrast_results: dict = {}
    critical = 0
    low_contrast = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, viewport, scale in VIEWS:
            print(name)
            page = browser.new_context(viewport=viewport, device_scale_factor=scale).new_page()
            login(page, args.web, args.user)
            page.wait_for_timeout(400)
            page.screenshot(path=OUT / f"{name}-sky.png", full_page=True)
            critical += axe(page, f"{name}-sky", results)
            low_contrast += contrast(page, f"{name}-sky", contrast_results)

            page.get_by_role("button", name="New shared expense").click()
            dialog = page.get_by_role("dialog", name="New shared expense")
            dialog.get_by_label("What was it for?").fill("Pizza night")
            dialog.get_by_label("Total you paid").fill("10.00")
            page.wait_for_timeout(200)
            dialog.get_by_label("Custom amounts").check()
            page.wait_for_timeout(200)
            page.screenshot(path=OUT / f"{name}-split.png")
            critical += axe(page, f"{name}-split", results)
            low_contrast += contrast(page, f"{name}-split", contrast_results, "dialog[open]")
            dialog.get_by_role("button", name="Cancel").click()

            page.goto(f"{args.web}/forecast")
            page.get_by_role("heading", name="Bills ahead").wait_for()
            page.wait_for_timeout(400)
            page.screenshot(path=OUT / f"{name}-forecast.png", full_page=True)
            critical += axe(page, f"{name}-forecast", results)
            low_contrast += contrast(page, f"{name}-forecast", contrast_results)
            page.context.close()
        browser.close()

    (OUT / "axe-results.json").write_text(json.dumps(results, indent=2))
    (OUT / "contrast-results.json").write_text(json.dumps(contrast_results, indent=2))
    print(f"critical axe violations: {critical}; text below AA on glass: {low_contrast}")
    print(f"screenshots in {OUT.relative_to(ROOT)}")
    return 1 if critical or low_contrast else 0


if __name__ == "__main__":
    sys.exit(main())
