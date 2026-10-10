"""Database connections (psycopg 3). Never log the DSN: it carries the password."""

import psycopg

from api.config import get_settings

CONNECT_TIMEOUT_S = 3


def connect(dsn: str | None = None, **kwargs) -> psycopg.Connection:
    return psycopg.connect(dsn or get_settings().dsn, connect_timeout=CONNECT_TIMEOUT_S, **kwargs)


async def connect_async(dsn: str | None = None, **kwargs) -> psycopg.AsyncConnection:
    return await psycopg.AsyncConnection.connect(
        dsn or get_settings().dsn, connect_timeout=CONNECT_TIMEOUT_S, **kwargs
    )


def get_conn():
    """FastAPI dependency: one sync connection per request (handlers are plain `def`, so they run in
    the threadpool). Tests override this to point at a scratch database."""
    with connect() as conn:
        yield conn
