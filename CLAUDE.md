# Clearday — HackNC 2026

A social money app for roommates: bills are glossy Frutiger Aero bubbles, splits run through a real ledger, a Monte Carlo "money weather" forecast warns of tight weeks, and Clearday Home (UNO Q + smart bulb) reacts live.

**Deadlines (EST):** code freeze 7:30 AM Sun Oct 11 · video by 8:00 AM · Devpost by 9:30 AM (hard close 10:00 AM). A working, polished core loop beats feature count.

## Source of truth: `docs/`

Read the relevant doc before building a feature. If an instruction conflicts with these docs, ask the user. Review checklist: `CODING_STANDARDS.md`; read it before writing or reviewing code.

| Doc | Use it for |
| --- | --- |
| `docs/01-proposal.md` | Product, MVP list, **stretch order** |
| `docs/02-technical-spec.md` | Tables, endpoints, Socket.IO events, ledger rules, forecast, design/a11y, **Analytics contracts** |
| `docs/03-security-and-privacy.md` | Model tool contract, device rules, rules for new features |
| `docs/04-clearday-home-hardware.md` | Device states, bridge protocol, fallbacks |
| `docs/05-build-plan.md` | **Phased checklist** and **Cut lines** |
| `docs/06-demo-and-submission.md` | Demo script, Q&A, submission checklist |

Where docs disagree with each other, the Technical Spec's Analytics contracts win over the Build Plan's older `forecast(...)` signature, and the Build Plan's Phase 1 (three accounts per roommate) wins over the spec's "one checking account each".

## Decisions (Round 3)

- `analytics/splits.py` is real, Claude-owned and tested (it is the ledger's math). The other 8 modules stay stubs.
- **Pop-to-pay:** the seed creates shared rent, electric and internet (Maya pays the landlord; Jake and Priya owe shares). Popping a shared bubble = Nessie transfer to Maya + ledger payment and allocation. Popping a personal bill marks the Nessie bill completed.
- **Hosting:** local only (user decision, Oct 10). No Vercel, Railway or .tech domain; the demo runs the API, web and DB on the laptop. Phase 1 step 8 (deploy skeleton) is cut.
- **Database:** local TimescaleDB in podman/Docker (`docker-compose.yml`) is primary for dev and the demo. Tiger Cloud (`DB_TARGET=tiger`) is an optional backup only.
- **Approved deps:** pandas, numpy, Recharts; device: `python-socketio[client]`, evdev; bulb is EcoSmart via Home Assistant REST, stdlib only. Home Assistant runs on the UNO Q itself (Linux side; `HA_URL=http://localhost:8123`), set up in the hardware phase. The seed plants the tight week on Priya, and the demo script uses Priya.
- **Nessie cents fallback:** if Nessie rejects cents, the ledger stays exact; Nessie gets a rounded mirror and the difference is stored on the payment row. The seed prefers whole-dollar shares.
- **Dev tooling:** pytest + ruff (Python), ESLint + Prettier (web), `scripts/check_money.sh` money lint in the pre-commit hook.

## Decisions (Round 4)

- **Pop-to-pay mirror:** a payer-side Nessie transfer plus a matching payee-side deposit, both described "Clearday: <label> share". The payment row stores `nessie_transfer_id`, `nessie_deposit_id` and `nessie_rounding_diff_cents` (Nessie gets whole dollars). If the mirror fails, the ledger still commits; sync retries it and the row records mirror status.
- **Balances** shown in the app come from our DB (opening balance plus stored transactions), never from Nessie.
- **Accepted data contract changes:** bills stored as transactions; added columns `category`, `opening_balance_cents`, `label`, `due_on`; `users.nessie_account_id` dropped; transactions unique on `(nessie_id, occurred_at)`.
- **Approved deps:** `socket.io-client` (web); Playwright (root uv dev group, for E2E scripts).
- **`web/lib/api/types.ts`** is the contract for payloads the spec leaves undefined; API tests check against it.
- **Model:** Gemma (Google's open model), not the Gemini API, through an OpenAI-compatible chat-completions endpoint with tool calling, configured only by `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in `api/.env`. The assistant falls back to templates when the model is slow, rate-limited or unset.
- **Socket.IO auth (Phase 1):** session cookie for browsers, device token for devices; other connections are rejected.

## Repo layout

```
web/        Next.js + TypeScript + Tailwind + Framer Motion (responsive)
api/        FastAPI + python-socketio; owns every secret and external call
analytics/  Pure Python modules from the stats teammate (stubs on main until swapped)
device/     Clearday Home: Linux-side Python (bulb, keypad, audio) + MCU sketch (LED matrix)
scripts/    seed_nessie.py, reset_demo.py, misc tooling
docs/       Plan (source of truth)
```

## Build order

- Build each phase in `docs/05-build-plan.md` end to end before starting the next. Don't start a stretch item until the Phase 2 checklist is done.
- Build stretch items in the Proposal's stretch order. If behind, **cut in the Build Plan's Cut lines order**, which is not the reverse of the stretch list. Never cut the live shared bubble, the forecast, or the accessibility baseline.
- Build only the tables and endpoints the current phase needs.
- After each working milestone: run it, fix errors, then commit with a clear message.
- Ask the user before adding dependencies beyond the approved list, changing the data contract, or cutting a feature.

## Non-negotiable rules

- **Money is integer cents everywhere.** Totals reconcile to the cent; distribute leftover cents with the largest-remainder method, ties broken by user ID. Nessie's dollar amounts are converted at the Nessie client boundary only.
- **Only the backend** calls Nessie, the model (Gemma) and ElevenLabs. Keys live only in `api/.env` (gitignored). Nothing secret goes in `web/` or `device/`.
- **Identity comes from the session cookie or device token**, never from request bodies or model output.
- **The model (Gemma)** gets only the tools in the model tool contract (find_purchase, list_household_members, propose_split, explain_forecast, explain_anomaly, read_receipt), with their field, row and date limits, max 3 tool calls per request, and handles mapped back server-side. It never sees raw history, account numbers, Nessie IDs or other people's real names. It proposes; the server recomputes every amount from the ledger; the user confirms in the UI. Log fields and row counts to `ai_audit`, never values.
- **Untrusted text:** merchant names, memos and receipt text are wrapped as data and can never trigger actions.
- **Payments** need a client-generated idempotency key, enforced by a unique constraint.
- **No amounts in the feed or on Clearday Home.** The device speaks household-level info only, without names by default, and gets data only from `/api/device/summary` and `/api/household/status`.
- **Accounts:** show the nickname and last 4 digits only. Nessie IDs and account numbers never leave the backend.
- **New features:** receipt images are deleted after extraction; the analyst view uses synthetic households only and hides segments under 20; the Future view is labeled "Hypothetical, not investment advice"; recap scripts use household data only.
- **Branding:** a Capital One-inspired palette only (navy base, sky blues, white glass, sparing red). No logos, wordmarks or implied affiliation. Original artwork only.

## Accessibility baseline (MVP, never cut)

WCAG AA contrast (check text on glass), every bubble state has an icon and a text label, `prefers-reduced-motion` plus an in-app toggle, full keyboard access with visible focus, bubbles are `<button>`s with accessible names, list view (the screen-reader default), a text-size control that survives 200% zoom, and transcripts for all audio. Check UI work with browser screenshots.

## Analytics stubs

`analytics/` modules (`synthetic_data, forecast, categorize, detection, splits, prices, cohorts, future, backtest`) must match the **exact** signatures and output shapes in the Technical Spec's "Analytics contracts". Stubs return realistic, deterministic fake data. The teammate's real modules replace them file for file; calling code never changes. Don't implement the teammate's algorithms. Exception: `splits.py` is real (see Decisions).

## Nessie

- Base URL `https://prod-api.nessieisreal.com`; key passed as the `?key=` query parameter. Docs: https://prod.nessieisreal.com/docs (OpenAPI at https://nessieisreal.com/nessie-openapi-spec.yaml).
- The published spec is incomplete: purchase and transfer create/list routes aren't in it. Live-verified details are in `notes/nessie-api.md`.
- POST returns `{"objectCreated": {..., "_id": ...}}`, so read the new ID from the response instead of re-listing.
- Purchase, deposit and transfer amounts (and account balances) are integer dollars. Non-integers are **silently truncated** (12.34 becomes 12). Only bill `payment_amount` keeps cents. Keep true cents in our ledger.
- Balances are static: nothing moves them. The backend derives balances from mirrored transactions.
- Transfers have **no payee field** (`payee_id` and `medium` are rejected). Record the payee in our `payments` table and mirror the money arriving as a deposit on the payee's account.
- If one record is missing a field the read schema needs, the whole list returns 400. The seed always sends every field: purchases need `purchase_date` and `status`, bills need `nickname`, `payment_date` and `recurring_date`.
- The single-purchase route is `/purchase/{id}` (singular). Transfer GETs return `id` and everything else returns `_id`. Normalise this in the client.
- There's no bulk delete and no DELETE for customers or merchants. Deleting an account doesn't cascade.
- Cache every Nessie response in the database. The demo reads from the cache.

## Commands

- **Setup (run first, and again after editing `.githooks/` or `pyproject.toml`):** `bash scripts/bootstrap.sh`. It's idempotent: installs Python 3.12, runs `uv sync`, and wires the git hooks.
- Python (uv, 3.12, root project): `uv run pytest`, `uv run ruff check`.
- Device (separate uv project in `device/`): `cd device && uv sync && uv run pytest`; run with `uv run python -m clearday_home` (env vars in `device/README.md`). Sketch host check: `bash device/sketch/host_check/check.sh`.
- Secret guard: `bash scripts/check_secrets.sh` (pre-commit hook in `.githooks/`, wired by `bootstrap.sh`). Blocks staged files containing any secret value from a gitignored `*.env`, `*credentials*` or `*api_key*` file in the root or `api/` (values are never printed).
- **Filesystems without exec bits (e.g. this NTFS mount):** `bootstrap.sh` detects this and keeps the venv at `~/.local/share/clearday/venv` (`.venv` is a symlink to it) and copies `.githooks/*` to `~/.local/share/clearday/githooks`, which `core.hooksPath` points at. On a normal filesystem it uses `.venv` and `.githooks` directly. Override the location with `CLEARDAY_LOCAL_DIR`.
- Money lint: `bash scripts/check_money.sh` (runs in pre-commit after the secret guard; suppress a line with `# money-ok: <reason>`). After editing `.githooks/`, re-run `bash scripts/bootstrap.sh` to refresh the external hook copy.
- **Run the servers with `scripts/dev.sh` (the only supported way):** `bash scripts/dev.sh up | down | restart | status`. `up` starts the local DB (podman-compose), then the API (uvicorn `--reload`, :8000, `logs/api.log`) and web (:3001, `logs/web.log`) in the background with pidfiles in `logs/`. `--e2e` runs a second stack side by side on the local `clearday_e2e` DB (API :8001, web :3002, `logs/*-e2e.log`, mocks off). `down` stops only processes dev.sh started; `down --force-port` also stops a listener on the stack's ports whose command line contains this repo's path. `bash scripts/dev.sh migrate [--db local|tiger|e2e]` applies migrations.
- **Local DB (primary):** TimescaleDB 2.17.2-pg16 via podman-compose on 127.0.0.1:5432 (`DATABASE_URL_LOCAL`); `dev.sh up` starts it. `DB_TARGET=local` (default) uses it; `DB_TARGET=tiger` switches to Tiger Cloud (`DATABASE_URL`), the optional backup. Set it in `api/.env` or the environment.
- **Migrations:** `uv run python -m api.migrate` applies `api/migrations/NNNN_name.sql` once each (tracked in `schema_migrations`, checksummed). Never edit an applied file; add a new one.
- **API:** FastAPI + Socket.IO at `/socket.io`; health at `/api/health`. Started by `dev.sh`. API tests need the DB up and create a throwaway database per test.
- Web (npm, in `web/`): `npm install`, then `npm run build`, `npm run lint`, `npm run typecheck`, `npm run format` (or `npm run check` for typecheck + lint + format check). Copy `web/.env.example` to `web/.env.local`; `NEXT_PUBLIC_USE_MOCKS=1` uses the in-memory mock API (`web/lib/api/mock`), `0` calls FastAPI. **No exec bits on this mount:** `node_modules/.bin/*` cannot run, so every npm script calls the tool's JS entry with `node` (e.g. `node node_modules/next/dist/bin/next dev`). Never use `npx <tool>` or `./node_modules/.bin/...`; add new tools as npm scripts the same way.
- **Live pop E2E:** Playwright is a root dev dependency; run `uv run playwright install chromium` once per machine. `bash scripts/dev.sh up --e2e` then `bash scripts/dev.sh e2e` (or `uv run python scripts/e2e_live_pop.py --web http://localhost:3001` against a running seeded stack): Maya and Jake in two browser sessions, Jake pops Rent, Maya updates over Socket.IO; screenshots in `logs/e2e/`.
- **Demo reset:** `uv run python -m scripts.reset_demo` (`--dry-run`, `--db-only` offline) returns the DB and our 3 customers' Nessie records to the seeded state in a few seconds; idempotent. Targets the DB `api.config` points at (e.g. `DATABASE_URL_LOCAL=.../clearday_e2e`). `e2e_live_pop.py` runs it first (`--no-reset`, `--reset-db-only`).
- **Logs:** `dev.sh` writes `logs/api.log` and `logs/web.log` (`logs/*-e2e.log` for `--e2e`, `logs/db.log` for podman-compose). Read those logs for errors before asking the user.
