#!/usr/bin/env bash
# Money lint: money is integer cents. Fails if float(, ": float", Decimal or
# "/ 100" (true division) appears in money code. Suppress one line with a
# trailing "# money-ok: <reason>" (the reason is required).
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"

files=()
[ -f analytics/splits.py ] && files+=(analytics/splits.py)
while IFS= read -r -d '' f; do files+=("$f"); done < <(
  find api -type f \( -name 'ledger*.py' -o -name 'payments*.py' \) -not -path '*/.venv/*' -print0 2>/dev/null || true)
[ "${#files[@]}" -eq 0 ] && exit 0

pattern='float\(|:[[:space:]]*float\b|Decimal|(^|[^/])/[[:space:]]*100([^0-9]|$)'
hits="$(grep -nHE "$pattern" "${files[@]}" | grep -vE '#[[:space:]]*money-ok:[[:space:]]*[^[:space:]]' || true)"

if [ -n "$hits" ]; then
  echo "check_money: non-integer money code (use int cents, // or divmod; or add '# money-ok: <reason>'):" >&2
  echo "$hits" >&2
  exit 1
fi
exit 0
