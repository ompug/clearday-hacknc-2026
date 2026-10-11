"""Background Nessie sync for the API process: once at startup, then every NESSIE_SYNC_INTERVAL_S.

Each run is `sync_accounts` (which first retries failed pop mirrors) on its own DB connection in a
worker thread, so requests never wait on it. A failure is logged by exception class only: Nessie errors
can carry URLs and response bodies, which must never reach the log. 0 disables the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from api.config import get_settings
from api.db import connect
from api.nessie.cache import PgCache
from api.nessie.client import NessieClient
from api.nessie.sync import sync_accounts

log = logging.getLogger("clearday.nessie.background")


def run_sync() -> None:
    """One sync with a fresh connection and the real Nessie client (blocking; run it in a thread)."""
    if not get_settings().nessie_api_key.get_secret_value():
        log.info("background sync skipped: no Nessie key configured")
        return
    from api import sky  # noqa: PLC0415 (sky imports the payments layer; keep startup imports light)

    with connect() as conn:
        with NessieClient.from_settings(cache=PgCache(conn)) as client:
            stats = sync_accounts(conn, client)
        conn.commit()
    if stats.changed:
        sky.invalidate_forecasts()
    log.info("background sync: %d changed, %d accounts", stats.changed, stats.accounts)


# Swapped in tests; read at call time.
sync_runner: Callable[[], object] = run_sync


async def sync_once() -> None:
    try:
        await asyncio.to_thread(sync_runner)
    except Exception as exc:  # never crash the loop; class name only (no URLs, keys or bodies)
        log.warning("background sync failed (%s); retrying next interval", type(exc).__name__)


async def sync_forever(interval_s: float) -> None:
    while True:
        await sync_once()
        await asyncio.sleep(interval_s)


@asynccontextmanager
async def lifespan(_app) -> AsyncIterator[None]:
    interval = get_settings().nessie_sync_interval_s
    task = asyncio.create_task(sync_forever(interval)) if interval > 0 else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
