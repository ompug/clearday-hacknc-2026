from fastapi.testclient import TestClient

import api.main as main
from api.main import app


def test_health_ok(server_dsn):
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}


def test_health_reports_unreachable_db(monkeypatch):
    async def refuse(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(main, "connect_async", refuse)
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json() == {"status": "degraded", "db": "unreachable"}


def test_health_reports_pending_migrations(server_dsn, monkeypatch):
    from pathlib import Path

    real = main.discover()
    monkeypatch.setattr(main, "discover", lambda: [*real, Path("9999_not_applied_yet.sql")])
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json() == {"status": "degraded", "db": "ok", "migrations": "pending"}


def test_health_reports_pending_when_the_tracking_table_is_missing(scratch_dsn, monkeypatch):
    from api.db import connect_async

    async def scratch(*args, **kwargs):
        return await connect_async(scratch_dsn)

    monkeypatch.setattr(main, "connect_async", scratch)
    with TestClient(app) as client:
        res = client.get("/api/health")
    assert res.status_code == 503
    assert res.json()["migrations"] == "pending"
