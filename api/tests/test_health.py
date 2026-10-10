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
