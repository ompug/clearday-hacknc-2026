"""GET /api/forecast and the debounced `forecast.updated` event.

Shapes mirror `ForecastResponse` / `ForecastUpdatedEvent` in web/lib/api/types.ts (written out by hand,
like test_api_contract.py). Fixtures come from the contract and payment tests so both seams run against
a real scratch database.
"""

from __future__ import annotations

import asyncio
import re
import time

import pytest

from api import forecast, sky
from api.realtime import sio, user_room
from api.tests.test_api_contract import ISO_DATE, NESSIE, NULL, NUM, STR, assert_shape, login
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)
from api.tests.test_ledger_payments import api as api  # noqa: F401  (fixture)
from api.tests.test_ledger_payments import as_user, body
from api.tests.test_ledger_payments import household as household  # noqa: F401  (fixture)

INT = "int"
FORECAST_DAY = {"date": {STR}, "p10_cents": {INT}, "p50_cents": {INT}, "p90_cents": {INT}}
FORECAST_BILL = {
    "label": {STR},
    "date": {STR},
    "amount_cents": {INT},
    "p_short": {NUM},
    "bubble_id": {STR, NULL},
    "weather": {STR},
}
SCENARIO_BILL = {"label": {STR}, "date": {STR}, "p_short": {NUM}, "bubble_id": {STR, NULL}, "weather": {STR}}
DRIVER = {"category": {STR}, "share_of_variance": {NUM}}
FORECAST = {
    "as_of": {STR},
    "threshold_cents": {INT},
    "days": {"list"},
    "bills": {"list"},
    "safe_to_spend_cents": {INT},
    "next_payday": {STR, NULL},
    "drivers": {"list"},
    "wants_trimmed": {"safe_to_spend_cents": {INT}, "bills": {"list"}},
}
EVENT = {"bubbles": {"list"}, "safe_to_spend_cents": {INT}}
EVENT_BUBBLE = {"bubble_id": {STR}, "weather": {STR}, "p_short": {NUM}}
WEATHER = {"clear", "watch", "tight"}


# ---- GET /api/forecast -------------------------------------------------------------------------


def test_forecast_requires_session(client):  # noqa: F811
    assert client.get("/api/forecast").status_code == 401


def test_forecast_shape_matches_types_ts(client):  # noqa: F811
    login(client, 0)
    res = client.get("/api/forecast")
    assert res.status_code == 200, res.text
    fc = res.json()
    assert_shape(fc, FORECAST, "ForecastResponse")
    assert fc["threshold_cents"] == sky.THRESHOLD_CENTS
    assert len(fc["days"]) == sky.HORIZON_DAYS
    assert fc["days"][0]["date"] == sky.today().isoformat()
    for d in fc["days"]:
        assert_shape(d, FORECAST_DAY, "ForecastDay")
        assert ISO_DATE.match(d["date"]) and d["p10_cents"] <= d["p50_cents"] <= d["p90_cents"]
    assert fc["next_payday"] is None or ISO_DATE.match(fc["next_payday"])
    assert fc["bills"], "Ana has a personal bill inside the horizon"
    for b in fc["bills"]:
        assert_shape(b, FORECAST_BILL, "ForecastBill")
        assert b["weather"] == sky.weather_for(b["p_short"]) and 0 <= b["p_short"] <= 1
    for b in fc["wants_trimmed"]["bills"]:
        assert_shape(b, SCENARIO_BILL, "ForecastScenarioBill")
        assert b["weather"] in WEATHER
    for d in fc["drivers"]:
        assert_shape(d, DRIVER, "ForecastDriver")


def test_forecast_bills_link_to_the_users_own_sky_bubbles(client):  # noqa: F811
    login(client, 0)
    sky_bubbles = {b["bubble_id"]: b for b in client.get("/api/sky").json()["bubbles"]}
    bills = client.get("/api/forecast").json()["bills"]
    bill = next(b for b in bills if b["bubble_id"] == f"bill_{client.ids['bill_txn']}")
    assert bill["amount_cents"] == 9000
    assert sky_bubbles[bill["bubble_id"]]["weather"] == bill["weather"]
    assert sky_bubbles[bill["bubble_id"]]["p_short"] == bill["p_short"]


def test_forecast_is_only_mine_and_leaks_no_ids(client):  # noqa: F811
    login(client, 1)  # Ben owes a Rent share; Ana's personal bill and balances are hers alone
    text = client.get("/api/forecast").text
    fc = client.get("/api/forecast").json()
    assert f"bill_{client.ids['bill_txn']}" not in text
    assert [b["bubble_id"] for b in fc["bills"]] == [f"exp_{client.ids['expense']}"]
    assert fc["bills"][0]["amount_cents"] == 3333  # his share, not the total
    for value in (v for group in NESSIE.values() for v in group):
        assert value not in text
    for name in ("Ana", "Cal", "Phone Co", "Payroll"):
        assert name not in text
    assert not re.search(r"\d{9,}", text)


# ---- debounce ----------------------------------------------------------------------------------


class RecordingDebouncer(forecast.Debouncer):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.flushes: list[tuple[list[int], list[int]]] = []

    async def flush(self, user_ids, payment_ids=()) -> None:
        self.flushes.append((list(user_ids), list(payment_ids)))


def test_debounce_coalesces_a_burst_into_one_recompute():
    async def scenario():
        d = RecordingDebouncer(delay_s=0.05, max_wait_s=5)
        d.add([1])
        await asyncio.sleep(0.02)
        d.add([2], [7])
        await asyncio.sleep(0.02)
        d.add([1])
        assert d.flushes == []  # nothing yet: still inside the quiet period
        await asyncio.sleep(0.15)
        assert d.flushes == [([1, 2], [7])]
        d.add([3])
        await asyncio.sleep(0.15)
        return d.flushes

    assert asyncio.run(scenario()) == [([1, 2], [7]), ([3], [])]


def test_debounce_max_wait_bounds_a_steady_stream():
    async def scenario():
        d = RecordingDebouncer(delay_s=0.05, max_wait_s=0.12)
        for _ in range(10):  # a write every 30 ms never goes quiet for 50 ms
            d.add([1])
            await asyncio.sleep(0.03)
        await asyncio.sleep(0.1)
        return d.flushes

    flushes = asyncio.run(scenario())
    assert 2 <= len(flushes) <= 4
    assert all(f == ([1], []) for f in flushes)


def test_request_update_from_a_threadpool_thread_schedules_on_the_loop(monkeypatch):
    from fastapi.concurrency import run_in_threadpool

    d = RecordingDebouncer(delay_s=0.01)
    monkeypatch.setattr(forecast, "debouncer", d)

    async def scenario():
        await run_in_threadpool(forecast.request_update, [4, 5])
        await asyncio.sleep(0.1)

    asyncio.run(scenario())
    assert d.flushes == [([4, 5], [])]


def test_request_update_without_a_loop_is_a_no_op(monkeypatch):
    d = RecordingDebouncer(delay_s=0.01)
    monkeypatch.setattr(forecast, "debouncer", d)
    forecast.request_update([1])  # e.g. a CLI script: must not raise
    assert d.flushes == []


# ---- event payloads ----------------------------------------------------------------------------


@pytest.fixture
def emits(monkeypatch):
    sent: list[tuple[str, dict, str]] = []

    async def fake_emit(event, payload, room=None, **_):
        sent.append((event, payload, room))

    monkeypatch.setattr(sio, "emit", fake_emit)
    return sent


def test_event_payload_is_each_users_own_sky_and_nothing_else(client, emits):  # noqa: F811
    users = client.ids["users"]
    asyncio.run(forecast.Debouncer().flush(users))
    assert [(e, room) for e, _, room in emits] == [("forecast.updated", user_room(u)) for u in users]
    for (_, payload, _), index in zip(emits, range(3), strict=True):
        assert_shape(payload, EVENT, "ForecastUpdatedEvent")
        for b in payload["bubbles"]:
            assert_shape(b, EVENT_BUBBLE, "bubble")
            assert b["weather"] in WEATHER
        client.cookies.clear()
        login(client, index)
        own = client.get("/api/sky").json()
        assert [b["bubble_id"] for b in payload["bubbles"]] == [b["bubble_id"] for b in own["bubbles"]]
        assert payload["safe_to_spend_cents"] == own["safe_to_spend_cents"]
    ben, cal = emits[1][1], emits[2][1]
    for other in (ben, cal):
        text = str(other)
        assert f"bill_{client.ids['bill_txn']}" not in text  # Ana's personal bill
        for leak in ("Ana", "Ben", "Cal", "Rent", "Phone", "label", "name", "_cents': 9000"):
            assert leak not in text
        assert other["safe_to_spend_cents"] == 0  # no accounts of their own


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_payments_emit_one_debounced_update_to_payer_and_payee_only(api, emits, monkeypatch):  # noqa: F811
    monkeypatch.setattr(forecast, "debouncer", forecast.Debouncer(delay_s=0.3))
    h = api.h
    as_user(api, "Ben")
    for label, cents, key in (("Electric", 4200, "pop-key-fc-0001"), ("Rent", 3333, "pop-key-fc-0002")):
        res = api.post("/api/payments", json=body(api, "Ben", f"exp_{h['expenses'][label]}", cents, key=key))
        assert res.status_code == 200, res.text

    def updates():
        return [(room, p) for e, p, room in emits if e == "forecast.updated"]

    assert _wait_for(lambda: len(updates()) >= 2)
    time.sleep(0.5)  # nothing else trickles in after the burst
    got = dict(updates())
    assert len(updates()) == 2
    assert set(got) == {user_room(h["users"]["Ben"]), user_room(h["users"]["Ana"])}  # not Cal
    ben = got[user_room(h["users"]["Ben"])]
    assert_shape(ben, EVENT, "ForecastUpdatedEvent")
    assert f"bill_{h['bill_txn']}" in {b["bubble_id"] for b in ben["bubbles"]}  # his own bill
    assert f"bill_{h['bill_txn']}" not in str(got[user_room(h["users"]["Ana"])])
    # The event is sent after the share/feed events of the same payment.
    events = [e for e, _, _ in emits]
    assert events.index("forecast.updated") > events.index("share.updated")


def test_new_expense_emits_one_update_to_each_participant_only(api, emits, monkeypatch):  # noqa: F811
    monkeypatch.setattr(forecast, "debouncer", forecast.Debouncer(delay_s=0.05))
    h = api.h
    as_user(api, "Ana")
    req = {
        "idempotency_key": "exp-key-fc-0001",
        "label": "Groceries",
        "total_cents": 1000,
        "split_method": "even",
        "participants": [{"user_id": f"u_{h['users']['Ana']}"}, {"user_id": f"u_{h['users']['Ben']}"}],
    }
    res = api.post("/api/expenses", json=req)
    assert res.status_code == 200, res.text
    assert _wait_for(lambda: sum(e == "forecast.updated" for e, _, _ in emits) >= 2)
    time.sleep(0.2)
    rooms = sorted(room for e, _, room in emits if e == "forecast.updated")
    assert rooms == sorted([user_room(h["users"]["Ana"]), user_room(h["users"]["Ben"])])  # not Cal
