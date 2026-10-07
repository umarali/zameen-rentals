#!/bin/bash
# Restore (or seed) the production SQLite database from a snapshot.
#
#   sudo zameenrentals-restore /tmp/zameenrentals-YYYY-MM-DD.db[.gz]
#
# Order matters. SQLite keeps recent writes in <db>-wal and <db>-shm next to
# the database, and every open connection maps them. Copying a snapshot over a
# database that any process still has open, or leaving the old -wal beside the
# new file, can corrupt it. So this script:
#   1. verifies the snapshot before touching anything,
#   2. stops every database user: backup timer and any running backup job,
#      crawler, web,
#   3. waits until no process has the database files open,
#   4. moves the old .db, -wal and -shm together into data/pre-restore-<time>/,
#   5. installs the snapshot and verifies it in place,
#   6. starts web and crawler, then the backup timer, and checks all three.
# If verification fails in step 5, services stay stopped and the old files stay
# in the pre-restore folder for a manual decision.
#
# Overrides (for tests): ZR_DATA_DIR, ZR_SYSTEMCTL, ZR_SERVICE_USER,
# ZR_RESTORE_ALLOW_NONROOT=1, ZR_WAIT_SECONDS.
set -euo pipefail

SNAPSHOT="${1:?usage: zameenrentals-restore <snapshot.db | snapshot.db.gz>}"
DATA_DIR="${ZR_DATA_DIR:-/opt/zameenrentals/data}"
SYSTEMCTL="${ZR_SYSTEMCTL:-systemctl}"
SERVICE_USER="${ZR_SERVICE_USER:-zrentals}"
WAIT_SECONDS="${ZR_WAIT_SECONDS:-60}"
DB="$DATA_DIR/zameenrentals.db"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [[ "$(id -u)" != 0 && "${ZR_RESTORE_ALLOW_NONROOT:-}" != 1 ]]; then
  echo "Run as root (sudo): it stops services and changes file ownership." >&2
  exit 1
fi

verify() {  # verify <db-file>: integrity ok and at least one listing
  local result count
  result="$(sqlite3 -readonly "$1" 'PRAGMA integrity_check;' 2>&1 | head -1)"
  [[ "$result" == "ok" ]] || { echo "Integrity check failed for $1: $result" >&2; return 1; }
  count="$(sqlite3 -readonly "$1" 'SELECT COUNT(*) FROM listings;' 2>&1)"
  [[ "$count" =~ ^[0-9]+$ && "$count" -gt 0 ]] || { echo "No listings in $1 ($count)" >&2; return 1; }
  echo "$count"
}

# 1. Verify the snapshot before stopping anything.
if [[ "$SNAPSHOT" == *.gz ]]; then
  gunzip -c "$SNAPSHOT" > "$WORK/snapshot.db"
else
  cp "$SNAPSHOT" "$WORK/snapshot.db"
fi
LISTINGS="$(verify "$WORK/snapshot.db")"
echo "Snapshot OK: $LISTINGS listings"

# 2. Stop every database user. The timer first, so it can't start a new job.
"$SYSTEMCTL" stop zameenrentals-backup.timer
"$SYSTEMCTL" stop zameenrentals-backup.service
"$SYSTEMCTL" stop zameenrentals-crawler
"$SYSTEMCTL" stop zameenrentals-web

# 3. Wait until nothing has the database open.
in_use() {
  command -v lsof >/dev/null || return 1
  local files=()
  for f in "$DB" "$DB-wal" "$DB-shm"; do [[ -e "$f" ]] && files+=("$f"); done
  (( ${#files[@]} )) || return 1
  lsof -t "${files[@]}" 2>/dev/null | grep -q .
}
for (( i = 0; i < WAIT_SECONDS; i++ )); do
  in_use || break
  sleep 1
done
if in_use; then
  echo "Database still open after ${WAIT_SECONDS}s; services are stopped, nothing was replaced." >&2
  lsof "$DB"* >&2 || true
  exit 1
fi

# 4. Keep the old database and its WAL files together.
BACKUP_DIR="$DATA_DIR/pre-restore-$STAMP"
moved=0
for f in "$DB" "$DB-wal" "$DB-shm"; do
  if [[ -e "$f" ]]; then
    mkdir -p "$BACKUP_DIR"
    mv "$f" "$BACKUP_DIR/"
    moved=1
  fi
done
(( moved )) && echo "Old database files kept in $BACKUP_DIR" || echo "No existing database (fresh install)"

# 5. Install the snapshot, then verify it in place before restarting.
install -m 640 "$WORK/snapshot.db" "$DB.restore-tmp"
if [[ "$(id -u)" == 0 ]]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$DB.restore-tmp"
fi
mv "$DB.restore-tmp" "$DB"
if ! verify "$DB" >/dev/null; then
  echo "Installed database failed verification; services left stopped. Old files: $BACKUP_DIR" >&2
  exit 1
fi

# 6. Start the services, then the backup timer, and check them.
"$SYSTEMCTL" start zameenrentals-web
"$SYSTEMCTL" start zameenrentals-crawler
"$SYSTEMCTL" start zameenrentals-backup.timer
for unit in zameenrentals-web zameenrentals-crawler zameenrentals-backup.timer; do
  "$SYSTEMCTL" is-active --quiet "$unit" || { echo "$unit is not active" >&2; exit 1; }
done
echo "Restore complete: $LISTINGS listings. Services and backup timer are active."
