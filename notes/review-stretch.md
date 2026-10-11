# Security and privacy review: stretch features (6b63599..a3f4ae6)

Scope: `/analyst`, `/recap`, `/future`, help panel, `/feed`, refined `safe_reply` (api/ai/gateway.py).
Read-only review. `safe_reply` was probed with crafted inputs; the new pages were run through
`scripts/shot_page.py` (axe, AA contrast, 100%, 200% and phone width) against the running dev stack.

## Ranked findings

| # | Sev | Where | Finding | Fix |
| - | --- | ----- | ------- | --- |
| 1 | High | api/ai/gateway.py:184, 198 | `safe_reply` passes model-sourced amounts: `"Each pays 36."`, `"Your share is ３６."` (fullwidth), `"Each owes ＄３６"`, `"That's ¥36 each."`, `"36 EUR each"`, `"USD 36"`, `"It costs 36 cents"`, `"Pay 12. 50 each"`, `"1 2 0 0 total"`, `"⅓"`, `"²⁵"`, `"thirty-six dollars each"` all come back unchanged. `\d` is Unicode-aware but the currency set is only `$€£`, and `SMALL_COUNT` allows any 1-2 digit run. | NFKC-normalise first; reject any `\p{Sc}` currency symbol, any `No`-category char (fractions, superscripts) and number words next to `dollar/cent/usd/eur/bucks`; allow only digits 1-9 directly followed by a whitelisted count noun (`ways`, `bills`, `roommates`, `people`). |
| 2 | High | api/ai/gateway.py:174 | Links and markup slip through: `[pay here](javascript:alert(1))`, `Visit evil.ru now` (TLD list is 7 entries), fullwidth `ｅｖｉｌ．ｃｏｍ` and `ＨＴＴＰＳ：//x`. No XSS today because SplitAssistant.tsx:142 renders text, but the rule is "reject links". | NFKC-normalise before `UNSAFE_REPLY`; reject `\w:` schemes (`javascript:`, `mailto:`, `data:`), `](`, and any `\w\.[a-z]{2,}\b` domain shape. |
| 3 | Med | api/feed.py:31; api/expenses.py:165; api/payments.py:176 | Feed `subject_label` is user-typed text, so `"Pizza $36"` or `"Rent 1200"` puts an amount in the feed (and in the `feed.created` event). Nothing strips digits or currency from feed labels. | In `feed.recent` (and the realtime emit) drop labels containing `\p{Sc}` or digits (fall back to "a bill"), or reject such labels at expense creation. |
| 4 | Med | api/feed.py:30; CODING_STANDARDS.md:23 | The feed returns `actor_display_name`. CODING_STANDARDS rule 6 says "No amounts **or names** in the feed" (check: the feed schema has no name fields), while docs/02 and CLAUDE.md allow names in the in-app feed. Docs conflict. | Ask the user which wins; if the standard holds, return "A roommate"/"You" instead of display names. |
| 5 | Low | web/components/more/RecapScreen.tsx:31 (same pattern AnalystScreen.tsx:25, FeedScreen.tsx:49, FutureScreen.tsx:70, PageShell.tsx:74) | Loading text sits outside a glass card: measured **1.54:1** contrast for "Loading the recap…" (seen on recap because voice synthesis makes it slow; axe and AA otherwise pass on every page at 100%, 200% and phone). | Wrap loading paragraphs in the `glass` card (or use `text-white` on the navy page) like the error states. |
| 6 | Low | web/components/more/FeedScreen.tsx:59, 64 | `aria-live="polite"` on the whole list with index-based keys: each new event shifts every key, remounting the list so screen readers can re-read all items. | Key on a stable value (`created_at` + `type` + actor, or add an event id) and announce only the newest event in a separate `role="status"` node. |
| 7 | Low | api/analyst.py:72-75 | Small-segment suppression is server-side (good, analyst.py:69 plus cohorts.segment_rates), but `total_households` minus the visible counts reveals the size of a hidden segment when only one is hidden (differencing). Synthetic data, so low impact. | Report `total_households` as the sum of shown segments, or drop it; never show a remainder. |
| 8 | Low | api/routes/voice.py:27-29 | `/api/voice/audio/{hash}` checks for a session but not the household. Recap text is counts only and the hash is a content hash, so another household could probe which count combinations exist. | Bind cached audio to the caller's household (store `household_id` with the hash) or include the household in the hash key and check it. |
| 9 | Low | api/routes/feed.py:15, recap.py:15, future.py:15 | Only `/api/help` sets `Cache-Control: private, no-store`; feed, recap and future return per-household or per-user data with default caching. | Set `private, no-store` on these routes too (or in a middleware for `/api/*`). |
| 10 | Low | api/help.py:93, 97-99 | Help triggers branch on merchant text (`ILIKE '%overdraft%'`, collector names), which CODING_STANDARDS rule 9 says untrusted text must not do; a merchant named "overdraft" shows the panel. Collector query also counts non-posted rows. | Accept as display-only (document the exception) or key on Nessie category/fee type; add `status = 'posted'` to the collector query. |
| 11 | Info | web/components/more/FutureScreen.tsx:53-62 | Future inputs report errors via `role="alert"` but fields lack `aria-invalid`/`aria-describedby`, and the updated range isn't announced. | Link the error to the field and wrap the headline range in `aria-live="polite"`. |

## Rules that hold

- **Feed:** `feed_events` stores no amount column; the query is scoped to `user.household_id` from the session (only user-typed labels can carry amounts, see #3).
- **Analyst:** reads only `analytics.cohorts.generate` synthetic households; segments under 20 are dropped server-side in two places; the response says `synthetic: true`.
- **Future:** the API returns `label: "Hypothetical, not investment advice"`; the UI shows it as a badge and in the table heading; rates are capped 0-15% and the what-if amount is range-checked server-side (NaN and inf rejected).
- **Recap:** built from `sky.household_status` plus feed counts by type; no names, labels or amounts; the transcript is always rendered and audio is optional.
- **Access:** every new route takes identity from `current_user` (session cookie); no route accepts a user or household ID, so there is no IDOR path.
- **Data leaks:** no new payload carries Nessie IDs, account numbers or `nessie_*` fields.
- **XSS:** model replies, feed labels and recap text render as React text; the only `dangerouslySetInnerHTML` is the static preferences script in app/layout.tsx:36. Help links are a server-side constant list with `rel="noopener noreferrer"`.
- **Help panel:** private (`no-store`), opt-in button before links, generic reasons, disclaimer shown.
- **A11y:** axe found no violations on /analyst, /recap, /future, /feed at 100%, 200% and phone width; all text at or above AA once loaded; one h1 per page; icons are `aria-hidden`; the scroll region is focusable.

## Secrets in history

Scanned all 67 commits (trees and messages) for every value of 8+ characters in the gitignored secret
files (`api/.env`, `openrouter_api_key.txt`, `tiger-cloud-hacknc-credentials.env`, plus `web/.env.local`).
**No secret value is in history**: `NESSIE_API_KEY`, `ELEVENLABS_API_KEY`, `LLM_API_KEY`, `SESSION_SECRET`,
`DATABASE_URL`, `TIMESCALE_SERVICE_URL`, `PGPASSWORD`, `PGHOST` and the OpenRouter key all have 0 hits. Hits
for `NESSIE_BASE_URL`, `ELEVENLABS_MODEL_ID`, `PGUSER`, `NEXT_PUBLIC_API_BASE_URL` and `DATABASE_URL_LOCAL`
(the local podman default in api/config.py and api/.env.example) are public or dev-only values. No secret
file is tracked.

`scripts/check_secrets.sh` gaps (low):
- scripts/check_secrets.sh:47 — the key regex skips `DATABASE_URL_LOCAL` and other `DATABASE_URL_*` names; fix: match `DATABASE_URL[A-Z_]*`.
- scripts/check_secrets.sh:16 — only root and `api/` are searched (`-maxdepth 1`), so `device/.env` (device token) or `web/.env.local` would not be sources; fix: add `device` and `web` to the find roots.
- scripts/check_secrets.sh:58 — only staged file contents are scanned, not the commit message; fix: add a `commit-msg` hook running the same pattern grep.
