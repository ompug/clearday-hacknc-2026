# Build Plan

## Roles

With two people, the CS student builds every piece of code with Claude Code, and the stats major owns the math, the data, the hardware build, and the numbers judges will ask about.

| Role | Owns | Name |
| --- | --- | --- |
| CS student (Claude Code) | Frontend and Aero UI, backend and API, Nessie seed and sync, ledger, Socket.IO, AI gateway, ElevenLabs, Clearday Home software, deploy |  |
| Stats major | Forecast engine, backtest, anomaly and recurring-charge detection, seed data design, hardware shopping and assembly, demo video, Q&A on methodology |  |

**Stats major's deliverables, in order**

1. **Seed data design (first 1 to 2 hours).** A spreadsheet or JSON spec of each roommate's realistic finances: paycheck amounts and timing, rent shares, utility ranges, category spending distributions, the planted duplicate subscription, anomaly, and tight week. The CS student turns this into the Nessie seed script.
2. **Forecast engine.** A standalone Python module, `forecast.py`, built in a notebook with pandas and NumPy against a CSV export of the seeded data. Contract: `forecast(transactions, scheduled_events, start_balance, horizon_days=30, n_paths=1000)` returns P10/P50/P90 balance per day, probability of falling below threshold before each bill, safe-to-spend, and top variance-driving categories as JSON.
3. **Recurring-charge and anomaly detection.** `detect_recurring(transactions)` and `detect_anomalies(transactions)` using robust statistics (median and MAD rather than mean and standard deviation, so one big charge doesn't hide others).
4. **Backtest.** Forecast the held-out 30 days; report band coverage (share of actual days inside P10 to P90) and median absolute error. One clean chart of forecast band vs. actual for the pitch.
5. **Hardware run and assembly.** Buy the parts on the Clearday Home Hardware tab and assemble the dome while code is in progress.
6. **Pitch.** Owns the forecast and backtest answers in Q&A, and records and edits the demo video.

The CS student calls these functions from the backend, so the stats major never needs to touch the web code. Agree on the JSON shapes in the first 30 minutes.

**Added to the stats major's list (all pure Python, no web code)**

- `categorize.py`: need or want tag per category and an income detector (amount, cadence, variability)
- Seed data with checking, savings, and a credit card per roommate, plus 3 to 4 sample grocery receipts as item lists for price memory
- `prices.py`: normalized item matching and unit-price comparison across stores and dates
- `cohorts.py`: about 200 synthetic households in a few segments, plus segment-level hardship rates for the analyst view
- `future.py`: 10-year low, middle, and high projection ranges from median monthly surplus
- Bench test of Gemma speed on the UNO Q, timed and written down, during the hardware build

**Scope for a team of two:** Photon is cut; everything beyond the MVP follows the stretch order in the Proposal and the Cut lines below.

## Phased checklist

Phase 1 must work end to end before anyone starts Phase 3; target times assume work started Saturday evening, so shift them to match your start.

**Phase 1: Foundation (by about 11:00 PM Saturday)**

- [ ] Repo, environment variables, and deploy pipeline set up; .tech domain claimed
- [ ] Nessie key verified; seed script creates three roommates with checking, savings, and credit card accounts and 60 days of data
- [ ] Tiger Data database with ledger and account tables and the transaction hypertable
- [ ] Sync job mirrors Nessie into the database
- [ ] Stubs for every analytics function return correctly shaped fake data
- [ ] Sky renders bill bubbles from real data with the palette and list view; pop-to-pay works for one user
- [ ] UNO Q joins the hotspot and changes the bulb color on command

**Phase 2: Shared, live, and accessible (by about 3:00 AM Sunday)**

- [ ] Shared expenses with even and custom splits; payment allocation
- [ ] Socket.IO rooms; shared bubble fills live on a second device
- [ ] Clearday Home reacts to `share.updated` and `bubble.popped`
- [ ] Real forecast, income detection, and needs-vs-wants swapped in from the analytics branch
- [ ] Accessibility pass: contrast, keyboard, reduced motion, text size, accessible names

**Phase 3: Intelligence and voice (by about 6:30 AM Sunday)**

- [ ] Gemini natural-language split through the AI gateway
- [ ] Receipt itemizing with price memory
- [ ] ElevenLabs announcement and briefing, with transcripts
- [ ] Gemma narrator on the device if the benchmark passed; templates otherwise
- [ ] Anomaly and duplicate-subscription detection
- [ ] Backtest number shown in the app
- [ ] Analyst view, weekly recap, and Future view only if all of the above are done

**Phase 4: Ship (by 10:00 AM Sunday)**

- [ ] Code freeze at 7:30 AM; only bug fixes after
- [ ] Lighthouse or axe accessibility audit, fix anything critical
- [ ] Record demo video by 8:00 AM; final version by 9:00 AM
- [ ] README with setup, architecture, sponsor technologies, and accessibility features
- [ ] Devpost submitted by 9:30 AM, with tracks selected and Commit form sent

## Cut lines

If a phase runs late, drop features in this order and keep going; never cut the live shared bubble, the forecast, or the accessibility baseline.

1. Gemma privacy guard and voice questions
2. Café concept mockup (pitch slide only)
3. Private feed
4. Help panel (keep as a slide and Q&A answer)
5. Future view
6. Weekly recap episode
7. Analyst view (keep as a pitch slide)
8. Gemma narrator (use templates)
9. Anomaly detection (keep duplicate subscriptions)
10. Price memory (keep receipt itemizing)
11. ElevenLabs on the device (play from laptop)
12. Gemini natural-language split (keep manual split UI)
