-- Phase 1 foundation: people, accounts, the transaction hypertable, the ledger and the Nessie cache.
-- Money is BIGINT cents. Direction comes from kind (deposit = in; purchase, bill, transfer = out),
-- so stored amounts are non-negative. Nessie IDs and account numbers never leave the backend.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE households (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name       TEXT NOT NULL CHECK (length(display_name) BETWEEN 1 AND 60),
    nessie_customer_id TEXT UNIQUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Membership spans drive proration on move-in and move-out.
CREATE TABLE household_members (
    household_id BIGINT NOT NULL REFERENCES households (id),
    user_id      BIGINT NOT NULL REFERENCES users (id),
    joined_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at      TIMESTAMPTZ,
    PRIMARY KEY (household_id, user_id, joined_at),
    CHECK (left_at IS NULL OR left_at > joined_at)
);
CREATE INDEX household_members_user_idx ON household_members (user_id);

-- Several per user (checking, savings, credit card). Only last4 of the account number is kept.
-- Nessie balances are static, so the live balance is opening_balance_cents plus mirrored transactions.
CREATE TABLE accounts (
    id                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id               BIGINT NOT NULL REFERENCES users (id),
    nessie_account_id     TEXT UNIQUE,
    type                  TEXT NOT NULL CHECK (type IN ('checking', 'savings', 'credit_card')),
    nickname              TEXT NOT NULL CHECK (length(nickname) BETWEEN 1 AND 60),
    last4                 CHAR(4) NOT NULL CHECK (last4 ~ '^[0-9]{4}$'),
    opening_balance_cents BIGINT NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX accounts_user_idx ON accounts (user_id);

-- Mirrored Nessie activity. Hypertable on occurred_at, so unique keys must include it.
-- Bills are kind 'bill' with occurred_at = due date; status 'pending' until paid.
CREATE TABLE transactions (
    id           BIGINT GENERATED ALWAYS AS IDENTITY,
    user_id      BIGINT NOT NULL REFERENCES users (id),
    account_id   BIGINT NOT NULL REFERENCES accounts (id),
    nessie_id    TEXT,
    kind         TEXT NOT NULL CHECK (kind IN ('purchase', 'deposit', 'bill', 'transfer')),
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    merchant     TEXT,
    category     TEXT,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'posted')),
    occurred_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (id, occurred_at),
    UNIQUE (nessie_id, occurred_at)
);
SELECT create_hypertable('transactions', by_range('occurred_at', INTERVAL '30 days'));
CREATE INDEX transactions_user_time_idx ON transactions (user_id, occurred_at DESC);
CREATE INDEX transactions_account_time_idx ON transactions (account_id, occurred_at DESC);

-- One shared cost. source_txn_id points into the hypertable without an FK (its key includes occurred_at).
CREATE TABLE expenses (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    household_id  BIGINT NOT NULL REFERENCES households (id),
    payer_id      BIGINT NOT NULL REFERENCES users (id),
    source_txn_id BIGINT,
    label         TEXT NOT NULL CHECK (length(label) BETWEEN 1 AND 80),
    total_cents   BIGINT NOT NULL CHECK (total_cents > 0),
    status        TEXT NOT NULL DEFAULT 'final' CHECK (status IN ('estimated', 'final')),
    split_method  TEXT NOT NULL CHECK (split_method IN ('even', 'percentage', 'custom', 'shares', 'itemized')),
    due_on        DATE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX expenses_household_idx ON expenses (household_id, due_on);

CREATE TABLE shares (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    expense_id   BIGINT NOT NULL REFERENCES expenses (id),
    user_id      BIGINT NOT NULL REFERENCES users (id),
    amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'partial', 'paid', 'disputed')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (expense_id, user_id)
);
CREATE INDEX shares_user_status_idx ON shares (user_id, status);

-- A double tap pays once: idempotency_key is client-generated and unique.
-- Nessie mirror: payer-side transfer and/or payee-side deposit (transfers have no payee).
-- nessie_rounding_diff_cents = ledger cents minus the whole dollars Nessie received.
CREATE TABLE payments (
    id                         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_user                  BIGINT NOT NULL REFERENCES users (id),
    to_user                    BIGINT NOT NULL REFERENCES users (id),
    amount_cents               BIGINT NOT NULL CHECK (amount_cents > 0),
    idempotency_key            TEXT NOT NULL UNIQUE CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    nessie_transfer_id         TEXT,
    nessie_deposit_id          TEXT,
    nessie_rounding_diff_cents BIGINT NOT NULL DEFAULT 0 CHECK (nessie_rounding_diff_cents BETWEEN -99 AND 99),
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_user <> to_user)
);
CREATE INDEX payments_from_idx ON payments (from_user);
CREATE INDEX payments_to_idx ON payments (to_user);

-- How a payment covers shares; share_id NULL means the remainder is a credit.
CREATE TABLE allocations (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payment_id   BIGINT NOT NULL REFERENCES payments (id),
    share_id     BIGINT REFERENCES shares (id),
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
    UNIQUE NULLS NOT DISTINCT (payment_id, share_id)
);
CREATE INDEX allocations_share_idx ON allocations (share_id);

-- Every Nessie response, keyed by sha256 of method + path + canonical query (minus the API key) + body.
-- The demo reads from here. The API key must never land in this table.
CREATE TABLE nessie_cache (
    cache_key     TEXT PRIMARY KEY CHECK (cache_key ~ '^[0-9a-f]{64}$'),
    method        TEXT NOT NULL CHECK (method IN ('GET', 'POST', 'PUT', 'DELETE')),
    path          TEXT NOT NULL CHECK (path LIKE '/%' AND position('key=' IN path) = 0),
    query         JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (NOT query ? 'key'),
    request_body  JSONB,
    status_code   INTEGER NOT NULL,
    response_body JSONB,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX nessie_cache_path_idx ON nessie_cache (method, path);
