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
