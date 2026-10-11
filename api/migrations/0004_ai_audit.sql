-- AI gateway audit (docs/03 rule 8): which tools ran, which fields and how many rows reached the model.
-- Never values: no message text, merchant, amount, name or date. `tool` is NULL when the model asked for
-- a tool outside the allowlist (the model-made name is not stored); `reason` is a fixed audit code.

CREATE TABLE ai_audit (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id UUID NOT NULL,
    user_id    BIGINT NOT NULL REFERENCES users (id),
    event      TEXT NOT NULL CHECK (event IN ('request', 'tool')),
    tool       TEXT CHECK (tool IN ('find_purchase', 'list_household_members', 'propose_split',
                                    'explain_forecast', 'explain_anomaly', 'read_receipt')),
    outcome    TEXT NOT NULL CHECK (outcome IN ('ok', 'rejected', 'fallback')),
    reason     TEXT CHECK (reason ~ '^[a-z_]{1,40}$'),
    fields     TEXT[] NOT NULL DEFAULT '{}',
    row_count  INTEGER NOT NULL DEFAULT 0 CHECK (row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ai_audit_user_idx ON ai_audit (user_id, created_at DESC);
