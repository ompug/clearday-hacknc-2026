"""Forecast backtest on held-out days.

Contract (docs/02-technical-spec.md, Analytics contracts):

    run(transactions, scheduled, holdout_days=30, seed=0) -> {"coverage",
      "median_abs_error_cents", "chart_path"}

Trains on early transaction history and evaluates empirical coverage and error
against the held-out period. Generates a fan-chart PNG for judges.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend safe for server/headless
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from analytics._common import iso, median_int, parse_date, records
from analytics.forecast import forecast


def run(
    transactions: Any,
    scheduled: Any,
    holdout_days: int = 30,
    seed: int = 0,
) -> dict[str, Any]:
    txns = records(transactions)
    sched = records(scheduled)
    if not txns:
        return {"coverage": 0.0, "median_abs_error_cents": 0, "chart_path": None}

    # If transactions contain multiple users, evaluate for the primary persona (Maya)
    user_counts: dict[str, int] = defaultdict(int)
    for t in txns:
        if t.get("user_id"):
            user_counts[str(t["user_id"])] += 1

    if "u_maya" in user_counts:
        target_user = "u_maya"
    elif user_counts:
        target_user = max(user_counts, key=user_counts.get)
    else:
        target_user = None

    if target_user:
        eval_txns = [t for t in txns if str(t.get("user_id")) == target_user]
        eval_sched = [s for s in sched if str(s.get("user_id")) == target_user]
    else:
        eval_txns = txns
        eval_sched = sched

    # Identify date range for holdout split
    all_dates = sorted({parse_date(t["date"]) for t in eval_txns})
    if len(all_dates) <= holdout_days:
        split_idx = max(1, len(all_dates) // 2)
        cutoff_date = all_dates[split_idx]
        eval_horizon = len(all_dates) - split_idx
    else:
        cutoff_date = all_dates[-holdout_days]
        eval_horizon = holdout_days

    holdout_start = cutoff_date
    holdout_end = all_dates[-1]

    # Split transactions into training and held-out evaluation window
    train_txns = [t for t in eval_txns if parse_date(t["date"]) < holdout_start]
    holdout_txns = [t for t in eval_txns if parse_date(t["date"]) >= holdout_start]

    # Initial opening balance at start of dataset (Maya opening checking = 310,000 cents)
    base_opening = 310_000 if target_user == "u_maya" else 150_000
    start_bal = base_opening
    for t in train_txns:
        cents = int(t.get("amount_cents") or 0)
        if t.get("kind") == "deposit":
            start_bal += cents
        else:
            start_bal -= cents
    start_bal = max(50_000, start_bal)

    # Align scheduled items into the holdout window by repeating their cadence
    holdout_sched: list[dict[str, Any]] = []
    seen_sched_keys: set[tuple[str, str, int]] = set()

    for s in eval_sched:
        orig_date = parse_date(s["date"])
        cadence = s.get("cadence")
        step = 14 if cadence == "biweekly" else (30 if cadence == "monthly" else 7)

        d = orig_date
        while d >= holdout_start:
            d -= dt.timedelta(days=step)
        while d <= holdout_end:
            if d >= holdout_start:
                key = (iso(d), str(s.get("label", "")), int(s.get("amount_cents") or 0))
                if key not in seen_sched_keys:
                    seen_sched_keys.add(key)
                    item = dict(s)
                    item["date"] = iso(d)
                    holdout_sched.append(item)
            d += dt.timedelta(days=step)

    # Run forecast simulation on training history for the holdout window
    fc = forecast(
        train_txns if train_txns else eval_txns,
        holdout_sched,
        start_balance_cents=start_bal,
        start_date=holdout_start,
        horizon_days=eval_horizon,
        seed=seed,
    )

    # Actual daily balance trajectory during holdout
    daily_actual_delta: dict[dt.date, int] = defaultdict(int)
    for t in holdout_txns:
        d = parse_date(t["date"])
        cents = int(t.get("amount_cents") or 0)
        if t.get("kind") == "deposit":
            daily_actual_delta[d] += cents
        else:
            daily_actual_delta[d] -= cents

    forecast_days = fc["days"]
    cur_actual = start_bal
    in_band_count = 0
    abs_errors: list[int] = []

    actual_curve: list[int] = []
    p10_curve: list[int] = []
    p50_curve: list[int] = []
    p90_curve: list[int] = []
    plot_dates: list[dt.date] = []

    for f_day in forecast_days:
        d = parse_date(f_day["date"])
        cur_actual += daily_actual_delta.get(d, 0)
        actual_curve.append(cur_actual)

        p10 = int(f_day["p10_cents"])
        p50 = int(f_day["p50_cents"])
        p90 = int(f_day["p90_cents"])

        p10_curve.append(p10)
        p50_curve.append(p50)
        p90_curve.append(p90)
        plot_dates.append(d)

        if p10 <= cur_actual <= p90:
            in_band_count += 1
        abs_errors.append(abs(cur_actual - p50))

    total_eval_days = max(len(forecast_days), 1)
    coverage = round(in_band_count / total_eval_days, 2)
    median_abs_error = median_int(abs_errors)

    # Render backtest fan chart PNG
    chart_filename = "backtest.png"
    chart_path = str(Path(__file__).resolve().parent / chart_filename)

    try:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        fig.patch.set_facecolor("#f8fafc")
        ax.set_facecolor("#ffffff")

        # Convert cents to dollars for plotting
        p10_dollars = [v / 100.0 for v in p10_curve]
        p50_dollars = [v / 100.0 for v in p50_curve]
        p90_dollars = [v / 100.0 for v in p90_curve]
        actual_dollars = [v / 100.0 for v in actual_curve]

        # 80% confidence interval (P10 to P90)
        ax.fill_between(
            plot_dates,
            p10_dollars,
            p90_dollars,
            color="#38bdf8",
            alpha=0.35,
            label="80% Prediction Interval (P10–P90)",
        )

        # Median forecast path
        ax.plot(
            plot_dates,
            p50_dollars,
            color="#0284c7",
            linestyle="--",
            linewidth=2,
            label="P50 Forecast Path",
        )

        # Actual observed balance
        ax.plot(
            plot_dates,
            actual_dollars,
            color="#0f172a",
            linewidth=2.2,
            marker="o",
            markersize=3.5,
            label="Actual Observed Balance",
        )

        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.set_ylabel("Account Balance ($)", fontsize=11, fontweight="medium", color="#1e293b")
        ax.set_title(
            f"Clearday Money Weather · 30-Day Forecast Backtest\nCoverage: {int(coverage * 100)}% within P10–P90 | Median Error: ${median_abs_error / 100:.2f}",
            fontsize=12,
            fontweight="bold",
            color="#0f172a",
            pad=14,
        )

        ax.grid(True, linestyle=":", alpha=0.6, color="#94a3b8")
        ax.legend(loc="upper left", framealpha=0.9, facecolor="#ffffff", edgecolor="#cbd5e1")
        plt.tight_layout()

        fig.savefig(chart_path, dpi=150)
        plt.close(fig)
    except Exception:
        chart_path = None

    return {
        "coverage": coverage,
        "median_abs_error_cents": median_abs_error,
        "chart_path": chart_path,
    }
