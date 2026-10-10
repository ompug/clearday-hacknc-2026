"""Splits and ledger math (contract stub; will become the real implementation).

Decision: Clearday implements this module for real (it is the ledger), with
tests. Until then this stub honors the contract shapes.

Contract (docs/02-technical-spec.md, Analytics contracts):

    split(total_cents, method, participants, weights=None, items=None,
          tax_cents=0, tip_cents=0) -> {user_id: cents}   # values always sum to total_cents
    allocate_payment(amount_cents, open_shares) -> {"allocations": [{"share_id", "amount_cents"}],
      "credit_cents"}
    simplify_debts(balances) -> [{"from", "to", "amount_cents"}]
"""

from __future__ import annotations


def split(total_cents, method, participants, weights=None, items=None, tax_cents=0, tip_cents=0):
    people = sorted(participants)
    base, extra = divmod(int(total_cents), len(people))
    return {u: base + (1 if i < extra else 0) for i, u in enumerate(people)}


def allocate_payment(amount_cents, open_shares):
    left, allocations = int(amount_cents), []
    for share in open_shares:
        take = min(left, int(share["amount_cents"]))
        if take > 0:
            allocations.append({"share_id": share["share_id"], "amount_cents": take})
            left -= take
    return {"allocations": allocations, "credit_cents": left}


def simplify_debts(balances):
    return []
