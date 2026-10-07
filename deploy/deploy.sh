#!/bin/bash
# Quick deploy script: syncs the LOCAL WORKING TREE (not git) and restarts services.
# Usage:
#   ZR_DEPLOY_HOST=root@<droplet-ip> ZR_DEPLOY_KEY=~/.ssh/id_ed25519 bash deploy/deploy.sh
# The remote user needs passwordless sudo (root on a fresh Droplet, ubuntu on EC2).

set -euo pipefail

HOST="${ZR_DEPLOY_HOST:?Set ZR_DEPLOY_HOST, e.g. root@203.0.113.10}"
KEY="${ZR_DEPLOY_KEY:-$HOME/.ssh/id_ed25519}"
SSH=(ssh -i "$KEY" "$HOST")

echo "=== Deploying to $HOST ==="

# Build the production frontend locally so static/assets is always current.
npm run build

# Sync code
rsync -avz --progress \
  --delete --delete-excluded \
  -e "ssh -i $KEY" \
  --exclude '.git' --exclude 'node_modules' --exclude 'test-results' \
  --exclude 'playwright-report' --exclude '.pytest_cache' --exclude 'tools/qa_verify_out' \
  --exclude 'tests' --exclude '__pycache__' --exclude '.env' --exclude '.venv' \
  --exclude 'data/*.db*' --exclude 'data/vapid_private.pem' --exclude 'data/vapid_public.txt' \
  --exclude 'deploy' --exclude '.claude' \
  --exclude 'package*.json' --exclude 'playwright.config.js' \
  ./ $HOST:/tmp/zameenrentals-deploy/

# deploy/ is excluded above; ship the restore tool on its own.
rsync -az -e "ssh -i $KEY" deploy/backup/zameenrentals-restore.sh $HOST:/tmp/zameenrentals-restore.sh

# Move code and restart services
"${SSH[@]}" bash -s << 'REMOTE'
sudo rsync -a --delete \
  --exclude '.env' --exclude '.venv' --exclude 'data' \
  /tmp/zameenrentals-deploy/ /opt/zameenrentals/
sudo chown -R zrentals:zrentals /opt/zameenrentals
sudo install -m 755 /tmp/zameenrentals-restore.sh /usr/local/bin/zameenrentals-restore
sudo -u zrentals /opt/zameenrentals/.venv/bin/python -m pip install \
  --disable-pip-version-check -r /opt/zameenrentals/requirements.txt
sudo systemctl restart zameenrentals-web
sudo systemctl restart zameenrentals-crawler
# The backup needs the venv and code installed above, so start its timer only
# now. user-data.sh enables it for boot but doesn't start it.
sudo systemctl enable --now zameenrentals-backup.timer
next_run="$(sudo systemctl show zameenrentals-backup.timer -p NextElapseUSecRealtime --value)"
if ! sudo systemctl is-active --quiet zameenrentals-backup.timer || [ -z "$next_run" ]; then
  echo "ERROR: zameenrentals-backup.timer is not active or has no next run" >&2
  exit 1
fi
echo "=== Deploy complete. Next backup: $next_run ==="
sudo systemctl status zameenrentals-web --no-pager | head -5
sudo systemctl status zameenrentals-crawler --no-pager | head -5
REMOTE
