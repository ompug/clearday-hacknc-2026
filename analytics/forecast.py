"""Monte Carlo "money weather" forecast.

Contract (docs/02-technical-spec.md, Analytics contracts):

    forecast(transactions, scheduled, start_balance_cents, start_date, horizon_days=30,
             n_paths=1000, threshold_cents=5000, seed=0) -> {
      "days": [{"date", "p10_cents", "p50_cents", "p90_cents"}],
      "bills": [{"label", "date", "amount_cents", "p_short"}],
      "safe_to_spend_cents", "next_payday",
      "drivers": [{"category", "share_of_variance"}],
      "wants_trimmed": {"safe_to_spend_cents", "bills": [{"label", "date", "p_short"}]}
    }

Simulates 1,000 paths by bootstrap-sampling historical daily discretionary spending
per category by day of week. Calculates empirical P10/P50/P90 percentile envelopes,
bill shortfall risk, safe-to-spend under pessimistic trajectory, variance drivers,
and a 25% wants-trimmed scenario.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import defaultdict
from typing import Any

from analytics._common import iso, median_int, parse_date, records

NEED_CATEGORIES = {
    "rent",
    "utilities",
    "internet",
    "groceries",
    "insurance",
    "health",
    "transfer",
    "income",
    "transport",
}
OUTFLOW_KINDS = {"purchase"}


def _build_category_pools(
    txns: list[dict[str, Any]],
) -> tuple[list[str], dict[str, dict[int, list[int]]], dict[str, int]]:
    """Build historical daily spend pools per category and day-of-week.

    Includes zero-spend days across the historical span for each category to capture
    realistic spending frequency.
    """
    by_date_cat: dict[dt.date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_dates: set[dt.date] = set()
    total_by_cat: dict[str, int] = defaultdict(int)

    for t in txns:
        d = parse_date(t["date"])
        all_dates.add(d)
        if t.get("kind") in OUTFLOW_KINDS:
            cat = str(t.get("category") or "other")
            cents = int(t.get("amount_cents") or 0)
            by_date_cat[d][cat] += cents
            total_by_cat[cat] += cents

    categories = sorted(total_by_cat.keys())
    cat_dow_pools: dict[str, dict[int, list[int]]] = defaultdict(dict)

    if all_dates and categories:
        min_date = min(all_dates)
        max_date = max(all_dates)
        cur = min_date
        dates_list: list[dt.date] = []
        while cur <= max_date:
            dates_list.append(cur)
            cur += dt.timedelta(days=1)

        for cat in categories:
            for dow in range(7):
                dow_dates = [d for d in dates_list if d.weekday() == dow]
                pool = [by_date_cat[d].get(cat, 0) for d in dow_dates]
                if pool:
                    sorted_pool = sorted(pool)
                    cap_idx = int(0.95 * len(sorted_pool))
                    cap_val = sorted_pool[cap_idx]
                    pool = [min(v, cap_val) for v in pool]
                cat_dow_pools[cat][dow] = pool
    else:
        categories = ["groceries", "dining"]
        for cat in categories:
            for dow in range(7):
                cat_dow_pools[cat][dow] = [1500 if cat == "groceries" else 1000]

    return categories, cat_dow_pools, dict(total_by_cat)


def forecast(
    transactions: Any,
    scheduled: Any,
    start_balance_cents: int,
    start_date: str | dt.date,
    horizon_days: int = 30,
    n_paths: int = 1000,
    threshold_cents: int = 5000,
    seed: int = 0,
) -> dict[str, Any]:
    txns = records(transactions)
    sched = records(scheduled)
    start = parse_date(start_date)
    end = start + dt.timedelta(days=horizon_days - 1)
    threshold = int(threshold_cents)
    start_bal = int(start_balance_cents)

    categories, cat_dow_pools, hist_cat_totals = _build_category_pools(txns)

    # Known scheduled income and bills
    scheduled_net: dict[dt.date, int] = defaultdict(int)
    bill_events: list[tuple[dt.date, str, int]] = []
    next_payday: str | None = None

    for s in sorted(sched, key=lambda r: (str(r["date"]), str(r.get("label", "")))):
        day = parse_date(s["date"])
        cents = int(s.get("amount_cents") or 0)
        is_income = s.get("kind") == "income"

        if is_income and day >= start and next_payday is None:
            next_payday = iso(day)

        if not start <= day <= end:
            continue

        if is_income:
            scheduled_net[day] += cents
        else:
            scheduled_net[day] -= cents
            bill_events.append((day, str(s.get("label") or "Bill"), cents))

    # Monte Carlo simulation: n_paths trajectories
    rng = random.Random(seed)
    horizon_dates = [start + dt.timedelta(days=i) for i in range(horizon_days)]

    path_balances: list[list[int]] = []
    trimmed_balances: list[list[int]] = []
    path_cat_totals: list[dict[str, int]] = []

    for _ in range(n_paths):
        cur_bal = start_bal
        cur_trimmed = start_bal
        bal_trace: list[int] = [0] * horizon_days
        trimmed_trace: list[int] = [0] * horizon_days
        cat_spends: dict[str, int] = defaultdict(int)

        for i, day in enumerate(horizon_dates):
            dow = day.weekday()
            base_spend = 0
            trimmed_spend = 0

            for cat in categories:
                pool = cat_dow_pools[cat].get(dow)
                amt = rng.choice(pool) if pool else 0
                cat_spends[cat] += amt
                base_spend += amt
                if cat in NEED_CATEGORIES:
                    trimmed_spend += amt
                else:
                    trimmed_spend += int(amt * 0.75)

            net_flow = scheduled_net.get(day, 0)
            cur_bal += net_flow - base_spend
            cur_trimmed += net_flow - trimmed_spend

            bal_trace[i] = cur_bal
            trimmed_trace[i] = cur_trimmed

        path_balances.append(bal_trace)
        trimmed_balances.append(trimmed_trace)
        path_cat_totals.append(cat_spends)

    days: list[dict[str, Any]] = []
    trimmed_p10_by_day: list[int] = []

    p10_idx = max(0, int(0.10 * n_paths))
    p50_idx = max(0, int(0.50 * n_paths))
    p90_idx = min(n_paths - 1, int(0.90 * n_paths))

    for i, day in enumerate(horizon_dates):
        daily_vals = sorted(path_balances[p][i] for p in range(n_paths))
        p10 = int(daily_vals[p10_idx])
        p50 = int(daily_vals[p50_idx])
        p90 = int(daily_vals[p90_idx])
        days.append({"date": iso(day), "p10_cents": p10, "p50_cents": p50, "p90_cents": p90})

        daily_trimmed = sorted(trimmed_balances[p][i] for p in range(n_paths))
        trimmed_p10_by_day.append(int(daily_trimmed[p10_idx]))

    payday_limit = parse_date(next_payday) if next_payday else end
    payday_limit_idx = min(max(0, (payday_limit - start).days), horizon_days - 1)

    low_p10 = min(days[i]["p10_cents"] for i in range(payday_limit_idx + 1))
    safe_to_spend_cents = max(0, low_p10 - threshold)

    trimmed_low_p10 = min(trimmed_p10_by_day[i] for i in range(payday_limit_idx + 1))
    trimmed_safe_to_spend = max(0, trimmed_low_p10 - threshold)

    def calc_bill_rows(traces: list[list[int]], with_amount: bool) -> list[dict[str, Any]]:
        rows = []
        for day, label, cents in bill_events:
            bill_idx = min((day - start).days, horizon_days - 1)
            shortfalls = 0
            for p in range(n_paths):
                path_min = min(traces[p][j] for j in range(bill_idx + 1))
                if path_min <= threshold:
                    shortfalls += 1

            p_short = round(shortfalls / n_paths, 2)
            row: dict[str, Any] = {"label": label, "date": iso(day)}
            if with_amount:
                row["amount_cents"] = cents
            row["p_short"] = p_short
            rows.append(row)
        return rows

    bills = calc_bill_rows(path_balances, with_amount=True)
    trimmed_bills = calc_bill_rows(trimmed_balances, with_amount=False)

    categories_set = set(hist_cat_totals)
    for cat_dict in path_cat_totals:
        categories_set.update(cat_dict)

    var_by_cat: dict[str, float] = {}
    for cat in categories_set:
        spends = [path_cat_totals[p].get(cat, 0) for p in range(n_paths)]
        mean_s = sum(spends) / n_paths
        variance = sum((s - mean_s) ** 2 for s in spends) / max(n_paths - 1, 1)
        if variance > 0:
            var_by_cat[cat] = variance

    total_var = sum(var_by_cat.values())
    if total_var > 0:
        ranked_vars = sorted(var_by_cat.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        ranked_total = sum(v for _, v in ranked_vars) or total_var
        drivers = [
            {"category": cat, "share_of_variance": round(var / ranked_total, 2)}
            for cat, var in ranked_vars
        ]
    elif hist_cat_totals:
        top_cats = sorted(hist_cat_totals.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
        tot = sum(v for _, v in top_cats) or 1
        drivers = [
            {"category": cat, "share_of_variance": round(v / tot, 2)}
            for cat, v in top_cats
        ]
    else:
        drivers = [{"category": "other", "share_of_variance": 1.0}]

    return {
        "days": days,
        "bills": bills,
        "safe_to_spend_cents": safe_to_spend_cents,
        "next_payday": next_payday,
        "drivers": drivers,
        "wants_trimmed": {
            "safe_to_spend_cents": trimmed_safe_to_spend,
            "bills": trimmed_bills,
        },
    }
