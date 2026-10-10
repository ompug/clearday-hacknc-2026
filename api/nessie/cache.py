"""The Nessie response cache (table nessie_cache). The demo reads from here if Nessie is down.

Keys are sha256 over method, path, canonical query (the API key is never part of it) and body.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class CacheEntry:
    method: str
    path: str
    query: dict[str, str]
    request_body: Any
    status_code: int
    response_body: Any


def cache_key(method: str, path: str, query: dict[str, str], body: Any) -> str:
    if "key" in query or "key=" in path:
        raise ValueError("the API key must never reach the cache")
    canonical = json.dumps([method.upper(), path, sorted(query.items()), body], sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class NessieCache(Protocol):
    def put(self, entry: CacheEntry) -> None: ...

    def get(self, method: str, path: str, query: dict[str, str], body: Any) -> CacheEntry | None: ...


class MemoryCache:
    """For tests and dry runs."""

    def __init__(self) -> None:
        self.entries: dict[str, CacheEntry] = {}

    def put(self, entry: CacheEntry) -> None:
        key = cache_key(entry.method, entry.path, entry.query, entry.request_body)
        self.entries[key] = entry

    def get(self, method, path, query, body):
        return self.entries.get(cache_key(method, path, query, body))


class PgCache:
    """Writes through to nessie_cache on a psycopg connection (autocommit or caller-managed)."""

    def __init__(self, conn) -> None:
        self.conn = conn

    def put(self, entry: CacheEntry) -> None:
        key = cache_key(entry.method, entry.path, entry.query, entry.request_body)
        body = None if entry.request_body is None else Jsonb(entry.request_body)
        self.conn.execute(
            """
            INSERT INTO nessie_cache
                (cache_key, method, path, query, request_body, status_code, response_body)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                status_code = EXCLUDED.status_code,
                response_body = EXCLUDED.response_body,
                fetched_at = now()
            """,
            (
                key,
                entry.method,
                entry.path,
                Jsonb(entry.query),
                body,
                entry.status_code,
                Jsonb(entry.response_body),
            ),
        )

    def get(self, method, path, query, body):
        row = self.conn.execute(
            "SELECT status_code, response_body FROM nessie_cache WHERE cache_key = %s",
            (cache_key(method, path, query, body),),
        ).fetchone()
        if row is None:
            return None
        return CacheEntry(method, path, query, body, row[0], row[1])
