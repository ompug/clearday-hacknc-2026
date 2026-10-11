"""scripts/dev.sh contract, checked on the script text (starting real servers belongs to e2e)."""

import re
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "scripts" / "dev.sh").read_text()


def up_branch() -> str:
    return re.search(r"^  up\)\n(.*?)^    ;;", SCRIPT, re.S | re.M).group(1)


def test_up_migrates_every_stack_before_starting_the_api():
    body = up_branch()
    migrate_at = body.index("api.migrate")
    assert migrate_at < body.index("api_up")
    # Not conditional on --e2e: the line that runs it is not an `[ "$e2e" ... ] &&` guard.
    line = next(ln for ln in body.splitlines() if "api.migrate" in ln)
    assert "e2e" not in line


def test_api_binds_loopback_unless_lan_is_asked_for():
    assert "host=127.0.0.1" in SCRIPT
    assert re.search(r'\[ "\$lan" -eq 1 \] && host=0\.0\.0\.0', SCRIPT)
    assert '--host "$host"' in SCRIPT
