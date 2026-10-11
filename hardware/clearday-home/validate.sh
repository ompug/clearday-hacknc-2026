#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker run --rm -v "$project_dir:/work" -w /work \
  kicad/kicad:8.0.9@sha256:5716d82aa247abdbe512650eb4e8fce5a4031cbbef0a2c8df83208a69fef87b2 \
  sh -ec '
    kicad-cli version
    kicad-cli sch erc --exit-code-violations -o erc.rpt clearday-home.kicad_sch
    kicad-cli sch export pdf -o clearday-home.pdf clearday-home.kicad_sch
    kicad-cli sch export netlist --format kicadxml -o clearday-home.xml clearday-home.kicad_sch
    python3 validate.py
    kicad-cli pcb drc -o drc.rpt clearday-home.kicad_pcb
  '
# DRC is reported, not asserted clean: this board is an unrouted placement study.
