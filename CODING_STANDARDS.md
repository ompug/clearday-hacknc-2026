# Coding Standards

Checkable rules for every change. Sources: `CLAUDE.md` and `docs/03-security-and-privacy.md`; those win on conflict. Each rule ends with **Check:** how a reviewer verifies it.

## Money

1. **Integer cents everywhere.** Amounts are `int` cents in Python, TS and the database; Nessie dollars convert to cents only inside the Nessie client.
   **Check:** `bash scripts/check_money.sh` passes; DB amount columns are integer types; no `parseFloat`/`toFixed` on amounts outside display formatting.
2. **Largest-remainder rounding.** Splits sum exactly to the total; leftover cents go by largest remainder, ties broken by user ID.
   **Check:** a test asserts `sum(shares) == total` for an uneven split (e.g. 10000 / 3) and the tie-break order.
3. **Idempotent payments.** Every payment carries a client-generated idempotency key with a unique DB constraint.
   **Check:** migration has the unique constraint; a test posts the same key twice and gets one payment.

## Identity and secrets

4. **Identity from the session cookie or device token only.** User and household IDs are never read from request bodies, query params or model output.
   **Check:** grep handlers for `user_id`/`household_id` in request models; each comes from the auth dependency.
5. **External calls live in `api/` only.** Nessie, Gemini and ElevenLabs keys sit in `api/.env`; `web/` and `device/` call only our API.
   **Check:** `grep -rE "nessieisreal|generativelanguage|elevenlabs" web device` is empty; `bash scripts/check_secrets.sh` passes.

## Privacy

6. **No amounts or names in the feed or on Clearday Home.** The device reads only `/api/device/summary` and `/api/household/status` and speaks household-level progress without names by default ("3 of 4 shares paid").
   **Check:** feed and device payload schemas contain no amount or name fields; a test asserts the summary JSON has none.
7. **Accounts show nickname + last 4 only.** Nessie IDs and account numbers stay in the backend.
   **Check:** account response models expose `nickname` and `last4` only; grep API responses for `nessie_id`/`account_number`.
8. **New-feature rules hold.** Receipt images deleted after extraction; analyst view uses synthetic households and hides segments under 20; Future view labeled "Hypothetical, not investment advice"; recap uses household data only.
   **Check:** a test confirms the receipt file is gone after extraction; the label string is present in the Future view.

## AI and untrusted text

9. **Untrusted text is data.** Merchant names, memos and receipt text are wrapped as untrusted content in prompts and never select tools or actions.
   **Check:** every prompt builder wraps these fields in the untrusted-data wrapper; no code path branches on their content.
10. **Gemini tool contract.** Only the six contract tools, their field/row/date limits, max 3 tool calls per request, handles mapped back server-side, every amount recomputed from the ledger, user confirms in the UI.
    **Check:** gateway tests reject an unknown tool and a 4th call; tool outputs omit account numbers, Nessie IDs and real names.
11. **`ai_audit` logs fields and row counts, never values.**
    **Check:** the audit insert writes field names and counts only; a test asserts no amount or merchant string lands in the row.

## Accessibility (never cut)

12. **Bubbles are `<button>`s with accessible names**, and every state has an icon plus a text label.
    **Check:** axe/Lighthouse shows no name violations; state is readable with colors removed.
13. **Keyboard and focus.** Everything is reachable by Tab with a visible focus ring.
    **Check:** tab through the screen in a browser; screenshot the focus state.
14. **Motion.** `prefers-reduced-motion` and the in-app toggle both stop non-essential animation.
    **Check:** toggle on, confirm Framer Motion animations are skipped.
15. **Contrast and text size.** WCAG AA on glass; the text-size control and 200% zoom keep the layout usable. The list view is the screen-reader default; all audio has transcripts.
    **Check:** contrast checker on text over glass; screenshot at 200% zoom.
