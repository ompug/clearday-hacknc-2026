"""Clearday Home device tokens: household-scoped, read-only, stored only as a SHA-256 hash, revocable.

`issue_token` makes a token and stores its hash (the plain token is returned once, never stored).
`device_household` resolves a presented token to its household, or None if unknown or revoked. The
device sends it as HTTP `Authorization: Bearer <token>` and as Socket.IO `auth={"token": ...}`.
"""

from __future__ import annotations

import hashlib
import secrets

MIN_TOKEN_CHARS = 16
MAX_TOKEN_CHARS = 256


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(conn, household_id: int) -> str:
    """Create a device token for the household; only its hash is written. The caller commits."""
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO devices (household_id, token_hash) VALUES (%s, %s)",
        (household_id, hash_device_token(token)),
    )
    return token


def device_household(conn, token: object) -> int | None:
    """The household an active device token belongs to, else None."""
    if not isinstance(token, str) or not MIN_TOKEN_CHARS <= len(token) <= MAX_TOKEN_CHARS:
        return None
    row = conn.execute(
        "SELECT household_id FROM devices WHERE token_hash = %s AND revoked_at IS NULL",
        (hash_device_token(token),),
    ).fetchone()
    return row[0] if row else None
