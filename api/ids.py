"""Opaque app IDs on the wire ("u_3", "acct_7"). Database keys stay integers inside the API, and
Nessie IDs never become app IDs."""

from __future__ import annotations

USER = "u"
HOUSEHOLD = "hh"
ACCOUNT = "acct"
EXPENSE = "exp"
SHARE = "sh"
BILL = "bill"  # a personal bill; the number is its transactions.id
TRANSACTION = "txn"  # an unusual charge; the number is its transactions.id
SUBSCRIPTION = "sub"  # a predicted recurring charge; the number is its latest transactions.id


def encode(prefix: str, pk: int) -> str:
    return f"{prefix}_{pk}"


def decode(prefix: str, value: object) -> int | None:
    """The integer key, or None if the value isn't this kind of ID."""
    if not isinstance(value, str) or not value.startswith(f"{prefix}_"):
        return None
    digits = value[len(prefix) + 1 :]
    if not digits.isascii() or not digits.isdigit() or len(digits) > 18:
        return None
    return int(digits)
