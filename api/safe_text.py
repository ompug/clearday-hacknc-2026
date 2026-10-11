"""One normaliser for display text that must never carry an amount or a link.

Used by the AI gateway (`safe_reply`) and the feed (labels). Allowlist design: after NFKC
normalisation, the only number-like content allowed is a bare count 1-9 directly followed by a count
noun ("3 ways", "2 bills"). Anything else that could spell an amount (any digit in any script, numeral
or fraction characters, currency symbols, currency words and codes, number words in a money context)
or a link (scheme:, //, domain-like token, markdown link, markup, @) makes `is_safe` false.
"""

from __future__ import annotations

import re
import unicodedata

# The only digits allowed: one 1-9 standing alone, followed by a count noun.
SMALL_COUNT = re.compile(
    r"(?<![\w.,:/$-])[1-9]\s(?:ways?|bills?|roommates?|people|persons?|shares?|bubbles?|purchases?|"
    r"days?|weeks?|months?|expenses?)\b",
    re.IGNORECASE,
)
CURRENCY_WORD = re.compile(
    r"\b(?:dollars?|bucks?|cents?|penn(?:y|ies)|euros?|pounds?|quid|yen|yuan|rupees?|pesos?|francs?|"
    r"usd|eur|gbp|jpy|cny|rmb|inr|cad|aud|nzd|chf|mxn|krw|btc|eth|usdc)\b",
    re.IGNORECASE,
)
# Number words that are never needed in a short reply about splitting.
BIG_NUMBER_WORD = re.compile(
    r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
    r"forty|fourty|fifty|sixty|seventy|eighty|ninety|hundreds?|thousands?|millions?|billions?|dozens?|"
    r"grand)\b",
    re.IGNORECASE,
)
# A small number word next to a money verb or "each" ("Each pays five", "You owe two", "nine each").
SMALL_NUMBER_WORD = r"(?:one|two|three|four|five|six|seven|eight|nine|zero)"
MONEY_CONTEXT = re.compile(
    rf"\b(?:pays?|paid|owes?|owed|costs?|is|was|are|be|of|for|at|about|around|totals?)\s+{SMALL_NUMBER_WORD}\b"
    rf"|\b{SMALL_NUMBER_WORD}\s+(?:each|apiece|total|per|a\s+head|in\s+total)\b",
    re.IGNORECASE,
)
LINK = re.compile(
    r"[<>@\[\]]"  # markup, emails, markdown link syntax
    r"|//"  # scheme-relative and http(s)://
    r"|\b[a-z][a-z0-9+.-]*:(?=\S)"  # any scheme: javascript:, mailto:, data:, https:
    r"|\bwww\b"
    r"|\w\.[^\W\d_]{2,}"  # domain-like token: evil.ru, x.co, evil.com
    r"|\b(?:u|hh|acct|exp|sh|bill|txn|sub|pay)_\w*",  # raw app IDs
    re.IGNORECASE,
)


def normalise(text: str | None) -> str:
    """NFKC, control/format/separator characters as spaces, single spaces."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    return " ".join("".join(" " if unicodedata.category(c)[0] in "CZ" else c for c in text).split())


def is_safe(text: str) -> bool:
    """True when normalised `text` has no amount-like content and no link-like token."""
    if LINK.search(text) or CURRENCY_WORD.search(text) or BIG_NUMBER_WORD.search(text):
        return False
    if MONEY_CONTEXT.search(text):
        return False
    rest = SMALL_COUNT.sub(" ", text)
    return not any(unicodedata.category(c) == "Sc" or unicodedata.category(c)[0] == "N" for c in rest)


def clean(text: str | None) -> str | None:
    """Normalised `text`, or None if it is empty or could carry an amount or a link. Numeral and
    fraction characters (Roman numerals, circled digits) are checked before NFKC turns them into letters."""
    raw = str(text or "")
    if any(unicodedata.category(c) in ("Nl", "No") for c in raw):
        return None
    out = normalise(raw)
    return out if out and is_safe(out) else None


def safe_label(text: str | None, fallback: str, max_len: int) -> str:
    """A label to show, or `fallback` if it could carry an amount or link."""
    out = clean(text)
    return out[:max_len].strip() if out else fallback
