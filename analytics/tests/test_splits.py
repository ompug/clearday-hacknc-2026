"""Behavior tests for the ledger math in analytics/splits.py (docs/02-technical-spec.md, Ledger rules)."""

from __future__ import annotations

import pytest

from analytics.splits import allocate_payment, simplify_debts, split


def test_even_split_gives_leftover_cents_to_lowest_user_ids():
    # 100 / 3 = 33 r1: the tie on remainder goes to the lowest user ID, regardless of input order.
    assert split(100, "even", ["u_priya", "u_maya", "u_jake"]) == {
        "u_jake": 34,
        "u_maya": 33,
        "u_priya": 33,
    }


def test_shares_split_gives_leftover_to_largest_remainder():
    # 1001 by weights 2:1:1 -> quotas 500.5, 250.25, 250.25; the .5 remainder wins the cent.
    assert split(
        1001, "shares", ["u_jake", "u_maya", "u_priya"], weights={"u_maya": 2, "u_jake": 1, "u_priya": 1}
    ) == {
        "u_maya": 501,
        "u_jake": 250,
        "u_priya": 250,
    }


def test_shares_split_with_zero_weight_gets_nothing():
    assert split(
        999, "shares", ["u_jake", "u_maya", "u_priya"], weights={"u_maya": 1, "u_jake": 1, "u_priya": 0}
    ) == {
        "u_jake": 500,
        "u_maya": 499,
        "u_priya": 0,
    }


def test_percentage_split_ties_go_to_lowest_user_id():
    assert split(101, "percentage", ["u_maya", "u_jake"], weights={"u_maya": 50, "u_jake": 50}) == {
        "u_jake": 51,
        "u_maya": 50,
    }


def test_percentage_split_accepts_two_decimal_strings():
    # Percentages may be exact decimal strings so no float ever touches the math.
    assert split(
        10_000,
        "percentage",
        ["u_jake", "u_maya", "u_priya"],
        weights={"u_maya": "33.33", "u_jake": "33.33", "u_priya": "33.34"},
    ) == {
        "u_jake": 3333,
        "u_maya": 3333,
        "u_priya": 3334,
    }
    assert split(999, "percentage", ["u_jake", "u_maya"], weights={"u_maya": "62.5", "u_jake": "37.5"}) == {
        "u_jake": 375,
        "u_maya": 624,
    }


@pytest.mark.parametrize(
    "weights",
    [
        {"u_maya": 50, "u_jake": 40},
        {"u_maya": 0.5, "u_jake": 99.5},
        {"u_maya": "50.005", "u_jake": "49.995"},
    ],
)
def test_percentage_split_rejects_bad_percentages(weights):
    with pytest.raises(ValueError):
        split(1000, "percentage", ["u_maya", "u_jake"], weights=weights)


def test_custom_split_uses_given_cents():
    assert split(12_345, "custom", ["u_maya", "u_jake"], weights={"u_maya": 10_000, "u_jake": 2_345}) == {
        "u_jake": 2_345,
        "u_maya": 10_000,
    }


def test_custom_split_must_reconcile_to_total():
    with pytest.raises(ValueError):
        split(12_345, "custom", ["u_maya", "u_jake"], weights={"u_maya": 10_000, "u_jake": 2_344})


RECEIPT = [
    {"label": "Pizza", "amount_cents": 3_000, "user_ids": ["u_maya", "u_jake", "u_priya"]},
    {"label": "Wings", "amount_cents": 1_500, "user_ids": ["u_jake"]},
    {"label": "Salad", "amount_cents": 1_001, "user_ids": ["u_priya"]},
]


def test_itemized_split_allocates_tax_and_tip_by_item_subtotal():
    # Subtotals: maya 1000, jake 2500, priya 2001 (5501).
    # Tax 441 -> 80.17 / 200.42 / 160.41 -> 80, 201, 160 (jake has the largest remainder).
    # Tip 1000 -> 181.79 / 454.46 / 363.75 -> 182, 454, 364 (maya and priya win the 2 cents).
    assert split(
        6_942, "itemized", ["u_maya", "u_jake", "u_priya"], items=RECEIPT, tax_cents=441, tip_cents=1_000
    ) == {
        "u_jake": 3_155,
        "u_maya": 1_262,
        "u_priya": 2_525,
    }


def test_itemized_shared_item_splits_evenly_with_id_tiebreak():
    items = [{"label": "Chips", "amount_cents": 1_000, "user_ids": ["u_priya", "u_maya", "u_jake"]}]
    assert split(1_000, "itemized", ["u_maya", "u_jake", "u_priya", "u_sam"], items=items) == {
        "u_jake": 334,
        "u_maya": 333,
        "u_priya": 333,
        "u_sam": 0,
    }


def test_itemized_total_must_match_items_plus_tax_and_tip():
    with pytest.raises(ValueError):
        split(
            6_941, "itemized", ["u_maya", "u_jake", "u_priya"], items=RECEIPT, tax_cents=441, tip_cents=1_000
        )


def test_itemized_items_must_belong_to_participants():
    with pytest.raises(ValueError):
        split(6_942, "itemized", ["u_maya", "u_jake"], items=RECEIPT, tax_cents=441, tip_cents=1_000)


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        ((10.5, "even", ["u_maya"]), {}),  # money must be int cents
        ((-100, "even", ["u_maya"]), {}),  # no negative totals
        ((100, "even", []), {}),  # nobody to split with
        ((100, "even", ["u_maya", "u_maya"]), {}),  # duplicate participant
        ((100, "even", ["u_maya", "u_jake"]), {"tax_cents": 10}),  # tax only for itemized
        ((100, "shares", ["u_maya", "u_jake"]), {"weights": {"u_maya": 1}}),  # missing weight
        ((100, "shares", ["u_maya", "u_jake"]), {"weights": {"u_maya": 0, "u_jake": 0}}),
        ((100, "shares", ["u_maya", "u_jake"]), {"weights": {"u_maya": -1, "u_jake": 3}}),
        ((100, "shares", ["u_maya", "u_jake"]), {"weights": {"u_maya": 1.5, "u_jake": 1}}),
        ((100, "bogus", ["u_maya"]), {}),
    ],
)
def test_split_rejects_invalid_input(args, kwargs):
    with pytest.raises(ValueError):
        split(*args, **kwargs)


def test_zero_total_splits_to_zeros():
    assert split(0, "even", ["u_maya", "u_jake"]) == {"u_jake": 0, "u_maya": 0}


OPEN = [  # oldest first, as the ledger passes them (or in the order the user picked)
    {"share_id": "s_sept_rent", "amount_cents": 80_000},
    {"share_id": "s_electric", "amount_cents": 4_150},
]


def test_partial_payment_covers_oldest_share_first():
    assert allocate_payment(82_000, OPEN) == {
        "allocations": [
            {"share_id": "s_sept_rent", "amount_cents": 80_000},
            {"share_id": "s_electric", "amount_cents": 2_000},
        ],
        "credit_cents": 0,
    }


def test_underpayment_leaves_share_partially_covered():
    assert allocate_payment(500, OPEN) == {
        "allocations": [{"share_id": "s_sept_rent", "amount_cents": 500}],
        "credit_cents": 0,
    }


def test_overpayment_becomes_credit():
    assert allocate_payment(90_000, OPEN) == {
        "allocations": [
            {"share_id": "s_sept_rent", "amount_cents": 80_000},
            {"share_id": "s_electric", "amount_cents": 4_150},
        ],
        "credit_cents": 5_850,
    }


def test_manual_pick_order_is_respected_and_settled_shares_skipped():
    picked = [
        {"share_id": "s_electric", "amount_cents": 4_150},
        {"share_id": "s_paid", "amount_cents": 0},
        {"share_id": "s_sept_rent", "amount_cents": 80_000},
    ]
    assert allocate_payment(5_000, picked) == {
        "allocations": [
            {"share_id": "s_electric", "amount_cents": 4_150},
            {"share_id": "s_sept_rent", "amount_cents": 850},
        ],
        "credit_cents": 0,
    }


def test_payment_with_no_open_shares_is_all_credit():
    assert allocate_payment(1_234, []) == {"allocations": [], "credit_cents": 1_234}


@pytest.mark.parametrize(
    ("amount", "shares"),
    [
        (0, OPEN),
        (-100, OPEN),
        (12.5, OPEN),
        (100, [{"share_id": "s1", "amount_cents": -5}]),
        (100, [{"share_id": "s1", "amount_cents": 50}, {"share_id": "s1", "amount_cents": 50}]),
    ],
)
def test_allocate_payment_rejects_invalid_input(amount, shares):
    with pytest.raises(ValueError):
        allocate_payment(amount, shares)


# simplify_debts: positive balance = is owed money, negative = owes money.


def test_simplify_debts_pays_the_creditor_directly():
    assert simplify_debts({"u_maya": 5_000, "u_jake": -3_000, "u_priya": -2_000}) == [
        {"from": "u_jake", "to": "u_maya", "amount_cents": 3_000},
        {"from": "u_priya", "to": "u_maya", "amount_cents": 2_000},
    ]


def test_simplify_debts_ties_break_by_user_id():
    assert simplify_debts({"u_maya": 2_000, "u_priya": -1_000, "u_jake": -1_000}) == [
        {"from": "u_jake", "to": "u_maya", "amount_cents": 1_000},
        {"from": "u_priya", "to": "u_maya", "amount_cents": 1_000},
    ]


def test_simplify_debts_chains_collapse():
    # Jake owes Maya 30, Maya owes Priya 30 -> nets to one transfer Jake -> Priya.
    assert simplify_debts({"u_jake": -3_000, "u_maya": 0, "u_priya": 3_000}) == [
        {"from": "u_jake", "to": "u_priya", "amount_cents": 3_000},
    ]


@pytest.mark.parametrize(
    "balances",
    [
        {"a": 7_001, "b": 2_999, "c": -4_000, "d": -5_500, "e": -500},
        {"a": 1, "b": 1, "c": 1, "d": -3},
        {"a": 10_000, "b": -2_500, "c": -2_500, "d": -2_500, "e": -2_500},
    ],
)
def test_simplify_debts_settles_everyone_in_at_most_n_minus_1_transfers(balances):
    transfers = simplify_debts(balances)
    remaining = dict(balances)
    for t in transfers:
        assert t["amount_cents"] > 0 and type(t["amount_cents"]) is int
        remaining[t["from"]] += t["amount_cents"]
        remaining[t["to"]] -= t["amount_cents"]
    assert set(remaining.values()) == {0}
    assert len(transfers) <= len([v for v in balances.values() if v]) - 1


def test_simplify_debts_with_nothing_owed_is_empty():
    assert simplify_debts({"u_maya": 0, "u_jake": 0}) == []
    assert simplify_debts({}) == []


@pytest.mark.parametrize(
    "balances",
    [
        {"u_maya": 100, "u_jake": -99},  # must net to zero
        {"u_maya": 1.5, "u_jake": -1.5},  # integer cents only
    ],
)
def test_simplify_debts_rejects_invalid_balances(balances):
    with pytest.raises(ValueError):
        simplify_debts(balances)


def test_every_split_reconciles_to_the_cent():
    people = ["u_a", "u_b", "u_c", "u_d", "u_e"]
    for n in range(1, 6):
        group = people[:n]
        for total in range(0, 400, 7):
            even = split(total, "even", group)
            assert sum(even.values()) == total
            assert max(even.values()) - min(even.values()) <= 1
            weighted = split(total, "shares", group, weights={u: i + 1 for i, u in enumerate(group)})
            assert sum(weighted.values()) == total
