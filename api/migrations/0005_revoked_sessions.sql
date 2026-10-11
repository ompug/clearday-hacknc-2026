-- Logout ends a session server-side. The signed cookie is otherwise valid for 7 days, so every request
-- and socket re-check looks its SHA-256 up here. 0004 is reserved for ai_audit.
CREATE TABLE revoked_sessions (
    token_hash TEXT PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    revoked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
