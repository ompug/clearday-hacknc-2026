from collections import Counter

import pytest

from analytics.splits import split
from api.db import connect
from api.migrate import migrate
from api.nessie.cache import PgCache
from api.nessie.client import NessieClient
from api.tests.fake_nessie import KEY, FakeNessie
from scripts import seed_nessie as seed


def test_plan_is_deterministic_and_nessie_safe():
    plan = seed.build_plan()
    assert plan == seed.build_plan()
    for x in [*plan.purchases, *plan.deposits, *plan.transfers]:
        assert x.amount_cents > 0 and x.amount_cents % 100 == 0, x  # Nessie truncates non-bill cents
    keys = Counter((x.person, x.account, x.merchant, x.date, x.amount_cents) for x in plan.purchases)
    assert max(keys.values()) == 1
    keys = Counter(
        (x.person, x.account, x.date, x.amount_cents, x.description)
        for x in [*plan.deposits, *plan.transfers]
    )
    assert max(keys.values()) == 1
    assert max(Counter((b.person, b.nickname, b.date) for b in plan.bills).values()) == 1
    for p in seed.PEOPLE:
        assert all(cents % 100 == 0 for cents in p.openings.values())


def test_shared_expenses_split_into_whole_dollars():
    plan = seed.build_plan()
    assert {e.label for e in plan.expenses} == {"Rent", "Electric", "Internet"}
    for e in plan.expenses:
        shares = split(e.total_cents, "even", [1, 2, 3])
        assert sum(shares.values()) == e.total_cents
        assert all(c % 100 == 0 for c in shares.values())


def test_past_shared_bills_are_repaid_to_the_cent():
    """Each completed shared bill: Maya's own share plus both roommates' repayments equals the total."""
    plan = seed.build_plan()
    rent = [m.amount_cents for m in plan.transfers if m.description == "Rent share to Maya"]
    assert rent and all(c == 80_000 for c in rent)  # 240000 / 3
    utilities = sorted(
        {(m.date, m.amount_cents) for m in plan.transfers if m.description.startswith("Utilities")}
    )
    assert utilities == [(seed.dt.date(2026, 8, 22), 7_100), (seed.dt.date(2026, 9, 22), 6_400)]


@pytest.mark.parametrize("total", [10_000, 10_100])
def test_a_shared_bill_whose_shares_are_not_whole_dollars_is_refused(monkeypatch, total):
    """Nessie keeps only whole dollars on transfers, so the seed refuses instead of dropping cents."""
    bills = [("Rent", "Franklin St Apartments", 1, [(seed.dt.date(2026, 9, 1), total, "completed")])]
    monkeypatch.setattr(seed, "SHARED_BILLS", bills)
    with pytest.raises(ValueError, match="whole dollars"):
        seed.build_plan()


def test_planted_cases_exist():
    plan = seed.build_plan()
    spotify = {x.person for x in plan.purchases if x.merchant == "Spotify"}
    assert spotify == {"maya", "jake"}
    assert any(x.person == "jake" and x.amount_cents == 21_800 for x in plan.purchases)
    balances = seed.projected_balances(plan)
    assert all(low >= 0 for _, low in balances.values())


def _client(fake, cache=None):
    return NessieClient(KEY, "https://nessie.test", cache=cache, transport=fake.transport())


def test_dry_run_writes_nothing():
    fake = FakeNessie()
    s = seed.seed_nessie(_client(fake), seed.build_plan(), dry_run=True)
    assert fake.writes() == 0
    assert s.created["customer"] == 3 and s.created["account"] == 9


def test_seed_reuses_by_name_ignores_probes_and_reruns_as_noop():
    fake = FakeNessie()
    client = _client(fake)
    client.create_customer("zz-probe", "", seed.HOME)
    client.create_merchant("zz-probe Merchant A", "x", seed.HOME, 0.0, 0.0)
    maya = client.create_customer("Maya", "Okafor", seed.HOME)  # left over from an earlier run
    client.create_merchant("Uber", "rideshare", seed.HOME, 0.0, 0.0)
    plan = seed.build_plan()
    first = seed.seed_nessie(client, plan, dry_run=False)
    assert first.customers["maya"] == maya["id"]
    assert first.reused["customer"] == 1 and first.created["customer"] == 2
    assert first.reused["merchant"] == 1 and first.created["merchant"] == len(seed.MERCHANTS) - 1
    assert first.created["purchase"] == len(plan.purchases)
    writes = fake.writes()
    second = seed.seed_nessie(client, plan, dry_run=False)
    assert fake.writes() == writes
    assert sum(second.created.values()) == 0
    assert second.customers == first.customers and second.accounts == first.accounts


@pytest.fixture
def db(scratch_dsn):
    with connect(scratch_dsn) as conn:
        migrate(conn)
        conn.autocommit = False
        yield conn


def test_full_seed_writes_db_once(db):
    fake = FakeNessie()
    client = _client(fake, PgCache(db))
    plan = seed.build_plan()
    s = seed.seed_nessie(client, plan, dry_run=False)
    first = seed.write_db(db, client, plan, s)
    db.commit()
    assert first["db_rows"] == {"member": 3, "account": 9, "expense": 3, "share": 9}
    n_txn = len(plan.purchases) + len(plan.deposits) + len(plan.transfers) + len(plan.bills)
    assert first["sync"].inserted == n_txn
    assert db.execute("SELECT count(*) FROM transactions").fetchone()[0] == n_txn
    open_shares = db.execute(
        "SELECT u.display_name, count(*), sum(s.amount_cents) FROM shares s JOIN users u ON u.id = s.user_id"
        " WHERE s.status = 'open' GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert open_shares == [("Jake", 3, 86_700), ("Priya", 3, 86_700)]
    assert db.execute("SELECT count(*) FROM expenses WHERE source_txn_id IS NULL").fetchone()[0] == 0
    last4 = db.execute("SELECT last4 FROM accounts").fetchall()
    assert all(len(r[0]) == 4 for r in last4)

    s2 = seed.seed_nessie(client, plan, dry_run=False)
    second = seed.write_db(db, client, plan, s2)
    assert second["db_rows"] == {}
    assert second["sync"].changed == 0
