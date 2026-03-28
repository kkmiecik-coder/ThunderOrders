#!/bin/bash
# ThunderOrders Auto-Deploy Script
# Called by GitHub webhook after push to main

LOCK_FILE="/tmp/thunderorders-deploy.lock"
APP_DIR="/var/www/ThunderOrders"
LOG_PREFIX="[DEPLOY $(date '+%Y-%m-%d %H:%M:%S')]"

# Prevent concurrent deploys
if [ -f "$LOCK_FILE" ]; then
    echo "$LOG_PREFIX Already deploying, skipping."
    exit 0
fi
trap "rm -f $LOCK_FILE" EXIT
touch "$LOCK_FILE"

echo "$LOG_PREFIX Starting deploy..."

cd "$APP_DIR" || exit 1

echo "$LOG_PREFIX Pulling latest code..."
git pull origin main 2>&1

echo "$LOG_PREFIX Installing dependencies..."
source venv/bin/activate
pip install -r requirements.txt --quiet 2>&1

echo "$LOG_PREFIX Running migrations..."
flask db upgrade 2>&1

echo "$LOG_PREFIX Restarting application..."
sudo systemctl restart thunderorders 2>&1

echo "$LOG_PREFIX Deploy complete!"
