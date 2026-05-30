#!/usr/bin/env bash
#
# RedDial — run everything (control-plane API + dashboard) with one command.
#
#   ./run.sh
#
# Starts the FastAPI control plane (offline loopback, port 8080) and the Vite
# dashboard (port 5173), waits for the API to be healthy, then opens the UI.
# Ctrl-C stops both. Everything is OFFLINE — no keys, no live dialing, FAKE PII.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_PORT="${REDDIAL_API_PORT:-8080}"
WEB_PORT="${REDDIAL_WEB_PORT:-5173}"
API_PID=""

# ── pretty output ────────────────────────────────────────────────────────────
c() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
log()  { echo "$(c '1;36' '▸') $*"; }
ok()   { echo "$(c '1;32' '✓') $*"; }
die()  { echo "$(c '1;31' '✗') $*" >&2; exit 1; }

cleanup() {
  echo
  log "Shutting down…"
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true
  # also reap any stragglers we started on these ports
  pkill -f "uvicorn api:app .*--port ${API_PORT}" 2>/dev/null || true
  ok "Stopped."
}
trap cleanup EXIT INT TERM

# ── prerequisites ────────────────────────────────────────────────────────────
command -v uv  >/dev/null 2>&1 || die "uv not found — install from https://docs.astral.sh/uv/"
command -v npm >/dev/null 2>&1 || die "npm not found — install Node.js 18+"

# ── free the ports if a previous run is still up ─────────────────────────────
pkill -f "uvicorn api:app .*--port ${API_PORT}" 2>/dev/null || true

# ── 1) control-plane API ─────────────────────────────────────────────────────
log "Syncing backend deps (uv sync --frozen)…"
( cd "$ROOT/server" && uv sync --frozen >/dev/null 2>&1 ) || \
  ( cd "$ROOT/server" && uv sync >/dev/null 2>&1 ) || die "uv sync failed"

log "Starting API on http://127.0.0.1:${API_PORT} …"
( cd "$ROOT/server" && exec uv run --no-sync uvicorn api:app --host 127.0.0.1 --port "${API_PORT}" ) &
API_PID=$!

# wait (≤30s) for the API to report healthy
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/healthz" >/dev/null 2>&1; then
    ok "API healthy."
    break
  fi
  kill -0 "$API_PID" 2>/dev/null || die "API process exited — check the logs above."
  [ "$i" = 30 ] && die "API did not become healthy in time."
  sleep 1
done

# ── 2) dashboard (Vite) ──────────────────────────────────────────────────────
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  log "Installing frontend deps (first run)…"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund ) || die "npm install failed"
fi

echo
ok "RedDial is up:"
echo "    Dashboard : $(c '1;33' "http://localhost:${WEB_PORT}")"
echo "    API       : http://127.0.0.1:${API_PORT}   (docs: /docs)"
echo "    $(c '2' 'Offline harness · FAKE PII · no live dialing. Press Ctrl-C to stop.')"
echo

# foreground: Vite holds the terminal; Ctrl-C triggers cleanup() which stops the API.
VITE_API_TARGET="http://127.0.0.1:${API_PORT}" \
  exec sh -c "cd '$ROOT/frontend' && npm run dev -- --port ${WEB_PORT}"
