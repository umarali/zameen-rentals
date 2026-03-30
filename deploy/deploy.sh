#!/bin/bash
# Quick deploy script: syncs code and restarts services
# Usage: bash deploy/deploy.sh

set -euo pipefail

HOST="ec2-user@34.196.86.31"
KEY="~/.ssh/zameenrentals-key.pem"
SSH="ssh -i $KEY $HOST"

echo "=== Deploying to $HOST ==="

# Sync code
rsync -avz --progress \
  -e "ssh -i $KEY" \
  --exclude '.git' --exclude 'node_modules' --exclude 'test-results' \
  --exclude 'tests' --exclude '__pycache__' --exclude '.env' \
  --exclude 'data/*.db*' --exclude 'deploy' --exclude '.claude' \
  --exclude 'package*.json' --exclude 'playwright.config.js' \
  ./ $HOST:/tmp/zameenrentals-deploy/

# Move code and restart services
$SSH bash -s << 'REMOTE'
sudo rsync -a /tmp/zameenrentals-deploy/ /opt/zameenrentals/
sudo chown -R zrentals:zrentals /opt/zameenrentals
sudo systemctl restart zameenrentals-web
sudo systemctl restart zameenrentals-crawler
echo "=== Deploy complete ==="
sudo systemctl status zameenrentals-web --no-pager | head -5
sudo systemctl status zameenrentals-crawler --no-pager | head -5
REMOTE
