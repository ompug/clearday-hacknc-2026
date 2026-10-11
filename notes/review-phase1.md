# Phase 1 review (1d0bc61..HEAD, 22 commits)

This review is read-only. It checks the code against `CODING_STANDARDS.md`, Phase 1 in `docs/05-build-plan.md`, `docs/02-technical-spec.md` and the Decisions in `CLAUDE.md`. It does not cover the uncommitted changes to `scripts/dev.sh` and the `web/` config.

## What passed

- **Identity:** it comes only from the cookie or device token. `current_user` reads the cookie, and Socket.IO rejects any connection without a valid cookie or device token (`api/realtime.py:63-87`). `PaymentRequest` ignores a `user_id` sent in the body.
- **Integer cents:** they hold from the Nessie boundary (`api/nessie/money.py`) through the ledger, `analytics/splits.py` and `api/balances.py`, to `formatCents` (`web/lib/money.ts`, integer math only). Largest-remainder ties go to the lower user ID (`analytics/splits.py:52`).
- **Device payloads:** they carry no amounts and no names. They're parsed against an allowlist (`device/clearday_home/payloads.py`), and the device room never gets `feed.created`.
- **Feed events:** they carry no amounts (`api/payments.py:194` sends only the type, the actor name and the label).
- **a11y baseline in `web/`:**
  - bubbles are `<button>`s with an `aria-label`;
  - every state has an icon and a text label;
  - motion follows `prefers-reduced-motion` and an in-app toggle (MotionConfig plus a CSS kill-switch);
  - `:focus-visible` shows a ring;
  - list view is the default;
  - text size is set in rem.

  Contrast on glass was not checked in a browser.
- **Payments and mirroring:**
  - the idempotency key has a unique constraint, and a replay returns the stored result;
  - the mirror is a transfer plus a deposit, both described "Clearday: <label> share";
  - `nessie_rounding_diff_cents`, `mirror_status` and `mirror_attempts` are stored;
  - transactions are unique on `(nessie_id, occurred_at)`;
  - balances come from the DB.
- **Analytics stubs:** their signatures match the contracts.
- **Deploy step:** it is correctly cut.

## Findings (most severe first)

### High

1. **Subscription bubbles offer Pay, but paying one always fails with 404.**
   - `api/sky.py:438-441` builds them with `solo()` (`api/sky.py:408-427`), which sets `kind: "bill"` and `status: "open"`.
   - `canPay` lets them through (`web/lib/bubbles.ts:25`).
   - `pop_bubble` accepts only `exp_` and `bill_` IDs (`api/payments.py:253-258`).

   This failure is visible in the demo. Fix: give `sub_` bubbles a non-payable status (e.g. `"predicted"`) and make `canPay` exclude them.

2. **Nothing runs sync, so a failed mirror is never retried.** Round 4 says "sync retries it". `sync_accounts` and `retry_mirrors` are only called from `scripts/seed_nessie.py:537` (`api/nessie/sync.py:71`). Fix: add a `python -m api.nessie.sync` entry point plus a periodic task in the `api/main.py` lifespan.

3. **A sync after `reset_demo --db-only` re-imports the Clearday mirror records.**
   - `--db-only` deletes the payment rows but leaves the "Clearday:" transfers and deposits in Nessie. It also leaves the popped bills marked completed there (`scripts/reset_demo.py:221-238`).
   - `ledger_owned_nessie_ids` (`api/payments.py:365-374`) builds the skip set at `api/nessie/sync.py:90` from payment rows. Without those rows, sync imports the mirrors as plain transfer and deposit rows (in whole dollars), which moves Jake's and Maya's balances. It also re-posts the reopened bills, which undoes the reset.
   - Today the only guard is the printed warning at `scripts/reset_demo.py:281`.
   - A crash or timeout between a Nessie POST and `_link` (`api/payments.py:318-322`) leaves the same kind of orphan, and the retry then duplicates it.

   Fix:
   - Sync should skip any transfer or deposit whose description starts with `MIRROR_PREFIX` and that no payment row owns, and log its ID.
   - Separately, sync should not re-post a bill that the DB has as pending while Nessie has it completed and no payment row links it. Alternatively, make `--db-only` refuse while the API's sync is enabled.

### Medium

4. **The seed floors the 3-way split and drops leftover cents** (`scripts/seed_nessie.py:277,282`, `cents // len(PEOPLE)`). This breaks the money rule (largest remainder, sum == total). The repayments under-sum, and `cents_to_whole_dollars` raises if a share isn't whole dollars. Fix: use the even split from `analytics.splits` and assert that shares are whole dollars.
5. **Dev login is on by default** (`api/config.py:26`, `enable_dev_routes: bool = True`). Anyone can log in as any persona through `/api/dev/login` (`api/routes/session.py:64`). Fix: default it to `False` and set it to true in `api/.env` for the demo.
6. **`requests` is used in `device/` but not approved or declared** (`device/clearday_home/api_client.py:11`). It only arrives transitively through `python-socketio[client]`. Fix: switch to stdlib `urllib`, or ask the user and then declare it in `device/pyproject.toml`.
7. **No JSON snapshot of the seed** (spec: "Keep a JSON snapshot of seeded data in the repo"). Fix: make the seed write `notes/seed_snapshot.json` from `build_plan()`.
8. **The progress logic is duplicated:**
   - the `expense_progress` CTE appears at `api/payments.py:91-103` and again at `api/sky.py:76-88`;
   - the `fill_fraction` rounding appears at `api/payments.py:163` and again at `api/sky.py:396`, where it is a literal `4`.

   The bubble and the payment result could disagree. Fix: keep one progress SQL and one `fill_fraction()` helper.

### Low

9. **Dollar rounding happens outside the Nessie money module** (`api/payments.py:54` `nessie_amount`, which hard-codes 100). `money.py` claims to be the only place that converts. Fix: move it to `api/nessie/money.py` and use `CENTS_PER_DOLLAR`.
10. **The money lint covers only `splits.py`, `ledger*.py` and `payments*.py`** (`scripts/check_money.sh:9-12`), so it missed findings 4 and 9. Fix: lint all of `api/`, `analytics/` and `scripts/`, with `money-ok` on the boundary file and on display ratios.
11. **A payment is marked `mirrored` when an account has no Nessie ID**, even though nothing was sent (`api/payments.py:317-329`). Fix: set `mirror_status = 'skipped'` (or `'failed'`) when `payer_nessie` or `payee_nessie` is missing.
12. **A partial share can't be paid.** `your_share_cents` is the full share (`api/sky.py:393`), but the server rejects any amount other than the remaining one with "Amount changed" (`api/payments.py:126`). Fix: send `amount_cents - allocated_cents` as `your_share_cents`.
13. **A personal bill paid from another account still debits the bill's own account** (`api/payments.py:229`). Fix: limit the account picker to the bill's account, or post the bill on the chosen account.
14. **`/api/household/status` accepts only the cookie** (`api/routes/reads.py:26`). The device calls it with a Bearer token, and calls `/api/device/summary`, which doesn't exist yet (`device/clearday_home/api_client.py:26-37`). This is Phase 2. Fix: add a dependency that accepts either the cookie or the device token, then implement `/api/device/summary`.
15. **CODING_STANDARDS #6 conflicts with the spec.** It says "no names in the feed", but `feed.created` carries `actor_display_name` (`api/payments.py:194`), which spec §155 allows for household members. Fix: change the standard to read "names only for household members, never in the device room".
16. **Household weather is decided in two places:** `household_status` (`api/sky.py:479`) has its own clear/tight rule, separate from `weather_for()` (`api/sky.py:69`). Fix: use one shared `household_weather()` helper.
17. **Payment IDs skip `api/ids.py`** (`api/payments.py:166,230` use a hand-built `f"pay_{...}"`). Fix: add `ids.PAYMENT` and use `ids.encode`.
18. **The bubble dict and `PaymentResult` dict are each built twice** (`api/sky.py:385-404` and `408-427`; `api/payments.py:165-172` and `229-236`). Fix: build each one in a single builder or dataclass.
19. **`forecast.updated` is never emitted after a payment** (`api/routes/payments.py:78` only invalidates the cache). This event is Phase 2. Fix: emit it to the user room after a payment commits.
20. **Some Phase 2 work was built early:**
    - the `feed_events` table, the `devices` table and the device state machine;
    - subscription clustering;
    - `/api/dev/personas`, `/api/dev/login` and `/api/me`, which aren't in the spec's endpoint table.

    None of it is harmful. Fix: no action. Note it in the build plan instead.
