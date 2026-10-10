# Nessie API: live probe results

Probed 2026-10-10 against `https://prod-api.nessieisreal.com` with stdlib Python. Auth is the `?key=` query parameter on every call (redacted everywhere here). The backend is a pydantic (v1-style) service behind AWS API Gateway, so it behaves differently from the classic Nessie docs and from parts of `CLAUDE.md`.

## Headline answers

| Question | Answer |
| --- | --- |
| Non-integer purchase/transfer/deposit amounts (e.g. `12.34`)? | **Accepted with 201 and silently truncated** to an int (`12.34` → `12`, `12.99` → `12`, `100.75` → `100`). Same for account `balance` (`1000.55` → `1000`). A string `"12.34"` is rejected with 400 `value is not a valid integer`. Negative amounts (`-5`) are accepted. Bill `payment_amount` is a float and is stored as-is (`84.37`). |
| Do transfers move balances? | **No.** Nothing moves `account.balance`: not transfers (`pending` or `completed`, still unchanged after a 35 s re-GET), purchases, deposits or completed bills. The OpenAPI spec says nothing about async balance updates, and the docs page is a JS shell with no text to check. The balance stays at whatever was set when the account was created. `PUT /accounts/{id}` silently ignores `balance`. |
| Does POST return the new id? | **Yes.** Every create returns `201 {"code":201,"message":"<X> created","objectCreated":{..., "_id": "<uuid>"}}`. You don't need to re-list. (This contradicts the "POST returns a string" note in `CLAUDE.md`.) |
| Rate limit? | **None observed**: 60 sequential and 100 concurrent (20 threads) GETs all returned 200, with no rate headers. Usually 0.1 to 0.2 s per call; the first POST to a route after idle takes about 1.2 s (cold start). |
| Merchant without geocode? | **Yes.** Only `name` is required. `category` must be a **string**, not an array (an array gives 400). |
| Transfer payee? | **A transfer has no payee field.** Re-tested with the classic body `{"medium":"balance","payee_id":"<second account>","amount":1,"description":"x"}`: it gets 400 `payee_id`/`medium` "extra fields not permitted", with or without `transaction_date` and `status`. `payer_id`, `account_id`, `payee` and similar are rejected too. A transfer shows up only under the account it was posted to. The payee's `/transfers` list stays 404. |

## Ids and errors

- Ids are 36-char UUIDs, not 24-char Mongo ids. Most objects use `_id`, but **transfer GETs return `id`** (their PUT response uses `_id`).
- Validation errors are `400` with a JSON **string** body that holds pydantic's message.
- Unknown routes return `403 {"message":"Missing Authentication Token"}` (API Gateway), not 404.
- There is **no referential integrity**: you can POST a deposit to a nonexistent account id, an account to a nonexistent customer id, or a purchase with a nonexistent merchant id.
- Date fields are free strings: `"garbage"` and ISO datetimes are both stored as sent.
- `DELETE` of a nonexistent id still returns `200`.

## Routes

| Resource | Method and path | Required body | Success | Notes |
| --- | --- | --- | --- | --- |
| Customer | `POST /customers` | `first_name` | 201 `objectCreated` | `last_name` and `address{street_number,street_name,city,state,zip}` are optional |
| | `GET /customers`, `GET /customers/{id}` | | 200 list / object | 404 `"Customer not found"` |
| | `PUT /customers/{id}` | any subset | 202 `objectUpdated` | |
| | `DELETE /customers/{id}` | | **403, route doesn't exist** | Customers can't be deleted |
| Account | `POST /customers/{cid}/accounts` | `type` ∈ `Checking`/`Savings`/`Credit Card`, `nickname`, `rewards`, `balance` (int) | 201 | `account_number` is server-generated (16 digits) and a sent one is ignored. Response includes `customer_id` |
| | `GET /accounts`, `GET /customers/{cid}/accounts`, `GET /accounts/{id}` | | 200 | 404 has an empty body |
| | `PUT /accounts/{id}` | `nickname` (required) | 202 | `balance` and unknown fields are silently ignored |
| | `DELETE /accounts/{id}` | | 200, empty body | **No cascade**: the account's deposits and purchases survive and stay listable under the dead id |
| Merchant | `POST /merchants` | `name` | 201 | `category` (string), `address` and `geocode{lat,lng}` are optional |
| | `GET /merchants`, `GET /merchants/{id}`, `GET /merchants/{id}/purchases` | | 200 | `?lat&lng&rad` is accepted but seemed to return all merchants. Merchants are scoped to the key (the list started empty) |
| | `PUT /merchants/{id}` | any subset | 202 | |
| | `DELETE /merchants/{id}` | | **403, route doesn't exist** | Merchants can't be deleted |
| Purchase | `POST /accounts/{aid}/purchases` | `merchant_id`, `medium` (`balance`/`rewards`), `amount` (int) | 201 | Not enforced at create but **effectively required**: `purchase_date`, `status` ∈ `pending`/`cancelled`/`completed` (see trap below). `description` is optional. The response adds `type:"merchant"` and `payer_id` |
| | `GET /accounts/{aid}/purchases`, `GET /purchase/{id}` | | 200 | Note the **singular** `/purchase/{id}`. `/purchases/{id}` gives 403 |
| | `PUT /purchase/{id}` | subset | 202 | `status` is **not** updatable ("extra fields not permitted"). `purchase_date`, `amount`, `description` and similar are |
| | `DELETE /purchase/{id}` | | 200 `"Purchase deleted"` | |
| Deposit | `POST /accounts/{aid}/deposits` | `medium`, `amount` (int), `transaction_date`, `status`, `description` | 201 | The response adds `creation_date`. Neither list nor get returns the account id |
| | `GET /accounts/{aid}/deposits`, `GET /deposits` (all), `GET /deposits/{id}` | | 200 | |
| | `PUT /deposits/{id}` | subset (`status` OK) | 202 | |
| | `DELETE /deposits/{id}` | | 200 | |
| Transfer | `POST /accounts/{aid}/transfers` | `amount` (int), `transaction_date`, `status`, `description` (nothing else is allowed) | 201 | Missing from the published spec |
| | `GET /accounts/{aid}/transfers`, `GET /transfers/{id}` | | 200; **404 `"No transfers found for this account"` when empty** | `GET /transfers` (no id) gives 403. Returns `id`, not `_id` |
| | `PUT /transfers/{id}` | subset (`status`, `amount`) | 202 | `amount` is truncated here too |
| | `DELETE /transfers/{id}` | | 200 | |
| Bill | `POST /accounts/{aid}/bills` | `status` ∈ `pending`/`cancelled`/`completed`/`recurring`, `payee` (string), `payment_amount` (float) | 201 | **Effectively required**: `nickname`, `payment_date`, `recurring_date` (1 to 31). The server sets `creation_date` and `upcoming_payment_date`, plus `account_id` |
| | `GET /accounts/{aid}/bills`, `GET /customers/{cid}/bills`, `GET /bills/{id}` | | 200 | 404 `"Bill with this id does not exist"` |
| | `PUT /bills/{id}` `{"status":"completed"}` | subset | 202 `objectUpdated` | This is how you mark a bill paid. It doesn't touch the balance |
| | `DELETE /bills/{id}` | | 200 `"Bill deleted"` | |

## Trap: one malformed record breaks the whole list

The create schemas are looser than the read schemas. Here are the cases we hit:

- A purchase created without `purchase_date` or `status` makes `GET /accounts/{aid}/purchases`, `GET /merchants/{mid}/purchases` and `GET /purchase/{id}` return **400** for the whole list.
- A bill created without `nickname`, `payment_date` or `recurring_date` does the same to `GET /accounts/{aid}/bills` and `GET /customers/{cid}/bills`.
- A purchase whose `merchant_id` is shorter than 24 chars does the same to the purchase list.

Deleting the bad record by id is the only fix. A purchase can be partly repaired with PUT, but its `status` can't be set afterwards.

## Implications for the seed/client

1. **Cents can't round-trip through Nessie.** Purchase, deposit and transfer amounts get floor-truncated without any error, so sending `12.34` silently loses 34 cents. The seed should generate whole-dollar purchases, deposits and transfers, keeping cent-level detail only in bills (`payment_amount` float, converted with `round(x*100)` at the client boundary). Otherwise the ledger must keep the true `amount_cents` locally and treat Nessie's number as a lossy mirror. The client must reject or round explicitly and never pass floats through and hope.
2. **Compute balances in our ledger.** Nessie balances are static, so set a sensible opening `balance` at account creation and derive the current balance from mirrored transactions in our database. Don't show `account.balance` as live.
3. **A payment is a transfer with no payee.** Post it on the payer's checking account, and record payee, split and idempotency key in our `payments` table. To mirror the money arriving, also post a matching deposit on the payee's account. Put the idempotency key in `description` so a re-list can find orphaned calls.
4. **Use the POST response.** Read `objectCreated._id` directly. Normalise transfers (`id`) and everything else (`_id`) at the client boundary.
5. **Always send every read-schema field.** Purchases need `purchase_date` and `status`. Bills need `nickname`, `payment_date` and `recurring_date`. Deposits and transfers already require theirs. Validate before POST, since Nessie won't check references or dates. Use `YYYY-MM-DD`.
6. **Treat a 404 on the transfers list as an empty list**, and an API Gateway 403 as a wrong path, not an auth failure.
7. **Make the seed idempotent ourselves.** Customers and merchants can't be deleted, so the seed must look up existing customers and merchants by name before creating them. `reset_demo.py` can delete only accounts, purchases, deposits, transfers and bills, and must delete children by id **before** the account, because there's no cascade.
8. **Rate limits aren't a concern.** A modest thread pool (about 10) is fine for seeding. Add a retry for the roughly 1 s cold-start latency.
9. The seed should ignore the leftover `zz-probe` records described below.

## Leftover probe data (couldn't be deleted, since no DELETE route exists)

- 3 customers with first name `zz-probe`
- 3 merchants: `zz-probe Merchant A`, `zz-probe Merchant B`, `zz-probe Merchant C`

All probe accounts, purchases, deposits, transfers and bills were deleted. `GET /accounts` and `GET /deposits` both return `[]`.
