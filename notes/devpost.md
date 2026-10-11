# Clearday: Devpost draft

## Inspiration
Venmo made splitting social but public, and banking apps only show what you already spent. We wanted a private, forward-looking tool that makes shared bills feel calm.

## What it does
Bills float as glossy bubbles. Roommates pop their share, paying through a Nessie transfer into a real ledger, and the bubble fills and pops live on everyone's screen and on Clearday Home, a bulb-and-matrix companion that announces cleared bills in an ElevenLabs voice without saying anyone's balance. A Monte Carlo money-weather forecast flags tight weeks. You can type "split last night's pizza with Jake and Priya" and Gemma finds the purchase while the server computes the amounts. Also built: receipt itemizing, price memory, anomaly detection, an amount-free feed, weekly recap, a hypothetical Future view, a synthetic analyst view, and a private NC help panel.

## How we built it
Next.js and Tailwind front end, FastAPI and python-socketio back end, local TimescaleDB, and Nessie for accounts and transfers (mirrored into a database cache). The ledger math (`splits.py`) is real, tested, and works in integer cents with largest-remainder allocation. The forecast, anomaly detection and backtest are our stats teammate's real models; the remaining analytics modules are stubs behind the same contracts. Clearday Home runs a Linux-side Python controller that drives a bulb through Home Assistant, plus an LED matrix sketch.

## Challenges
Nessie silently truncates non-integer amounts and has no transfer payee, so we keep exact cents in our ledger and mirror whole dollars plus a payee-side deposit. Keeping the model safe meant a strict six-tool contract and server-side amount recomputation. Live sync and a deterministic demo reset took iteration.

## Accomplishments
A polished core loop verified by a live two-browser E2E and a scripted rehearsal of the whole demo. An accessibility baseline we audited at 100%, 200% zoom and phone width with axe and contrast checks.

## What we learned
Privacy and accessibility constraints made the design better, not smaller. Treating the model as a proposer, never an authority over money, kept things simple.

## What's next
Real forecast and categorization modules from our stats teammate, a bank-side hardship view, other-bank linking through open banking, and native apps.

## Built with
Next.js, TypeScript, Tailwind CSS, Framer Motion, Recharts, FastAPI, python-socketio, pandas, numpy, TimescaleDB, Nessie API, ElevenLabs, Gemma, Home Assistant, Arduino UNO Q, Playwright, uv.

## Tracks (verify before opting in)
- General: yes.
- Nessie: yes; accounts, purchases, bills, deposits and transfers drive the ledger.
- ElevenLabs: yes; announcements and recap with transcripts.
- Community: yes (shared household finance plus legal-aid referrals).
- Commit Fellowship: submit the supplemental form.
- UNSURE, Tiger Data: we use TimescaleDB locally; Tiger Cloud is only an optional backup and we hosted nothing there. Opt in only if the team used Tiger Cloud, and don't claim it otherwise.
- DEV Writing Challenge: post-event only.

## TODO for the user
- [ ] Record the demo video (2 min or less; show Nessie, ElevenLabs and Tiger Data names if opting in)
- [ ] Teammate names and Devpost accounts added to the project
- [ ] Pick the General track (or Beginner)
- [ ] Add the public GitHub link and confirm the repo is public with this README
- [ ] Commit Fellowship supplemental form
- [ ] Hardware: confirm Clearday Home (UNO Q, bulb, matrix, audio) works at the table; bring laptops, chargers, hotspot, power strip
- [ ] Tables tab by 11:00 AM; a teammate at the table 12:00 to 1:30 PM
- [ ] Publish the DEV build story afterward

## System design visuals
- docs/img/design/system-architecture.png
- docs/img/design/hardware-today.png
- docs/img/design/hardware-vision.png
- docs/img/design/data-flow-pop.png
