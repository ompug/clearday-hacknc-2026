#!/usr/bin/env bash
# The one way to run Clearday's dev servers. Usage:
#   bash scripts/dev.sh up [--e2e] [--lan]    DB (podman-compose) + migrate + API + web, in the background
#                                             --lan binds the API to 0.0.0.0 for Clearday Home (web stays on loopback)
#   bash scripts/dev.sh down [--e2e] [--force-port]
#   bash scripts/dev.sh restart [--e2e]
#   bash scripts/dev.sh status [--e2e]
#   bash scripts/dev.sh migrate [--db local|tiger|e2e]   (default: DB_TARGET from api/.env)
#   bash scripts/dev.sh e2e [args...]         run scripts/e2e_live_pop.py against the --e2e stack
#
# Normal stack: API :8000 (logs/api.log), web :3001 (logs/web.log), DB from api/.env (DB_TARGET).
# --e2e stack:  API :8001 (logs/api-e2e.log), web :3002 (logs/web-e2e.log), local DB clearday_e2e.
# The two stacks can run side by side. Pidfiles live in logs/*.pid; `down` only stops processes this
# script started. `down --force-port` also stops a process listening on the stack's ports whose
# command line (or its parent's) contains this repo's path. Never prints database URLs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"
cd "$ROOT"

die() { echo "dev.sh: $*" >&2; exit 1; }

cmd="${1:-}"; [ $# -gt 0 ] && shift
e2e=0; lan=0; force_port=0; db=""; passthru=()
if [ "$cmd" = "e2e" ]; then
  e2e=1; passthru=("$@"); set --
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --e2e) e2e=1 ;;
    --force-port) force_port=1 ;;
    --lan) lan=1 ;;
    --db) [ $# -ge 2 ] || die "--db needs local, tiger or e2e"; db="$2"; shift ;;
    --db=*) db="${1#--db=}" ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

if [ "$e2e" -eq 1 ]; then
  sfx="-e2e"; api_port="${CLEARDAY_API_PORT:-8001}"; web_port="${CLEARDAY_WEB_PORT:-3002}"
else
  sfx=""; api_port="${CLEARDAY_API_PORT:-8000}"; web_port="${CLEARDAY_WEB_PORT:-3001}"
fi

# --- E2E database: same local server, database clearday_e2e. URL stays in env vars only. ---------
E2E_DB_NAME="clearday_e2e"
use_e2e_db() {
  local url
  url="$(uv run python - "$E2E_DB_NAME" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql

from api.config import get_settings

name = sys.argv[1]
base = get_settings().database_url_local.get_secret_value()
parts = urlsplit(base)
with psycopg.connect(base, autocommit=True, connect_timeout=5) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        print(f"dev.sh: created local database {name}", file=sys.stderr)
print(urlunsplit(parts._replace(path="/" + name)))
PY
)" || die "could not prepare the $E2E_DB_NAME database (is the local DB up?)"
  export DB_TARGET=local DATABASE_URL_LOCAL="$url"
}

# --- local DB via podman-compose ------------------------------------------------------------------
db_up() {
  command -v podman-compose >/dev/null || die "podman-compose not found"
  podman-compose up -d >>"$LOGS/db.log" 2>&1 || die "podman-compose up failed (see logs/db.log)"
  local name status i
  name="$(basename "$ROOT")_db_1"
  for i in $(seq 1 60); do
    status="$(podman inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || true)"
    [ "$status" = "healthy" ] && { echo "db: healthy (127.0.0.1:5432)"; return 0; }
    sleep 1
  done
  die "local DB not healthy after 60s (podman-compose ps; logs/db.log)"
}

# --- process bookkeeping --------------------------------------------------------------------------
# A pidfile holds "<pid> <starttime>" so a recycled PID is never mistaken for ours.
starttime() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }
pidfile() { echo "$LOGS/$1$sfx.pid"; }
running_pid() {  # prints the pid if the pidfile's process is still the one we started
  local f pid st
  f="$(pidfile "$1")"
  [ -f "$f" ] || return 1
  read -r pid st <"$f" || return 1
  [ -n "${pid:-}" ] && [ -d "/proc/$pid" ] && [ "$(starttime "$pid")" = "$st" ] || { rm -f "$f"; return 1; }
  echo "$pid"
}
port_pids() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u; }
port_busy() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }

start() {  # name port logfile command...
  local name="$1" port="$2" log="$3"; shift 3
  local pid
  if pid="$(running_pid "$name")"; then echo "$name: already running (pid $pid, :$port)"; return 0; fi
  port_busy "$port" && die "$name: port $port is in use by a process dev.sh didn't start. \
Stop it, or run: bash scripts/dev.sh down${sfx:+ --e2e} --force-port"
  : >"$log"
  # setsid: the server gets its own process group, so `down` stops it and its children together.
  setsid "$@" >>"$log" 2>&1 </dev/null &
  pid=$!
  echo "$pid $(starttime "$pid")" >"$(pidfile "$name")"
  echo "$name: started (pid $pid, :$port, ${log#"$ROOT"/})"
}

stop_group() {  # pid label
  local pid="$1" i
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for i in $(seq 1 50); do
    kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null || { echo "$2: stopped"; return 0; }
    sleep 0.2
  done
  kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  echo "$2: killed after 10s"
}

stop() {  # name
  local pid
  if pid="$(running_pid "$1")"; then
    stop_group "$pid" "$1 (pid $pid)"
    rm -f "$(pidfile "$1")"
  else
    echo "$1: not running (no live pidfile)"
  fi
}

force_port() {  # port: stop listeners whose own or parent's command line contains the repo path
  local port="$1" pid ppid target cl
  for pid in $(port_pids "$port"); do
    target=""
    cl="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
    if [[ "$cl" == *"$ROOT"* ]]; then
      target="$pid"
    else
      ppid="$(awk '{print $4}' "/proc/$pid/stat" 2>/dev/null || true)"
      cl="$(tr '\0' ' ' <"/proc/$ppid/cmdline" 2>/dev/null || true)"
      [[ -n "$ppid" && "$ppid" != 1 && "$cl" == *"$ROOT"* ]] && target="$ppid"
    fi
    if [ -z "$target" ]; then
      echo "port $port: pid $pid is not from this repo; leaving it alone" >&2
      continue
    fi
    kill -TERM "$target" 2>/dev/null || true
    [ "$target" != "$pid" ] && kill -TERM "$pid" 2>/dev/null || true
    echo "port $port: sent TERM to pid $target (listener $pid)"
  done
}

# --- services -------------------------------------------------------------------------------------
api_up() {
  local env=(env)
  if [ "$e2e" -eq 1 ]; then
    env+=("WEB_ORIGINS=[\"http://localhost:$web_port\",\"http://127.0.0.1:$web_port\"]")
  fi
  local host=127.0.0.1
  # --lan: the device (UNO Q) reaches the API over the hotspot. Persona login stays loopback-only in the API.
  [ "$lan" -eq 1 ] && host=0.0.0.0
  start api "$api_port" "$LOGS/api$sfx.log" "${env[@]}" uv run uvicorn api.main:app --reload \
    --reload-dir "$ROOT/api" --reload-dir "$ROOT/analytics" --host "$host" --port "$api_port"
}

web_up() {
  [ -f "$ROOT/web/node_modules/next/dist/bin/next" ] || die "web deps missing: cd web && npm install"
  local env=(env)
  if [ "$e2e" -eq 1 ]; then
    env+=(NEXT_PUBLIC_USE_MOCKS=0 "NEXT_PUBLIC_API_BASE_URL=http://localhost:$api_port" NEXT_DIST_DIR=.next-e2e)
  fi
  # Absolute path to next's JS entry: no exec bits needed, and the repo path is in the command line.
  start web "$web_port" "$LOGS/web$sfx.log" "${env[@]}" \
    bash -c 'cd "$1/web" && shift && exec "$@"' _ "$ROOT" \
    node "$ROOT/web/node_modules/next/dist/bin/next" dev -p "$web_port"
}

wait_http() {  # label url
  local i
  for i in $(seq 1 90); do
    curl -fsS -o /dev/null --max-time 2 "$2" 2>/dev/null && { echo "$1: up at $2"; return 0; }
    sleep 1
  done
  echo "$1: no answer from $2 after 90s; check the log" >&2
  return 1
}

status() {
  local name port pid label
  label="${sfx:+e2e }stack"
  echo "$label (API :$api_port, web :$web_port)"
  for name in api web; do
    port="$api_port"; [ "$name" = web ] && port="$web_port"
    if pid="$(running_pid "$name")"; then
      echo "  $name: running (pid $pid, :$port, logs/$name$sfx.log)"
    elif port_busy "$port"; then
      echo "  $name: port $port busy, not started by dev.sh"
    else
      echo "  $name: stopped"
    fi
  done
  if curl -fsS -o /dev/null --max-time 2 "http://localhost:$api_port/api/health" 2>/dev/null; then
    echo "  api health: ok"
  else
    echo "  api health: no answer"
  fi
  local st
  st="$(podman inspect --format '{{.State.Health.Status}}' "$(basename "$ROOT")_db_1" 2>/dev/null || echo "not running")"
  echo "  local db: $st"
}

case "$cmd" in
  up)
    db_up
    [ "$e2e" -eq 1 ] && use_e2e_db
    uv run python -m api.migrate || die "migrations failed (see above); not starting the API"
    api_up
    web_up
    wait_http api "http://localhost:$api_port/api/health" || true
    wait_http web "http://localhost:$web_port/login" || true
    ;;
  down)
    stop web
    stop api
    if [ "$force_port" -eq 1 ]; then force_port "$web_port"; force_port "$api_port"; fi
    ;;
  restart)
    bash "$0" down ${sfx:+--e2e}
    exec bash "$0" up ${sfx:+--e2e} $([ "$lan" -eq 1 ] && echo --lan)
    ;;
  status)
    status
    ;;
  migrate)
    case "$db" in
      "") [ "$e2e" -eq 1 ] && use_e2e_db ;;
      local|tiger) export DB_TARGET="$db" ;;
      e2e) use_e2e_db ;;
      *) die "--db must be local, tiger or e2e" ;;
    esac
    uv run python -m api.migrate
    ;;
  e2e)
    pid="$(running_pid api)" || die "e2e stack isn't running: bash scripts/dev.sh up --e2e"
    use_e2e_db
    exec uv run python scripts/e2e_live_pop.py --web "http://localhost:$web_port" "${passthru[@]}"
    ;;
  *)
    sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
    [ -z "$cmd" ] || [ "$cmd" = help ] || [ "$cmd" = -h ] || exit 2
    ;;
esac
