"""The device keeps household-level counts only; amounts and names never get in."""

import dataclasses

import pytest

from clearday_home.payloads import PayloadError, parse_announcement, parse_status, parse_summary

SECRETS = ("45000", "Alex Rivera", "Jordan", "acct-9911", "1234")

SALTED_STATUS = {
    "weather": "clear",
    "open_bills": 2,
    "due_soon_bills": 1,
    "shares_paid": 3,
    "shares_total": 4,
    # things a buggy backend might leak; the device must drop them
    "total_cents": 45000,
    "amount_cents": 45000,
    "safe_to_spend_cents": 1234,
    "members": [{"name": "Alex Rivera"}, {"display_name": "Jordan"}],
    "actor": "Jordan",
    "account_id": "acct-9911",
}


def all_values(obj):
    if dataclasses.is_dataclass(obj):
        for f in dataclasses.fields(obj):
            yield f.name
            yield from all_values(getattr(obj, f.name))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from all_values(item)
    else:
        yield str(obj)


def test_status_keeps_only_allowlisted_counts():
    st = parse_status(SALTED_STATUS)
    assert {f.name for f in dataclasses.fields(st)} == {
        "weather",
        "open_bills",
        "due_soon_bills",
        "shares_paid",
        "shares_total",
    }
    flat = " ".join(all_values(st))
    for secret in SECRETS:
        assert secret not in flat
    for word in ("amount", "cents", "name", "balance", "actor"):
        assert word not in flat


def test_summary_drops_amounts_and_names():
    summary = parse_summary(
        {
            "weather": "tight",
            "open_bills": 1,
            "bills": [
                {
                    "label": "Rent",
                    "shares_paid": 2,
                    "shares_total": 3,
                    "due_in_days": 2,
                    "amount_cents": 45000,
                    "paid_by": ["Alex Rivera"],
                    "payer_name": "Jordan",
                }
            ],
            "safe_to_spend_cents": 1234,
        }
    )
    assert summary.bills[0].label == "Rent"
    flat = " ".join(all_values(summary))
    for secret in SECRETS:
        assert secret not in flat


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {**SALTED_STATUS, "weather": "stormy"},
        {**SALTED_STATUS, "open_bills": "2"},
        {**SALTED_STATUS, "open_bills": -1},
        {**SALTED_STATUS, "open_bills": True},
        {**SALTED_STATUS, "shares_paid": 5},
        [],
    ],
)
def test_status_rejects_malformed(bad):
    with pytest.raises(PayloadError):
        parse_status(bad)


def test_announcement_must_be_our_api():
    a = parse_announcement({"audio_url": "/api/device/audio/abc.mp3", "light_pattern": "burst"})
    assert a.audio_path == "/api/device/audio/abc.mp3"
    for url in (
        "https://evil.example/x.mp3",
        "//evil.example/api/x",
        "/static/x.mp3",
        "/api/../etc/passwd",
        "file:///api/x",
    ):
        with pytest.raises(PayloadError):
            parse_announcement({"audio_url": url})
