# Clearday Home Hardware

## Product requirements

Clearday Home is a glowing glass globe that shows household money status and announces cleared bills, built entirely from parts sold in Walmart, Target, Best Buy, Home Depot, or Lowe's, with no soldering or wiring.

The design swaps hobby LEDs for a Wi-Fi color smart bulb, which the UNO Q controls over the local network, and swaps an arcade button for a USB numeric keypad.

| ID | Requirement | Priority |
| --- | --- | --- |
| FR1 | Globe color reflects household status within 2 seconds of a change in the app | Must |
| FR2 | Globe plays a celebration (color burst) when a shared bill is fully paid | Must |
| FR3 | Onboard LED matrix shows a weather icon or open-bill count | Must |
| FR4 | One key press plays the ElevenLabs household briefing | Should |
| FR5 | Spoken announcement when a bill pops | Should |
| FR6 | Shows an Offline state when the backend is unreachable | Should |
| NFR1 | Speaks household-level information only (Security and Privacy tab) | Must |
| NFR2 | No modification of mains wiring; only pre-wired, store-bought lamp parts | Must |
| NFR3 | Board kept outside the globe for airflow | Must |
| NFR4 | Assembles in under 1 hour with no tools beyond scissors and tape | Should |

**Acceptance test:** pay the last share on laptop B; within 2 seconds the globe bursts, settles to calm blue, the matrix shows the sun icon, and the announcement plays.

## Buy list

Prices are rough estimates; check the box for the exact words in the Must-check column before buying.

| Item | Where | Approx. price | Must check on the box |
| --- | --- | --- | --- |
| Wi-Fi color smart bulb, E26 base (WiZ first choice, TP-Link Kasa second) | Home Depot, Lowe's, Walmart, Target | $10 to $20 | "Color", "Wi-Fi", "no hub required"; avoid Bluetooth-only and hub-based bulbs |
| Plug-in lamp socket cord kit with switch, or a small accent lamp with an E26 socket and no shade | Home Depot, Lowe's (lighting parts), Walmart | $8 to $15 | Pre-wired with a plug; takes a standard E26 bulb |
| Glass globe: replacement light-fixture globe (6 to 8 in, frosted or clear), glass cloche, or fishbowl | Home Depot, Lowe's (lighting parts); Walmart home decor | $8 to $20 | Opening wide enough to sit over the bulb |
| USB-C hub with power passthrough | Walmart, Best Buy, Target | $20 to $35 | "PD passthrough" plus at least 2 USB-A ports |
| USB-C power adapter | Walmart, Best Buy, Target | $15 to $25 | Meets the UNO Q's power spec (check Arduino's docs; 20 W or more is a safe start) |
| Wired USB numeric keypad | Walmart, Best Buy, Target, Staples | $10 to $15 | Wired USB, not Bluetooth |
| USB audio adapter (USB to 3.5 mm) | Best Buy, Walmart, Target | $8 to $15 | Says "USB sound card" or "USB audio adapter" (a DAC), not a passive dongle |
| Small powered speaker with a 3.5 mm input | Walmart, Best Buy, Target | $10 to $20 | Powered by USB or wall plug |
| Parchment paper or white tissue paper | Walmart, Target | $3 | Diffuses a clear globe |
| Power strip and double-sided mounting tape | Any | $10 |  |

About $100 to $175 total. If the budget is tight, skip the audio adapter and speaker and play audio from a laptop.

## Assembly

Test every part on the table before building the globe; assembly takes about 45 minutes, and the network setup in step 1 is what usually goes wrong.

1. **Set up a phone hotspot as the device network.** Hackathon Wi-Fi often blocks devices from talking to each other, and most smart bulbs need 2.4 GHz. On an iPhone, turn on Maximize Compatibility in Personal Hotspot settings; on Android, choose the 2.4 GHz band.
2. **Pair the bulb.** Screw it into any socket, set it up with its own app (WiZ or Kasa) on the hotspot network, and confirm you can change its color from the phone.
3. **Connect the UNO Q.** Plug the power adapter into the hub's power-in port and the hub into the UNO Q. Join the board to the same hotspot.
4. **Control the bulb from the board.** Install the bulb's Python library on the board (`pywizlight` for WiZ, `python-kasa` for Kasa), discover the bulb's IP address, and send a test color. Write the IP into the device config.
5. **Connect the keypad and audio.** Plug the keypad and USB audio adapter into the hub, and the speaker into the adapter. On the board, `lsusb` should list both devices, `aplay -l` should list the USB sound card, and `speaker-test -c 2 -t wav` should play sound.
6. **Build the globe.** Remove the accent lamp's shade (or stand the socket kit upright), screw in the bulb, line a clear globe with parchment or tissue for a soft glow, and set the globe over the bulb.
   - Leave the top open or a gap at the base for airflow.
   - After 10 minutes on full brightness, the glass should feel only warm.
7. **Place the board.** Mount the UNO Q in front of the globe with the LED matrix facing the judge, using mounting tape on a small stand or clear container. Keep it outside the globe.
8. **Label the keys.** Put a sticker on one key as "Briefing"; tape over the rest so judges press the right one.
9. **Tidy power.** Run the lamp, hub, and speaker into one power strip and bundle the cables.
10. **Run the acceptance test** from Product requirements, then reset demo data.

## Device states and behaviors

Color always pairs with a sound or the matrix icon so status never depends on color alone.

| State | Trigger | Lights | Matrix | Sound |
| --- | --- | --- | --- | --- |
| Clear skies | All shared bills on track | Slow calm blue breathing | Sun icon | None |
| Tight week ahead | Household forecast flags risk | Soft amber | Cloud icon | None |
| Bill due soon | Shared bill due within 3 days | Gentle pulse | Count of open bills | None |
| Share paid | share.updated event | Brief sparkle | Count updates | Soft chime |
| Bubble popped | bubble.popped event | Burst animation, then blue | Sun icon | Chime + announcement |
| Briefing | Button press | Rotating shimmer while speaking | Weather icon | ElevenLabs briefing |
| Listening | Button held (stretch) | Steady white | Mic icon | None |
| Offline | No backend connection | Dim slow gray | Dash | None |

## Software layout and protocol

Python on the Linux side owns the network, the smart bulb, the keypad, and audio; the Arduino sketch on the microcontroller only drives the LED matrix, linked by Arduino's bridge (check the App Lab examples for the current API).

**Linux side (Python)**

1. On boot, read the household token and bulb IP from a local config file and connect to the backend's Socket.IO household room.
2. On `share.updated`, `bubble.popped`, or `forecast.updated`, set the bulb's color and brightness over the local network and send the matching icon to the microcontroller.
3. Animations (breathing, sparkle, burst) are short loops of color and brightness changes; keep updates to a few per second, since smart bulbs drop rapid commands.
4. On `device.announce`, download the audio file and play it while the bulb animation runs.
5. Read keypad presses with the `evdev` library; the Briefing key calls `POST /api/device/briefing` and plays the returned audio.
6. Reconnect with backoff; show the Offline state while disconnected.

**Microcontroller side (sketch)**

- Draws the LED matrix icons: sun, cloud, count, dash

**Commands across the bridge** (simple strings)

```csv
direction,message,example
to MCU,matrix icon,matrix:sun
to MCU,matrix icon,matrix:cloud
to MCU,matrix count,matrix:count:3
to MCU,matrix offline,matrix:dash
```

## On-device AI (Gemma)

Gemma runs on the UNO Q's Linux side only after the lights and celebration work; if the 30-minute benchmark below fails, ship templates instead and mention the design in Q&A.

1. **Benchmark first (30 minutes max).** Build llama.cpp on the board, download Gemma 3 270M as a 4-bit GGUF, and time a 60-word briefing. Keep it if a briefing finishes in under about 20 seconds and memory stays below about 1.2 GB; try Gemma 3 1B only if 270M is fast and its text is weak.
2. **Narrator.** When the household summary changes, fetch `/api/device/summary`, have Gemma write a 2 to 3 sentence briefing, validate it against the summary (Security and Privacy tab), send the text to the backend for ElevenLabs audio, and cache the result. Pressing Briefing plays the cached audio instantly.
3. **Privacy guard (last stretch).** Record a short clip on long-press, transcribe it with whisper.cpp tiny on the device, and have Gemma label it household or personal. Only household questions go to the backend.
4. **Template fallback, always present.** "Rent is 2 of 3 paid and due Friday. Skies look clear this week." Used whenever the model is slow, fails, or its output fails validation.

These model sizes and speeds are estimates for this board; trust your own benchmark.

## Fallbacks

Each fallback keeps the demo moment intact: a payment on one screen visibly changes the dome.

| If this fails | Fall back to |
| --- | --- |
| Audio on the UNO Q | Play ElevenLabs audio from a laptop beside the dome |
| Smart bulb won't connect | Onboard LED matrix only |
| Venue Wi-Fi | Phone hotspot for both laptop and board |
| Socket.IO connection from the board | Poll `GET /api/household/status` every 2 seconds |
| The board entirely | Show the dome states as an animated panel in the web app and explain the hardware in Q&A |
