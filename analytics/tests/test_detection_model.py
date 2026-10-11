"""Behavioral tests for detection algorithms: MAD anomaly detection, recurring charges, and duplicate subscriptions."""

from __future__ import annotations

import pandas as pd
import pytest

from analytics import detection, synthetic_data


@pytest.fixture(scope="module")
def household_dataset():
    return synthetic_data.generate(seed=42, days=60)


def test_mad_anomaly_detection_planted_case(household_dataset):
    txns = pd.DataFrame(household_dataset["transactions"])
    jake_txns = txns[txns["user_id"] == "u_jake"]

    anomalies = detection.detect_anomalies(jake_txns)
    assert anomalies

    # Find the planted anomaly: oversized Harris Teeter charge for Jake ($218.40 = 21,840 cents)
    harris_anomalies = [a for a in anomalies if a["merchant"] == "Harris Teeter"]
    assert len(harris_anomalies) >= 1

    top = harris_anomalies[0]
    assert top["amount_cents"] == 21_840
    assert top["typical_low_cents"] <= top["typical_high_cents"] < 21_840
    assert top["score"] >= 0.5


def test_mad_anomaly_identical_charges_no_zero_division():
    # When all charges are identical, raw MAD is zero
    test_rows = [
        {"transaction_id": f"t{i}", "kind": "purchase", "merchant": "Store", "amount_cents": 5000, "date": "2026-09-01"}
        for i in range(5)
    ]
    test_rows.append(
        {"transaction_id": "t_outlier", "kind": "purchase", "merchant": "Store", "amount_cents": 25000, "date": "2026-09-10"}
    )

    anomalies = detection.detect_anomalies(test_rows)
    assert len(anomalies) == 1
    assert anomalies[0]["transaction_id"] == "t_outlier"
    assert anomalies[0]["amount_cents"] == 25000
    assert anomalies[0]["typical_low_cents"] <= 5000
    assert anomalies[0]["typical_high_cents"] < 25000


def test_detect_recurring_subscriptions(household_dataset):
    txns = pd.DataFrame(household_dataset["transactions"])
    maya_txns = txns[txns["user_id"] == "u_maya"]

    recurring = detection.detect_recurring(maya_txns)
    merchants = {r["merchant"]: r for r in recurring}

    # Maya has monthly Spotify, Netflix, iCloud in synthetic data
    assert "Spotify" in merchants
    assert merchants["Spotify"]["cadence"] == "monthly"
    assert merchants["Spotify"]["amount_cents"] == 1199
    assert merchants["Spotify"]["confidence"] >= 0.7


def test_duplicate_household_subscriptions(household_dataset):
    duplicates = detection.duplicate_subscriptions(household_dataset["transactions"])
    spotify_dups = [d for d in duplicates if d["merchant"] == "Spotify"]

    assert len(spotify_dups) == 1
    dup = spotify_dups[0]
    assert set(dup["user_ids"]) == {"u_jake", "u_maya"}
    assert dup["monthly_cost_cents"] == 1199 * 2
    assert dup["possible_savings_cents"] == 1199
