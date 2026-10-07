#!/usr/bin/env bash
# Drive the running instance headlessly with a steps file; evidence lands in the run's evidence dir.
# Usage: drive.sh <steps.mjs> [--mobile] [--run RUN_ID] [--fresh-user]
set -euo pipefail
. "$(dirname "$0")/_common.sh"
exec node "$(dirname "$0")/drive.mjs" "$@"
