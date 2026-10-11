"""scripts/reset_demo.py: seed (fake Nessie), pay through the service layer, reset, and compare the DB and
Nessie with the snapshot taken straight after the seed."""

from __future__ import annotations

import copy

import pytest

from api import ids, payments
from api.db import connect
from api.migrate import migrate
from api.nessie.cache import PgCache
from api.nessie.client import NessieClient
from api.session import load_member
from api.tests.fake_nessie import KEY, FakeNessie
from scripts import reset_demo
from scripts import seed_nessie as seed

SNAPSHOT_SQL = {
    "transactions": "SELECT * FROM transactions ORDER BY id",
    "shares": "SELECT * FROM shares ORDER BY id",
    "expenses": "SELECT * FROM expenses ORDER BY id",
    "accounts": "SELECT * FROM accounts ORDER BY id",
    "payments": "SELECT * FROM payments ORDER BY id",
    "allocations": "SELECT * FROM allocations ORDER BY id",
    "feed_events": "SELECT * FROM feed_events ORDER BY id",
}


def snapshot(conn) -> dict:
    out = {name: conn.execute(sql).fetchall() for name, sql in SNAPSHOT_SQL.items()}
    conn.commit()
    return out


@pytest.fixture
def seeded(scratch_dsn):
    fake = FakeNessie()
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        client = NessieClient(KEY, "https://nessie.test", cache=PgCache(conn), transport=fake.transport())
        # Records outside our 3 customers must survive the reset, "Clearday:" description or not.
        probe = client.create_customer("zz-probe", "", seed.HOME)
        probe_acct = client.create_account(probe["id"], "checking", "Everyday Checking", 0)
        client.create_transfer(probe_acct["id"], 500, "2026-10-10", "completed", "Clearday: Rent share")
        plan = seed.build_plan()
        s = seed.seed_nessie(client, plan, dry_run=False)
        seed.write_db(conn, client, plan, s)
        conn.commit()
        yield {"conn": conn, "client": client, "fake": fake, "plan": plan, "seeded": s}


def _pop(conn, client, user_id: int, bubble_id: str, amount: int, key: str) -> None:
    user = load_member(conn, user_id)
    account = conn.execute(
        "SELECT id FROM accounts WHERE user_id = %s AND type = 'checking'", (user_id,)
    ).fetchone()[0]
    outcome = payments.pop_bubble(
        conn,
        user,
        idempotency_key=key,
        bubble_id=bubble_id,
        account_id=ids.encode(ids.ACCOUNT, account),
        amount_cents=amount,
    )
    assert payments.mirror_payment(conn, client, outcome.payment_id) == "mirrored"


def test_reset_returns_db_and_nessie_to_the_seed(seeded):
    conn, client, fake = seeded["conn"], seeded["client"], seeded["fake"]
    before_db = snapshot(conn)
    before_nessie = copy.deepcopy(fake.children)

    jake = conn.execute("SELECT id FROM users WHERE display_name = 'Jake'").fetchone()[0]
    rent, share = conn.execute(
        """SELECT e.id, s.amount_cents FROM expenses e JOIN shares s ON s.expense_id = e.id
           WHERE e.label = 'Rent' AND s.user_id = %s""",
        (jake,),
    ).fetchone()
    _pop(conn, client, jake, ids.encode(ids.EXPENSE, rent), share, "reset-test-rent-0001")
    phone, phone_cents = conn.execute(
        "SELECT id, amount_cents FROM transactions"
        " WHERE user_id = %s AND kind = 'bill' AND status = 'pending'",
        (jake,),
    ).fetchone()
    _pop(conn, client, jake, ids.encode(ids.BILL, phone), phone_cents, "reset-test-phone-0001")
    # A stray mirror with no payment row (e.g. its row was lost) is still found by its description.
    jake_checking = seeded["seeded"].accounts[("jake", "checking")]
    client.create_transfer(jake_checking, 100, "2026-10-10", "completed", "Clearday: Internet share")
    conn.execute(
        "INSERT INTO feed_events (household_id, type, actor_id, subject_label)"
        " SELECT household_id, 'share_paid', %s, 'Rent' FROM household_members WHERE user_id = %s",
        (jake, jake),
    )
    conn.commit()

    after_pop = snapshot(conn)
    assert len(after_pop["payments"]) == 2 and after_pop["feed_events"]
    assert after_pop != before_db

    result = reset_demo.reset(conn, client, plan=seeded["plan"])
    assert result.nessie == {"transfers deleted": 2, "deposits deleted": 1, "bills reopened": 1}
    assert result.db["payments deleted"] == 2 and result.db["bills reopened"] == 1
    assert snapshot(conn) == before_db

    # Nessie: our accounts match the seed; the zz-probe "Clearday:" transfer is untouched.
    ours = set(seeded["seeded"].accounts.values())
    for kind, store in fake.children.items():
        mine = {k: v for k, v in store.items() if v.get("account_id") in ours}
        seed_mine = {k: v for k, v in before_nessie[kind].items() if v.get("account_id") in ours}
        assert mine == seed_mine, kind
    assert any(t["description"].startswith("Clearday:") for t in fake.children["transfers"].values())

    # Idempotent: a second run (and a dry run) changes nothing.
    writes = fake.writes()
    again = reset_demo.reset(conn, client, plan=seeded["plan"])
    assert not any(again.nessie.values()) and not any(again.db.values())
    assert fake.writes() == writes
    assert snapshot(conn) == before_db


def test_dry_run_and_db_only(seeded):
    conn, client, fake = seeded["conn"], seeded["client"], seeded["fake"]
    before_db = snapshot(conn)
    priya = conn.execute("SELECT id FROM users WHERE display_name = 'Priya'").fetchone()[0]
    internet, share = conn.execute(
        """SELECT e.id, s.amount_cents FROM expenses e JOIN shares s ON s.expense_id = e.id
           WHERE e.label = 'Internet' AND s.user_id = %s""",
        (priya,),
    ).fetchone()
    _pop(conn, client, priya, ids.encode(ids.EXPENSE, internet), share, "reset-test-net-00001")
    popped_db, popped_nessie, writes = snapshot(conn), copy.deepcopy(fake.children), fake.writes()

    dry = reset_demo.reset(conn, client, dry_run=True, plan=seeded["plan"])
    assert dry.nessie == {"transfers deleted": 1, "deposits deleted": 1}
    assert dry.db["payments deleted"] == 1 and dry.db["shares reset"] == 1
    assert snapshot(conn) == popped_db and fake.writes() == writes

    requests = len(fake.requests)
    db_only = reset_demo.reset(conn, None, plan=seeded["plan"])
    assert db_only.nessie is None and db_only.nessie_left == 2
    assert len(fake.requests) == requests  # Nessie never called
    assert fake.children == popped_nessie
    assert snapshot(conn) == before_db

    # Back online: the full reset cleans the mirror records the DB no longer knows about.
    online = reset_demo.reset(conn, client, plan=seeded["plan"])
    assert online.nessie == {"transfers deleted": 1, "deposits deleted": 1}
    assert snapshot(conn) == before_db


def test_sync_after_db_only_reset_keeps_the_seeded_state(seeded):
    """After --db-only, Nessie still holds the "Clearday:" mirrors and the completed bill. A sync must
    not import those mirrors or re-post the reopened bill, so the reset sticks."""
    from api.nessie.sync import sync_accounts  # noqa: PLC0415

    conn, client = seeded["conn"], seeded["client"]
    sync_accounts(conn, client)
    conn.commit()
    before_db = snapshot(conn)
    jake = conn.execute("SELECT id FROM users WHERE display_name = 'Jake'").fetchone()[0]
    rent, share = conn.execute(
        """SELECT e.id, s.amount_cents FROM expenses e JOIN shares s ON s.expense_id = e.id
           WHERE e.label = 'Rent' AND s.user_id = %s""",
        (jake,),
    ).fetchone()
    _pop(conn, client, jake, ids.encode(ids.EXPENSE, rent), share, "dbonly-sync-rent-01")
    phone, phone_cents = conn.execute(
        "SELECT id, amount_cents FROM transactions"
        " WHERE user_id = %s AND kind = 'bill' AND status = 'pending'",
        (jake,),
    ).fetchone()
    _pop(conn, client, jake, ids.encode(ids.BILL, phone), phone_cents, "dbonly-sync-phone-1")

    reset_demo.reset(conn, None, plan=seeded["plan"])
    assert snapshot(conn) == before_db
    stats = sync_accounts(conn, client)
    conn.commit()
    assert stats.orphan_mirrors == 2
    assert snapshot(conn) == before_db
