# Phase 2 review (9ce0787..e6fdaf7)

This review is read-only. It covers correctness and security in everything since the Phase 1 review, including the anomalies commit `e6fdaf7`. It checks the code against `CODING_STANDARDS.md` and `docs/03-security-and-privacy.md`. It does not re-report Phase 1 findings that are now fixed. No secret values were printed.

## Checked and clean

- **Gateway allowlist and cap:**
  - only the six tools run (`api/ai/tools.py:283-287`), and a model-made tool name is never logged (`api/ai/gateway.py:299`);
  - the 4th tool call is rejected and stops the loop (`gateway.py:300-302`);
  - unknown argument keys are dropped, and `approx_amount_cents` only ranks results;
  - shares come from `analytics.splits.split` on the stored purchase amount (`tools.py:216-221`);
  - handles map back server-side, and raw IDs are rejected (`api/ai/handles.py`).
- **`ai_audit`:**
  - it holds tool names, fixed reason codes, field names and row counts only;
  - the schema enforces this (`reason ~ '^[a-z_]{1,40}$'`, a `tool` allowlist).
- **Receipts:**
  - the upload is capped at 5 MB, by Content-Length and while streaming (`api/routes/receipts.py:21-30`);
  - the type is checked by magic bytes and content type (`api/ai/receipts.py:53-65`);
  - the file is created by `mkstemp` (0600) and removed in a `finally`;
  - the model is called with no tools;
  - the reply is parsed as JSON, validated as integer cents, and must satisfy items + tax + tip == total;
  - nothing is stored.
- **Web XSS:**
  - model replies, receipt labels and merchant names are rendered as React text (`web/components/assistant/SplitAssistant.tsx:139,155`);
  - the only `dangerouslySetInnerHTML` is the static preferences script (`web/app/layout.tsx:36`);
  - `audio_url` is built server-side from a hash.
- **Voice:**
  - the text is built from counts only, with no names, amounts or labels (`api/voice.py:43-53`);
  - the cache path is gated by `^[0-9a-f]{64}$` (`api/voice.py:61-65`), so path traversal isn't possible;
  - the key is never logged.
- **Device tokens:**
  - tokens come from `secrets.token_urlsafe(32)` and only their SHA-256 is stored;
  - an invalid Bearer token never falls back to the cookie (`api/routes/reads.py:39-48`);
  - `/api/device/summary` accepts the token only;
  - revocation drops the socket within `socket_recheck_interval_s`.
- **Sessions:**
  - the token carries a random nonce;
  - logout writes its SHA-256 to `revoked_sessions`, which every request and socket re-check consults;
  - logout disconnects the session's sockets;
  - dev login answers only to loopback peers (`api/routes/session.py:52-57`), which mitigates Phase 1 security #1.
- **Expenses:**
  - the payer comes from the cookie;
  - participants must be current members;
  - the idempotency key is unique and a race is handled;
  - the freeze trigger blocks amount and owner edits once allocations exist;
  - FKs are RESTRICT, so a paid share can't be deleted.
- **Forecast debounce:**
  - it debounces on the trailing edge with a 3 s max wait;
  - it invalidates the cache before recomputing;
  - `forecast.updated` goes to `user:<id>` only.
- **Mirror races:**
  - an advisory lock per payment stops `retry_mirrors` and the request path from double-posting;
  - orphan `Clearday:` mirrors are skipped by sync;
  - ledger rows are protected from sync's delete.

## Findings (most severe first)

### Medium

1. **Cold-start demo breaker: `dev.sh up` never migrates the main stack.**
   - Migrations run only with `--e2e` (`scripts/dev.sh:216`).
   - On a fresh DB volume, or on a teammate's laptop, `revoked_sessions` is missing. Every authenticated request then fails with a 500 (`api/session.py:116`), while `/api/health` still reports ok (it runs only `SELECT 1`).
   - Fix: run `uv run python -m api.migrate` in `up` for both stacks (it's idempotent), and have health check `schema_migrations` against the files.
2. **Race: a sync can reopen a bill that was just paid, which allows a double payment.**
   - Sync reads `owned` once (`api/nessie/sync.py:89`) and then upserts the bill status it fetched earlier (`sync.py:117-127`).
   - If `_pop_bill` commits in between, the upsert waits on the row lock and then writes `pending` over `posted`. The bubble reappears and can be paid again. Later syncs treat it as owned and never repair it.
   - Fix: add `AND NOT EXISTS (SELECT 1 FROM payments p WHERE p.bill_txn_id = transactions.id)` to the `DO UPDATE ... WHERE`.
3. **A malformed model reply or an analytics error returns a 500 instead of the template fallback.**
   - If `function` is a string, `_assistant_turn` and the loop call `.get` on it (`api/ai/gateway.py:250-253,297,305`).
   - If `name` is a list, `name in ALLOWED` raises TypeError (`gateway.py:299`).
   - `anomalies.find` now runs before every request with no guard (`gateway.py:321`).
   - Only `ModelUnavailable` is caught (`gateway.py:336`).
   - Fix: treat a non-dict `function` or a non-str name as `bad_response`, and wrap `anomalies.find` in try/except that falls back to `[]`.
4. **Clearday Home can't reach the API.**
   - uvicorn binds 127.0.0.1 (`scripts/dev.sh:162-163`, no `--host`).
   - The device defaults to `http://localhost:8000` (`device/README.md:50`), but it runs on the UNO Q, not the laptop.
   - Fix: add `dev.sh up --lan`, which binds the laptop's LAN IP. Dev login is already loopback-only. Document `CLEARDAY_API_URL=http://<laptop-ip>:8000`.
5. **`/api/device/summary` sends user-typed bill labels to a shared speaker** (`api/sky.py:519`).
   - Expense labels are free text: "Jake's birthday", "Priya owes $40", or a merchant name from an assistant proposal.
   - `api/voice.py` leaves labels out for exactly this reason. The device narrator's name and amount check only compares against the summary, so a name or amount inside a label passes.
   - Fix: send a category-level label (e.g. "rent", "utilities", "shared purchase"), or run labels through a names-and-digits scrub before they reach the device.

### Low

6. **Real names can reach the model through untrusted text.**
   - Merchant names and bill labels are wrapped but not redacted (`api/ai/tools.py:202,253,269`).
   - A shared label like "Maya's rent" reaches the model, against docs/03's "never real names of other people".
   - Fix: pass each wrapped string through `ctx.handles.redact` before `untrusted()`.
7. **The model's free-text reply is shown unchecked** (`api/ai/gateway.py:332`).
   - Injected merchant text could make it say "call this number", or state an invented amount. The only guard is the prompt.
   - Fix: when the reply contains `$`, digits followed by a currency word, or a URL, use the template reply instead.
8. **The same purchase can be split again and again.**
   - Each assistant ask issues a new idempotency key (`SplitAssistant.tsx:50,64-70`).
   - The confirmed expense isn't linked to the purchase, so "split last night's pizza" twice makes two expenses.
   - Fix: send the purchase handle's txn as `source_txn_id`, with a unique constraint per household.
9. **The insights page shows former roommates.**
   - Neither membership join filters `left_at IS NULL` (`api/insights.py:28,44-46`).
   - The subscriptions and names of someone who left are still shown.
   - Fix: add `AND m.left_at IS NULL` to both joins.
10. **Nessie account IDs land in `logs/api.log`.**
    - The retry warning logs the full path (`api/nessie/client.py:190`).
    - With background sync every 60 s, offline runs fill the log with `/accounts/<id>/...`.
    - Fix: log the path with IDs masked, e.g. `re.sub(r"/[0-9a-f-]{20,}", "/<id>", path)`.
11. **No upper bound on `total_cents`** (`api/routes/expenses.py:34`, `StrictInt`). A value above BIGINT raises an uncaught `NumericValueOutOfRange`, which becomes a 500. Fix: `Field(gt=0, le=10_000_000_00)`.
12. **A hard kill (`--reload`, SIGKILL) mid-read leaves `receipt-*` files in /tmp** (`api/ai/receipts.py:148`). Fix: on lifespan start, delete `spool_dir().glob("receipt-*")`, or skip the temp file and send `data` straight from memory.
13. **The freeze trigger covers only `total_cents` on expenses** (`api/migrations/0003_expenses_create.sql:17`). After payments, `payer_id` and `household_id` can still change silently. Fix: in a new migration, also freeze `payer_id` and `household_id` once allocations exist.
14. **Client tie-break uses a string sort** (`web/components/split/cents.ts:29,50,60`). `"u_10" < "u_2"` disagrees with `analytics.splits` (numeric IDs). Itemized splits store these client numbers as a custom split. The demo has only u_1 to u_3. Fix: sort by `Number(id.slice(2))`, or add an `itemized` method server-side.
15. **Still open from Phase 1:** a payment is marked `mirrored` when an account has no Nessie ID (`api/payments.py:324,333`), and `enable_dev_routes` still defaults to True (`api/config.py:31`). The loopback gate now limits the impact of the second.

### Info

- **Demo date:** the pizza is seeded on ANCHOR 2026-10-10 (`scripts/seed_nessie.py:268`), and the prompt's "last night" window is today-1..today. It works on Oct 11, but a re-run on Oct 12 or later can't find it.
- **After `reset_demo`:** open browsers get no event and keep stale bubbles until they reload. The API's forecast cache can serve the old forecast for up to 15 s (`api/sky.py:39`). Reload both demo browsers after a reset.
- **Forecast cache race:** a forecast computed before a commit can be stored after the invalidation, and is then served for up to 15 s. The debouncer's later recompute corrects the socket push.
- **No rate limit** on `/api/assistant` or `/api/receipts`. Each request costs model calls.
- **Bill status sync rule:** `_is_pending_bill` means a bill paid outside Clearday never becomes posted (`api/nessie/sync.py:104-107`). This is fine for the demo.
