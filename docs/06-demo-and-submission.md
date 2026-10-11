# Demo and Submission

## 2-minute demo script

The same script works for the video and each judge visit; the pop on both screens and the dome is the moment everything builds toward.

| Time | Show | Say |
| --- | --- | --- |
| 0:00 to 0:15 | Laptop A on the sky | "Roommates fight about money more than anything. Venmo made splitting social but public, and banks only show what you already spent. This is Clearday." |
| 0:15 to 0:35 | Priya's sky: her rent bubble in storm colors; open her forecast | "Each bill is a bubble. Our Monte Carlo forecast, built on Capital One's Nessie data, says Priya has a [read the chance shown on her forecast]% chance of coming up short before rent." (Say the number the app shows at demo time; don't memorize one.) |
| 0:35 to 0:55 | Type "split last night's pizza with Jake" | "Gemma, Google's open model, finds the purchase through narrow, scoped tools; the server computes the split, I confirm, and Jake gets a request bubble." |
| 0:55 to 1:20 | Laptop B (Jake) pays; share fills on both screens | "Jake pays through a Nessie transfer, and his share fills live for everyone." |
| 1:20 to 1:40 | Last share paid; bubble pops on both laptops; dome glows and announces | "When rent is covered, it pops for the whole household, and Clearday Home tells the apartment, with an ElevenLabs voice, without ever saying anyone's balance." |
| 1:40 to 2:00 | Feed, help panel, backtest number | "The feed celebrates without amounts, users at risk get private links to free NC legal aid, and our forecast landed within its range X% of the time in backtesting." |

In the video, show the Nessie, ElevenLabs, and Tiger Data names on screen at least once each.

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
- [ ] GitHub link to a public repo with a README
- [ ] Demo video 2 minutes or less
- [ ] Commit Fellowship supplemental form submitted

**Judging day**

- [ ] Find the assigned table on Devpost's Tables tab by 11:00 AM
- [ ] Two laptops, Clearday Home, chargers, phone hotspot, and power strip at the table
- [ ] Demo data reset script ready so every judge sees a fresh run
- [ ] At least one teammate at the table from 12:00 to 1:30 PM (a missing team scores 0 from that judge)
- [ ] Closing ceremony at 3:00 PM, Pauli Murray (Hamilton) Hall 100

**After the event**

- [ ] Publish the build story on DEV for the writing challenge
