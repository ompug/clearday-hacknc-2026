"""Real-database fixtures. Each test session gets a throwaway database on the configured server
(local docker-compose TimescaleDB by default) and drops it afterwards. Tests skip if no DB is up."""

import uuid

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from api.config import get_settings
from api.db import connect


@pytest.fixture(scope="session")
def server_dsn() -> str:
    dsn = get_settings().dsn
    try:
        with connect(dsn) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        pytest.skip("database not reachable; start it with: podman-compose up -d")
    return dsn


@pytest.fixture
def scratch_dsn(server_dsn: str):
    name = f"clearday_test_{uuid.uuid4().hex[:12]}"
    with connect(server_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield make_conninfo(server_dsn, dbname=name)
    finally:
        with connect(server_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(autouse=True)
def no_background_sync(monkeypatch):
    """TestClient(app) runs the lifespan; keep the real Nessie sync off unless a test turns it on."""
    monkeypatch.setattr(get_settings(), "nessie_sync_interval_s", 0)


@pytest.fixture(autouse=True)
def testclient_counts_as_loopback(monkeypatch):
    """Starlette's TestClient reports its peer as "testclient"; count it as this computer so login helpers
    work. test_session_security checks real loopback and LAN addresses."""
    from api.routes import session as session_routes  # noqa: PLC0415

    real = session_routes.is_loopback
    monkeypatch.setattr(session_routes, "is_loopback", lambda host: host == "testclient" or real(host))
