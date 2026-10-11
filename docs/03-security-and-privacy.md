# Security and Privacy Rules

## Core principles

The model can read only what the current request needs and can never move money; every rule below is enforced in backend code, not in the prompt.

1. **No direct access.** Only the backend holds the Nessie, model, and ElevenLabs keys. The model (Gemma) never calls Nessie.
2. **Identity from the session.** The user or household ID comes from the authenticated session or device token, never from model output or request bodies.
3. **Interpret, then fetch.** The first model call sees the user's message and tool definitions only. The backend validates the returned intent before running any query.
4. **Minimum data.** Each tool returns only the fields its purpose needs, with row and date limits.
5. **Math in code.** Splits, forecasts, and anomaly scores are computed by the backend; the model only phrases results.
6. **Propose, then confirm.** The model can propose a split or request; the user confirms in the UI, and the server re-validates amounts against the ledger.
7. **Untrusted text is data.** Merchant names, memos, and receipt text are wrapped as untrusted content and can't trigger actions.
8. **Opt-in and auditable.** AI features are opt-in; each AI request logs which fields and how many rows were sent, never raw values.
9. **Private by default.** Amounts never appear in the feed or on Clearday Home.

## Model tool contract

The app's model is Gemma (Google's open model), called by the backend through an OpenAI-compatible chat-completions endpoint with tool calling; the endpoint is configured only in `api/.env`. The model may call only these tools; anything else is rejected by the AI gateway.

| Tool | Inputs (validated) | Returns to the model | Limits |
| --- | --- | --- | --- |
| find\_purchase | date range, merchant hint, approximate amount | handle, merchant, amount, date | 30 days, 20 rows |
| list\_household\_members | none | placeholder names (Person A, B, C) | Current household only |
| propose\_split | purchase handle, people, method | proposed shares in cents | Proposal only; nothing saved |
| explain\_forecast | none | dates, probabilities, top 3 categories | Computed summary only |
| explain\_anomaly | anomaly handle | merchant, amount, typical range | One item |
| read\_receipt | uploaded image | line items, tax, tip | Image the user just uploaded |

**Never sent to the model:** account numbers, Nessie IDs, balances (unless the question requires one), other households' data, real names of other people, full transaction history.

**Gateway checks on every call:** schema validation, tool allowlist, maximum 3 tool calls per request, handles mapped back server-side, and all amounts recomputed from the ledger before showing a proposal.

Check the model host's terms for how prompts are used; free and paid tiers often differ on data use. If the model is slow, rate-limited or unset, the assistant answers from a deterministic template instead.

## Clearday Home device rules

A shared speaker can be overheard and voice is not identity, so the device only ever speaks household-level information.

- Speaks shared bill status and household weather only; never a personal balance, purchase, or forecast.
- Reports progress without names by default ("3 of 4 shares paid"); naming requires every roommate to opt in.
- Personal questions get "I've sent that to your phone."
- Cannot move money; it can only trigger a confirmation prompt on a member's phone.
- Never mentions hardship signals or help resources.
- Holds a hashed, revocable household token with read-only scope; no Nessie, model, or ElevenLabs keys on the device.
- Quiet hours and announcement types are set in the app.

**On-device AI (Gemma)**

- The narrator receives only the household summary from `/api/device/summary`; it never receives personal data.
- For voice questions, speech-to-text and the household-or-personal check both run on the device; personal questions are never sent to the backend or any cloud service.
- If the model fails or is unsure, the device defaults to treating the question as personal and sends a phone notification instead.
- Narrator output is checked against the summary before speaking: any dollar figure or name not in the summary is dropped and the template version is used.

## Legal considerations

None of this blocks the hackathon build, which runs entirely in Nessie's sandbox; it is the landscape to show judges you understand a real launch. This is not legal advice.

| Area | What applies to a real launch | Clearday's approach |
| --- | --- | --- |
| Money transmission | Moving money between people generally needs state licenses or a licensed bank partner | Run on top of a bank partner; Clearday never holds funds |
| P2P payments | Electronic fund transfer rules (Regulation E) include error resolution; CFPB oversees large payment apps | Dispute flow plus bank-partner error handling |
| Identity and fraud | KYC and anti-money-laundering programs | Handled by the bank partner |
| Financial privacy and security | Federal financial privacy rules (e.g. Gramm-Leach-Bliley) and state breach notification laws, including North Carolina's | Data minimization, encryption, private-by-default feed |
| Forecasts and suggestions | Claims must not mislead | Label forecasts as estimates; show ranges |
| Investment projections | Personalized investment advice can require adviser registration | Future view is educational: generic index-fund ranges, visible assumptions, labeled hypothetical |
| Reminders | Collection-style pressure tactics are risky | Friendly, non-threatening reminders between members |
| Bank-side hardship view | Using forecasts for credit decisions raises fair-lending issues | Support outreach only, never credit decisions |

## Help panel guardrails

The help panel gives general information and referrals only; it never interprets a user's specific legal situation, which would risk the unauthorized practice of law.

**Triggers (private to the user):** rent share forecast unpayable 2 cycles in a row, utility bill overdue, 2 or more overdraft fees in 30 days, or a charge from a known debt collector.

**Rules**

- Opt-in, shown only to the user, never in the feed, to roommates, or on Clearday Home
- Explicit consent before any data is shared with a third party
- No referral fees or paid placements
- Disclaimer on every screen: "General information, not legal advice"
- The model is instructed to route legal questions to the panel, not answer them

**North Carolina resources to verify before the demo** (names from memory; confirm current links, phone numbers, and eligibility on each official site)

- [ ] Legal Aid of North Carolina
- [ ] LawHelpNC.org
- [ ] North Carolina Pro Bono Resource Center
- [ ] NC 211 for rent and utility assistance
- [ ] VITA free tax preparation sites
- [ ] CFPB complaint portal
- [ ] Federal and NC energy bill assistance programs

## Rules for the new features

| Feature | Rule |
| --- | --- |
| Multiple accounts | Account numbers never leave the backend; the app shows nicknames and the last 4 digits only |
| Receipts | Images are deleted after item extraction; only items, prices, merchant, and date are kept; receipt text is untrusted data |
| Price memory | Compares only the user's own and their household's receipts, never other households' |
| Weekly recap | Script built from the household summary only; no news or outside claims; transcript always available |
| Analyst view | Synthetic households only in the demo; segments under 20 households are hidden; never used for credit decisions |
| Future view | Educational ranges with visible assumptions; no specific securities or personalized advice |
| Capital One styling | Palette inspiration only; no logos, wordmarks, or implied official affiliation |
| Café events | Not built; if shown in the pitch, labeled "concept" with no real offers or dates |
