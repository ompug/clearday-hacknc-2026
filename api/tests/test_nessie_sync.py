import pytest

from api.balances import account_balances_cents
from api.db import connect
from api.migrate import migrate
from api.nessie.cache import PgCache
from api.nessie.client import NessieClient
from api.nessie.sync import sync_accounts
from api.tests.fake_nessie import KEY, FakeNessie

ADDR = {"street_number": 1, "street_name": "A", "city": "B", "state": "NC", "zip": "27516"}


@pytest.fixture
def db(scratch_dsn):
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        yield conn


@pytest.fixture
def world(db):
    """A Nessie with one checking account and some activity, mirrored as one account in our DB."""
    fake = FakeNessie()
    client = NessieClient(KEY, "https://nessie.test", cache=PgCache(db), transport=fake.transport())
    cust = client.create_customer("Maya", "Okafor", ADDR)
    acct = client.create_account(cust["id"], "checking", "Everyday Checking", 100_000)
    shop = client.create_merchant("Harris Teeter", "groceries", ADDR, 35.9, -79.0)
    client.create_purchase(acct["id"], shop["id"], 4_200, "2026-10-01", "completed", "Groceries")
    client.create_purchase(acct["id"], shop["id"], 1_000, "2026-10-10", "pending", "Groceries")
    client.create_deposit(acct["id"], 120_000, "2026-10-03", "completed", "Payroll")
    client.create_transfer(acct["id"], 30_000, "2026-10-05", "completed", "Savings transfer")
    client.create_bill(acct["id"], "Duke Energy", "Electric", 12_637, "2026-09-15", 15, "completed")
    client.create_bill(acct["id"], "Duke Energy", "Electric", 9_900, "2026-10-15", 15, "pending")
    user_id = db.execute(
        "INSERT INTO users (display_name, nessie_customer_id) VALUES ('Maya', %s) RETURNING id", (cust["id"],)
    ).fetchone()[0]
    account_id = db.execute(
        """INSERT INTO accounts (user_id, nessie_account_id, type, nickname, last4, opening_balance_cents)
           VALUES (%s, %s, 'checking', 'Everyday Checking', '1234', 100000) RETURNING id""",
        (user_id, acct["id"]),
    ).fetchone()[0]
    db.commit()
    return fake, client, user_id, account_id, acct["id"]


def txns(db):
    return db.execute(
        "SELECT kind, amount_cents, merchant, category, status, occurred_at::date::text"
        " FROM transactions ORDER BY occurred_at, kind"
    ).fetchall()


def test_sync_mirrors_activity_in_cents(db, world):
    _, client, *_ = world
    stats = sync_accounts(db, client)
    assert (stats.accounts, stats.inserted, stats.updated, stats.removed) == (1, 6, 0, 0)
    assert txns(db) == [
        ("bill", 12_637, "Duke Energy", "bills", "posted", "2026-09-15"),
        ("purchase", 4_200, "Harris Teeter", "groceries", "posted", "2026-10-01"),
        ("deposit", 120_000, "Payroll", "income", "posted", "2026-10-03"),
        ("transfer", 30_000, "Savings transfer", "transfer", "posted", "2026-10-05"),
        ("purchase", 1_000, "Harris Teeter", "groceries", "pending", "2026-10-10"),
        ("bill", 9_900, "Duke Energy", "bills", "pending", "2026-10-15"),
    ]


def test_sync_is_idempotent(db, world):
    _, client, *_ = world
    sync_accounts(db, client)
    before = txns(db)
    again = sync_accounts(db, client)
    assert again.changed == 0 and again.unchanged == 6
    assert txns(db) == before


def test_sync_applies_edits_moves_and_removals(db, world):
    fake, client, *_ = world
    sync_accounts(db, client)
    purchase = next(p for p in fake.children["purchases"].values() if p["status"] == "completed")
    purchase["amount"] = 45
    bill = next(b for b in fake.children["bills"].values() if b["status"] == "pending")
    bill["payment_date"] = "2026-10-16"
    deposit = next(iter(fake.children["deposits"].values()))
    del fake.children["deposits"][deposit["_id"]]
    stats = sync_accounts(db, client)
    assert (stats.inserted, stats.updated, stats.removed) == (0, 2, 1)
    rows = txns(db)
    assert ("purchase", 4_500, "Harris Teeter", "groceries", "posted", "2026-10-01") in rows
    assert ("bill", 9_900, "Duke Energy", "bills", "pending", "2026-10-16") in rows
    assert not any(r[0] == "deposit" for r in rows)
    assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == 5


def test_sync_refreshes_the_cache_without_the_key(db, world):
    _, client, *_ = world
    db.execute("DELETE FROM nessie_cache")
    sync_accounts(db, client)
    db.commit()
    paths = {r[0] for r in db.execute("SELECT path FROM nessie_cache WHERE method = 'GET'").fetchall()}
    assert "/merchants" in paths and any(p.endswith("/transfers") for p in paths)
    dump = db.execute("SELECT string_agg(row_to_json(c)::text, '') FROM nessie_cache c").fetchone()[0]
    assert KEY not in dump


def test_sync_from_cache_when_nessie_is_down(db, world):
    fake, client, *_ = world
    sync_accounts(db, client)
    db.commit()
    fake.down = True
    assert sync_accounts(db, client).changed == 0


def test_balance_is_opening_plus_mirrored_transactions(db, world):
    _, client, user_id, account_id, _ = world
    sync_accounts(db, client)
    # 100000 + 120000 - 4200 - 1000 (pending purchase) - 30000 - 12637 (posted bill); pending bill ignored
    assert account_balances_cents(db, user_id) == {account_id: 172_163}


def test_sync_skips_clearday_mirror_records_no_payment_owns(db, world):
    """A "Clearday:" transfer or deposit with no payment row (e.g. after reset_demo --db-only) is our
    own mirror, not real activity: importing it would move balances by whole dollars."""
    _, client, user_id, _, nessie_acct = world
    sync_accounts(db, client)
    before = txns(db)
    balance = account_balances_cents(db, user_id)
    client.create_transfer(nessie_acct, 3_300, "2026-10-10", "completed", "Clearday: Rent share")
    client.create_deposit(nessie_acct, 3_300, "2026-10-10", "completed", "Clearday: Rent share")
    stats = sync_accounts(db, client)
    assert stats.inserted == 0
    assert txns(db) == before
    assert stats.orphan_mirrors == 2
    assert account_balances_cents(db, user_id) == balance


def test_sync_removes_previously_imported_orphan_mirrors(db, world):
    _, client, _, _, nessie_acct = world
    sync_accounts(db, client)
    before = txns(db)
    orphan = client.create_transfer(nessie_acct, 3_300, "2026-10-10", "completed", "Clearday: Rent share")
    # Simulate the old behaviour: the orphan was imported before the guard existed.
    db.execute(
        """INSERT INTO transactions (user_id, account_id, nessie_id, kind, amount_cents, merchant, category,
               status, occurred_at)
           SELECT user_id, id, %s, 'transfer', 3300, 'Clearday: Rent share', 'transfer', 'posted',
                  '2026-10-10 12:00Z' FROM accounts""",
        (orphan["id"],),
    )
    db.commit()
    stats = sync_accounts(db, client)
    assert stats.removed == 1
    assert txns(db) == before


def test_sync_never_reposts_a_pending_bill_nessie_marks_completed(db, world):
    """reset_demo --db-only reopens a popped bill in our DB while Nessie still says completed. Only a
    payment row may post a bill; without one, our pending status stands."""
    fake, client, *_ = world
    sync_accounts(db, client)
    pending = next(b for b in fake.children["bills"].values() if b["status"] == "pending")
    client.set_bill_status(pending["_id"], "completed")
    sync_accounts(db, client)
    assert ("bill", 9_900, "Duke Energy", "bills", "pending", "2026-10-15") in txns(db)
