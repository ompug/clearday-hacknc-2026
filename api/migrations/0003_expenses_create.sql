-- POST /api/expenses: shared expenses created in the app (ledger only; money moves on pop).
-- A client idempotency key makes a double submit create one expense. App-created expenses always
-- carry one; seeded expenses (from Nessie bills) have none.

ALTER TABLE expenses
    ADD COLUMN idempotency_key TEXT UNIQUE CHECK (length(idempotency_key) BETWEEN 8 AND 128);

ALTER TABLE feed_events DROP CONSTRAINT feed_events_type_check;
ALTER TABLE feed_events ADD CONSTRAINT feed_events_type_check
    CHECK (type IN ('share_paid', 'bubble_popped', 'expense_created'));

-- Ledger rule 10, no silent edits: once a payment touches an expense, its total and its shares'
-- amounts and owners are frozen. Corrections must be new adjustment entries.
CREATE FUNCTION ledger_no_silent_edits() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'expenses' THEN
        IF NEW.total_cents IS DISTINCT FROM OLD.total_cents
           AND EXISTS (SELECT 1 FROM allocations a JOIN shares s ON s.id = a.share_id
                       WHERE s.expense_id = OLD.id) THEN
            RAISE EXCEPTION 'expense % has payments; add an adjustment instead', OLD.id;
        END IF;
    ELSIF (NEW.amount_cents IS DISTINCT FROM OLD.amount_cents OR NEW.user_id IS DISTINCT FROM OLD.user_id
           OR NEW.expense_id IS DISTINCT FROM OLD.expense_id)
          AND EXISTS (SELECT 1 FROM allocations a WHERE a.share_id = OLD.id) THEN
        RAISE EXCEPTION 'share % has payments; add an adjustment instead', OLD.id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER expenses_no_silent_edits BEFORE UPDATE ON expenses
    FOR EACH ROW EXECUTE FUNCTION ledger_no_silent_edits();
CREATE TRIGGER shares_no_silent_edits BEFORE UPDATE ON shares
    FOR EACH ROW EXECUTE FUNCTION ledger_no_silent_edits();
