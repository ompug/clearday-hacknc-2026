# Demo and Submission

## 1:50 demo script (mobile-first, video max 2:00)

Setup: laptop runs API, web and DB locally. Record in Chrome device emulation at `/m` (390x844): one normal window for Jake, one incognito for Maya, a third for Priya. Before recording: `uv run python -m scripts.reset_demo && bash scripts/dev.sh warm` (caches the voice audio, forecasts and warms the model; the assistant call in the video is still live). Clearday Home (`bash scripts/dev.sh device`) supplies the bulb and speaker. Narration pace is about 140 words per minute; the budgets total about 230 words, leaving 10 seconds of slack.

| Time | Words | Show | Say |
| --- | --- | --- | --- |
| 0:00 to 0:22 | 45 | Priya's phone: the Rent bubble in storm colors, then her 30-day forecast with the Rent line | "Roommates fight about money more than anything. Clearday turns every bill into a bubble the whole apartment sees. Our Monte Carlo forecast shows Priya's checking running tight before rent is due, so she hears it before it hurts." |
| 0:22 to 0:50 | 45 | Jake pops Rent; Maya's phone updates live; Priya pops the last share; bulb flashes, voice plays (transcript on screen) | "Jake pays through a Nessie transfer and pops the bubble. Maya's phone updates instantly. When the last share clears, the Clearday Home bulb celebrates and an ElevenLabs voice tells the apartment, with no names and no amounts." |
| 0:50 to 1:12 | 40 | Maya: "split last night's pizza with Jake and Priya", Find it, Confirm. If it takes over 4 s, the screen reads "Gemma is reading your purchases"; narrate over it | "I ask Gemma, Google's open model, in plain words. It finds the pizza through narrow tools, the server computes every cent, I confirm, and Jake gets a request bubble." |
| 1:12 to 1:24 | 25 | Receipt scan (only if time allows; otherwise skip the visuals and say the line over the pizza result) | "Or scan a receipt: items become a split, and the image is deleted after reading." |
| 1:24 to 1:38 | 30 | Forecast page: duplicate Spotify card | "Clearday spots duplicate subscriptions. One household sharing services means less waste; that is the nudge, not a measured claim." |
| 1:38 to 1:50 | 35 | `docs/img/design/hardware-vision.png`, then text-size and reduced-motion toggles | "Next is a custom Clearday Home board replacing the laptop. Accessibility is built in: WCAG AA, list view, keyboard, reduced motion and transcripts. Built on Nessie and ElevenLabs." |

Cut order if over time: receipt first, then the sustainability sentence, then the hardware line. Never cut the live pop, the forecast or accessibility. `bash scripts/dev.sh rehearse` walks these beats in the same order and prints per-beat timings.

Be honest when asked: the forecast, detection and backtest are the stats teammate's real models; categorize, prices, cohorts and future are still stubs, and the ledger math is real. The demo branch plants Priya's lower checking balance in our DB so the tight-week case shows; the model is Gemma, not Gemini; everything is hosted locally on the laptop; the Arduino UNO Q build is deferred.

In the video, show the Nessie and ElevenLabs names on screen at least once each. Judge Q&A still applies.

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
- [ ] Tracks opted in: Nessie, ElevenLabs, Community, Commit
- [ ] GitHub link to a public repo with a README (README.md written; confirm the repo is public)
- [ ] Demo video 2 minutes or less (the 1:50 script above)
- [ ] Commit Fellowship supplemental form submitted

**Judging day**

- [ ] Find the assigned table on Devpost's Tables tab by 11:00 AM
- [ ] Two laptops, Clearday Home, chargers, phone hotspot, and power strip at the table
- [x] Demo data reset script ready so every judge sees a fresh run (`uv run python -m scripts.reset_demo`)
- [ ] At least one teammate at the table from 12:00 to 1:30 PM (a missing team scores 0 from that judge)
- [ ] Closing ceremony at 3:00 PM, Pauli Murray (Hamilton) Hall 100

**After the event**

- [ ] Publish the build story on DEV for the writing challenge
