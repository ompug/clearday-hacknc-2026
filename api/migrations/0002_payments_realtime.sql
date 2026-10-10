-- Pop-to-pay and realtime (Round 4 decisions).
-- A payment either covers household shares (to_user = the expense payer) or pays a personal bill
-- (to_user NULL, bill_txn_id set). The ledger commits first; the Nessie mirror (payer transfer plus
-- payee deposit, or marking the personal bill completed) follows and is retried by sync.

ALTER TABLE payments ALTER COLUMN to_user DROP NOT NULL;

ALTER TABLE payments
    ADD COLUMN account_id     BIGINT REFERENCES accounts (id),
    ADD COLUMN expense_id     BIGINT REFERENCES expenses (id),
    ADD COLUMN bill_txn_id    BIGINT,
    ADD COLUMN payer_txn_id   BIGINT,
    ADD COLUMN payee_txn_id   BIGINT,
    ADD COLUMN mirror_status  TEXT NOT NULL DEFAULT 'pending'
        CHECK (mirror_status IN ('pending', 'mirrored', 'failed')),
    ADD COLUMN mirror_attempts INTEGER NOT NULL DEFAULT 0,
    -- The PaymentResult first returned, so a replayed idempotency key returns it unchanged.
    ADD COLUMN result         JSONB,
    ADD CONSTRAINT payments_target_chk CHECK ((to_user IS NULL) = (bill_txn_id IS NOT NULL));

CREATE INDEX payments_mirror_idx ON payments (mirror_status) WHERE mirror_status <> 'mirrored';

-- Clearday Home: a hashed, revocable, read-only household token.
CREATE TABLE devices (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id BIGINT NOT NULL REFERENCES households (id),
    token_hash   TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ
);

-- Household feed. No amounts, ever.
CREATE TABLE feed_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id  BIGINT NOT NULL REFERENCES households (id),
    type          TEXT NOT NULL CHECK (type IN ('share_paid', 'bubble_popped')),
    actor_id      BIGINT NOT NULL REFERENCES users (id),
    subject_label TEXT NOT NULL CHECK (length(subject_label) BETWEEN 1 AND 80),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX feed_events_household_idx ON feed_events (household_id, created_at DESC);
