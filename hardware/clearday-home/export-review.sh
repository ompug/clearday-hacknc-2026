#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker run --rm -v "$project_dir:/work" -w /work \
  kicad/kicad:8.0.9@sha256:5716d82aa247abdbe512650eb4e8fce5a4031cbbef0a2c8df83208a69fef87b2 \
  sh -ec '
    mkdir -p fab/unrouted-review
    kicad-cli pcb export svg --page-size-mode 2 --exclude-drawing-sheet --black-and-white \
      -l F.Fab,F.SilkS,Edge.Cuts -o fab/placement-front.svg clearday-home.kicad_pcb
    kicad-cli pcb export svg --page-size-mode 2 --exclude-drawing-sheet --black-and-white --mirror \
      -l B.Fab,B.SilkS,Edge.Cuts -o fab/placement-back.svg clearday-home.kicad_pcb
    kicad-cli pcb export gerbers -l F.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,F.Paste,B.Paste,Edge.Cuts \
      -o fab/unrouted-review/ clearday-home.kicad_pcb
    kicad-cli pcb export drill -o fab/unrouted-review/ clearday-home.kicad_pcb
  '
sed -i 's/[[:blank:]]*$//' "$project_dir/fab/placement-front.svg" "$project_dir/fab/placement-back.svg"
convert -background white -density 300 "$project_dir/fab/placement-front.svg" \
  -resize 1400x1400 "$project_dir/fab/placement-front.png"
convert -background white -density 300 "$project_dir/fab/placement-back.svg" \
  -resize 1400x1400 "$project_dir/fab/placement-back.png"
