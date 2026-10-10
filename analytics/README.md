# analytics/

Pure Python modules for Clearday's stats work. On `main` they are **stubs**: realistic,
deterministic fake data with the exact signatures and output shapes from
"Analytics contracts" in `docs/02-technical-spec.md`.

## For the stats teammate

1. Replace modules **one file for one file** (`synthetic_data.py`, `forecast.py`,
   `categorize.py`, `detection.py`, `prices.py`, `cohorts.py`, `future.py`, `backtest.py`).
   `splits.py` is the ledger and is owned by the app side; don't replace it.
2. Keep every function name, parameter, default and output key exactly as in the contract.
   The backend calls them directly and must not change.
3. Rules: money is integer cents (`int`, never float); dates are `YYYY-MM-DD` strings; outputs
   are JSON-serializable (convert numpy scalars with `int(...)`/`float(...)`); every random
   function takes a `seed` and is deterministic for it. Inputs are pandas DataFrames with the
   shared transaction columns. `amount_cents` is positive; direction comes from `kind`.
4. Run the contract tests before pushing:

   ```bash
   uv sync
   uv run pytest analytics/tests/test_contracts.py
   uv run ruff check
   ```

   `_common.py` holds small helpers the stubs share. Use it or don't.
