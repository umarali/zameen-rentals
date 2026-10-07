# Shared by launch/doctor/cleanup/drive. Source it; don't run it.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel)
ARTIFACTS="$ROOT/.verify-artifacts"
STATE_ROOT="$ARTIFACTS/.state"
NODE22_BIN="$HOME/.nvm/versions/node/v22.13.0/bin"
[ -d "$NODE22_BIN" ] && export PATH="$NODE22_BIN:$PATH"

# Resolve a run's state dir: explicit RUN_ID arg, else the newest live run.
resolve_run() {
  local run="${1:-}"
  if [ -z "$run" ]; then
    run=$(ls -1t "$STATE_ROOT" 2>/dev/null | head -1 || true)
  fi
  if [ -z "$run" ] || [ ! -f "$STATE_ROOT/$run/env" ]; then
    echo "No verification instance found${1:+ for run $1}. Start one with launch.sh." >&2
    return 1
  fi
  # shellcheck disable=SC1090
  . "$STATE_ROOT/$run/env"
}

# True when PID is alive AND is our serve_playwright.py (guards against PID reuse).
is_our_server() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null && ps -o command= -p "$pid" | grep -q "tests/serve_playwright.py"
}
