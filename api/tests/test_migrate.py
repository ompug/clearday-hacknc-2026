import psycopg
import pytest

from api.db import connect
from api.migrate import MIGRATIONS_DIR, MigrationError, discover, migrate

PHASE1_TABLES = {
    "households",
    "users",
    "household_members",
    "accounts",
    "transactions",
    "expenses",
    "shares",
    "payments",
    "allocations",
    "nessie_cache",
    "devices",
    "feed_events",
    "revoked_sessions",
    "schema_migrations",
}


def tables(conn) -> set[str]:
    rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {r[0] for r in rows}


def test_migrate_is_idempotent(scratch_dsn):
    with connect(scratch_dsn) as conn:
        first = migrate(conn)
        assert first == [p.name for p in discover()]
        assert migrate(conn) == []
        assert tables(conn) == PHASE1_TABLES
        count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        assert count == len(first)
        hyper = conn.execute("SELECT hypertable_name FROM timescaledb_information.hypertables").fetchall()
        assert hyper == [("transactions",)]


def test_edited_migration_is_rejected(scratch_dsn, tmp_path):
    sql = tmp_path / "0001_demo.sql"
    sql.write_text("CREATE TABLE demo (id INT);")
    with connect(scratch_dsn) as conn:
        assert migrate(conn, tmp_path) == ["0001_demo.sql"]
        sql.write_text("CREATE TABLE demo (id BIGINT);")
        with pytest.raises(MigrationError):
            migrate(conn, tmp_path)


def test_failed_migration_rolls_back(scratch_dsn, tmp_path):
    (tmp_path / "0001_ok.sql").write_text("CREATE TABLE ok_t (id INT);")
    (tmp_path / "0002_bad.sql").write_text("CREATE TABLE half_t (id INT); SELECT nope_missing();")
    with connect(scratch_dsn) as conn:
        with pytest.raises(psycopg.Error):
            migrate(conn, tmp_path)
        assert "ok_t" in tables(conn)
        assert "half_t" not in tables(conn)
        applied = conn.execute("SELECT filename FROM schema_migrations").fetchall()
        assert applied == [("0001_ok.sql",)]


def test_bad_filename_is_rejected(tmp_path):
    (tmp_path / "add_stuff.sql").write_text("SELECT 1;")
    with pytest.raises(MigrationError):
        discover(tmp_path)


def test_payment_idempotency_key_is_unique(scratch_dsn):
    with connect(scratch_dsn) as conn:
        migrate(conn, MIGRATIONS_DIR)
        conn.autocommit = False
        a, b = (
            conn.execute("INSERT INTO users (display_name) VALUES (%s) RETURNING id", (n,)).fetchone()[0]
            for n in ("Maya", "Jake")
        )
        insert = (
            "INSERT INTO payments (from_user, to_user, amount_cents, idempotency_key) VALUES (%s, %s, %s, %s)"
        )
        conn.execute(insert, (b, a, 3333, "tap-0001-key"))
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(insert, (b, a, 3333, "tap-0001-key"))
