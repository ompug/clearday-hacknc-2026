# Clearday: Project Proposal & Build Kit

HackNC 2026 · Oct 10, 2026 · @Om

## Overview

Clearday is a social money app for roommates and friend groups, built on Capital One's Nessie API, where upcoming bills float as glossy Frutiger Aero bubbles you pop when they're paid. Shared expenses split fairly through a real ledger and update live for everyone. A probabilistic "money weather" forecast warns of tight weeks before they happen, and a kitchen-counter companion, Clearday Home, brings household updates to life with an ElevenLabs voice.

**Pitch line:** "Venmo made splitting money social but made your transactions public and did nothing to help you plan. Clearday is private by default, predicts trouble before it happens, and celebrates every bill your household clears."

**Submission deadline:** Devpost by 10:00 AM EST, Sunday, October 11, with a GitHub link and a demo video of 2 minutes or less.

## Problem

Shared money is the most common source of friction between roommates, and today's tools only handle half of it.

- **Splitting is fragile.** Itemized dinners, partial payments, and one payment covering several debts break simple even-split tools, so people track it in their heads or a group chat.
- **P2P apps overshare.** Venmo-style feeds have historically shown transactions publicly by default, exposing who paid whom and for what.
- **Banking apps look backward.** They show what you already spent. Few tell you a tight week is coming, and none account for your share of household bills that haven't posted yet.
- **Budgeting feels like a chore.** Students avoid tools that feel like spreadsheets, so problems surface as overdraft fees or late rent.
- **Help arrives too late.** People at risk of eviction or utility shutoff often don't know free legal aid and assistance programs exist until a crisis.

## Solution

Clearday combines a shared ledger, a forecasting engine, and a calm Frutiger Aero interface into one app, with a physical companion for the home.

| Feature | What the user sees | What powers it | Tier |
| --- | --- | --- | --- |
| The sky | Upcoming bills float as glossy bubbles; height = how soon it's due, color = whether the forecast says you can cover it | Nessie bills + forecast engine | MVP |
| Shared bubbles | Rent, utilities, and group purchases live on every roommate's screen; each share fills in live as it's paid, and the bubble pops for everyone when covered | Ledger + Nessie transfers + WebSockets | MVP |
| Multiple accounts | Checking, savings, and a credit card per person, combined in one sky | Several Nessie accounts per customer | MVP |
| Income and needs vs. wants | Tracks paychecks and separates essentials from extras; shows how the forecast improves if extras drop | Forecast engine + category rules | MVP |
| Money weather | "70% chance of a tight week before rent" for the next 30 days | Monte Carlo simulation over Nessie history | MVP |
| Natural-language splits | "Split last night's pizza with Jake and Priya" finds the purchase and sends request bubbles | Gemini function calling over scoped tools | Stretch |
| Receipt itemizing and price memory | Snap a receipt; items are identified, split, and remembered, so Clearday can say "eggs were $0.60 cheaper at Harris Teeter last week" | Gemini vision + item price history | Stretch |
| Smart suggestions | Safe-to-spend, what-if checks, duplicate household subscriptions, reimbursement nudges | Forecast engine + recurring-charge detection | Stretch |
| Clearday Home | A glass globe that shows household status, announces cleared bills, and runs its own small AI model to write briefings and screen questions | Arduino UNO Q + local Gemma + ElevenLabs | MVP lights; stretch AI |
| Weekly recap episode | A 60-second, two-voice audio recap of the household's week, with a transcript | Gemini script from summaries + ElevenLabs | Stretch |
| Analyst view (demo) | Anonymized view of which customer segments are heading toward hardship, so a bank can offer help early | Forecast run over synthetic households | Stretch |
| Future view | Educational range of what steady surplus could grow to over 10 years, with assumptions shown | Projection with stated return ranges | Stretch |
| Help panel | Private, opt-in links to free legal aid, assistance, and Capital One Café money coaching | Forecast triggers + vetted resource list | Stretch |
| Private feed | Celebrations without amounts | Ledger events, privacy filter | Stretch |

Every screen targets WCAG AA contrast and includes a list view, keyboard navigation, a reduced-motion mode, adjustable text size, and transcripts for all audio. Clustering keeps the sky to about 7 full-size bubbles.

## How Clearday differs

Clearday is the only one of these that looks forward, understands shared obligations, and keeps amounts private.

| Capability | Venmo | Splitwise | Typical banking app | Clearday |
| --- | --- | --- | --- | --- |
| Moves money between people | Yes | No (tracks only) | Sometimes (e.g. Zelle) | Yes, via bank partner (Nessie in demo) |
| Itemized and partial-payment ledger | No | Yes | No | Yes, with receipt scanning |
| Feed private by default | Historically no | No feed | No feed | Yes, celebrations without amounts |
| Forecasts upcoming shortfalls | No | No | Rarely | Yes, probabilistic money weather |
| Counts your share of household bills | No | Partly | No | Yes, in safe-to-spend |
| Connects users to free legal and financial help | No | No | Rarely | Yes, private and opt-in |
| Physical home companion | No | No | No | Yes, Clearday Home |

Competitor details are from general knowledge; confirm any you cite in the pitch.

## Target users

The primary user is a college student or young adult sharing a household; the secondary user is the bank that serves them.

- **Roommates and shared households:** split rent, utilities, and groceries without awkward reminders.
- **Friend groups:** dinners, trips, and events with itemized splits.
- **Students living paycheck to paycheck:** forecasting and safe-to-spend prevent overdrafts and late rent.
- **Low-income users at risk of hardship:** private referrals to free legal aid and assistance programs.
- **Banks (pitch to Capital One):** an anonymized hardship view lets the bank offer help before customers fall behind. Used only for support outreach, never for credit decisions.

**Demo personas** (seeded in Nessie): three roommates in Apartment 4B, each with a paycheck, rent share, utilities, subscriptions, and one planted anomaly.

## Track and prize strategy

Clearday enters 8 tracks where each sponsor does real work, plus 2 optional ones if time allows.

| Track | Prize | How Clearday qualifies | Priority |
| --- | --- | --- | --- |
| General (required) | AirPods 4 / camera / Nespresso for 1st | The whole product | Core |
| Capital One: Best Use of Nessie | $250 gift card per member | Customers, accounts, purchases, bills, deposits, transfers drive the ledger and forecast | Core |
| Best Use of Gemini API | MLH swag | Function-calling splits, receipt itemizing with price memory, weekly recap scripts, plain-English explanations | Core |
| Best Use of ElevenLabs | Wireless earbuds | Clearday Home announcements, two-voice weekly recap episode, transcripts for accessibility | Core |
| Best Use of Tiger Data | Stream Deck Mini | Transaction time-series, continuous aggregates for the forecast, cohort rollups for the analyst view | Core |
| Community | $70 GoHeels gift card | Shared household finances plus legal aid referrals | Core |
| Best .Tech Domain | Mic + 10-year domain | Host at clearday.tech or a fallback .tech name; claim the free MLH .tech code at the event | Easy |
| Commit Fellowship | Interview + book | Working prototype with a real problem; submit the supplemental form | Easy |
| DEV Writing Challenge | $100 | Post the build story after the event | Post-event |
| Best iMessage Agent (Photon) | $400 + credits | Optional group-chat agent: "split the groceries" | Stretch only |

Skip Solana, Snowflake (duplicates Gemini and Tiger Data), Frutiger Aero (requires a sustainability angle), and Ig Turing. Mention every sponsor technology by name in the video and at the table.

## Scope

The MVP is the sky, live shared bubbles, and an income-aware forecast; each new idea was kept only if it strengthens the demo or a prize, and everything else moved to the roadmap.

**MVP (must ship)**

- Seed data for three roommates, each with checking, savings, and a credit card in Nessie
- Sync from Nessie into Tiger Data, cached for the demo
- Ledger with even, custom, and itemized splits; integer cents; payment allocation
- The sky: bill bubbles, clustering, pop-to-pay, list view
- Shared bubbles with real-time updates across two devices
- Money weather: 30-day forecast that tracks income and separates needs from wants
- Capital One-inspired palette and accessibility baseline (contrast, keyboard, reduced motion, text size)
- Clearday Home: globe color and celebration on bill cleared
- Deployed on a .tech domain

**Stretch (in priority order)**

1. Gemini natural-language splits
2. Receipt itemizing with price memory ("cheaper last time")
3. ElevenLabs announcements and briefing on Clearday Home, with on-screen transcripts
4. Gemma on Clearday Home as local narrator (template fallback)
5. Anomaly and duplicate-subscription detection
6. Analyst view over synthetic households
7. Weekly recap episode
8. Future view (educational long-term projection)
9. Help panel with NC resources and Café money coaching
10. Private feed
11. Gemma privacy guard for voice questions, with local speech-to-text

**Roadmap (pitch only, not built)**

- Linking accounts at other banks through open-banking data connections
- Groups beyond households: student orgs and small teams itemizing costs and finding savings
- Café community events and perks with Capital One brands (shown at most as a labeled concept mockup)
- Financial news segments in the recap, once sourcing and accuracy can be guaranteed
- A full analyst product for banks and hobbyists, built on the same forecast engine
- Real money movement, KYC, and licensing through a bank partner

## Success criteria

Clearday is ready when a judge can watch a roommate pay on one laptop and see the bubble pop on a second laptop and on Clearday Home within 2 seconds.

| Judging criterion | What we show | Answer ready for Q&A |
| --- | --- | --- |
| Application/Impact | Shared bills, overdraft prevention, private legal aid referrals | Who uses it, and how it reaches people at risk |
| Functionality/Quality | Bug-free core loop, polished Aero UI, list view | What happens when Nessie is slow (cache) |
| Creativity | Bubbles as bills, money weather, physical home companion | Why skeuomorphic glass makes money less stressful |
| Technical Complexity | Ledger, Monte Carlo forecast with backtest accuracy, real-time sync, hardware | How the forecast works and how accurate it is |
| Presentation | 2-minute demo, then future roadmap | Security model for Gemini and the shared device |

- [ ] Core loop works end to end on two devices
- [ ] Forecast backtest accuracy measured on held-out month
- [ ] Every sponsor technology visible in the video
- [ ] Demo video under 2 minutes, recorded by 8:00 AM Sunday
- [ ] Devpost submitted by 10:00 AM Sunday with GitHub link

## Risks and mitigations

The biggest risk is scope: cut from the bottom of the stretch list, never from the core loop.

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Too many features for one night | High | Strict build order; stretch items only after MVP checklist is done |
| Nessie slow, down, or returns empty data | Medium | Seed early; cache all Nessie data in Tiger Data; demo reads from cache |
| Arduino UNO Q audio setup fails | Medium | LEDs only on the device; play ElevenLabs audio from a laptop beside it |
| Venue Wi-Fi unreliable at demo | Medium | Phone hotspot; run backend locally with cached data as backup |
| Gemini returns wrong split amounts | Medium | Server re-validates every amount against the ledger; user confirms before anything moves |
| Prompt injection via memos or merchant names | Low | Tool results marked as untrusted data; no chained actions; no money movement by the model |
| Demo video not finished | Medium | Record a rough version by 8:00 AM, then improve if time allows |
| Team member missing at judging | Low | At least one person at the table 12:00 to 1:30 PM, or the judge scores 0 |

## Companion documents

- [Technical Spec](02-technical-spec.md): architecture, data model, Nessie integration, ledger rules, forecast engine, API
- [Security and Privacy](03-security-and-privacy.md): Gemini data-access rules, device rules, legal notes, help panel guardrails
- [Clearday Home Hardware](04-clearday-home-hardware.md): parts, device states, software layout, fallbacks
- [Build Plan](05-build-plan.md): roles, phased checklist, cut lines
- [Demo and Submission](06-demo-and-submission.md): demo script, Q&A prep, submission checklist
