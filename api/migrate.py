"""Apply numbered SQL migrations in api/migrations/ once each, in order.

Usage: uv run python -m api.migrate

Each file runs in its own transaction and is recorded in schema_migrations with a
checksum. Re-running is a no-op. Editing an applied file is an error: add a new file.
"""

import hashlib
import logging
import re
import sys
from pathlib import Path

import psycopg

from api.db import connect

log = logging.getLogger("clearday.migrate")

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
NAME_RE = re.compile(r"^\d{4}_[a-z0-9_]+\.sql$")
LOCK_ID = 0x0C1EA4DA  # pg advisory lock: one runner at a time

CREATE_TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    checksum   TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


class MigrationError(RuntimeError):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = sorted(p for p in directory.glob("*.sql"))
    bad = [p.name for p in files if not NAME_RE.match(p.name)]
    if bad:
        raise MigrationError(f"migration names must look like 0001_name.sql: {bad}")
    return files


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; return the filenames applied this run."""
    files = discover(directory)
    conn.autocommit = True
    conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
    try:
        conn.execute(CREATE_TRACKING)
        applied = dict(conn.execute("SELECT filename, checksum FROM schema_migrations").fetchall())
        done: list[str] = []
        for path in files:
            digest = checksum(path)
            if path.name in applied:
                if applied[path.name] != digest:
                    raise MigrationError(f"{path.name} changed after it was applied; add a new migration")
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)", (path.name, digest)
                )
            log.info("applied %s", path.name)
            done.append(path.name)
        return done
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        with connect() as conn:
            done = migrate(conn)
    except MigrationError as exc:
        log.error("%s", exc)
        return 1
    except psycopg.OperationalError as exc:
        log.error("cannot connect to the database (%s); is it running?", type(exc).__name__)
        return 1
    if done:
        log.info("%d migration(s) applied", len(done))
    else:
        log.info("up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
