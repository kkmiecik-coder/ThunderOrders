#!/bin/bash
# ThunderOrders Auto-Deploy Script
# Called by GitHub webhook after push to main

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

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
# Architektura rozdzielona (2026-06-04): HTTP (gthread) + WS (eventlet/Socket.IO).
# Stara monolityczna usługa `thunderorders` jest martwa (disabled) — NIE restartować jej tutaj,
# bo failuje z "Connection in use: 8000" i nie przeładowuje żywych procesów.
# UWAGA: dwie osobne komendy, bo reguła sudoers NOPASSWD dopasowuje dokładne wywołanie
# per usługa (`systemctl restart thunderorders-http` i `...-ws` osobno).
#
# Zwolnij lock PRZED restartem: ten skrypt biegnie w cgroupie usługi thunderorders-http
# (webhook obsługiwany przez tę samą usługę), więc restart ubija deploy.sh (SIGTERM,
# "Terminated") zanim trap EXIT zdąży usunąć lock. Bez tego lock zostaje osierocony i
# blokuje WSZYSTKIE kolejne deploye ("Already deploying, skipping"). Usuwamy go tutaj,
# żeby kolejny push wszedł nawet gdy ten proces nie dożyje do trap-a.
rm -f "$LOCK_FILE"
# KOLEJNOŚĆ KRYTYCZNA: najpierw -ws, potem -http. Ten skrypt biegnie w cgroupie
# thunderorders-http, więc restart -http ubija go natychmiast (SIGTERM) — linia
# wykonana PO restarcie -http nigdy się nie wykona. Przy starej kolejności -ws
# nie był restartowany NIGDY (potwierdzone 2026-06-12: ws działał na kodzie
# sprzed 10h mimo deployu) i procesy serwowały rozjechane wersje kodu.
sudo systemctl restart thunderorders-ws 2>&1
sudo systemctl restart thunderorders-http 2>&1

echo "$LOG_PREFIX Deploy complete!"
