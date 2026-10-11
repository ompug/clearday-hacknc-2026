"""Behavioral tests for the Monte Carlo forecast simulation engine."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics import forecast, synthetic_data


@pytest.fixture(scope="module")
def dataset():
    return synthetic_data.generate(seed=42, days=60)


@pytest.fixture(scope="module")
def priya_txns(dataset):
    df = pd.DataFrame(dataset["transactions"])
    return df[df["user_id"] == "u_priya"].reset_index(drop=True)


@pytest.fixture(scope="module")
def priya_sched(dataset):
    df = pd.DataFrame(dataset["scheduled"])
    return df[df["user_id"] == "u_priya"].reset_index(drop=True)


def test_forecast_monte_carlo_envelope(priya_txns, priya_sched):
    result = forecast.forecast(
        priya_txns,
        priya_sched,
        start_balance_cents=62_000,
        start_date="2026-10-11",
        horizon_days=30,
        n_paths=500,
        seed=123,
    )

    days = result["days"]
    assert len(days) == 30

    for d in days:
        p10 = d["p10_cents"]
        p50 = d["p50_cents"]
        p90 = d["p90_cents"]
        assert p10 <= p50 <= p90
        assert isinstance(p10, int) and isinstance(p50, int) and isinstance(p90, int)

    # Over time, Monte Carlo spread should reflect cumulative uncertainty
    initial_spread = days[0]["p90_cents"] - days[0]["p10_cents"]
    final_spread = days[-1]["p90_cents"] - days[-1]["p10_cents"]
    assert final_spread >= initial_spread


def test_safe_to_spend_and_wants_trimmed(priya_txns, priya_sched):
    result = forecast.forecast(
        priya_txns,
        priya_sched,
        start_balance_cents=62_000,
        start_date="2026-10-11",
        horizon_days=30,
        n_paths=500,
        threshold_cents=5000,
        seed=42,
    )

    safe = result["safe_to_spend_cents"]
    trimmed_safe = result["wants_trimmed"]["safe_to_spend_cents"]

    assert safe >= 0
    assert trimmed_safe >= 0
    # Trimming discretionary wants by 25% should result in >= safe-to-spend
    assert trimmed_safe >= safe

    # Shortfall probability on bills
    base_bills = {b["label"]: b["p_short"] for b in result["bills"]}
    trimmed_bills = {b["label"]: b["p_short"] for b in result["wants_trimmed"]["bills"]}

    for label in base_bills:
        if label in trimmed_bills:
            assert 0.0 <= base_bills[label] <= 1.0
            assert 0.0 <= trimmed_bills[label] <= 1.0
            # Risk under trimmed spending should be <= base risk
            assert trimmed_bills[label] <= base_bills[label] + 0.05  # within margin


def test_variance_drivers_ranked(priya_txns, priya_sched):
    result = forecast.forecast(
        priya_txns,
        priya_sched,
        start_balance_cents=62_000,
        start_date="2026-10-11",
        horizon_days=30,
        n_paths=500,
        seed=77,
    )

    drivers = result["drivers"]
    assert drivers
    for d in drivers:
        assert isinstance(d["category"], str)
        assert 0.0 <= d["share_of_variance"] <= 1.0

    # Ensure drivers are ranked descending
    shares = [d["share_of_variance"] for d in drivers]
    assert shares == sorted(shares, reverse=True)
