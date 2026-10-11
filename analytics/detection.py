"""Recurring charges, anomaly detection with Median and MAD, and duplicate subscriptions.

Contract (docs/02-technical-spec.md, Analytics contracts):

    detect_recurring(transactions) -> [{"merchant", "amount_cents", "cadence",
      "next_expected_date", "confidence"}]
    detect_anomalies(transactions) -> [{"transaction_id", "merchant", "amount_cents",
      "typical_low_cents", "typical_high_cents", "score"}]
    duplicate_subscriptions(household_transactions) -> [{"merchant", "user_ids",
      "monthly_cost_cents", "possible_savings_cents"}]

Pure functions on the shared format with integer cents and deterministic output.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from analytics._common import iso, median_int, parse_date, records


def _purchases(transactions: Any) -> list[dict[str, Any]]:
    return [r for r in records(transactions) if r.get("kind") in ("purchase", "bill")]


def detect_recurring(transactions: Any) -> list[dict[str, Any]]:
    """Detect recurring charges with consistent amount and regular intervals."""
    by_merchant: dict[str, list[tuple[dt.date, int]]] = defaultdict(list)
    for r in _purchases(transactions):
        by_merchant[str(r["merchant"])].append((parse_date(r["date"]), int(r["amount_cents"])))

    out: list[dict[str, Any]] = []
    for merchant in sorted(by_merchant):
        rows = sorted(by_merchant[merchant])
        if len(rows) < 2:
            continue
        amounts = [a for _, a in rows]
        typical = median_int(amounts)
        # Amounts must be stable within ~15% or a small dollar margin
        tolerance = max(int(typical * 0.15), 150)
        if max(amounts) - min(amounts) > tolerance:
            continue

        gaps = [(b[0] - a[0]).days for a, b in zip(rows, rows[1:], strict=False)]
        gap = median_int(gaps)
        cadence = None
        if 6 <= gap <= 8:
            cadence = "weekly"
            expected_step = 7
        elif 13 <= gap <= 16:
            cadence = "biweekly"
            expected_step = 14
        elif 27 <= gap <= 33:
            cadence = "monthly"
            expected_step = gap

        if cadence is None:
            continue

        confidence = 0.95 if len(rows) >= 4 else (0.9 if len(rows) >= 3 else 0.7)
        out.append(
            {
                "merchant": merchant,
                "amount_cents": typical,
                "cadence": cadence,
                "next_expected_date": iso(rows[-1][0] + dt.timedelta(days=expected_step)),
                "confidence": confidence,
            }
        )
    return out


def _compute_mad(values: list[int], median_val: int) -> int:
    """Compute Median Absolute Deviation (MAD) of integer values."""
    deviations = [abs(v - median_val) for v in values]
    return median_int(deviations)


def detect_anomalies(transactions: Any) -> list[dict[str, Any]]:
    """Detect anomalous charges using Median and Median Absolute Deviation (MAD).

    Uses a modified Z-score based on MAD to identify outlier purchases
    significantly higher than typical spending at the merchant.
    """
    by_merchant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in _purchases(transactions):
        by_merchant[str(r["merchant"])].append(r)

    out: list[dict[str, Any]] = []
    for merchant in sorted(by_merchant):
        rows = by_merchant[merchant]
        if len(rows) < 4:
            continue

        amounts = [int(r["amount_cents"]) for r in rows]
        med = median_int(amounts)
        raw_mad = _compute_mad(amounts, med)

        # In discrete/identical charges, raw MAD can be 0.
        # Fall back to mean absolute deviation or a 5% floor to prevent division by zero.
        if raw_mad == 0:
            devs = [abs(v - med) for v in amounts]
            mean_dev = sum(devs) // len(devs) if devs else 0
            mad_eff = max(mean_dev, int(med * 0.05), 50)
        else:
            mad_eff = raw_mad

        # Normal-consistent scale: sigma ~= 1.4826 * MAD
        # Modified z-score: M_i = |x - median| / (1.4826 * MAD)
        sigma = max(int(1.4826 * mad_eff), 1)

        # Typical non-anomalous range
        non_outlier = [x for x in amounts if (x - med) / sigma < 3.0]
        if non_outlier:
            low = min(non_outlier)
            high = max(non_outlier)
        else:
            low = max(0, med - 2 * sigma)
            high = med + 2 * sigma

        for r in rows:
            cents = int(r["amount_cents"])
            # Outlier charge: substantially above median and modified z-score >= 3.0
            if cents > med and (cents - med) / sigma >= 3.0 and cents >= int(med * 1.5):
                z_score = (cents - med) / sigma
                score = round(min(1.0, z_score / 10.0), 2)
                out.append(
                    {
                        "transaction_id": str(r["transaction_id"]),
                        "merchant": merchant,
                        "amount_cents": cents,
                        "typical_low_cents": int(low),
                        "typical_high_cents": int(high),
                        "score": score,
                    }
                )

    return sorted(out, key=lambda a: (-a["score"], str(a["transaction_id"])))


def duplicate_subscriptions(household_transactions: Any) -> list[dict[str, Any]]:
    """Detect subscriptions paid by multiple household members."""
    per_merchant: dict[str, dict[str, int]] = defaultdict(dict)
    for r in records(household_transactions):
        if r.get("category") != "subscriptions":
            continue
        per_merchant[str(r["merchant"])][str(r["user_id"])] = int(r["amount_cents"])

    out: list[dict[str, Any]] = []
    for merchant in sorted(per_merchant):
        users = per_merchant[merchant]
        if len(users) < 2:
            continue
        monthly = sum(users.values())
        out.append(
            {
                "merchant": merchant,
                "user_ids": sorted(users),
                "monthly_cost_cents": monthly,
                "possible_savings_cents": monthly - max(users.values()),
            }
        )
    return out
