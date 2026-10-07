#!/usr/bin/env bash
# Read-only: is this verification instance worth driving?
# Usage: doctor.sh [RUN_ID]   (default: newest live run)
set -uo pipefail
. "$(dirname "$0")/_common.sh"
resolve_run "${1:-}" || exit 1

fail=0
check() { if eval "$2" >/dev/null 2>&1; then echo "ok    $1"; else echo "FAIL  $1"; fail=1; fi; }

check "pid $VERIFY_PID is our serve_playwright.py" "is_our_server $VERIFY_PID"
check "port $VERIFY_PORT is owned by pid $VERIFY_PID" \
  "lsof -nP -iTCP:$VERIFY_PORT -sTCP:LISTEN -t | grep -qx $VERIFY_PID"
check "/api/health status ok" \
  "curl -fsS $VERIFY_URL/api/health | jq -e '.status==\"ok\"'"
check "/api/cities lists karachi, lahore, islamabad" \
  "curl -fsS $VERIFY_URL/api/cities | jq -e '[.[].key]|sort==[\"islamabad\",\"karachi\",\"lahore\"]'"
check "seeded DB: Karachi/Clifton results are fixture ids (99xxxxxx)" \
  "curl -fsS '$VERIFY_URL/api/search?city=karachi&area=Clifton' | jq -e '.total>0 and (.results|all(.zameen_id|startswith(\"99\")))'"
asset=$(curl -fsS "$VERIFY_URL/" | grep -oE '/static/assets/index-[^"]+\.js' | head -1)
check "built JS bundle ${asset:-<none>} is served" "[ -n '$asset' ] && curl -fsS -o /dev/null $VERIFY_URL$asset"

echo "version: $(curl -fsS "$VERIFY_URL/api/health" 2>/dev/null | jq -r .version 2>/dev/null)  run: $VERIFY_RUN_ID  url: $VERIFY_URL"
[ $fail = 0 ] && echo "DOCTOR OK" || { echo "DOCTOR FAILED (server log: $VERIFY_STATE/server.log)"; exit 1; }
