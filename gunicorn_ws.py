"""
Gunicorn config dla procesu Socket.IO (ThunderOrders production).

Obsługuje WYŁĄCZNIE /socket.io/* requests (route'owane przez nginx).
HTTP requesty idą do osobnego procesu (gunicorn_http.py).

1 worker eventlet — może obsłużyć tysiące jednoczesnych WS connections
przez greenlety (model async). Skalowanie do >1 workera wymagałoby ip_hash
po porcie/cookie, ale 1 worker eventlet wystarczy dla 100+ jednoczesnych
sesji (ograniczenie to RAM, nie CPU/IO).

Uruchamianie:
  gunicorn -c gunicorn_ws.py wsgi_ws:application
"""

bind = "127.0.0.1:8001"

workers = 1
worker_class = "eventlet"
worker_connections = 2000

# Timeouts — WS connections są długo żyjące, ping_interval=25s w SocketIO
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
import os as _os
_log_dir = _os.environ.get("GUNICORN_LOG_DIR", "/var/www/ThunderOrders/logs")
errorlog = f"{_log_dir}/gunicorn-ws-error.log"
accesslog = f"{_log_dir}/gunicorn-ws-access.log"
loglevel = "warning"
