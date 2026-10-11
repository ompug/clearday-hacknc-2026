# Clearday Home

Rev A, 2026-10-11, HackNC 2026. A USB-powered kitchen-counter companion for
the Clearday roommate bill-splitting app. It uses light and short spoken
announcements, with no display and no dollar amounts shown on the device.

Open **`clearday-home.kicad_pro` in KiCad 8**. The five-sheet schematic, BOM,
and PDF are complete. The 70 mm PCB is an **unrouted placement study, not a
manufacturing release**. The board and review Gerbers must not be fabricated.

## Files and verification

- `clearday-home.kicad_sch`: Power & USB and links to four child sheets.
- `mcu.kicad_sch`, `leds.kicad_sch`, `audio.kicad_sch`, `inputs.kicad_sch`:
  MCU, LEDs, Audio, and Inputs & Expansion.
- `clearday-home.kicad_pcb`: two-layer placement study with assigned nets,
  twelve edge LEDs, rear service components, and ground pours on both layers.
- `clearday-home.pdf`: five-page schematic export.
- `bom.csv`: grouped references, quantity, value, exact MPN, footprint,
  manufacturer, and assembly notes for 78 components.
- `erc.rpt`: KiCad **8.0.9**, zero errors and zero warnings; no exclusions.
- `drc.rpt`: 72 PCB violations and 122 unconnected items. Not a pass.
- `clearday-home.xml` and `validation.json`: exported connectivity and checks
  of all 295 numbered PCB pads against the schematic, plus critical pin maps.
- `fab/`: front/back PNGs, SVGs, and explicitly labeled unrouted review Gerbers.
- `generate.py`, `validate.py`, `validate.sh`, `export-review.sh`: reproducible
  generation, checking, and export. `design.json` is generator metadata.
- `SOURCING.md`: part availability evidence and datasheet references.

All footprints are from KiCad 8 standard libraries. Symbols are standard
except the local TPS22918 and a corrected copy of the standard MAX98357A.
The latter sets exposed pad 17 to power input rather than unspecified, as the
datasheet requires it to connect to ground. No electrical check is suppressed.
See `LIBRARIES.md` for attribution. The project library tables use KiCad 8
environment variables, not machine-specific absolute paths.

## Circuit blocks

**Power & USB.** J1 is a GCT USB4105-GF-A 16-pin USB 2.0 Type-C receptacle.
Separate 5.1 kΩ resistors terminate CC1 and CC2. Their voltages reach ADC1
through 10 kΩ / 10 nF filters for source-current detection. U2 protects the
data pair, with both orientations of the receptacle wired together. R3/R4
are 22 Ω series resistors intended near the MCU. F1 is a 2 A hold PTC;
U3 is a 1 A AP7361C-33E 3.3 V LDO with input/output capacitors. D1 indicates
3.3 V power. The USB shell is bonded to ground.

**MCU.** U1 is ESP32-S3-WROOM-1-N8R8, with 8 MB flash and 8 MB octal PSRAM.
Native USB supports programming and USB serial; UART0 is also available on
J5. EN has a 10 kΩ / 1 µF reset network and reset switch. GPIO0 has a 10 kΩ
pull-up and BOOT switch. Hold BOOT, tap RESET, then release BOOT for ROM
download mode. Unused pins have no-connect markers. GPIO3/45/46 are unloaded;
GPIO35/36/37 are reserved for PSRAM and unconnected.

**LEDs.** D2 through D13 are WS2812B-V5/W RGB pixels, each with 100 nF
decoupling. U5 converts GPIO4's 3.3 V data to 5 V logic, followed by a 330 Ω
series resistor. U6 switches the LED supply and its 1000 µF reservoir.
A 10 nF CT capacitor gives roughly 26 ms rise time at 5 V. QOD is deliberately
unconnected, so the 1000 µF capacitor does not discharge through the switch's
internal discharge device. Firmware keeps data low while power is off, then
waits at least 50 ms after LED_ENABLE before transmitting. The ring itself
is the light; no smart-bulb bridge is included.

**Audio.** MAX98357A U4 drives a floating 4–8 Ω speaker through JST-PH J2.
Use a speaker rated around 3 W. Neither terminal is ground. R15's 100 kΩ
connection to VDD selects +3 dB gain. R13's 560 kΩ resistor from AMP_ENABLE
and the amplifier's internal 100 kΩ pulldown produce nominally 0.500 V on
SD_MODE, selecting `(left + right) / 2`; a low GPIO shuts it down. A 100 kΩ
external enable pulldown mutes at reset. Output power depends on impedance,
supply voltage, digital level, and distortion; a 3 W speaker rating does not
mean the board delivers 3 W continuously.

MK1 is an ICS-43434 bottom-port microphone, powered from 3.3 V. LR is grounded
for the left slot, and a 100 kΩ data pulldown defines the high-impedance slot.
The ESP32 supplies shared BCLK/LRCLK to both audio ICs. A suitable starting
configuration is 48 kHz, two 32-bit slots, 3.072 MHz BCLK, with 24 significant
microphone bits. The amplifier and microphone have separate data nets and
need no MCLK. Keep the acoustic hole open and isolate the mic from speaker
vibration. Future voice commands still require firmware and an app privacy flow.

**Inputs & expansion.** SW3 is a 12 mm acknowledge switch. J3 accepts a
parallel external passive arcade button. R17, R18, and C28 filter BTN_ACK:
about 0.9 ms press and 10 ms release time constants; pressed voltage is
approximately 0.3 V. Require 30 ms stable state in firmware. J4 provides
Qwiic/STEMMA QT I2C with 4.7 kΩ pull-ups and local decoupling. Start at
100 kHz, budget at most 50 mA for sensors, and check the combined pull-up
resistance when attaching a board with its own pull-ups.

## GPIO map

| GPIO | Net | Direction / purpose |
| --- | --- | --- |
| 0 | BOOT | Boot strap and service switch only |
| 1 | CC1_SENSE | ADC input for Type-C source-current indication |
| 2 | CC2_SENSE | ADC input for Type-C source-current indication |
| 4 | LED_DATA | Output to 74AHCT1G125 |
| 5 | BTN_ACK | Active-low button input |
| 8 | I2C_SDA | Bidirectional, 3.3 V |
| 9 | I2C_SCL | I2C clock, 3.3 V |
| 10 | I2S_BCLK | Output to amplifier and microphone |
| 11 | I2S_LRCLK | Output to amplifier and microphone |
| 12 | I2S_DOUT | Output to amplifier DIN |
| 13 | I2S_DIN | Input from microphone SD |
| 14 | AMP_ENABLE | High selects mixed audio; low shuts down |
| 16 | LED_ENABLE | High enables U6 slow start |
| 19 | USB_DN | Native USB D− |
| 20 | USB_DP | Native USB D+ |
| 43 | UART_TX | UART0 output |
| 44 | UART_RX | UART0 input |

## Connector pinouts

| Connector | Pinout |
| --- | --- |
| J2 speaker | 1 SPK_P, 2 SPK_N; neither grounded |
| J3 external button | 1 BTN_RAW, 2 GND; short with passive switch only |
| J4 Qwiic | 1 GND, 2 3V3, 3 SDA, 4 SCL |
| J5 custom service | 1 3V3, 2 GND, 3 TX, 4 GND, 5 RX, 6 GND, 7 EN, 8 GND, 9 BOOT, 10 GND |

J5 is a 2×5, 1.27 mm **custom UART header, not ARM SWD**. TX and RX are named
from the MCU perspective. Use 3.3 V logic and open-drain EN/BOOT control.
Its 3V3 pin is a reference; do not power the board from it while USB is present.

## App behavior and firmware contract

The intended device firmware connects over Wi-Fi to the app's Socket.IO
server, authenticates for one household, and receives semantic states:

| App state | Device output |
| --- | --- |
| clear | Steady soft blue: bills on track |
| tight week | Amber: a tight week ahead |
| celebration | Brief rainbow burst, then return to the current state |

Short announcements use the speaker. The app must show the same announcement
as an on-screen transcript, including when audio is muted. BTN_ACK acknowledges
the current notification and can stop speech. Do not include dollar amounts
in device announcements. Device messages should carry a household ID, event
ID, semantic state, and expiry so firmware can reject stale or duplicate
notifications. A disconnect should not leave a stale blue state indefinitely.

This is an intended contract, not an implemented API integration. Socket.IO
requires its Engine.IO/Socket.IO framing; a plain WebSocket client alone is
insufficient. Event names, authentication, pairing, reconnect behavior,
announcement transport, and acknowledgement semantics need agreement with
the app. No app or firmware files were changed by this hardware work.

## Power budget and board work remaining

Use a regulated **5 V / 3 A Type-C supply** for full operation. There is no
USB PD controller. CC pulldowns do not authorize an arbitrary current draw.
Firmware must classify the active CC voltage with ADC calibration and USB-C
thresholds, account for USB configuration/suspend where applicable, and cap
LED brightness and audio level to the available current. ADC sensing and
soft start are provided; that policy is not implemented here. Treat a PC
port as a restricted programming source until this has been validated.

For budgeting, reserve up to 720 mA for twelve legacy-compatible RGB pixels
at full white, about 700 mA for loud 4 Ω audio, and 500 mA for MCU peaks plus
sensor headroom. The selected V5 LEDs generally need less than that legacy
allowance. Avoid simultaneous maximum loads: the 2 A PTC derates with
temperature. At 300 mA, the LDO dissipates about 0.51 W; its 1 A electrical
rating is not a continuous thermal guarantee in a closed dome. Thermal
copper, Wi-Fi current transients, USB attach/inrush/suspend, and brownout
behavior need bench validation.

The PCB has no signal or supply traces yet. The provisional placement uses
a 60 mm LED circle inside a 70 mm board. LEDs leave a 90-degree antenna gap
and a smaller USB-shell gap; a perfectly uniform ring is not achieved in
this study. Review that optical tradeoff under the dome. USB, speaker
connector, and button face the back. The standard ESP32 footprint's antenna
keepout is retained. Ground pours are filled but are not a completed return
path design.

Before fabrication: route and verify USB at 90 Ω differential impedance for
the selected stackup; route power for the load budget; shorten decoupler
connections; keep I2S away from speaker outputs; add ground stitching;
resolve every DRC finding; review the module's 0.2 mm thermal-via drills
against fabricator capabilities; inspect footprint-mismatch reports after
rotation/mirroring; finish silkscreen; add mounting and enclosure details;
verify connector drawings and microphone sealing. Select the speaker,
cables, diffuser, power supply, and enclosure separately. No populated
prototype, RF/EMC testing, production procurement, or firmware is included.

## Reproduce the checks

With Docker installed, from the repository root:

```sh
bash hardware/clearday-home/validate.sh
bash hardware/clearday-home/export-review.sh
```

The first script pins the KiCad 8.0.9 image by digest, asserts a clean ERC,
exports the PDF/netlist, checks pad connectivity, and records DRC without
pretending the unrouted board passes. The second exports review-only
Gerbers/drills and requires ImageMagick `convert` for PNG rendering.

To regenerate the design, run `python3 generate.py` **inside that KiCad 8
container**, mounting this directory at `/work` and using it as the working
directory. Regeneration replaces the generated schematic, BOM, metadata,
project settings, and PCB, so preserve any later hand edits first. The
generator uses standard libraries supplied by that image and Python's
standard library plus KiCad's `pcbnew` module.
