-- Price memory (docs/02 data model): the items of receipts the user confirmed, kept so Clearday can say
-- an item was cheaper at another store. Only text and cents; the receipt image is never stored.
-- `unit_price_cents` is the line total per unit (quantity 1 unless the receipt says otherwise).

CREATE TABLE receipts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users (id),
    expense_id   BIGINT REFERENCES expenses (id),
    merchant     TEXT NOT NULL CHECK (length(merchant) BETWEEN 1 AND 80),
    purchased_at DATE NOT NULL,
    total_cents  BIGINT NOT NULL CHECK (total_cents > 0),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, merchant, purchased_at, total_cents)
);

CREATE TABLE receipt_items (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id       BIGINT NOT NULL REFERENCES receipts (id) ON DELETE CASCADE,
    raw_label        TEXT NOT NULL CHECK (length(raw_label) BETWEEN 1 AND 80),
    normalized_name  TEXT NOT NULL CHECK (length(normalized_name) BETWEEN 1 AND 80),
    quantity         INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit             TEXT,
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents > 0)
);
CREATE INDEX receipt_items_name_idx ON receipt_items (normalized_name);
