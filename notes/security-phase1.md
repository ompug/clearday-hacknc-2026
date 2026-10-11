# Phase 1 security review

Scope: whole tree since the first commit (`1d0bc61`) through `e09db9b`, against
`docs/03-security-and-privacy.md` and `CODING_STANDARDS.md`. Review only; nothing was fixed.
No secret values were printed while producing this note.

## Findings, ranked

### 1. Medium: dev persona login is on by default and impersonates anyone

- `api/config.py:26` `enable_dev_routes: bool = True`
- `api/routes/session.py:63` `POST /api/dev/login` takes a `user_id` (`u_1`, `u_2`, ... enumerable,
  and listed by `GET /api/dev/personas`) and sets a session cookie for that user with no other check.

Whoever can reach the API can sign in as Maya and pop bills, read balances and the sky. Today
uvicorn binds 127.0.0.1 (`scripts/dev.sh` passes no `--host`), so exposure is the laptop only. Clearday
Home must reach the API over the LAN (`CLEARDAY_API_URL`), so the moment the API binds `0.0.0.0` on
hackathon Wi-Fi this becomes a full account takeover for anyone on that network.

Fix: default `enable_dev_routes` to `False` and set `ENABLE_DEV_ROUTES=true` only in `api/.env`;
refuse to start with dev routes on when the bind host isn't loopback (or require a demo PIN in the
login body). When the device needs LAN access, keep the API on 127.0.0.1 and expose only the
device endpoints, or firewall the port to the device's IP.

### 2. Medium: sessions can't be revoked, and sockets are never re-checked

- `api/session.py:50-67` the token is `<user_id>.<issued_at>.<hmac>`; it stays valid for 7 days
  (`MAX_AGE_S`, line 23) whatever happens server-side.
- `api/routes/session.py:74` logout only deletes the browser cookie; a copied cookie still works.
- `api/realtime.py:80-89` membership is checked once at connect; a socket keeps receiving
  `hh:<id>` events after logout, after the user leaves the household (`left_at` set), or after the
  cookie expires.

Signing itself is sound: HMAC-SHA256, `hmac.compare_digest`, 16+ char secret enforced, future-dated
tokens rejected, membership re-checked on every HTTP request (`current_user`).

Fix: add a per-user `session_version` (or a `sessions` table with a random id) to the signed body and
bump it on logout; on logout or `left_at`, `sio.disconnect` the sids in `user:<id>`; re-verify the
cookie on reconnect (already happens) and drop sockets whose token has expired (periodic sweep).

### 3. Low-Medium: device token path is half-built

- `api/routes/reads.py:26` `/api/household/status` accepts only the session cookie (TODO), and
  `/api/device/summary` doesn't exist yet, so the device can't use its token over HTTP.
- No issuance or revocation code: nothing writes `devices` rows outside tests.
- `api/realtime.py:63-72` a revoked token is refused at connect, but an already-connected device
  stays in `hh:<id>:device` (same root cause as 2).
- `device/clearday_home/api_client.py:23`, `bridge.py:139-140` the token travels as a Bearer header
  over `http://` (`CLEARDAY_API_URL` default). On shared Wi-Fi it can be sniffed. Scope is read-only
  household data, so impact is limited.

Good: tokens are stored as SHA-256 hashes (`api/realtime.py:49`, `devices.token_hash` check
constraint), a present-but-wrong token is refused rather than falling back to the cookie, and the
device room never gets `feed.created` (names). Device `Config.__repr__` hides the token.

Fix: one `current_device` dependency (Bearer -> hash lookup, `revoked_at IS NULL`) that returns only
a household id and is accepted only by `/api/household/status` and `/api/device/summary`; an issue
and revoke endpoint for members that shows the token once; disconnect `hh:<id>:device` sids on
revoke; generate tokens with `secrets.token_urlsafe(32)`.

### 4. Low: idempotency replay doesn't compare the request

- `api/payments.py:80-89` a replayed key returns the stored result if `bubble_id` matches, without
  comparing `account_id` or `amount_cents`.
- `api/ledger.py:53-61` / migration `0001` line 99: the key is globally unique, so another user's
  key gets 409 "already used" (an existence oracle; harmless with `crypto.randomUUID`,
  `web/components/sky/PayDialog.tsx:18`).

The core property holds: a unique constraint, `ON CONFLICT DO NOTHING`, `FOR UPDATE` on the share,
and concurrent double taps resolve to one payment and the original result.

Fix: store the request's `account_id` and `amount_cents` with the payment and return 409 on a replay
whose fields differ. Optionally make the constraint `UNIQUE (from_user, idempotency_key)`.

### 5. Low: Nessie key redaction is logger-scoped; NessieError carries response bodies

- `api/nessie/client.py:38-51` the `?key=` redaction filter sits on the `httpx` and `httpcore`
  loggers only. A filter on a parent logger doesn't run for records from child loggers
  (`httpcore.http11` and others) or for other code that logs a URL (e.g. `httpx.InvalidURL`,
  `HTTPStatusError` text in a traceback).
- `api/nessie/client.py:59,209` `NessieError` embeds 200 chars of the Nessie response body, which
  can include account numbers and Nessie IDs. Today every caller logs `type(exc).__name__` only
  (`api/payments.py:325`, `api/routes/payments.py:55`, `scripts/reset_demo.py:271`), so nothing leaks;
  one future `log.exception` would.

Verified: no Nessie key, `key=` parameter, session secret, 24-hex Nessie ID or 16-digit account
number appears in any file under `logs/`. `Settings` keeps keys as `SecretStr`; the cache key
refuses a `key` query (`api/nessie/cache.py:27`).

Fix: attach the redaction filter to the root handler (via `logging.basicConfig` in `api/main.py`
and scripts) instead of named loggers; keep the body in a separate `NessieError.detail` attribute
and leave it out of `str(exc)`.

### 6. Low: secret guard (committed version) scans api/.env only

- `scripts/check_secrets.sh` at HEAD reads values from `api/.env` only. The root
  `tiger-cloud-hacknc-credentials.env` and `openrouter_api_key.txt` values weren't compared.

The working tree already has an uncommitted extension that scans every gitignored `*.env`,
`*credentials*` and `*api_key*` file in the root and `api/` (`scripts/check_secrets.sh:10-17`).
Commit it and re-run `bootstrap.sh` to refresh the hook copy.

History scan (every blob of every commit, `git grep -F` per value): **no secret value was ever
committed.** Zero hits for `NESSIE_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`,
`DATABASE_URL`, `SESSION_SECRET`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`,
`TIMESCALE_SERVICE_URL`, `PGPASSWORD`, `PGHOST` and the OpenRouter key file. Hits only for
non-secret values (`NESSIE_BASE_URL`, `ELEVENLABS_MODEL_ID`, `PGUSER`, and the
`postgres:postgres@localhost` local DSN that is also in `.env.example`). No `.env`, credentials or
api_key file appears in any commit's tree. `api/.env`, `device/.env`, `web/.env.local`,
`tiger-cloud-hacknc-credentials.env` and `openrouter_api_key.txt` are all gitignored
(`.gitignore:5-6,54-57`).

### 7. Low: reset_demo can't touch non-seeded Nessie accounts, but its scoping is by name

- `scripts/reset_demo.py:96-109` Nessie customers and accounts are found by exact
  (first, last) and (type, nickname); writes happen only inside those accounts. Inside them it
  deletes transfers/deposits whose id is on our payment rows **or** whose description starts with
  `Clearday:` (line 123), and reverts bills that match a seeded (nickname, date) or a payment-row id
  (lines 128-136). Customers, merchants and other accounts are only read.
- `scripts/reset_demo.py:58-61` the DB household is picked by name ("Apartment 4B", lowest id) and
  members by `display_name` (line 71), so a duplicate name resolves silently.
- `scripts/reset_demo.py:259-267` it resets whatever `DB_TARGET` points at, including Tiger Cloud,
  with no confirmation (it prints the DB name).

Verdict: other customers' and other accounts' Nessie data is out of reach. Within the 9 seeded
accounts, any manually created record described `Clearday: ...` would also be deleted.

Fix: resolve seeded accounts from our DB (`accounts.nessie_account_id` for the seeded users) and
intersect with the Nessie lookup; require `--yes` when `DB_TARGET=tiger`.

### 8. Info

- Session cookie flags (`api/session.py:70-79`): `HttpOnly`, `SameSite=Lax`, `Path=/`,
  `Max-Age` 7 days; `Secure` off by default (`api/config.py:24`), which is right for
  http://localhost. Turn it on and use a `__Host-` name if this is ever served over HTTPS.
- `api/main.py:23` OpenAPI docs are public at `/api/docs`. Harmless locally; disable with dev routes.
- `api/sky.py:468-486` household weather turns "tight" when any one member's personal forecast is
  short, and Clearday Home reads it. It reveals no one, but in a 2-person household it implies who.
  Worth a product decision against the device rule "never mentions hardship signals".

## Checked and clean

- **CORS** (`api/main.py:24-30`, `api/realtime.py:25-27`): explicit origin list with credentials,
  no wildcard; Socket.IO checks the same list. Cross-site JSON POSTs need a preflight, and FastAPI
  won't parse a `text/plain` body as JSON, so form-based CSRF on `/api/payments` fails.
- **Socket.IO rooms** (`api/realtime.py:63-77`): rooms come only from the DB (cookie -> current
  household, token -> device room); the server registers no client events, so a client can't join
  or emit into another household's room. Personal bill pops go to `user:<id>` only
  (`api/payments.py:241`); `feed.created` skips the device room.
- **IDOR**: `_pop_shared` requires `e.household_id = user.household_id` and `s.user_id = user.user_id`
  (`api/payments.py:111-121`); `_pop_bill` requires `t.user_id` (line 206-212); the paying account
  must belong to the user (`_user_account`, line 72-77); the payee account is chosen server-side.
  Body `user_id` is ignored (`extra="ignore"`). `/api/sky` and `/api/accounts` read only the cookie
  user's rows. Jake can't pay or see another household's shares.
- **Nessie IDs / account numbers**: no response or socket payload carries them. Wire IDs are
  `api/ids.py` prefixes over our integer keys; accounts expose nickname and last4 only
  (`api/sky.py:164-182`); `web/lib/api/types.ts` has no Nessie fields.
- **Amounts on device / feed**: `feed_events` has no amount column; device-room events carry IDs,
  status and a fill ratio only; `/api/household/status` returns counts.
- `web/` and `device/` never call Nessie, Gemini or ElevenLabs.
