# Clearday — HackNC 2026

A social money app for roommates: bills are glossy Frutiger Aero bubbles, splits run through a real ledger, a Monte Carlo "money weather" forecast warns of tight weeks, and Clearday Home (UNO Q + smart bulb) reacts live.

**Deadlines (EST):** code freeze 7:30 AM Sun Oct 11 · video by 8:00 AM · Devpost by 9:30 AM (hard close 10:00 AM). A working, polished core loop beats feature count.

## Source of truth: `docs/`

Read the relevant doc before building a feature. If an instruction conflicts with these docs, ask the user.

| Doc | Use it for |
| --- | --- |
| `docs/Proposal.md` | Product, MVP list, **stretch order** |
| `docs/Technical Spec.md` | Tables, endpoints, Socket.IO events, ledger rules, forecast, design/a11y, **Analytics contracts** |
| `docs/Security and Privacy.md` | Gemini tool contract, device rules, rules for new features |
| `docs/Clearday Home Hardware.md` | Device states, bridge protocol, fallbacks |
| `docs/Build Plan.md` | **Phased checklist** and **Cut lines** |
| `docs/Demo and Submission.md` | Demo script, Q&A, submission checklist |

Where docs disagree with each other, the Technical Spec's Analytics contracts win over the Build Plan's older `forecast(...)` signature, and the Build Plan's Phase 1 (three accounts per roommate) wins over the spec's "one checking account each".

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

- Build each phase in `docs/Build Plan.md` end to end before starting the next. Don't start a stretch item until the Phase 2 checklist is done.
- Build stretch items in the Proposal's stretch order. If behind, **cut in the Build Plan's Cut lines order**, which is not the reverse of the stretch list. Never cut the live shared bubble, the forecast, or the accessibility baseline.
- Build only the tables and endpoints the current phase needs.
- After each working milestone: run it, fix errors, then commit with a clear message.
- Ask the user before adding dependencies beyond the approved list, changing the data contract, or cutting a feature.

## Non-negotiable rules

- **Money is integer cents everywhere.** Totals reconcile to the cent; distribute leftover cents with the largest-remainder method, ties broken by user ID. Nessie's dollar amounts are converted at the Nessie client boundary only.
- **Only the backend** calls Nessie, Gemini and ElevenLabs. Keys live only in `api/.env` (gitignored). Nothing secret goes in `web/` or `device/`.
- **Identity comes from the session cookie or device token**, never from request bodies or model output.
- **Gemini** gets only the tools in the Gemini tool contract (find_purchase, list_household_members, propose_split, explain_forecast, explain_anomaly, read_receipt), with their field, row and date limits, max 3 tool calls per request, and handles mapped back server-side. It never sees raw history, account numbers, Nessie IDs or other people's real names. It proposes; the server recomputes every amount from the ledger; the user confirms in the UI. Log fields and row counts to `ai_audit`, never values.
- **Untrusted text:** merchant names, memos and receipt text are wrapped as data and can never trigger actions.
- **Payments** need a client-generated idempotency key, enforced by a unique constraint.
- **No amounts in the feed or on Clearday Home.** The device speaks household-level info only, without names by default, and gets data only from `/api/device/summary` and `/api/household/status`.
- **Accounts:** show the nickname and last 4 digits only. Nessie IDs and account numbers never leave the backend.
- **New features:** receipt images are deleted after extraction; the analyst view uses synthetic households only and hides segments under 20; the Future view is labeled "Hypothetical, not investment advice"; recap scripts use household data only.
- **Branding:** a Capital One-inspired palette only (navy base, sky blues, white glass, sparing red). No logos, wordmarks or implied affiliation. Original artwork only.

## Accessibility baseline (MVP, never cut)

WCAG AA contrast (check text on glass), every bubble state has an icon and a text label, `prefers-reduced-motion` plus an in-app toggle, full keyboard access with visible focus, bubbles are `<button>`s with accessible names, list view (the screen-reader default), a text-size control that survives 200% zoom, and transcripts for all audio. Check UI work with browser screenshots.

## Analytics stubs

`analytics/` modules (`synthetic_data, forecast, categorize, detection, splits, prices, cohorts, future, backtest`) must match the **exact** signatures and output shapes in the Technical Spec's "Analytics contracts". Stubs return realistic, deterministic fake data. The teammate's real modules replace them file for file; calling code never changes. Don't implement the teammate's algorithms.

## Nessie

- Base URL `https://prod-api.nessieisreal.com`; key passed as the `?key=` query parameter. Docs: https://prod.nessieisreal.com/docs (OpenAPI at https://nessieisreal.com/nessie-openapi-spec.yaml).
- The published spec is incomplete: purchase and transfer create/list routes aren't in it. Verify routes live before relying on them.
- POST returns a string, not the created object, so re-list to find new IDs.
- Purchase, deposit and transfer amounts and balances are integer dollars; bill `payment_amount` is a float. There's no bulk data delete.
- Cache every Nessie response in the database. The demo reads from the cache.

## Commands

- Python (uv, 3.12, root project): `uv sync`, `uv run pytest`, `uv run ruff check`.
- Secret guard: `bash scripts/check_secrets.sh` (pre-commit hook in `.githooks/`; enable with `git config core.hooksPath .githooks`).
- This checkout lives on an NTFS mount without exec bits, so locally `.venv` is a symlink to `~/.local/share/clearday/venv` and `core.hooksPath` points at `~/.local/share/clearday/githooks` (a copy of `.githooks/pre-commit`).
- Web (npm): _to be filled in._
