#!/usr/bin/env bash
# Tear down instances this skill started. Never touches other processes; never deletes evidence.
# Usage: cleanup.sh [RUN_ID]   (default: newest live run)
#        cleanup.sh --all      (every live run, e.g. residue from failed iterations)
set -uo pipefail
. "$(dirname "$0")/_common.sh"

teardown() {
  resolve_run "$1" || return 1
  local dbdir=""
  if is_our_server "$VERIFY_PID"; then
    # serve_playwright.py's TemporaryDirectory; recorded so we can confirm it's gone.
    dbdir=$(lsof -p "$VERIFY_PID" -Fn 2>/dev/null | sed -n 's/^n\(.*zameen-playwright-[^/]*\).*/\1/p' | head -1)
    kill -TERM "$VERIFY_PID"
    for _ in $(seq 1 20); do kill -0 "$VERIFY_PID" 2>/dev/null || break; sleep 0.5; done
    if kill -0 "$VERIFY_PID" 2>/dev/null; then
      echo "pid $VERIFY_PID ignored SIGTERM; sending SIGKILL (it is ours)"
      kill -KILL "$VERIFY_PID"
    fi
  elif kill -0 "$VERIFY_PID" 2>/dev/null; then
    echo "pid $VERIFY_PID is alive but is not serve_playwright.py (PID reused?) — leaving it alone"
  fi

  mkdir -p "$VERIFY_EVIDENCE"
  cp "$VERIFY_STATE/server.log" "$VERIFY_EVIDENCE/server.log" 2>/dev/null || true
  rm -rf "$VERIFY_STATE"

  lsof -nP -iTCP:"$VERIFY_PORT" -sTCP:LISTEN -t >/dev/null 2>&1 \
    && echo "WARN  port $VERIFY_PORT still has a listener" || echo "ok    port $VERIFY_PORT free"
  # uvicorn re-raises SIGTERM after shutdown, so serve_playwright.py's TemporaryDirectory
  # never runs its cleanup. Remove the one dir our PID held open — nothing else.
  case "$dbdir" in
    */zameen-playwright-*) rm -rf "$dbdir"
      [ -e "$dbdir" ] && echo "WARN  temp DB dir still exists: $dbdir" || echo "ok    temp DB dir removed" ;;
  esac
  local n
  n=$(find "$VERIFY_EVIDENCE" -type f | wc -l | tr -d ' ')
  if [ "$n" -gt 0 ]; then echo "ok    evidence kept: $VERIFY_EVIDENCE ($n files)"
  else echo "WARN  evidence dir is empty: $VERIFY_EVIDENCE"; fi
}

if [ "${1:-}" = "--all" ]; then
  for run in $(ls -1 "$STATE_ROOT" 2>/dev/null); do echo "== $run"; teardown "$run"; done
else
  teardown "${1:-}"
fi
