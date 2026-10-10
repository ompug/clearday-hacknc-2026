"""STUB: forecast backtest on held-out days.

Contract (docs/02-technical-spec.md, Analytics contracts):

    run(transactions, scheduled, holdout_days=30, seed=0) -> {"coverage",
      "median_abs_error_cents", "chart_path"}

The stub returns fixed, plausible numbers derived from the data size and does
not render a chart, so ``chart_path`` is None. The real module writes a PNG.
"""

from __future__ import annotations

from analytics._common import median_int, records


def run(transactions, scheduled, holdout_days=30, seed=0):
    txns = records(transactions)
    amounts = [int(t["amount_cents"]) for t in txns if t.get("kind") == "purchase"]
    typical = median_int(amounts)
    return {
        "coverage": 0.83,
        "median_abs_error_cents": typical * 3 + (seed % 5) * 100,
        "chart_path": None,
    }
