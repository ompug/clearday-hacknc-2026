# Phase 2 execution plan (Sat 9:15 PM → freeze Sun 7:30 AM)

Remaining Phase 2: `POST /api/expenses` + create-split UI, `GET /api/forecast` + `forecast.updated`, real analytics swap, bulb driver, a11y pass.

## Shared-file rules (all streams)
- `api/main.py`: append one `include_router` line per stream only.
- `web/lib/api/types.ts`, `client.ts`, `mock/*`, `api/tests/test_api_contract.py`: append only.
- Migration numbers are pre-assigned: A = `0003`, E = `0004`.
- Re-read shared files before editing; minimal Edits; stage only your paths.

## Streams
**A. Expenses API (~2.5 h).** Owns `api/expenses.py`, `api/routes/expenses.py`, `api/migrations/0003_*.sql`, `api/tests/test_expenses.py`. Contract: spec Ledger rules 1–3, 9, 10, plus `CreateExpenseRequest/Result` in types.ts (land the types FIRST so B can mock). Even and custom splits via `splits.split`, idempotency key, emits `share.updated` and an amount-free `feed.created`, new shared bubbles appear in `/api/sky`. Accept: $10.00 / 3 → 334/333/333; a replayed key gives one row; a test fails if an amount appears in the feed.

**B. Web: split UI, forecast view, a11y (~4 h).** Owns `web/app/forecast/`, `web/components/split/`, `web/components/forecast/`, `web/components/sky/*`, `DisplaySettings.tsx`, `globals.css`. Order: New shared expense dialog (even/custom, live sum check) → Recharts forecast page with plain-language labels and the "wants trimmed 25%" toggle → a11y pass (contrast on glass, focus, reduced motion, 200% zoom). Accept: screenshots at 100% and 200%, axe with no criticals, the E2E extended so Maya splits and Jake's sky updates.

**C. Forecast endpoint + analytics swap (~2 h + swap).** Owns `api/forecast.py`, `api/routes/forecast.py`, `api/tests/test_forecast.py`, and later `analytics/forecast.py`/`categorize.py` swaps. `GET /api/forecast` on the stub; `forecast.updated` to the user room after a payment or expense (debounced, after the response; one hook call in `api/payments.py` and A's expense path). Accept: contract tests pass; the seed shows Maya "tight" before rent.

**D. Clearday Home (~1.5 h software, hardware-bound).** Owns `device/**`. Bulb driver slot → live API with a device token → flash the UNO Q. Accept: a pop on laptop B makes the dome burst within 2 s. BLOCKED on the bulb brand.

**E. Model gateway (~3 h, stretch #1).** Owns `api/ai/`, `api/routes/assistant.py`, `api/migrations/0004_ai_audit.sql`, `api/tests/test_ai_gateway.py`, `web/components/assistant/`. Provider-neutral chat-completions with tools via httpx, configured only by `LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`. Enforces the docs/03 tool contract: allowlist, schema validation, ≤3 tool calls, 30-day/20-row limits, placeholder names, handles mapped back server-side, amounts recomputed via `splits.split`, `ai_audit` logs fields and counts only. Accept: a fake endpoint test rejects a 4th call, an unknown tool and a raw ID, and ignores a model-supplied amount. Pending user decisions.

## Defaults applied
- Split UI: even and custom only (itemized waits for receipts).
- New expenses are ledger-only; money moves only on pop (no Nessie write).
- `forecast.updated` is debounced and computed after the response.

## Timeline
- 9:15 PM–12:30 AM: streams in parallel.
- 12:30–1:00: integrate, run the E2E, commit (Phase 2 gate).
- 1:00–5:00: E merge, ElevenLabs announcement + transcript, duplicate subscriptions, backtest number.
- 5:00–6:00: reset_demo, full dry run, bug fixes.
- 6:00–7:30: rehearsal and video buffer. Bug fixes only after 7:30.

## Cut order if behind
Cut lines 1–7 are effectively out already. Next: 8 narrator (use templates), 9 anomalies, 10 price memory, 11 device audio, then 12 natural-language split (keep the manual split). Never cut the live shared bubble, the forecast or the a11y baseline.
