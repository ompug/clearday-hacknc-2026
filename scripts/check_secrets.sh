#!/usr/bin/env bash
# Secret guard: fails if a secret file is tracked/staged, or if any staged file contains a secret
# value read from a gitignored secret file. Secret files are every gitignored `*.env`, `*credentials*`
# and `*api_key*` file in the repo root and api/ (api/.env included). Never prints the values.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
cd "$root"
fail=0

# Gitignored secret files in the root and api/ (find's -name '*' also matches dotfiles like .env).
sources=()
while IFS= read -r -d '' f; do
  f="${f#./}"
  case "$f" in *.example) continue ;; esac
  git check-ignore -q --no-index "$f" && sources+=("$f")
done < <(find . api -maxdepth 1 -type f \
  \( -name '*.env' -o -name '*credentials*' -o -name '*api_key*' \) -print0 2>/dev/null)

for f in api/.env nessie_and_elevenlabs_api_setup tiger_nessie_elevenlabs_api_setup "${sources[@]}"; do
  if git ls-files --cached --error-unmatch "$f" >/dev/null 2>&1; then
    echo "check_secrets: $f is tracked or staged. Run: git rm --cached $f" >&2
    fail=1
  fi
done
if git diff --cached --name-only | grep -E '(^|/)\.env(\.[^/]*)?$' | grep -vq '\.env\.example$'; then
  echo "check_secrets: a .env file is staged." >&2
  fail=1
fi

if [ "${#sources[@]}" -gt 0 ]; then
  patterns="$(mktemp)"
  trap 'rm -f "$patterns"' EXIT
  # From KEY=VALUE lines: values of *KEY*, *SECRET*, *PASSWORD*, *TOKEN*, *PWD* vars, DATABASE_URL
  # and *SERVICE_URL. A non-comment line that is a single bare token (e.g. a key-only .txt file) is
  # taken whole. Only values of 8+ characters count.
  for f in "${sources[@]}"; do
    awk '
      { sub(/\r$/, ""); sub(/^[ \t]+/, ""); sub(/[ \t]+$/, "") }
      $0 == "" || /^#/ { next }
      {
        line = $0
        sub(/^export[ \t]+/, "", line)
        if (match(line, /^[A-Za-z_][A-Za-z0-9_]*[ \t]*=/)) {
          key = line; sub(/[ \t]*=.*/, "", key); key = toupper(key)
          val = substr(line, RLENGTH + 1); sub(/^[ \t]+/, "", val)
          if (val ~ /^".*"$/ || val ~ /^\x27.*\x27$/) val = substr(val, 2, length(val) - 2)
          if (key ~ /^(DATABASE_URL|[A-Z_]*SERVICE_URL|[A-Z_]*(KEY|SECRET|PASSWORD|PASSWD|TOKEN|PWD)[A-Z_]*)$/)
            print val
        } else if (line !~ /[ \t]/) {
          print line
        }
      }' "$f"
  done | awk 'length($0) >= 8' | sort -u > "$patterns" || true

  if [ -s "$patterns" ]; then
    while IFS= read -r -d '' file; do
      [ -f "$file" ] || continue
      if git show ":$file" 2>/dev/null | grep -qFf "$patterns"; then
        echo "check_secrets: staged file '$file' contains a secret value from a gitignored secret file" >&2
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
