# Clearday Home (device)

Linux-side controller for the Arduino UNO Q globe, plus the microcontroller sketch for the LED matrix. Behaviour follows `docs/04-clearday-home-hardware.md`; privacy rules follow the device section of `docs/03-security-and-privacy.md`.

```
clearday_home/
  state.py        Pure state machine: states, transitions, fallbacks (no I/O)
  payloads.py     Allowlist parsers for /api/household/status, /api/device/summary, device.announce
  bridge.py       Socket.IO client (device token auth) + status polling fallback, reconnect with backoff
  controller.py   Applies state-machine effects to the bulb, matrix and audio
  bulb.py         BulbDriver protocol, FakeBulb, empty WizBulb / KasaBulb slots
  lights.py       Light patterns (breathing, sparkle, burst...) as slow loops of bulb commands
  matrix.py       Sends bridge strings ("matrix:sun") to the sketch
  audio.py        Chime + announcement/briefing playback (ffplay, mpg123 or aplay)
  keypad.py       evdev keypad: press = Briefing, hold = Listening (stretch)
sketch/clearday_matrix/   MCU sketch (LED matrix only) + pure renderer header
sketch/host_check/        Compiles the sketch on a laptop against mock headers
tests/                    pytest, including an in-process fake Socket.IO/HTTP server
```

## Run it

Off-board (laptop) with the fake bulb and logged matrix:

```bash
cd device
uv sync                                   # python-socketio[client] + pytest
cp .env.example .env                      # then set CLEARDAY_DEVICE_TOKEN and CLEARDAY_API_URL
uv run python -m clearday_home            # logs to stdout and logs/device.log
uv run pytest                             # state machine, privacy, bridge, sketch host check
```

On the NTFS checkout used by the team, `device/.venv` is a symlink to `~/.local/share/clearday/device-venv` (no exec bits on the mount). Recreate it with `ln -s ~/.local/share/clearday/device-venv .venv && UV_PROJECT_ENVIRONMENT=~/.local/share/clearday/device-venv uv sync`.

On the UNO Q (Debian on the Linux side):

1. Join the board to the phone hotspot (hardware doc, Assembly step 1); the API laptop must be on the same network.
2. Copy `device/` to the board, install uv, then `uv sync --group keypad` (needs `linux-headers` / `build-essential` for evdev). Add your user to the `input` group, or set `CLEARDAY_KEYPAD_DEVICE`, so evdev can read the keypad.
3. Create `device/.env` from `.env.example` with the device token from the app and `CLEARDAY_MATRIX=bridge`.
4. Flash the sketch (below), then `uv run python -m clearday_home`.
5. Run the acceptance test: pay the last share on laptop B; within 2 s the globe bursts, settles to calm blue, the matrix shows the sun, and the chime plays.

`CLEARDAY_MATRIX=bridge` uses `arduino.app_utils.Bridge`, which Arduino App Lab provides. If the controller runs outside App Lab and that import fails, it logs and falls back to logging matrix commands; in that case run the controller inside an App Lab app instead: copy `clearday_home/` into the app's `python/` folder and call `clearday_home.__main__.main()` from its `main.py`.

## Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLEARDAY_DEVICE_TOKEN` | (required) | Household device token: read-only, hashed and revocable on the server. Sent as Socket.IO `auth={"token": ...}` and HTTP `Authorization: Bearer`. |
| `CLEARDAY_API_URL` | `http://localhost:8000` | The Clearday API (the only host the device talks to). |
| `CLEARDAY_BULB` | `fake` | `fake`, `wiz` or `kasa`. Unimplemented or failing drivers fall back to `fake` (matrix-only demo). |
| `CLEARDAY_BULB_IP` | | Bulb IP on the hotspot, for `wiz` / `kasa`. |
| `CLEARDAY_MATRIX` | `log` | `bridge` on the UNO Q, `log` elsewhere. |
| `CLEARDAY_AUDIO` | `1` | `0` to skip playback (play audio from a laptop instead). |
| `CLEARDAY_KEYPAD_DEVICE` | auto | `/dev/input/eventN` of the keypad. |
| `CLEARDAY_BRIEFING_KEY` | `KEY_KPENTER` | evdev key name of the Briefing key. |
| `CLEARDAY_LOG_DIR` | `logs` | Log directory (`device.log`). |
| `CLEARDAY_POLL_SECONDS` | `2` | Status polling interval when Socket.IO is down. |

`device/.env` is gitignored. No Nessie, Gemini or ElevenLabs keys ever go on the device.

## Where the bulb driver plugs in

`clearday_home/bulb.py` defines the `BulbDriver` protocol: `set_color(rgb)`, `set_brightness(percent)`, `celebrate()`, `off()`. `make_bulb()` picks the driver from `CLEARDAY_BULB`. Once the bulb is bought:

1. Get team sign-off for the library, then add `pywizlight` (WiZ) or `python-kasa` (Kasa) to `device/pyproject.toml`.
2. Fill in `WizBulb` or `KasaBulb` (both libraries are asyncio: run one event loop on a background thread and submit coroutines to it).
3. Set `CLEARDAY_BULB` and `CLEARDAY_BULB_IP`, and check that commands stay at a few per second (`lights.MIN_HOLD`).

## Backend contract the device expects

The device reads only these. Parsers in `payloads.py` copy the listed fields and drop everything else, so a stray amount or name never reaches state, logs, the bulb or the matrix (`tests/test_payloads.py`, `tests/test_bridge.py::test_never_handles_amounts_or_names`).

`GET /api/household/status` (counts only):

```json
{"weather": "clear", "open_bills": 2, "due_soon_bills": 1, "shares_paid": 3, "shares_total": 4}
```

`weather` is `"clear"` or `"tight"`; `due_soon_bills` counts shared bills due within 3 days.

`GET /api/device/summary` (for the later Gemma narrator):

```json
{"weather": "clear", "open_bills": 1, "bills": [{"label": "Rent", "shares_paid": 2, "shares_total": 3, "due_in_days": 2}]}
```

Socket.IO (household room, joined by the server from the device token): `share.updated`, `bubble.popped` and `forecast.updated` are triggers only; their payloads are ignored and the device re-reads the status. `device.announce` must carry `audio_url` as a path on our API (`/api/...`); anything else is rejected.

## States

| State | Lights | Matrix | Sound |
| --- | --- | --- | --- |
| Clear skies | breathe_blue | `matrix:sun` | |
| Tight week ahead | amber | `matrix:cloud` | |
| Bill due soon | pulse | `matrix:count:N` (open bills) | |
| Share paid (2.5 s) | sparkle | `matrix:count:N` | chime |
| Bubble popped (4 s) | burst, then blue | `matrix:sun` | chime (+ `device.announce` audio) |
| Briefing (until audio ends) | shimmer | weather icon | briefing audio |
| Listening (key held, stretch) | white | `matrix:mic` | |
| Offline | dim_gray | `matrix:dash` | |

Base-state priority is Offline > Bill due soon > Tight week > Clear skies (`DeviceMachine.base_state`). If Socket.IO is down, the device polls status every 2 s and infers the sparkle and the pop from count changes; if polling fails too, it shows Offline. Socket reconnects back off from 1 s to 30 s.

## Flash the sketch

The sketch only draws the 13x8 matrix and exposes one Bridge function, `matrix`, which takes the full command string (`matrix:sun`, `matrix:cloud`, `matrix:count:3`, `matrix:dash`, `matrix:mic`). It boots showing the dash.

- **Arduino App Lab (recommended):** create an app, copy `sketch/clearday_matrix/clearday_matrix.ino` and `matrix_render.h` into the app's `sketch/` folder (renaming the `.ino` to `sketch.ino`), add `Arduino_RouterBridge` and `Arduino_LED_Matrix` to the sketch libraries, and press Run.
- **arduino-cli:** `arduino-cli core install arduino:zephyr`, then `arduino-cli compile --fqbn arduino:zephyr:unoq sketch/clearday_matrix` and `arduino-cli upload --fqbn arduino:zephyr:unoq -p <port> sketch/clearday_matrix` (confirm the FQBN with `arduino-cli board listall`).

Without hardware, `bash sketch/host_check/check.sh` compiles the sketch with `g++ -Wall -Wextra -Werror` against mock headers and prints every frame; `uv run pytest` runs it too. The mocks assume `Bridge.provide(name, fn)` and `Arduino_LED_Matrix::draw(uint8_t[104])`; confirm both against the App Lab examples on the board, since only `show()` and `setup()` touch those APIs.
