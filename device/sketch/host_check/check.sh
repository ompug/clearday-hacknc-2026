#!/usr/bin/env bash
# Compile the matrix sketch on a laptop against mock Arduino headers and run
# its protocol checks. Catches syntax and logic errors; it does not replace a
# real build for the UNO Q (see device/README.md).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$(mktemp -d "${TMPDIR:-/tmp}/clearday-sketch.XXXXXX")"
trap 'rm -rf "$out"' EXIT
"${CXX:-g++}" -std=c++17 -Wall -Wextra -Werror -x c++ -I"$here/mocks" \
  "$here/host_main.cpp" -o "$out/host_check"
"$out/host_check" "$@"
