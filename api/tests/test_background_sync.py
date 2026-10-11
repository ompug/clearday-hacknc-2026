"""Background Nessie sync: runs at API startup and every NESSIE_SYNC_INTERVAL_S, off the event loop, and
logs a failure by class name only (so no key, URL or response body reaches the log)."""

from __future__ import annotations

import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

from api.config import get_settings
from api.main import app
from api.nessie import background


@pytest.fixture
def interval(monkeypatch):
    def set_interval(seconds: float) -> None:
        monkeypatch.setattr(get_settings(), "nessie_sync_interval_s", seconds)

    return set_interval


def test_sync_runs_at_startup_and_then_periodically(monkeypatch, interval):
    calls = []
    monkeypatch.setattr(background, "sync_runner", lambda: calls.append(time.monotonic()))
    interval(0.05)
    with TestClient(app):
        deadline = time.monotonic() + 3
        while len(calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
    assert len(calls) >= 3
    stopped = len(calls)
    time.sleep(0.2)
    assert len(calls) == stopped, "the loop stops with the app"


def test_interval_zero_disables_the_background_sync(monkeypatch, interval):
    calls = []
    monkeypatch.setattr(background, "sync_runner", lambda: calls.append(1))
    interval(0)
    with TestClient(app):
        time.sleep(0.2)
    assert calls == []


def test_a_slow_sync_never_blocks_requests(monkeypatch, interval):
    release = threading.Event()
    started = threading.Event()

    def slow_sync():
        started.set()
        release.wait(5)

    monkeypatch.setattr(background, "sync_runner", slow_sync)
    interval(60)
    try:
        with TestClient(app) as client:
            assert started.wait(3), "startup sync should begin straight away"
            t0 = time.monotonic()
            client.get("/api/health")  # any route; 503 is fine when the DB is down
            assert time.monotonic() - t0 < 2
            release.set()
    finally:
        release.set()


def test_failures_are_logged_without_secrets_and_the_loop_keeps_going(monkeypatch, interval, caplog):
    calls = []

    def failing_sync():
        calls.append(1)
        raise RuntimeError("GET https://nessie.test/x?key=SUPERSECRETKEY -> 500 account 1234567890123456")

    monkeypatch.setattr(background, "sync_runner", failing_sync)
    interval(0.05)
    with caplog.at_level(logging.WARNING, logger="clearday.nessie.background"):
        with TestClient(app):
            deadline = time.monotonic() + 3
            while len(calls) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
    assert len(calls) >= 2, "a failed sync must not stop the loop"
    text = caplog.text
    assert "RuntimeError" in text
    for leak in ("SUPERSECRETKEY", "key=", "1234567890123456", "nessie.test"):
        assert leak not in text


def test_a_pop_that_lands_mid_sync_keeps_its_ledger_transactions(scratch_dsn):
    """The background sync can overlap a pop: the pop's mirror is linked after sync read the owned set.
    Sync must never delete the ledger's own payer or payee transaction rows."""
    from api import ids, payments  # noqa: PLC0415
    from api.db import connect  # noqa: PLC0415
    from api.migrate import migrate  # noqa: PLC0415
    from api.nessie.cache import PgCache  # noqa: PLC0415
    from api.nessie.client import NessieClient  # noqa: PLC0415
    from api.nessie.sync import sync_accounts  # noqa: PLC0415
    from api.session import load_member  # noqa: PLC0415
    from api.tests.fake_nessie import KEY, FakeNessie  # noqa: PLC0415
    from scripts import seed_nessie as seed  # noqa: PLC0415

    fake = FakeNessie()
    with connect(scratch_dsn) as conn, connect(scratch_dsn) as other:
        migrate(conn)
        conn.autocommit = False
        client = NessieClient(KEY, "https://nessie.test", cache=PgCache(conn), transport=fake.transport())
        plan = seed.build_plan()
        seed.write_db(conn, client, plan, seed.seed_nessie(client, plan, dry_run=False))
        conn.commit()
        sync_accounts(conn, client)
        conn.commit()

        jake = other.execute("SELECT id FROM users WHERE display_name = 'Jake'").fetchone()[0]
        rent, share = other.execute(
            """SELECT e.id, s.amount_cents FROM expenses e JOIN shares s ON s.expense_id = e.id
               WHERE e.label = 'Rent' AND s.user_id = %s""",
            (jake,),
        ).fetchone()
        account = other.execute(
            "SELECT id FROM accounts WHERE user_id = %s AND type = 'checking'", (jake,)
        ).fetchone()[0]
        other.commit()
        other_client = NessieClient(
            KEY, "https://nessie.test", cache=PgCache(other), transport=fake.transport()
        )

        def pop_now():
            outcome = payments.pop_bubble(
                other,
                load_member(other, jake),
                idempotency_key="mid-sync-pop-0001",
                bubble_id=ids.encode(ids.EXPENSE, rent),
                account_id=ids.encode(ids.ACCOUNT, account),
                amount_cents=share,
            )
            assert payments.mirror_payment(other, other_client, outcome.payment_id) == "mirrored"
            return outcome.payment_id

        popped = []
        real_list = client.list_transfers

        def list_transfers_with_a_pop(acct):
            if not popped:
                popped.append(pop_now())
            return real_list(acct)

        client.list_transfers = list_transfers_with_a_pop
        sync_accounts(conn, client)
        conn.commit()
        missing = conn.execute(
            """SELECT p.id FROM payments p
               WHERE NOT EXISTS (SELECT 1 FROM transactions t WHERE t.id = p.payer_txn_id)
                  OR NOT EXISTS (SELECT 1 FROM transactions t WHERE t.id = p.payee_txn_id)"""
        ).fetchall()
        assert popped and missing == []
