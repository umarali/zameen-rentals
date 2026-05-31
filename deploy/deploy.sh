#!/bin/bash
# Quick deploy script: syncs code and restarts services
# Usage: bash deploy/deploy.sh

set -euo pipefail

HOST="ubuntu@34.196.86.31"
KEY="$HOME/.ssh/zameenrentals-key.pem"
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

# Move code and restart services
"${SSH[@]}" bash -s << 'REMOTE'
sudo rsync -a --delete \
  --exclude '.env' --exclude '.venv' --exclude 'data' \
  /tmp/zameenrentals-deploy/ /opt/zameenrentals/
sudo chown -R zrentals:zrentals /opt/zameenrentals
sudo -u zrentals /opt/zameenrentals/.venv/bin/python -m pip install \
  --disable-pip-version-check -r /opt/zameenrentals/requirements.txt
sudo systemctl restart zameenrentals-web
sudo systemctl restart zameenrentals-crawler
echo "=== Deploy complete ==="
sudo systemctl status zameenrentals-web --no-pager | head -5
sudo systemctl status zameenrentals-crawler --no-pager | head -5
REMOTE
