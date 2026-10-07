#!/usr/bin/env bash
# Start a disposable ZameenRentals instance (seeded temp DB, no scraping, no Claude).
# Usage: launch.sh            # auto-picks a free port in 8300-8399
#        VERIFY_PORT=8323 launch.sh   # exact port; refuses if taken
#        VERIFY_SKIP_BUILD=1 launch.sh  # don't rebuild a stale static/
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$ROOT"

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1; }

if [ -n "${VERIFY_PORT:-}" ]; then
  PORT="$VERIFY_PORT"
  if port_busy "$PORT"; then
    echo "Port $PORT is in use by someone else; refusing to touch it:" >&2
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
    exit 1
  fi
else
  PORT=""
  for p in $(seq 8300 8399); do port_busy "$p" || { PORT=$p; break; }; done
  [ -n "$PORT" ] || { echo "No free port in 8300-8399" >&2; exit 1; }
fi

if [ ! -d "$HOME/Library/Caches/ms-playwright/chromium_headless_shell-1208" ]; then
  echo "WARN: chromium_headless_shell-1208 (Playwright 1.58.2) missing; drive.sh will fail." >&2
  echo "      Install with: npx playwright install --only-shell chromium  (it garbage-collects other versions' browsers — ask the user first)" >&2
fi

# The server serves the built static/, so a stale build proves old code.
# A fresh worktree has no static/assets/ (gitignored), so a missing bundle also forces a build.
bundle=$(grep -oE '/static/assets/index-[^"]+\.js' static/index.html 2>/dev/null | head -1)
stale=$(find frontend -type f -newer static/index.html -not -path '*/node_modules/*' | head -1)
[ -n "$bundle" ] && [ -f ".${bundle}" ] || stale="${stale:-missing ${bundle:-static bundle}}"
if [ -n "$stale" ]; then
  if [ "${VERIFY_SKIP_BUILD:-0}" = 1 ]; then
    echo "WARN: $stale is newer than static/index.html; driving a stale build (VERIFY_SKIP_BUILD=1)." >&2
  else
    echo "static/ build is stale or incomplete ($stale); running npm run build..."
    npm run build --silent >/dev/null
  fi
fi

RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M%S)-$PORT}"
STATE="$STATE_ROOT/$RUN_ID"
EVIDENCE="$ARTIFACTS/$RUN_ID"
mkdir -p "$STATE" "$EVIDENCE"

PLAYWRIGHT_PORT="$PORT" nohup python3 tests/serve_playwright.py >"$STATE/server.log" 2>&1 &
PID=$!

cat >"$STATE/env" <<EOF
VERIFY_RUN_ID=$RUN_ID
VERIFY_PORT=$PORT
VERIFY_URL=http://127.0.0.1:$PORT
VERIFY_PID=$PID
VERIFY_STATE=$STATE
VERIFY_EVIDENCE=$EVIDENCE
EOF

for _ in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "Server exited during startup. Log tail:" >&2
    tail -20 "$STATE/server.log" >&2
    rm -rf "$STATE"
    exit 1
  fi
  curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null || { echo "Health check timed out; run cleanup.sh $RUN_ID" >&2; exit 1; }

echo "READY run=$RUN_ID url=http://127.0.0.1:$PORT pid=$PID"
echo "evidence: $EVIDENCE"
