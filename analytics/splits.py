"""Splits and ledger math: the real implementation (owned by the app, not the stats stubs).

Contract (docs/02-technical-spec.md, Analytics contracts):

    split(total_cents, method, participants, weights=None, items=None,
          tax_cents=0, tip_cents=0) -> {user_id: cents}   # values always sum to total_cents
    allocate_payment(amount_cents, open_shares) -> {"allocations": [{"share_id", "amount_cents"}],
      "credit_cents"}
    simplify_debts(balances) -> [{"from", "to", "amount_cents"}]

All money is integer cents and every computation is integer arithmetic.
Leftover cents go out by the largest-remainder method, ties broken by user ID.
"""

from __future__ import annotations

import re

_PERCENT = re.compile(r"^(\d{1,3})(?:\.(\d{1,2}))?$")
HUNDRED_PERCENT_BP = 10_000  # 100% in basis points (hundredths of a percent)


def _basis_points(percent) -> int:
    """Parse an int or a decimal string with up to 2 places into basis points, exactly."""
    if isinstance(percent, bool):
        raise ValueError("percentage must be an int or a decimal string")
    if isinstance(percent, int):
        return percent * 100
    match = _PERCENT.match(percent) if isinstance(percent, str) else None
    if not match:
        raise ValueError(f"percentage must be an int or a string like '33.33', got {percent!r}")
    whole, frac = match.groups()
    return int(whole) * 100 + int((frac or "0").ljust(2, "0"))


def _cents(value) -> int:
    """Accept only real ints (never bool or float) as money."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"money must be integer cents, got {value!r}")
    if value < 0:
        raise ValueError(f"money must not be negative, got {value!r}")
    return value


def _largest_remainder(total_cents: int, weights: dict) -> dict:
    """Split ``total_cents`` in proportion to integer ``weights`` exactly."""
    weight_sum = sum(weights.values())
    base, remainders = {}, {}
    for user, weight in weights.items():
        base[user], remainders[user] = divmod(total_cents * weight, weight_sum)
    leftover = total_cents - sum(base.values())
    for user in sorted(weights, key=lambda u: (-remainders[u], u))[:leftover]:
        base[user] += 1
    return base


def _itemized(total_cents: int, people: list, items: list, tax_cents: int, tip_cents: int) -> dict:
    """Each item splits evenly among its user_ids; tax and tip follow item subtotals."""
    subtotals = dict.fromkeys(people, 0)
    for item in items:
        owners = list(item["user_ids"])
        if not owners or any(u not in subtotals for u in owners):
            raise ValueError(f"item {item.get('label', '')!r} has users outside the participants")
        for user, cents in _largest_remainder(_cents(item["amount_cents"]), dict.fromkeys(owners, 1)).items():
            subtotals[user] += cents
    if sum(subtotals.values()) + tax_cents + tip_cents != total_cents:
        raise ValueError("itemized total must equal items + tax + tip")
    basis = subtotals if any(subtotals.values()) else dict.fromkeys(people, 1)
    result = dict(subtotals)
    for extra in (tax_cents, tip_cents):
        for user, cents in _largest_remainder(extra, basis).items():
            result[user] += cents
    return result


def split(total_cents, method, participants, weights=None, items=None, tax_cents=0, tip_cents=0):
    total_cents = _cents(total_cents)
    people = list(participants)
    if not people or len(set(people)) != len(people):
        raise ValueError("participants must be non-empty and unique")
    if method != "itemized" and (tax_cents or tip_cents):
        raise ValueError("tax_cents and tip_cents apply only to itemized splits")
    if method in ("percentage", "custom", "shares"):
        if not weights or any(u not in weights for u in people):
            raise ValueError(f"{method} split needs a weight for every participant")
    if method == "even":
        shares = _largest_remainder(total_cents, dict.fromkeys(people, 1))
    elif method == "percentage":
        bp = {u: _basis_points(weights[u]) for u in people}
        if sum(bp.values()) != HUNDRED_PERCENT_BP:
            raise ValueError("percentages must sum to exactly 100")
        shares = _largest_remainder(total_cents, bp)
    elif method == "custom":
        shares = {u: _cents(weights[u]) for u in people}
        if sum(shares.values()) != total_cents:
            raise ValueError("custom amounts must sum to total_cents")
    elif method == "shares":
        units = {u: _cents(weights[u]) for u in people}  # integer weights, same checks as cents
        if not any(units.values()):
            raise ValueError("shares weights must not all be zero")
        shares = _largest_remainder(total_cents, units)
    elif method == "itemized":
        shares = _itemized(total_cents, people, items or [], _cents(tax_cents), _cents(tip_cents))
    else:
        raise ValueError(f"unknown split method: {method!r}")
    return {u: shares[u] for u in sorted(people)}


def allocate_payment(amount_cents, open_shares):
    """Apply a payment to ``open_shares`` in the given order, overflow becoming credit.

    ``open_shares`` is [{"share_id", "amount_cents"}] where amount_cents is what is still
    owed. The caller passes them oldest first, or in the order the user picked. A share
    that receives less than it owes stays ``partial``; the ledger derives that status.
    """
    left = _cents(amount_cents)
    if left == 0:
        raise ValueError("payment must be positive")
    seen, allocations = set(), []
    for share in open_shares:
        share_id, owed = share["share_id"], _cents(share["amount_cents"])
        if share_id in seen:
            raise ValueError(f"duplicate share_id {share_id!r}")
        seen.add(share_id)
        take = min(left, owed)
        if take > 0:
            allocations.append({"share_id": share_id, "amount_cents": take})
            left -= take
    return {"allocations": allocations, "credit_cents": left}


def simplify_debts(balances):
    """Settle up with few transfers. ``balances`` maps user_id to net cents:
    positive means the household owes them, negative means they owe.

    Greedy: the largest debtor pays the largest creditor, ties broken by user ID.
    This needs at most (people with a nonzero balance - 1) transfers.
    """
    for user, cents in balances.items():
        if isinstance(cents, bool) or not isinstance(cents, int):
            raise ValueError(f"balance for {user!r} must be integer cents")
    if sum(balances.values()) != 0:
        raise ValueError("balances must net to zero")
    owed = {u: c for u, c in balances.items() if c > 0}
    owes = {u: -c for u, c in balances.items() if c < 0}
    transfers = []
    while owes:
        debtor = min(owes, key=lambda u: (-owes[u], u))
        creditor = min(owed, key=lambda u: (-owed[u], u))
        amount = min(owes[debtor], owed[creditor])
        transfers.append({"from": debtor, "to": creditor, "amount_cents": amount})
        for side, user in ((owes, debtor), (owed, creditor)):
            side[user] -= amount
            if side[user] == 0:
                del side[user]
    return transfers
