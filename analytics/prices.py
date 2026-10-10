"""STUB: receipt price memory.

Contract (docs/02-technical-spec.md, Analytics contracts):

    normalize(raw_label) -> str
    compare(normalized_name, history) -> {"item", "best": {"merchant", "date", "unit_price_cents"},
      "latest": {"merchant", "date", "unit_price_cents"}, "savings_cents_per_unit"}

``history`` rows have "merchant", "date", "unit_price_cents" and either
"normalized_name" or "raw_label". "best"/"latest" are None when nothing matches.
"""

from __future__ import annotations

import re

from analytics._common import records

ABBREVIATIONS = {
    "org": "organic",
    "whl": "whole",
    "mlk": "milk",
    "bnls": "boneless",
    "chkn": "chicken",
    "brst": "breast",
    "ppr": "paper",
    "twl": "towels",
    "towel": "towels",
}
SIZE_TOKEN = re.compile(r"^\d+(\.\d+)?(gal|lb|oz|pk|ct|g|kg|l|ml)?$")
UNIT_WORDS = {"gal", "lb", "oz", "pk", "ct", "each"}


def normalize(raw_label):
    words = re.sub(r"[^a-z0-9. ]+", " ", str(raw_label).lower()).split()
    kept = []
    for word in words:
        if SIZE_TOKEN.match(word) or word in UNIT_WORDS:
            continue
        kept.append(ABBREVIATIONS.get(word, word))
    return " ".join(kept)


def compare(normalized_name, history):
    matches = []
    for r in records(history):
        name = r.get("normalized_name") or normalize(r.get("raw_label", ""))
        if name == normalized_name:
            matches.append(
                {
                    "merchant": str(r["merchant"]),
                    "date": str(r["date"])[:10],
                    "unit_price_cents": int(r["unit_price_cents"]),
                }
            )
    if not matches:
        return {"item": normalized_name, "best": None, "latest": None, "savings_cents_per_unit": 0}
    best = min(matches, key=lambda m: (m["unit_price_cents"], m["date"], m["merchant"]))
    latest = max(matches, key=lambda m: (m["date"], m["merchant"]))
    return {
        "item": normalized_name,
        "best": best,
        "latest": latest,
        "savings_cents_per_unit": latest["unit_price_cents"] - best["unit_price_cents"],
    }
