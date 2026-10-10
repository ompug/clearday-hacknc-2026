#!/usr/bin/env bash
# Secret guard: fails if api/.env is tracked/staged or if any staged file
# contains a secret value from api/.env. Never prints the values themselves.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
fail=0

for f in api/.env nessie_and_elevenlabs_api_setup tiger_nessie_elevenlabs_api_setup; do
  if git ls-files --cached --error-unmatch "$f" >/dev/null 2>&1; then
    echo "check_secrets: $f is tracked or staged. Run: git rm --cached $f" >&2
    fail=1
  fi
done
if git diff --cached --name-only | grep -Eq '(^|/)\.env(\.[^/]*)?$' ; then
  if git diff --cached --name-only | grep -E '(^|/)\.env(\.[^/]*)?$' | grep -vq '\.env\.example$'; then
    echo "check_secrets: a .env file is staged." >&2
    fail=1
  fi
fi

env_file="api/.env"
if [ -f "$env_file" ]; then
  patterns="$(mktemp)"
  trap 'rm -f "$patterns"' EXIT
  # Values of *KEY*, *SECRET*, *PASSWORD*, *TOKEN* vars and DATABASE_URL, 8+ chars.
  grep -E '^(DATABASE_URL|[A-Z_]*(KEY|SECRET|PASSWORD|TOKEN)[A-Z_]*)=' "$env_file" \
    | sed -E 's/^[^=]+=//; s/^"(.*)"$/\1/' \
    | awk 'length($0) >= 8' > "$patterns" || true
  if [ -s "$patterns" ]; then
    while IFS= read -r -d '' file; do
      [ -f "$file" ] || continue
      if git show ":$file" 2>/dev/null | grep -qFf "$patterns"; then
        echo "check_secrets: staged file '$file' contains a secret value from api/.env" >&2
        fail=1
      fi
    done < <(git diff --cached --name-only -z --diff-filter=ACMR)
  fi
fi

if [ "$fail" -ne 0 ]; then
  echo "check_secrets: commit blocked." >&2
  exit 1
fi
exit 0
