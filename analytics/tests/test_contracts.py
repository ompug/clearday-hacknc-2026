"""Contract tests: every analytics module must keep these signatures and output shapes.

Stubs and the real modules must both pass this file unchanged
(see "Analytics contracts" in docs/02-technical-spec.md).
"""

from __future__ import annotations

import inspect
import json

import pandas as pd
import pytest

from analytics import (
    backtest,
    categorize,
    cohorts,
    detection,
    forecast,
    prices,
    splits,
    synthetic_data,
)

TXN_COLUMNS = [
    "transaction_id",
    "user_id",
    "account_id",
    "date",
    "amount_cents",
    "kind",
    "category",
    "merchant",
    "status",
]

SIGNATURES = {
    (synthetic_data, "generate"): ["seed=42", "days=60"],
    (forecast, "forecast"): [
        "transactions",
        "scheduled",
        "start_balance_cents",
        "start_date",
        "horizon_days=30",
        "n_paths=1000",
        "threshold_cents=5000",
        "seed=0",
    ],
    (categorize, "tag_needs"): ["transactions"],
    (categorize, "detect_income"): ["transactions"],
    (detection, "detect_recurring"): ["transactions"],
    (detection, "detect_anomalies"): ["transactions"],
    (detection, "duplicate_subscriptions"): ["household_transactions"],
    (splits, "split"): [
        "total_cents",
        "method",
        "participants",
        "weights=None",
        "items=None",
        "tax_cents=0",
        "tip_cents=0",
    ],
    (splits, "allocate_payment"): ["amount_cents", "open_shares"],
    (splits, "simplify_debts"): ["balances"],
    (prices, "normalize"): ["raw_label"],
    (prices, "compare"): ["normalized_name", "history"],
    (cohorts, "generate"): ["n=200", "seed=42"],
    (cohorts, "segment_rates"): ["forecasts_by_household", "households"],
    (backtest, "run"): ["transactions", "scheduled", "holdout_days=30", "seed=0"],
}


def _params(fn) -> list[str]:
    out = []
    for p in inspect.signature(fn).parameters.values():
        out.append(p.name if p.default is inspect.Parameter.empty else f"{p.name}={p.default!r}")
    return out


@pytest.mark.parametrize(("module", "name"), list(SIGNATURES))
def test_signature(module, name):
    assert _params(getattr(module, name)) == SIGNATURES[(module, name)]


def test_future_signature():
    from analytics import future

    assert _params(future.project) == [
        "monthly_surplus_cents",
        "years=10",
        "rates={'low': 0.03, 'mid': 0.06, 'high': 0.08}",
    ]


def is_cents(value) -> bool:
    return type(value) is int


def is_date(value) -> bool:
    return isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-"


@pytest.fixture(scope="module")
def data():
    return synthetic_data.generate(seed=42, days=60)


@pytest.fixture(scope="module")
def txns(data):
    return pd.DataFrame(data["transactions"], columns=TXN_COLUMNS)


@pytest.fixture(scope="module")
def sched(data):
    return pd.DataFrame(data["scheduled"])


def user_txns(txns, user_id="u_priya"):
    return txns[txns["user_id"] == user_id].reset_index(drop=True)


# synthetic_data -------------------------------------------------------------


def test_generate_shape(data):
    assert set(data) == {"users", "transactions", "scheduled", "receipts"}
    assert len(data["users"]) == 3
    for user in data["users"]:
        assert set(user) == {"user_id", "name", "accounts"}
        assert {a["type"] for a in user["accounts"]} == {"checking", "savings", "credit_card"}
        for acct in user["accounts"]:
            assert set(acct) == {"account_id", "type", "nickname", "opening_balance_cents"}
            assert is_cents(acct["opening_balance_cents"])
    for t in data["transactions"]:
        assert list(t) == TXN_COLUMNS
        assert is_cents(t["amount_cents"]) and is_date(t["date"])
        assert t["kind"] in {"purchase", "deposit", "bill", "transfer"}
        assert t["status"] in {"pending", "posted"}
    for s in data["scheduled"]:
        assert set(s) == {"user_id", "account_id", "date", "amount_cents", "kind", "label", "cadence"}
        assert s["kind"] in {"income", "bill"} and is_cents(s["amount_cents"])
    for r in data["receipts"]:
        assert set(r) == {"receipt_id", "user_id", "merchant", "date", "items"}
        for item in r["items"]:
            assert set(item) == {"raw_label", "quantity", "unit", "unit_price_cents"}
            assert is_cents(item["unit_price_cents"])
    json.dumps(data)


def test_generate_deterministic(data):
    assert synthetic_data.generate(seed=42, days=60) == data
    assert synthetic_data.generate(seed=7, days=60) != data
    assert len({t["date"] for t in synthetic_data.generate(days=30)["transactions"]}) <= 30


# forecast -------------------------------------------------------------------


def _forecast(txns, sched):
    return forecast.forecast(
        user_txns(txns),
        sched[sched["user_id"] == "u_priya"],
        start_balance_cents=62_000,
        start_date="2026-10-11",
    )


def test_forecast_shape(txns, sched):
    out = _forecast(txns, sched)
    assert set(out) == {"days", "bills", "safe_to_spend_cents", "next_payday", "drivers", "wants_trimmed"}
    assert len(out["days"]) == 30
    for d in out["days"]:
        assert set(d) == {"date", "p10_cents", "p50_cents", "p90_cents"}
        assert is_date(d["date"])
        assert all(is_cents(d[k]) for k in ("p10_cents", "p50_cents", "p90_cents"))
        assert d["p10_cents"] <= d["p50_cents"] <= d["p90_cents"]
    assert out["bills"]
    for b in out["bills"]:
        assert set(b) == {"label", "date", "amount_cents", "p_short"}
        assert is_cents(b["amount_cents"]) and 0 <= b["p_short"] <= 1
    assert is_cents(out["safe_to_spend_cents"])
    assert out["next_payday"] is None or is_date(out["next_payday"])
    for d in out["drivers"]:
        assert set(d) == {"category", "share_of_variance"}
    wt = out["wants_trimmed"]
    assert set(wt) == {"safe_to_spend_cents", "bills"} and is_cents(wt["safe_to_spend_cents"])
    for b in wt["bills"]:
        assert set(b) == {"label", "date", "p_short"}
    json.dumps(out)


def test_forecast_deterministic(txns, sched):
    assert _forecast(txns, sched) == _forecast(txns, sched)


# categorize -----------------------------------------------------------------


def test_tag_needs(txns):
    out = categorize.tag_needs(txns)
    assert isinstance(out, pd.DataFrame)
    assert list(out.columns) == TXN_COLUMNS + ["necessity"]
    assert set(out["necessity"]) <= {"need", "want"}
    assert "necessity" not in txns.columns
    assert out.equals(categorize.tag_needs(txns))


def test_detect_income(txns):
    out = categorize.detect_income(user_txns(txns))
    assert set(out) == {"cadence", "typical_amount_cents", "variability_cents", "next_expected_date"}
    assert out["cadence"] in {"weekly", "biweekly", "monthly", "irregular"}
    assert is_cents(out["typical_amount_cents"]) and is_cents(out["variability_cents"])
    assert out["next_expected_date"] is None or is_date(out["next_expected_date"])
    assert out == categorize.detect_income(user_txns(txns))


# detection ------------------------------------------------------------------


def test_detect_recurring(txns):
    out = detection.detect_recurring(user_txns(txns, "u_maya"))
    assert out
    for r in out:
        assert set(r) == {"merchant", "amount_cents", "cadence", "next_expected_date", "confidence"}
        assert is_cents(r["amount_cents"]) and is_date(r["next_expected_date"])
    assert out == detection.detect_recurring(user_txns(txns, "u_maya"))


def test_detect_anomalies(txns):
    out = detection.detect_anomalies(user_txns(txns, "u_jake"))
    assert out
    for a in out:
        assert set(a) == {
            "transaction_id",
            "merchant",
            "amount_cents",
            "typical_low_cents",
            "typical_high_cents",
            "score",
        }
        assert all(is_cents(a[k]) for k in ("amount_cents", "typical_low_cents", "typical_high_cents"))
    assert out == detection.detect_anomalies(user_txns(txns, "u_jake"))


def test_duplicate_subscriptions(txns):
    out = detection.duplicate_subscriptions(txns)
    assert out
    for d in out:
        assert set(d) == {"merchant", "user_ids", "monthly_cost_cents", "possible_savings_cents"}
        assert is_cents(d["monthly_cost_cents"]) and is_cents(d["possible_savings_cents"])
        assert len(d["user_ids"]) >= 2
    assert out == detection.duplicate_subscriptions(txns)


# splits ---------------------------------------------------------------------


def test_split_contract():
    out = splits.split(10_001, "even", ["u_maya", "u_jake", "u_priya"])
    assert set(out) == {"u_maya", "u_jake", "u_priya"}
    assert all(is_cents(v) for v in out.values()) and sum(out.values()) == 10_001
    assert out == splits.split(10_001, "even", ["u_maya", "u_jake", "u_priya"])


def test_allocate_payment_contract():
    shares = [{"share_id": "s1", "amount_cents": 3000}, {"share_id": "s2", "amount_cents": 2000}]
    out = splits.allocate_payment(6000, shares)
    assert set(out) == {"allocations", "credit_cents"}
    for a in out["allocations"]:
        assert set(a) == {"share_id", "amount_cents"} and is_cents(a["amount_cents"])
    assert is_cents(out["credit_cents"])
    assert sum(a["amount_cents"] for a in out["allocations"]) + out["credit_cents"] == 6000


def test_simplify_debts_contract():
    out = splits.simplify_debts({"u_maya": 5000, "u_jake": -3000, "u_priya": -2000})
    assert isinstance(out, list)
    for t in out:
        assert set(t) == {"from", "to", "amount_cents"} and is_cents(t["amount_cents"])


# prices ---------------------------------------------------------------------


def test_prices(data):
    assert prices.normalize("ORG WHL MLK 1GAL") == prices.normalize("Organic Whole Milk 1 gal")
    history = [
        {**item, "merchant": r["merchant"], "date": r["date"]}
        for r in data["receipts"]
        for item in r["items"]
    ]
    name = prices.normalize("ORG WHL MLK 1GAL")
    out = prices.compare(name, pd.DataFrame(history))
    assert set(out) == {"item", "best", "latest", "savings_cents_per_unit"}
    for key in ("best", "latest"):
        assert set(out[key]) == {"merchant", "date", "unit_price_cents"}
        assert is_cents(out[key]["unit_price_cents"]) and is_date(out[key]["date"])
    assert is_cents(out["savings_cents_per_unit"])
    assert out == prices.compare(name, pd.DataFrame(history))


# cohorts --------------------------------------------------------------------


def test_cohorts(txns, sched):
    gen = cohorts.generate(n=60, seed=42)
    assert set(gen) == {"households", "transactions", "scheduled"}
    assert len(gen["households"]) == 60
    assert all(h["synthetic"] is True for h in gen["households"])
    assert gen == cohorts.generate(n=60, seed=42)
    for t in gen["transactions"]:
        assert list(t) == TXN_COLUMNS and is_cents(t["amount_cents"])

    households = pd.DataFrame(gen["households"])
    fake = {
        h["household_id"]: {"bills": [{"p_short": 0.7 if i % 3 == 0 else 0.1}]}
        for i, h in enumerate(gen["households"])
    }
    out = cohorts.segment_rates(fake, households)
    for row in out:
        assert set(row) == {"segment", "households", "share_at_risk"}
        assert row["households"] >= 20 and 0 <= row["share_at_risk"] <= 1
    sizes = households["segment"].value_counts()
    assert {r["segment"] for r in out} == set(sizes[sizes >= 20].index)


# future ---------------------------------------------------------------------


def test_future():
    from analytics import future

    out = future.project(25_000)
    assert set(out) == {"assumptions", "series"}
    assert out["assumptions"] == {"low": 0.03, "mid": 0.06, "high": 0.08}
    assert [r["year"] for r in out["series"]] == list(range(1, 11))
    for r in out["series"]:
        assert set(r) == {"year", "low_cents", "mid_cents", "high_cents"}
        assert all(is_cents(r[k]) for k in ("low_cents", "mid_cents", "high_cents"))
        assert r["low_cents"] <= r["mid_cents"] <= r["high_cents"]
    assert out == future.project(25_000)


# backtest -------------------------------------------------------------------


def test_backtest(txns, sched):
    out = backtest.run(txns, sched)
    assert set(out) == {"coverage", "median_abs_error_cents", "chart_path"}
    assert 0 <= out["coverage"] <= 1 and is_cents(out["median_abs_error_cents"])
    assert out["chart_path"] is None or isinstance(out["chart_path"], str)
    assert out == backtest.run(txns, sched)
