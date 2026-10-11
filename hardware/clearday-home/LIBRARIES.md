# Library provenance

The schematic embeds symbols from the standard libraries shipped with
`kicad/kicad:8.0.9`. The PCB uses standard footprints from that same image.
No third-party footprint package is required. Library tables refer to
`KICAD8_SYMBOL_DIR` and `KICAD8_FOOTPRINT_DIR`.

`Clearday.kicad_sym` contains:

- `TPS22918DBVR`: a simple project-local symbol drawn from TI's datasheet.
- `MAX98357A`: a copy of KiCad's `Audio:MAX98357A`, with exposed pad 17 changed
  from `unspecified` to `power_in`. Geometry, pin numbering, NC pins, and
  standard footprint assignment are retained. Its ground connection follows
  the Analog Devices datasheet.

KiCad library contributors retain copyright in the standard symbols and
footprints. They are distributed under
[CC BY-SA 4.0 with the KiCad libraries exception](https://www.kicad.org/libraries/license/).
The modified MAX98357A library symbol carries the same license and exception.
Original symbol source: [KiCad kicad-symbols / Audio.kicad_sym](https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/8.0.9/Audio.kicad_sym).
