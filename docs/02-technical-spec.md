# Technical Spec

## Architecture

&#91;embedded content: Clearday architecture · 2 clients, 1 backend, 4 services\]

The app and Clearday Home call only the Clearday backend, which holds every API key; the model (Gemma) sees computed summaries, never raw Nessie data.

## Tech stack

Choose tools the team already knows; these are defaults, not requirements.

| Layer | Choice | Why |
| --- | --- | --- |
| Frontend | Next.js (React), responsive web | One codebase for laptop and phone demo |
| Aero visuals | CSS `backdrop-filter`, layered gradients, Framer Motion or Matter.js for bubble physics | Glass look without image assets |
| Charts | Recharts or D3 for the forecast fan chart | Fast to wire, customizable |
| Backend | Node (Express or Next API routes) or Python (FastAPI) | Owns all secrets and external calls |
| Database | Postgres on Tiger Data | Time-series transactions, continuous aggregates, ledger tables in one place |
| Real-time | Socket.IO | Live shared bubbles across devices and Clearday Home |
| AI | Gemma through an OpenAI-compatible chat-completions endpoint with tool calling (template fallback) | Splits, receipts, explanations |
| Voice | ElevenLabs text-to-speech (speech-to-text for stretch) | Clearday Home and money weather report |
| Banking data | Capital One Nessie API | Customers, accounts, purchases, bills, deposits, transfers |
| Hardware | Arduino UNO Q | Clearday Home |
| Hosting | Local only: API, web, and database on the demo laptop | No public deploy (user decision) |

Money is stored as integer cents everywhere. All timestamps are UTC; due dates display in America/New\_York.

**Additions for the expanded plan**

| Layer | Choice | Why |
| --- | --- | --- |
| Backend language | Python FastAPI with python-socketio | The stats teammate's modules import directly |
| On-device AI | Gemma 3 270M (try 1B if fast enough), 4-bit GGUF via llama.cpp | Local narrator and privacy guard on Clearday Home |
| On-device speech-to-text (last stretch) | whisper.cpp tiny model | Voice questions never leave the house before screening |
| Accessibility checks | axe DevTools or Lighthouse accessibility audit | Catch contrast and labeling issues quickly |

## Data model

The ledger is the source of truth; bubbles are a view over it, and Nessie is mirrored, never trusted directly by the UI.

| Table | Key columns | Notes |
| --- | --- | --- |
| users | id, display\_name, nessie\_customer\_id, nessie\_account\_id | Nessie IDs never leave the backend |
| households | id, name | e.g. Apartment 4B |
| household\_members | household\_id, user\_id, joined\_at, left\_at | Prorating on move-in and move-out |
| devices | id, household\_id, token\_hash, revoked\_at | Clearday Home; read-only household scope |
| transactions | id, user\_id, nessie\_id, kind (purchase, deposit, bill, transfer), amount\_cents, merchant, status (pending, posted), occurred\_at | Tiger Data hypertable on occurred\_at |
| expenses | id, household\_id, payer\_id, source\_txn\_id, total\_cents, status (estimated, final), split\_method | One shared cost |
| expense\_items | id, expense\_id, label, amount\_cents | From receipt scanning |
| shares | id, expense\_id, user\_id, amount\_cents, status (open, partial, paid, disputed) | One person's part |
| payments | id, from\_user, to\_user, amount\_cents, nessie\_transfer\_id, idempotency\_key | Unique on idempotency\_key |
| allocations | payment\_id, share\_id, amount\_cents | How a payment covers shares; credit when share\_id is null |
| feed\_events | id, household\_id, type, actor\_id, subject\_label, created\_at | No amounts stored |
| forecasts | user\_id, run\_at, horizon\_days, p10, p50, p90 by day, model\_version | Cached results |
| ai\_audit | id, user\_id, tool, fields\_sent, row\_count, created\_at | No raw financial values |

**Tables added for the expanded plan**

| Table | Key columns | Notes |
| --- | --- | --- |
| accounts | id, user\_id, nessie\_account\_id, type (checking, savings, credit\_card), nickname | Several per user; `transactions` gains an account\_id column |
| categories | name, necessity (need, want) | Default mapping, user can override per transaction |
| receipts | id, user\_id, expense\_id, merchant, purchased\_at, total\_cents | Image deleted after extraction |
| receipt\_items | id, receipt\_id, raw\_label, normalized\_name, quantity, unit, unit\_price\_cents | Price memory compares normalized\_name across stores and dates |
| recaps | household\_id, week\_start, script\_text, audio\_url | Transcript always stored with the audio |
| cohort\_households | id, segment (e.g. student, early career), synthetic | Analyst view only; synthetic data, never real users |

## Nessie integration

Only the backend calls Nessie, with the key in an environment variable, and every response is cached in Tiger Data. Endpoint paths below are from memory; confirm them on the Nessie docs page before building.

| Use | Endpoint (verify) | Direction |
| --- | --- | --- |
| Create roommate personas | POST /customers, POST /customers/{id}/accounts | Seed |
| Merchants (Duke Energy, Harris Teeter, etc.) | GET/POST /merchants | Seed + read |
| Spending history | GET/POST /accounts/{id}/purchases | Seed + sync |
| Paychecks | GET/POST /accounts/{id}/deposits | Seed + sync |
| Bills | GET/POST /accounts/{id}/bills | Seed + sync |
| Paying a share | POST /accounts/{id}/transfers | App action |

**Seed script requirements**

- Three customers (Maya, Jake, Priya), one checking account each, with names and IDs written to a local config
- About 60 days of history: biweekly paychecks, rent, electric, internet, groceries, dining, rideshare, 3 subscriptions each
- Planted cases: one duplicate household subscription, one anomalous charge, one tight week before rent for one roommate
- Idempotent: safe to rerun without duplicating data
- Hold out the last 30 days for forecast backtesting

Keep a JSON snapshot of seeded data in the repo so the demo can run from cache if Nessie is unreachable.

## Ledger rules

Every rule below must hold so totals always reconcile to the cent.

1. **Split methods:** even, percentage, custom amounts, shares (weights), and itemized. Itemized splits allocate tax and tip in proportion to each person's item subtotal.
2. **Rounding:** compute in integer cents; distribute leftover cents with the largest-remainder method, ties broken by user ID so results are stable.
3. **Payment allocation:** a payment covers the payer's open shares to that recipient oldest first, unless the user picks shares manually. Underpayment leaves the share `partial`; overpayment becomes a credit.
4. **Netting:** balances between two people net to one figure. A household "settle up" uses debt simplification to minimize the number of transfers.
5. **Pending vs. posted:** expenses from pending transactions are `estimated`. When the final amount posts, shares are recomputed and affected users are notified.
6. **Variable bills:** utilities forecast from history and stay `estimated` until the real bill arrives.
7. **Membership changes:** shared bills prorate by days of membership in the billing period.
8. **Disputes:** a disputed share pauses reminders until resolved by the group.
9. **Idempotency:** every payment carries a client-generated key; the database enforces uniqueness so a double tap pays once.
10. **No silent edits:** changing an expense after payments exist creates adjustment entries rather than rewriting history.

## Forecast engine (money weather)

The engine simulates 1,000 possible next-30-day paths per user and reports the chance the balance drops below a safety threshold before each bill.

1. **Known events:** scheduled paychecks, bills, and the user's open household shares are placed on their dates.
2. **Recurring detection:** group purchases by merchant; flag as recurring when amounts are within about 10% and intervals are roughly weekly, biweekly, or monthly.
3. **Discretionary spending:** for each simulated day, bootstrap-sample daily spend per category from the user's own history (same weekday type where data allows).
4. **Simulate:** run the paths, record daily balances, and compute P10, P50, and P90 per day.
5. **Outputs:** probability of going below threshold before each bill (drives bubble color), safe-to-spend until next paycheck (P10-based, conservative), and the categories contributing most variance.
6. **Backtest:** forecast the held-out 30 days from earlier data, then report how often the actual balance fell inside the P10 to P90 band and the median error. Show this number to judges.

The formula for safe-to-spend, using the pessimistic path:

```latex
\text{safe} = \min_{d \le \text{payday}} B_{P10}(d) - \text{buffer}
```

The model receives only the outputs (dates, probabilities, top categories), never the underlying transactions. Thresholds and the buffer are user settings with a sensible default, e.g. $50.

**Income and needs vs. wants.** Income is modeled explicitly: detected paycheck amount, cadence, and variability, so irregular earners get wider bands. Every spending category is tagged need or want, and the engine reports both the base forecast and a "wants trimmed by 25%" scenario, so users see exactly how much safer their month gets.

**Analyst view.** The same engine runs in batch over about 200 synthetic households in a few segments. Tiger Data rollups report, per segment, the share of households with more than a 50% chance of a shortfall in the next 30 days. Segments under 20 households are hidden.

**Future view (educational).** Takes the user's median monthly surplus and projects 10 years under low, middle, and high annual return assumptions for a broad index fund that the user can see and adjust. Shown as a range with the label "Hypothetical, not investment advice"; no specific securities.

## Backend API and real-time events

The app and Clearday Home talk only to this API; user identity always comes from the session or device token, never from the request body.

| Method | Path | Purpose | Caller |
| --- | --- | --- | --- |
| GET | /api/sky | Bubbles for the current user: bills, shares, clusters, forecast color | App |
| GET | /api/forecast | P10/P50/P90 bands, safe-to-spend, drivers | App |
| POST | /api/expenses | Create a shared expense with a split | App |
| POST | /api/expenses/:id/receipt | Upload receipt image for itemizing | App |
| POST | /api/payments | Pay shares (requires idempotency key and user confirmation) | App |
| POST | /api/assistant | Natural-language request; returns a proposed action for confirmation | App |
| GET | /api/feed | Household feed events, no amounts | App |
| GET | /api/household/status | Household-only summary | App, Clearday Home |
| POST | /api/device/briefing | Returns briefing audio for the household | Clearday Home |
| POST | /api/dev/seed | Run the Nessie seed (disabled in production) | Team |

**Socket.IO events** (room per household, plus a private room per user)

| Event | Room | Payload |
| --- | --- | --- |
| share.updated | household | expense id, share id, new status, fill fraction |
| bubble.popped | household | expense id, label |
| feed.created | household | event type, actor display name, subject label |
| forecast.updated | user | new bubble colors, safe-to-spend |
| device.announce | household (device) | audio URL, light pattern |

**Endpoints added for the expanded plan**

| Method | Path | Purpose | Caller |
| --- | --- | --- | --- |
| GET | /api/accounts | The user's accounts and balances by type | App |
| POST | /api/receipts | Upload receipt image; returns items for the user to confirm | App |
| GET | /api/prices?item= | Price history of a normalized item across stores | App |
| GET | /api/recap/latest | Latest weekly recap audio and transcript | App, Clearday Home |
| GET | /api/future | Educational long-term projection ranges | App |
| GET | /api/analyst/segments | Segment-level hardship rates from synthetic households | App (analyst page) |
| GET | /api/device/summary | Household summary for the on-device Gemma narrator | Clearday Home |

## Design system and accessibility

The look blends Frutiger Aero gloss with a Capital One-inspired palette: deep navy as the base, bright sky blues for the bubbles and glass, white panels, and a red accent used sparingly for alerts and the primary action. Use the palette only; no Capital One logos, wordmarks, or anything implying an official product.

| Requirement | How |
| --- | --- |
| Contrast | WCAG AA: 4.5:1 for body text, 3:1 for large text and icons; check text on glass panels especially |
| Not color alone | Every bubble state has an icon and a label ("Due in 3 days") |
| Reduced motion | Respect `prefers-reduced-motion` plus an in-app toggle that stills bubbles |
| Keyboard | Every action reachable by keyboard with visible focus rings; bubbles are buttons |
| Screen readers | Accessible names on bubbles ("Rent, $450 your share, due Friday, 2 of 3 paid"); list view as the screen-reader default |
| Text size | In-app text size control; layout survives 200% zoom |
| Audio | Transcripts for briefings and recaps; captions while playing |
| Plain language | Forecasts phrased as "likely" ranges, never jargon like P10 on the main screens |

## Analytics contracts

These signatures and output shapes are fixed; the backend codes against them with stubs, and the stats major's real modules replace the stubs without any calling code changing.

**Shared rules:** inputs are pandas DataFrames using the shared transaction columns (`transaction_id, user_id, account_id, date, amount_cents, kind, category, merchant, status`); money is integer cents; dates are `YYYY-MM-DD` strings; outputs are JSON-serializable dicts or lists; every random function takes a `seed`.

```python
# synthetic_data.py
generate(seed=42, days=60) -> {
  "users": [{"user_id", "name", "accounts": [{"account_id", "type", "nickname", "opening_balance_cents"}]}],
  "transactions": [ ...shared columns... ],
  "scheduled": [{"user_id", "account_id", "date", "amount_cents", "kind": "income"|"bill", "label", "cadence"}],
  "receipts": [{"receipt_id", "user_id", "merchant", "date", "items": [{"raw_label", "quantity", "unit", "unit_price_cents"}]}]
}

# forecast.py
forecast(transactions, scheduled, start_balance_cents, start_date, horizon_days=30,
         n_paths=1000, threshold_cents=5000, seed=0) -> {
  "days": [{"date", "p10_cents", "p50_cents", "p90_cents"}],
  "bills": [{"label", "date", "amount_cents", "p_short"}],
  "safe_to_spend_cents", "next_payday",
  "drivers": [{"category", "share_of_variance"}],
  "wants_trimmed": {"safe_to_spend_cents", "bills": [{"label", "date", "p_short"}]}
}

# categorize.py
tag_needs(transactions) -> transactions with added column "necessity" ("need"|"want")
detect_income(transactions) -> {"cadence": "weekly"|"biweekly"|"monthly"|"irregular",
  "typical_amount_cents", "variability_cents", "next_expected_date"}

# detection.py
detect_recurring(transactions) -> [{"merchant", "amount_cents", "cadence", "next_expected_date", "confidence"}]
detect_anomalies(transactions) -> [{"transaction_id", "merchant", "amount_cents",
  "typical_low_cents", "typical_high_cents", "score"}]
duplicate_subscriptions(household_transactions) -> [{"merchant", "user_ids",
  "monthly_cost_cents", "possible_savings_cents"}]

# splits.py
split(total_cents, method, participants, weights=None, items=None,
      tax_cents=0, tip_cents=0) -> {user_id: cents}   # values always sum to total_cents
allocate_payment(amount_cents, open_shares) -> {"allocations": [{"share_id", "amount_cents"}], "credit_cents"}
simplify_debts(balances) -> [{"from", "to", "amount_cents"}]

# prices.py
normalize(raw_label) -> str
compare(normalized_name, history) -> {"item", "best": {"merchant", "date", "unit_price_cents"},
  "latest": {"merchant", "date", "unit_price_cents"}, "savings_cents_per_unit"}

# cohorts.py
generate(n=200, seed=42) -> {"households": [...], "transactions": [...], "scheduled": [...]}
segment_rates(forecasts_by_household, households) -> [{"segment", "households", "share_at_risk"}]
  # segments with fewer than 20 households are omitted

# future.py
project(monthly_surplus_cents, years=10, rates={"low": 0.03, "mid": 0.06, "high": 0.08}) -> {
  "assumptions": {...rates used...}, "series": [{"year", "low_cents", "mid_cents", "high_cents"}]
}   # rates are adjustable placeholders shown to the user, not advice

# backtest.py
run(transactions, scheduled, holdout_days=30, seed=0) -> {"coverage", "median_abs_error_cents", "chart_path"}
```
