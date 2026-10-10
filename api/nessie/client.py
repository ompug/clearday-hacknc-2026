"""Nessie (Capital One sandbox) client. Live-verified behaviour is in notes/nessie-api.md.

Callers only ever see integer cents: every amount converts in api.nessie.money inside this module.
Every response is written to the cache, and a GET that can't reach Nessie falls back to it.
The API key travels only as the ``key`` query parameter and never appears in logs, errors or the cache.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any

import httpx

from api.nessie import money
from api.nessie.cache import CacheEntry, NessieCache

log = logging.getLogger("clearday.nessie")

DEFAULT_TIMEOUT_S = 15.0  # the first POST to a cold route takes about 1.2 s
GET_ATTEMPTS = 2

ACCOUNT_TYPES = {"checking": "Checking", "savings": "Savings", "credit_card": "Credit Card"}
ACCOUNT_TYPES_IN = {v: k for k, v in ACCOUNT_TYPES.items()}
TXN_STATUSES = {"pending", "cancelled", "completed"}
BILL_STATUSES = TXN_STATUSES | {"recurring"}
MEDIUMS = {"balance", "rewards"}

_KEY_RE = re.compile(r"(key=)[^&\s\"']*", re.IGNORECASE)


def redact(text: str) -> str:
    return _KEY_RE.sub(r"\1REDACTED", text)


class _RedactKeyFilter(logging.Filter):
    """httpx logs full request URLs at INFO, and those URLs carry ?key=. Rewrite them."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "key=" in message.lower():
            record.msg, record.args = redact(message), ()
        return True


for _name in ("httpx", "httpcore"):
    _logger = logging.getLogger(_name)
    if not any(isinstance(f, _RedactKeyFilter) for f in _logger.filters):
        _logger.addFilter(_RedactKeyFilter())


class NessieError(RuntimeError):
    """A failed Nessie call. Carries the path (never the URL, which holds the key)."""

    def __init__(self, method: str, path: str, status_code: int | None, detail: str) -> None:
        self.method, self.path, self.status_code = method, path, status_code
        super().__init__(redact(f"Nessie {method} {path} -> {status_code}: {detail[:200]}"))


def _date(value: str | dt.date) -> str:
    text = value.isoformat() if isinstance(value, dt.date) else value
    dt.date.fromisoformat(text)  # Nessie stores any string; validate before POST
    if len(text) != 10:
        raise ValueError(f"dates must be YYYY-MM-DD, got {text!r}")
    return text


def _choice(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _id(obj: dict) -> str:
    """Transfers return ``id``; everything else returns ``_id``."""
    value = obj.get("_id", obj.get("id"))
    if not isinstance(value, str) or not value:
        raise ValueError("Nessie object without an id")
    return value


# ---- normalisers: wire shape -> our shape (cents, ``id``, our enums) -------------------------


def _customer(o: dict) -> dict:
    return {"id": _id(o), "first_name": o.get("first_name", ""), "last_name": o.get("last_name", "")}


def _account(o: dict) -> dict:
    return {
        "id": _id(o),
        "customer_id": o.get("customer_id"),
        "type": ACCOUNT_TYPES_IN.get(o.get("type", ""), o.get("type")),
        "nickname": o.get("nickname", ""),
        "balance_cents": money.whole_dollars_to_cents(o.get("balance", 0)),
        "account_number": o.get("account_number"),  # backend only; store last4
    }


def _merchant(o: dict) -> dict:
    category = o.get("category")
    if isinstance(category, list):  # classic Nessie used arrays
        category = category[0] if category else None
    return {"id": _id(o), "name": o.get("name", ""), "category": category}


def _purchase(o: dict) -> dict:
    return {
        "id": _id(o),
        "account_id": o.get("payer_id"),
        "merchant_id": o.get("merchant_id"),
        "medium": o.get("medium"),
        "amount_cents": money.whole_dollars_to_cents(o["amount"]),
        "date": o.get("purchase_date"),
        "status": o.get("status"),
        "description": o.get("description", ""),
    }


def _money_movement(o: dict) -> dict:
    """Deposits and transfers."""
    return {
        "id": _id(o),
        "medium": o.get("medium"),
        "amount_cents": money.whole_dollars_to_cents(o["amount"]),
        "date": o.get("transaction_date"),
        "status": o.get("status"),
        "description": o.get("description", ""),
    }


def _bill(o: dict) -> dict:
    return {
        "id": _id(o),
        "account_id": o.get("account_id"),
        "status": o.get("status"),
        "payee": o.get("payee", ""),
        "nickname": o.get("nickname", ""),
        "amount_cents": money.bill_amount_to_cents(o["payment_amount"]),
        "date": o.get("payment_date"),
        "recurring_date": o.get("recurring_date"),
    }


class NessieClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://prod-api.nessieisreal.com",
        cache: NessieCache | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if not api_key:
            raise ValueError("NESSIE_API_KEY is not set (api/.env)")
        self._key = api_key
        self.cache = cache
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    @classmethod
    def from_settings(cls, cache: NessieCache | None = None) -> NessieClient:
        from api.config import get_settings

        settings = get_settings()
        return cls(settings.nessie_api_key.get_secret_value(), settings.nessie_base_url, cache=cache)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> NessieClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- transport ---------------------------------------------------------------------------

    def _request(self, method: str, path: str, body: Any = None, *, empty_on_404: bool = False) -> Any:
        query: dict[str, str] = {}
        attempts = GET_ATTEMPTS if method == "GET" else 1  # never retry a write: it may have landed
        response = None
        for attempt in range(attempts):
            try:
                response = self._http.request(method, path, params={"key": self._key}, json=body)
                break
            except httpx.HTTPError as exc:
                log.warning(
                    "Nessie %s %s failed (%s), attempt %d", method, path, type(exc).__name__, attempt + 1
                )
        if response is None:
            cached = self.cache.get(method, path, query, body) if self.cache and method == "GET" else None
            if cached is None:
                raise NessieError(method, path, None, "unreachable and not cached")
            log.warning("Nessie %s %s served from cache", method, path)
            response_status, data = cached.status_code, cached.response_body
        else:
            response_status = response.status_code
            try:
                data = response.json() if response.content else None
            except ValueError:
                data = response.text
            if self.cache is not None:
                self.cache.put(CacheEntry(method, path, query, body, response_status, data))
        if response_status == 404 and empty_on_404:
            return []  # e.g. an account with no transfers
        if response_status >= 400:
            raise NessieError(method, path, response_status, str(data))
        return data

    def _get_list(self, path: str, *, empty_on_404: bool = False) -> list[dict]:
        data = self._request("GET", path, empty_on_404=empty_on_404)
        if not isinstance(data, list):
            raise NessieError("GET", path, 200, "expected a list")
        return data

    def _create(self, path: str, body: dict) -> dict:
        data = self._request("POST", path, body)
        created = data.get("objectCreated") if isinstance(data, dict) else None
        if not isinstance(created, dict):
            raise NessieError("POST", path, 201, "response has no objectCreated")
        return created

    # ---- customers and merchants (no DELETE exists: look up by name before creating) -----------

    def list_customers(self) -> list[dict]:
        return [_customer(o) for o in self._get_list("/customers")]

    def create_customer(self, first_name: str, last_name: str, address: dict) -> dict:
        body = {
            "first_name": first_name,
            "last_name": last_name,
            "address": {k: str(address[k]) for k in ("street_number", "street_name", "city", "state", "zip")},
        }
        return _customer(self._create("/customers", body))

    def list_merchants(self) -> list[dict]:
        return [_merchant(o) for o in self._get_list("/merchants")]

    def create_merchant(self, name: str, category: str, address: dict, lat: float, lng: float) -> dict:
        body = {
            "name": name,
            "category": category,  # a string; an array gets 400
            "address": {k: str(address[k]) for k in ("street_number", "street_name", "city", "state", "zip")},
            "geocode": {"lat": lat, "lng": lng},
        }
        return _merchant(self._create("/merchants", body))

    # ---- accounts --------------------------------------------------------------------------------

    def list_accounts(self, customer_id: str) -> list[dict]:
        return [_account(o) for o in self._get_list(f"/customers/{customer_id}/accounts")]

    def get_account(self, account_id: str) -> dict:
        return _account(self._request("GET", f"/accounts/{account_id}"))

    def create_account(
        self, customer_id: str, type: str, nickname: str, opening_balance_cents: int, rewards: int = 0
    ) -> dict:
        body = {
            "type": ACCOUNT_TYPES[type],
            "nickname": nickname,
            "rewards": rewards,
            "balance": money.cents_to_whole_dollars(opening_balance_cents),
        }
        return _account(self._create(f"/customers/{customer_id}/accounts", body))

    # ---- activity --------------------------------------------------------------------------------

    def list_purchases(self, account_id: str) -> list[dict]:
        return [_purchase(o) for o in self._get_list(f"/accounts/{account_id}/purchases")]

    def create_purchase(
        self,
        account_id: str,
        merchant_id: str,
        amount_cents: int,
        date: str | dt.date,
        status: str,
        description: str,
        medium: str = "balance",
    ) -> dict:
        body = {
            "merchant_id": merchant_id,
            "medium": _choice(medium, MEDIUMS, "medium"),
            "purchase_date": _date(date),
            "amount": money.cents_to_whole_dollars(amount_cents),
            "status": _choice(status, TXN_STATUSES, "status"),
            "description": description,
        }
        return _purchase(self._create(f"/accounts/{account_id}/purchases", body))

    def list_deposits(self, account_id: str) -> list[dict]:
        return [_money_movement(o) for o in self._get_list(f"/accounts/{account_id}/deposits")]

    def create_deposit(
        self,
        account_id: str,
        amount_cents: int,
        date: str | dt.date,
        status: str,
        description: str,
        medium: str = "balance",
    ) -> dict:
        body = {
            "medium": _choice(medium, MEDIUMS, "medium"),
            "transaction_date": _date(date),
            "status": _choice(status, TXN_STATUSES, "status"),
            "amount": money.cents_to_whole_dollars(amount_cents),
            "description": description,
        }
        return _money_movement(self._create(f"/accounts/{account_id}/deposits", body))

    def list_transfers(self, account_id: str) -> list[dict]:
        # Nessie answers 404 "No transfers found for this account" for an empty list.
        rows = self._get_list(f"/accounts/{account_id}/transfers", empty_on_404=True)
        return [_money_movement(o) for o in rows]

    def create_transfer(
        self, account_id: str, amount_cents: int, date: str | dt.date, status: str, description: str
    ) -> dict:
        # Transfers have no payee field (payee_id/medium are rejected). Record the payee ourselves.
        body = {
            "transaction_date": _date(date),
            "status": _choice(status, TXN_STATUSES, "status"),
            "amount": money.cents_to_whole_dollars(amount_cents),
            "description": description,
        }
        return _money_movement(self._create(f"/accounts/{account_id}/transfers", body))

    def list_bills(self, account_id: str) -> list[dict]:
        return [_bill(o) for o in self._get_list(f"/accounts/{account_id}/bills")]

    def set_bill_status(self, bill_id: str, status: str) -> None:
        """PUT /bills/{id} {"status"}: "completed" is how a bill is marked paid (balances don't move)."""
        self._request("PUT", f"/bills/{bill_id}", {"status": _choice(status, BILL_STATUSES, "status")})

    def create_bill(
        self,
        account_id: str,
        payee: str,
        nickname: str,
        amount_cents: int,
        date: str | dt.date,
        recurring_date: int,
        status: str,
    ) -> dict:
        if not 1 <= recurring_date <= 31:
            raise ValueError("recurring_date must be a day of month (1 to 31)")
        body = {
            "status": _choice(status, BILL_STATUSES, "status"),
            "payee": payee,
            "nickname": nickname,
            "payment_date": _date(date),
            "recurring_date": recurring_date,
            "payment_amount": money.cents_to_bill_amount(amount_cents),
        }
        return _bill(self._create(f"/accounts/{account_id}/bills", body))
