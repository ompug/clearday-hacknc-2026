"""Behavioral tests for synthetic data generation and seed_data.json export."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import pytest

from analytics import synthetic_data


def test_synthetic_data_generation():
    data = synthetic_data.generate(seed=42, days=60)

    # Validate structure
    assert set(data) == {"users", "transactions", "scheduled", "receipts"}
    assert len(data["users"]) == 3
    user_ids = {u["user_id"] for u in data["users"]}
    assert user_ids == {"u_maya", "u_jake", "u_priya"}

    # Check transactions span 60 calendar days
    txns = data["transactions"]
    dates = sorted({t["date"] for t in txns})
    min_d = dt.date.fromisoformat(dates[0])
    max_d = dt.date.fromisoformat(dates[-1])
    assert (max_d - min_d).days + 1 == 60

    # Check duplicate subscription planted: Maya and Jake both have Spotify
    spotify_users = {
        t["user_id"]
        for t in txns
        if t["category"] == "subscriptions" and t["merchant"] == "Spotify"
    }
    assert spotify_users == {"u_maya", "u_jake"}

    # Check planted anomaly: Jake's $218.40 Harris Teeter charge
    jake_grocery = [
        t
        for t in txns
        if t["user_id"] == "u_jake"
        and t["merchant"] == "Harris Teeter"
        and t["amount_cents"] == 21840
    ]
    assert len(jake_grocery) == 1

    # Check planted tight week: Priya has elevated shopping charges before rent (days 24-30)
    priya_tight_charges = [
        t
        for t in txns
        if t["user_id"] == "u_priya"
        and t["category"] == "shopping"
        and 24 <= int(t["date"][-2:]) <= 30
    ]
    assert len(priya_tight_charges) >= 1


def test_save_seed_json(tmp_path):
    target = tmp_path / "test_seed.json"
    out = synthetic_data.save_seed(path=target, seed=42, days=60)
    assert Path(out).exists()

    with open(out, encoding="utf-8") as f:
        loaded = json.load(f)

    assert set(loaded) == {"users", "transactions", "scheduled", "receipts"}
    assert len(loaded["transactions"]) > 0
