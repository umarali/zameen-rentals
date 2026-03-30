#!/bin/bash
set -euo pipefail
exec > /var/log/user-data.log 2>&1

echo "=== ZameenRentals Bootstrap ==="

# System packages
dnf update -y
dnf install -y python3.11 python3.11-pip git

# Install Caddy
dnf install -y 'dnf-command(copr)'
dnf copr enable -y @caddy/caddy
dnf install -y caddy

# Create app user
useradd -m -s /bin/bash zrentals || true

# Create data directory on root volume (EBS-backed, persists with instance)
mkdir -p /opt/zameenrentals/data
chown -R zrentals:zrentals /opt/zameenrentals

echo "=== Bootstrap complete, waiting for code deploy ==="
