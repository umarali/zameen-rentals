#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/zameenrentals-bootstrap.log) 2>&1

echo "=== ZameenRentals Bootstrap ==="

# System packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y caddy python3-venv rsync

# Create app user
id -u zrentals >/dev/null 2>&1 || useradd -m -s /bin/bash zrentals

# Create data directory on root volume (EBS-backed, persists with instance)
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

cat > /etc/caddy/Caddyfile <<'CADDY'
zameenrentals.emerssive.com {
	encode zstd gzip
	reverse_proxy 127.0.0.1:8000

	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		X-Frame-Options "DENY"
		Referrer-Policy "strict-origin-when-cross-origin"
	}
}
CADDY

systemctl daemon-reload
systemctl enable caddy zameenrentals-web zameenrentals-crawler
systemctl restart caddy

echo "=== Bootstrap complete, waiting for code deploy ==="
