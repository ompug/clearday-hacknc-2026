#!/usr/bin/env bash
# Idempotent dev setup: Python 3.12 + deps via uv, and git hooks.
# If the checkout's filesystem can't hold exec bits (e.g. NTFS via fuseblk),
# the venv and the hooks dir live under ~/.local/share/clearday instead.
set -euo pipefail
root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$root"
ext="${CLEARDAY_LOCAL_DIR:-$HOME/.local/share/clearday}"

probe="$(mktemp "$root/.exec-probe.XXXXXX")"
chmod +x "$probe" 2>/dev/null || true
if [ -x "$probe" ]; then exec_ok=1; else exec_ok=0; fi
rm -f "$probe"

uv python install 3.12

if [ "$exec_ok" -eq 1 ]; then
  echo "bootstrap: filesystem supports exec bits; using .venv and .githooks in the repo"
  [ -L .venv ] && rm .venv
  uv sync
  chmod +x .githooks/* scripts/*.sh
  git config core.hooksPath .githooks
else
  echo "bootstrap: no exec bits here; using $ext for the venv and hooks"
  mkdir -p "$ext/githooks"
  if [ ! -L .venv ]; then
    rm -rf .venv
    ln -s "$ext/venv" .venv
  fi
  UV_PROJECT_ENVIRONMENT="$ext/venv" uv sync
  # Refresh hook copies every run so changes to .githooks/ are picked up.
  for hook in .githooks/*; do
    cp "$hook" "$ext/githooks/$(basename "$hook")"
    chmod +x "$ext/githooks/$(basename "$hook")"
  done
  git config core.hooksPath "$ext/githooks"
fi

echo "bootstrap: done (hooksPath=$(git config core.hooksPath))"
