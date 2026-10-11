"""Behavioral tests for the forecast backtest engine."""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from analytics import backtest, synthetic_data


@pytest.fixture(scope="module")
def data():
    return synthetic_data.generate(seed=42, days=60)


def test_backtest_execution_and_metrics(data):
    txns = pd.DataFrame(data["transactions"])
    sched = pd.DataFrame(data["scheduled"])

    # Backtest held-out 30 days
    result = backtest.run(txns, sched, holdout_days=30, seed=42)

    assert set(result) == {"coverage", "median_abs_error_cents", "chart_path"}
    coverage = result["coverage"]
    median_err = result["median_abs_error_cents"]
    chart_path = result["chart_path"]

    # Coverage should be a valid percentage
    assert 0.0 <= coverage <= 1.0
    assert isinstance(median_err, int) and median_err >= 0

    # Verify PNG chart generation
    assert chart_path is not None
    p = Path(chart_path)
    assert p.exists()
    assert p.stat().st_size > 1000
