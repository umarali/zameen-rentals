#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/zameenrentals-bootstrap.log) 2>&1

echo "=== ZameenRentals Bootstrap ==="

# System packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y caddy python3-venv rsync sqlite3 ufw lsof

# Firewall: SSH and web only (DigitalOcean Droplets have no firewall by default).
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Backup credentials for S3-compatible storage (Spaces); filled in by hand.
install -d -m 700 /etc/zameenrentals
[ -f /etc/zameenrentals/backup.env ] || install -m 600 /dev/null /etc/zameenrentals/backup.env

# Create app user
id -u zrentals >/dev/null 2>&1 || useradd -m -s /bin/bash zrentals

# Data directory on the root volume (persists with the server)
install -d -o zrentals -g zrentals /opt/zameenrentals
install -d -o zrentals -g zrentals /opt/zameenrentals/data
python3 -m venv /opt/zameenrentals/.venv
chown -R zrentals:zrentals /opt/zameenrentals/.venv

cat > /etc/systemd/system/zameenrentals-web.service <<'UNIT'
[Unit]
Description=ZameenRentals web application
After=network.target

[Service]
Type=simple
User=zrentals
Group=zrentals
WorkingDirectory=/opt/zameenrentals
EnvironmentFile=-/opt/zameenrentals/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/zameenrentals/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/zameenrentals-crawler.service <<'UNIT'
[Unit]
Description=ZameenRentals crawler
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=zrentals
Group=zrentals
WorkingDirectory=/opt/zameenrentals
EnvironmentFile=-/opt/zameenrentals/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/zameenrentals/.venv/bin/python -m app.crawler
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT

# zameenrental.com is the primary host (DNS on Cloudflare, DNS-only records).
# www and the old zameenrentals.emerssive.com address redirect to it.
cat > /etc/caddy/Caddyfile <<'CADDY'
(app) {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8000

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "strict-origin-when-cross-origin"
	}
}

zameenrental.com {
	import app
}

www.zameenrental.com {
	redir https://zameenrental.com{uri} permanent
}

zameenrentals.emerssive.com {
	redir https://zameenrental.com{uri} permanent
}
CADDY

# --- Daily SQLite backup to S3-compatible storage -----------------------------
# WAL-safe snapshot -> gzip -> upload to <bucket>/backups/. On AWS, auth is the
# instance IAM role; on DigitalOcean, Spaces keys in /etc/zameenrentals/backup.env.
# Canonical source: deploy/backup/ (tests check the copy below matches).
# boto3 is installed into the venv by requirements.txt on the first code deploy.
install -d /usr/local/bin
cat > /usr/local/bin/zameenrentals-backup.py <<'PYEOF'
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
PYEOF
chmod 755 /usr/local/bin/zameenrentals-backup.py

cat > /etc/systemd/system/zameenrentals-backup.service <<'UNIT'
[Unit]
Description=ZameenRentals daily SQLite backup to S3-compatible storage
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=zrentals
Group=zrentals
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-/etc/zameenrentals/backup.env
ExecStart=/opt/zameenrentals/.venv/bin/python /usr/local/bin/zameenrentals-backup.py
UNIT

cat > /etc/systemd/system/zameenrentals-backup.timer <<'UNIT'
[Unit]
Description=Run the ZameenRentals DB backup daily

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
# Enabled for later boots only. The backup timer is started by deploy/deploy.sh
# once the code and venv it runs from are installed.
systemctl enable caddy zameenrentals-web zameenrentals-crawler zameenrentals-backup.timer
systemctl restart caddy

echo "=== Bootstrap complete, waiting for code deploy ==="
