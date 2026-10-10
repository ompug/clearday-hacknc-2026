import json
import logging

import httpx
import pytest

from api.nessie import money
from api.nessie.cache import MemoryCache, cache_key
from api.nessie.client import NessieClient, NessieError
from api.tests.fake_nessie import KEY, FakeNessie


@pytest.fixture
def fake():
    return FakeNessie()


@pytest.fixture
def client(fake):
    with NessieClient(KEY, "https://nessie.test", cache=MemoryCache(), transport=fake.transport()) as c:
        yield c


# ---- conversion ------------------------------------------------------------------------------


def test_whole_dollar_conversion_refuses_lost_cents():
    assert money.cents_to_whole_dollars(123_400) == 1234
    assert money.whole_dollars_to_cents(1234) == 123_400
    assert money.whole_dollars_to_cents(12.0) == 1200
    with pytest.raises(money.LossyAmountError):
        money.cents_to_whole_dollars(1234)
    with pytest.raises(money.LossyAmountError):
        money.whole_dollars_to_cents(12.34)
    with pytest.raises(TypeError):
        money.cents_to_whole_dollars(12.0)
    with pytest.raises(TypeError):
        money.cents_to_whole_dollars(True)
    with pytest.raises(ValueError):
        money.cents_to_whole_dollars(-100)


def test_bill_amounts_round_trip_every_cent():
    assert money.cents_to_bill_amount(8437) == 84.37
    assert money.cents_to_bill_amount(5) == 0.05
    for cents in range(0, 200_001, 7):
        assert money.bill_amount_to_cents(money.cents_to_bill_amount(cents)) == cents
    assert money.bill_amount_to_cents(0.1 + 0.2) == 30  # float noise rounds, never truncates


def test_purchase_goes_out_in_dollars_with_every_field_and_comes_back_in_cents(client, fake):
    made = client.create_purchase("acct-1", "m" * 36, 4_200, "2026-10-01", "completed", "Groceries")
    sent = json.loads(fake.requests[-1].content)
    assert sent == {
        "merchant_id": "m" * 36,
        "medium": "balance",
        "purchase_date": "2026-10-01",
        "amount": 42,
        "status": "completed",
        "description": "Groceries",
    }
    assert isinstance(sent["amount"], int)
    assert made["amount_cents"] == 4_200 and made["id"]
    assert client.list_purchases("acct-1")[0]["amount_cents"] == 4_200


def test_lossy_amount_is_rejected_before_any_request(client, fake):
    with pytest.raises(money.LossyAmountError):
        client.create_deposit("acct-1", 1_234, "2026-10-01", "completed", "Payroll")
    assert fake.requests == []


def test_bill_keeps_cents_and_sends_every_read_field(client, fake):
    client.create_bill("acct-1", "Duke Energy", "Electric", 12_637, "2026-10-15", 15, "pending")
    sent = json.loads(fake.requests[-1].content)
    assert sent["payment_amount"] == 126.37
    assert {"nickname", "payment_date", "recurring_date", "status", "payee"} <= sent.keys()
    assert client.list_bills("acct-1")[0]["amount_cents"] == 12_637


def test_transfer_id_is_normalised_and_empty_list_404_is_empty(client):
    assert client.list_transfers("acct-1") == []
    made = client.create_transfer("acct-1", 80_000, "2026-10-03", "completed", "Rent share to Maya")
    listed = client.list_transfers("acct-1")
    assert listed[0]["id"] == made["id"]
    assert listed[0]["amount_cents"] == 80_000


def test_account_types_map_both_ways(client, fake):
    made = client.create_account("cust-1", "credit_card", "Rewards Card", 0)
    assert json.loads(fake.requests[-1].content)["type"] == "Credit Card"
    assert made["type"] == "credit_card"
    with pytest.raises(KeyError):
        client.create_account("cust-1", "brokerage", "Nope", 0)


def test_bad_dates_and_statuses_are_rejected(client):
    with pytest.raises(ValueError):
        client.create_deposit("a", 100, "10/01/2026", "completed", "x")
    with pytest.raises(ValueError):
        client.create_deposit("a", 100, "2026-10-01", "posted", "x")


# ---- caching ---------------------------------------------------------------------------------


def test_every_response_is_cached_without_the_key(client):
    client.list_customers()
    client.create_customer(
        "Maya", "Okafor", {"street_number": 1, "street_name": "A", "city": "B", "state": "NC", "zip": "27516"}
    )
    entries = list(client.cache.entries.values())
    assert [(e.method, e.path) for e in entries] == [("GET", "/customers"), ("POST", "/customers")]
    for e in entries:
        assert e.query == {}
        assert KEY not in json.dumps([e.path, e.query, e.request_body, e.response_body])


def test_get_falls_back_to_cache_when_nessie_is_down(client, fake):
    client.create_merchant(
        "Harris Teeter",
        "groceries",
        {"street_number": 1, "street_name": "A", "city": "B", "state": "NC", "zip": "1"},
        35.9,
        -79.0,
    )
    live = client.list_merchants()
    fake.down = True
    assert client.list_merchants() == live
    with pytest.raises(NessieError):
        client.list_customers()  # never fetched, so nothing cached
    with pytest.raises(NessieError):  # writes never come from cache
        client.create_merchant(
            "X",
            "y",
            {"street_number": 1, "street_name": "A", "city": "B", "state": "NC", "zip": "1"},
            0.0,
            0.0,
        )


def test_cache_key_refuses_the_api_key():
    with pytest.raises(ValueError):
        cache_key("GET", "/customers", {"key": KEY}, None)


# ---- redaction -------------------------------------------------------------------------------


def _assert_no_key(text: str):
    assert KEY not in text
    assert "key=" not in text or "key=REDACTED" in text


def test_key_never_reaches_logs_or_errors(fake, caplog):
    caplog.set_level(logging.DEBUG)
    with NessieClient(KEY, "https://nessie.test", transport=fake.transport()) as client:
        client.list_customers()  # httpx logs the request URL at INFO
        with pytest.raises(NessieError) as bad_route:
            client._request("GET", "/nope")
        fake.down = True
        with pytest.raises(NessieError) as down:
            client.list_customers()
    assert any("HTTP Request" in r.getMessage() for r in caplog.records)
    for record in caplog.records:
        _assert_no_key(record.getMessage())
    for exc in (bad_route.value, down.value):
        _assert_no_key(str(exc))
        _assert_no_key(repr(exc))
        assert exc.__cause__ is None or KEY not in str(exc.__cause__)
    assert down.value.__suppress_context__ or down.value.__context__ is None


def test_key_is_sent_as_query_param(client, fake):
    client.list_customers()
    assert fake.requests[-1].url.params["key"] == KEY


def test_missing_key_is_refused():
    with pytest.raises(ValueError):
        NessieClient("", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
