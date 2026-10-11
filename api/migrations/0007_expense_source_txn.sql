-- One source purchase can back only one shared expense per household (the assistant could otherwise
-- split "last night's pizza" twice). expenses.source_txn_id already exists (0001, no FK because the
-- transactions hypertable key includes occurred_at); this makes it unique per household.

CREATE UNIQUE INDEX expenses_household_source_txn_uniq
    ON expenses (household_id, source_txn_id) WHERE source_txn_id IS NOT NULL;
