"""Dollars <-> cents. The ONLY place in the codebase where Nessie dollar amounts convert.

Nessie stores purchase, deposit and transfer amounts (and account balances) as integer dollars and
silently truncates anything else (12.34 becomes 12). Only bill ``payment_amount`` keeps cents, as a
float. So: non-bill amounts must be whole dollars on the way out (we refuse instead of losing cents),
and bill floats are rounded to the nearest cent on the way in.
"""

from __future__ import annotations

CENTS_PER_DOLLAR = 100


class LossyAmountError(ValueError):
    """The amount can't be sent to Nessie without losing cents."""


def _require_cents(cents: int) -> int:
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TypeError(f"money must be integer cents, got {type(cents).__name__}")
    if cents < 0:
        raise ValueError("amounts sent to Nessie must not be negative")
    return cents


def cents_to_whole_dollars(cents: int) -> int:
    """Outgoing purchase/deposit/transfer amount or opening balance. Refuses partial dollars."""
    dollars, rem = divmod(_require_cents(cents), CENTS_PER_DOLLAR)
    if rem:
        raise LossyAmountError("Nessie truncates non-bill amounts to whole dollars; send a multiple of 100")
    return dollars


def whole_dollars_to_cents(dollars: int | float) -> int:
    """Incoming purchase/deposit/transfer amount or balance (Nessie returns ints; tolerate 12.0)."""
    if isinstance(dollars, bool) or not isinstance(dollars, int | float):
        raise TypeError(f"expected a number of dollars, got {type(dollars).__name__}")
    if isinstance(dollars, float):
        if not dollars.is_integer():
            raise LossyAmountError("expected whole dollars from Nessie")
        dollars = int(dollars)
    return dollars * CENTS_PER_DOLLAR


def cents_to_bill_amount(cents: int) -> float:
    """Outgoing bill payment_amount (a float with cents on the wire)."""
    dollars, rem = divmod(_require_cents(cents), CENTS_PER_DOLLAR)
    return float(f"{dollars}.{rem:02d}")


def bill_amount_to_cents(amount: int | float) -> int:
    """Incoming bill payment_amount; rounds float noise (84.37 -> 8437) to the nearest cent."""
    if isinstance(amount, bool) or not isinstance(amount, int | float):
        raise TypeError(f"expected a bill amount, got {type(amount).__name__}")
    return round(amount * CENTS_PER_DOLLAR)
