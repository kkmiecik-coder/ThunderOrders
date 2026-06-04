"""
Gunicorn config dla procesu HTTP (ThunderOrders production).

Obsługuje WSZYSTKIE endpointy HTTP poza /socket.io/* (te nginx rutuje
do osobnego procesu Socket.IO — patrz gunicorn_ws.py).

gthread workers (zwykłe threading), 3 procesy x 8 threadów = 24 jednoczesnych
żądań. Pod obciążeniem 30+ userów to wystarczy — większość requestów to
szybkie endpointy (<100ms). Wolne queries (np. /availability po Fazie 1 ma
9 queries) nie blokują innych workerów bo każdy ma własny threadpool.

Uruchamianie:
  gunicorn -c gunicorn_http.py wsgi:application
"""

bind = "127.0.0.1:8000"

# gthread = threading model — nie wymaga eventlet monkey_patch
workers = 3
worker_class = "gthread"
threads = 8

# Timeouts
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging — ścieżki override przez env vars dla lokalnych testów
import os as _os
_log_dir = _os.environ.get("GUNICORN_LOG_DIR", "/var/www/ThunderOrders/logs")
errorlog = f"{_log_dir}/gunicorn-http-error.log"
accesslog = f"{_log_dir}/gunicorn-http-access.log"
loglevel = "warning"
