# Demo and Submission

## 3-minute demo script (mobile-first)

Setup: the laptop runs the API, web and DB locally, plus Clearday Home (`bash scripts/dev.sh device`: EcoSmart bulb via Home Assistant, laptop speaker). Roommates use phones at `/m` on the same Wi-Fi. No Arduino/UNO Q today (deferred); a laptop screen shows the same sky as a backup.

| Time | Show | Say |
| --- | --- | --- |
| 0:00 to 0:20 | Three phones (Maya, Jake, Priya) on the sky at `/m` | "Roommates fight about money more than anything. Venmo made splitting social but public. This is Clearday: every bill is a bubble, and the whole apartment sees the same sky." |
| 0:20 to 1:00 | Jake pops Rent on his phone; Maya's phone updates live; the bulb flashes and the laptop voice announces | "Jake pays his share through a Nessie transfer and pops the bubble. Everyone updates live, the bulb celebrates, and the ElevenLabs voice tells the apartment without saying anyone's balance." |
| 1:00 to 1:40 | Priya's phone: tight-week forecast | "Our Monte Carlo forecast says Priya's rent is [read the line under Rent on her forecast; seeded data reads "Almost certain"]. It counts her share of household bills." |
| 1:40 to 2:15 | Assistant: "split last night's pizza with Jake and Priya"; Find it, check shares, Confirm | "Gemma, Google's open model, finds the purchase through narrow, scoped tools. The server computes the split, I confirm, and they get a request bubble." |
| 2:15 to 2:35 | Receipt scan on the phone | "Scan a receipt and the items become a split; the image is deleted after extraction." |
| 2:35 to 3:00 | Show the hardware sketch/schematic, then toggle text size and reduced motion | "One household sharing its utilities, internet and subscriptions means fewer duplicate services and less waste; we don't measure that, it's just the nudge. Next is a custom Clearday Home PCB, schematic in progress, replacing today's laptop host. And accessibility is baseline: WCAG AA, list view, keyboard, reduced motion, transcripts." |

Be honest when asked: the forecast, backtest and several analytics modules are stubs returning deterministic data (the ledger math is real); the model is Gemma, not Gemini; everything is hosted locally on the laptop; the Arduino UNO Q build is deferred.

In the video, show the Nessie, ElevenLabs, and Tiger Data names on screen at least once each. Judge Q&A still applies; the 2-minute video cut keeps beats 1, 2, 4 and 6.

### Opening the mobile app (`/m`)

- **Recorded video (recommended):** on the laptop, open `http://localhost:3001/m` in Chrome, press F12, toggle device emulation (Ctrl+Shift+M) and pick a 390x844 phone (e.g. iPhone 12 Pro). Use one normal window for Jake and one incognito window for Maya, so each has its own session cookie; Jake pops Rent and Maya's sky updates live. Persona login (`/api/dev/login`) only answers loopback requests, so this is the only way to sign in as a persona for the video.
- **Real phone (same Wi-Fi):** browse to `http://<laptop-ip>:3001/m` (find the IP with `ip -4 addr` or `hostname -I`). Caveats: persona login is loopback-only, so a phone can't sign in as a persona; `web/.env.local` points the API at `http://localhost:8000`, which on a phone means the phone itself, so it would need `NEXT_PUBLIC_API_BASE_URL=http://<laptop-ip>:8000` plus `http://<laptop-ip>:3001` in the API's `web_origins`. Treat real phones as a stretch; emulation is what we record.
- A narrow viewport (640 px or less) opening `/` is sent to `/m`; the desktop routes stay as they are.

## Judge Q&A prep

Each judge gets 2 minutes of questions; keep answers to about 30 seconds and end on a concrete detail.

| Likely question | Short answer |
| --- | --- |
| How does the forecast work? | 1,000 simulated 30-day paths from scheduled events plus bootstrapped spending; P10 drives safe-to-spend. Backtest: X% of actual days inside the band. |
| Isn't giving an AI bank data risky? | The model never touches Nessie. It sees only fields a scoped tool returns, capped in rows and dates, and can't move money; the server re-checks every amount. |
| What if a payment doesn't match what's owed? | A ledger allocates it oldest first; underpayment leaves a partial share, overpayment becomes credit, and pending amounts recompute when they post. |
| How is this different from Venmo or Splitwise? | Private by default, forecasts shortfalls, and counts your share of household bills in safe-to-spend. |
| Could this launch for real? | On top of a bank partner like Capital One, which handles licensing, KYC, and money movement; Clearday is the experience and intelligence layer. |
| Why this visual style? | Skeuomorphic, glossy design makes money feel approachable; the list view and non-color cues keep it accessible. |
| What's next? | Bank-side hardship view for proactive support, long-term savings projections (educational only), and native apps. |
| What was hardest? | Pick a real story: reconciling pending amounts, real-time sync, or the hardware bridge. |

**Answers for the expanded features**

| Likely question | Short answer |
| --- | --- |
| Why run a model on the device? | Household questions are screened in the kitchen; personal ones never leave the house. Small models handle that classification well, with a template fallback. |
| Can it connect other banks? | The demo uses several Nessie accounts per person; real launches would link other banks through open-banking data connections. |
| How does price memory work? | The model reads receipt items, we normalize names and compare unit prices across your household's past receipts. |
| Who is the analyst view for? | Banks offering help before customers fall behind; it uses synthetic households, hides small segments, and is never for credit decisions. |
| How accessible is it? | WCAG AA contrast, keyboard and screen-reader support, reduced motion, text size, and transcripts for all audio. |

## Submission and judging-day checklist

Devpost closes at 10:00 AM EST Sunday with no extensions; submit early and keep editing until the deadline.

**Devpost**

- [ ] Every teammate has a Devpost account and is added to the project
- [ ] One submission only, started by one team member
- [ ] General track selected (or Beginner if more than half the team is new to hackathons)
- [ ] Tracks opted in: Nessie, ElevenLabs, Tiger Data, Community, Commit
- [ ] GitHub link to a public repo with a README (README.md written; confirm the repo is public)
- [ ] Demo video 2 minutes or less (cut from the 3-minute script)
- [ ] Commit Fellowship supplemental form submitted

**Judging day**

- [ ] Find the assigned table on Devpost's Tables tab by 11:00 AM
- [ ] Two laptops, Clearday Home, chargers, phone hotspot, and power strip at the table
- [x] Demo data reset script ready so every judge sees a fresh run (`uv run python -m scripts.reset_demo`)
- [ ] At least one teammate at the table from 12:00 to 1:30 PM (a missing team scores 0 from that judge)
- [ ] Closing ceremony at 3:00 PM, Pauli Murray (Hamilton) Hall 100

**After the event**

- [ ] Publish the build story on DEV for the writing challenge
