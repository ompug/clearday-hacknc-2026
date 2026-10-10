"""An in-memory Nessie behind httpx.MockTransport, mimicking the live quirks in notes/nessie-api.md:
POST returns objectCreated with ``_id``, transfers come back with ``id``, an empty transfer list is a
404, amounts are truncated to whole dollars, and unknown routes are 403."""

from __future__ import annotations

import itertools
import json
import re

import httpx

KEY = "test-secret-key-123"


class FakeNessie:
    def __init__(self) -> None:
        self.ids = itertools.count(1)
        self.customers: dict[str, dict] = {}
        self.merchants: dict[str, dict] = {}
        self.accounts: dict[str, dict] = {}
        self.children: dict[str, dict[str, dict]] = {
            "purchases": {},
            "deposits": {},
            "transfers": {},
            "bills": {},
        }
        self.requests: list[httpx.Request] = []
        self.down = False

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def new_id(self) -> str:
        return f"00000000-0000-0000-0000-{next(self.ids):012d}"

    def writes(self) -> int:
        return sum(1 for r in self.requests if r.method != "GET")

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("boom", request=request)
        if request.url.params.get("key") != KEY:
            return httpx.Response(401, json="bad key")
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else None
        m = re.fullmatch(r"/accounts/([^/]+)/(purchases|deposits|transfers|bills)", path)
        if path == "/customers":
            return self._list_or_create(method, body, self.customers, {})
        if path == "/merchants":
            return self._list_or_create(method, body, self.merchants, {})
        if mc := re.fullmatch(r"/customers/([^/]+)/accounts", path):
            cid = mc.group(1)
            if method == "POST":
                extra = {
                    "customer_id": cid,
                    "account_number": f"4000{next(self.ids):012d}",
                    "balance": int(body["balance"]),
                }
                return self._create(body, self.accounts, extra)
            return httpx.Response(200, json=[a for a in self.accounts.values() if a["customer_id"] == cid])
        if m:
            aid, kind = m.groups()
            store = self.children[kind]
            if method == "POST":
                extra = {"account_id": aid}
                if "amount" in body:
                    extra["amount"] = int(body["amount"])  # Nessie truncates
                return self._create(body, store, extra)
            rows = [dict(r) for r in store.values() if r["account_id"] == aid]
            if kind == "transfers":
                if not rows:
                    return httpx.Response(404, json="No transfers found for this account")
                for r in rows:
                    r["id"] = r.pop("_id")
            if kind == "purchases":
                for r in rows:
                    r["payer_id"] = r.pop("account_id")
            return httpx.Response(200, json=rows)
        return httpx.Response(403, json={"message": "Missing Authentication Token"})

    def _list_or_create(self, method, body, store, extra):
        if method == "POST":
            return self._create(body, store, extra)
        return httpx.Response(200, json=list(store.values()))

    def _create(self, body, store, extra):
        obj = {**body, **extra, "_id": self.new_id()}
        store[obj["_id"]] = obj
        return httpx.Response(201, json={"code": 201, "message": "Created", "objectCreated": obj})
