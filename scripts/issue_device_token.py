"""Issue a Clearday Home device token for the household and print it once.

Usage (from the repo root; the DB is the one api.config points at):
    uv run python -m scripts.issue_device_token                    # the only household
    uv run python -m scripts.issue_device_token --household-id 1   # when there are several
    uv run python -m scripts.issue_device_token --revoke-others    # also revoke its older tokens

Only the token's SHA-256 hash is stored (`devices.token_hash`); the token itself is printed once as
`CLEARDAY_DEVICE_TOKEN=...` for `device/.env` and can't be shown again. Issue a new one if it's lost.
"""

from __future__ import annotations

import argparse
import sys

from api.db import connect
from api.devices import issue_token


def main(argv: list[str] | None = None, dsn: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--household-id", type=int, help="needed only when the DB has several households")
    parser.add_argument("--revoke-others", action="store_true", help="revoke the household's older tokens")
    args = parser.parse_args(argv)

    with connect(dsn) as conn:
        households = [r[0] for r in conn.execute("SELECT id FROM households ORDER BY id").fetchall()]
        if args.household_id is not None:
            if args.household_id not in households:
                print(f"No household with id {args.household_id}.", file=sys.stderr)
                return 2
            household_id = args.household_id
        elif len(households) == 1:
            household_id = households[0]
        else:
            print(
                f"{len(households)} households in this DB; pass --household-id (one of {households}).",
                file=sys.stderr,
            )
            return 2
        if args.revoke_others:
            revoked = conn.execute(
                "UPDATE devices SET revoked_at = now() WHERE household_id = %s AND revoked_at IS NULL",
                (household_id,),
            ).rowcount
            print(f"Revoked {revoked} older token(s).", file=sys.stderr)
        token = issue_token(conn, household_id)
        conn.commit()

    print(
        f"Device token for household {household_id} (shown once; only its hash is stored):", file=sys.stderr
    )
    print(f"CLEARDAY_DEVICE_TOKEN={token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
