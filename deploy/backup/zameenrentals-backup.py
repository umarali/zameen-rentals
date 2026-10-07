#!/usr/bin/env python3
"""Daily backup of the ZameenRentals SQLite DB to S3.

Takes a WAL-safe consistent snapshot via the sqlite3 online backup API,
gzips it, and uploads to s3://<bucket>/backups/zameenrentals-YYYY-MM-DD.db.gz.

Invoked by the zameenrentals-backup.timer systemd unit (daily).

Works with any S3-compatible store:
- AWS S3: credentials from the instance IAM role via IMDS; leave
  ZR_BACKUP_ENDPOINT unset.
- DigitalOcean Spaces (or another S3-compatible store): set ZR_BACKUP_ENDPOINT,
  e.g. https://fra1.digitaloceanspaces.com, plus AWS_ACCESS_KEY_ID and
  AWS_SECRET_ACCESS_KEY, in /etc/zameenrentals/backup.env (mode 600).
"""
import datetime as dt
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile

import boto3

DB_PATH = os.environ.get("ZR_DB_PATH", "/opt/zameenrentals/data/zameenrentals.db")
BUCKET = os.environ.get("ZR_BACKUP_BUCKET", "zameenrentals")
PREFIX = os.environ.get("ZR_BACKUP_PREFIX", "backups")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ENDPOINT = os.environ.get("ZR_BACKUP_ENDPOINT") or None


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"ERROR: database not found at {DB_PATH}", file=sys.stderr)
        return 1

    date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    key = f"{PREFIX}/zameenrentals-{date}.db.gz"
    tmpdir = tempfile.mkdtemp(prefix="zr-backup-")
    snapshot = os.path.join(tmpdir, "snapshot.db")
    archive = snapshot + ".gz"

    try:
        # Consistent snapshot of the live DB (safe while the crawler writes).
        src = sqlite3.connect(DB_PATH, timeout=60)
        try:
            dst = sqlite3.connect(snapshot)
            with dst:
                src.backup(dst)
            dst.close()
        finally:
            src.close()

        with open(snapshot, "rb") as f_in, gzip.open(archive, "wb", compresslevel=6) as f_out:
            shutil.copyfileobj(f_in, f_out)

        size_mb = os.path.getsize(archive) / 1_048_576
        boto3.client("s3", region_name=REGION, endpoint_url=ENDPOINT).upload_file(archive, BUCKET, key)
        print(f"OK: uploaded s3://{BUCKET}/{key} ({size_mb:.1f} MiB)")
        return 0
    except Exception as exc:  # noqa: BLE001 - log and exit non-zero for systemd
        print(f"ERROR: backup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
