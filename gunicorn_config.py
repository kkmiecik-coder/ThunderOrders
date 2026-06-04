"""
Gunicorn configuration for ThunderOrders production.

Multi-worker eventlet setup:
- 3 workers — każdy obsługuje WS + HTTP równolegle
- Sticky session w nginx (ip_hash) jest WYMAGANE, bo Socket.IO trzyma
  klienta na konkretnym workerze (długo żyjące WS connections)
- Redis (SOCKETIO_MESSAGE_QUEUE) jest WYMAGANE do pub/sub między workerami
  inaczej emit z workera A nie dotrze do klienta na workerze B

W razie problemu z eventletem (np. blocking I/O), można tymczasowo
zejść do workers=1 — będzie wolniej ale stabilnie (jak przed Fazą 1).
"""

bind = "127.0.0.1:8000"

# Multi-worker — wymaga Redis (message_queue) + nginx sticky session (ip_hash)
workers = 3
worker_class = "eventlet"
worker_connections = 1000

# Timeouts
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
errorlog = "/var/www/ThunderOrders/logs/gunicorn-error.log"
accesslog = "/var/www/ThunderOrders/logs/gunicorn-access.log"
# WARNING zamiast INFO — produkcja generuje masę spamu Socket.IO
loglevel = "warning"

# Wymaga zainicjalizowania eventlet na poziomie procesu (monkey patching)
# Robione przez Flask-SocketIO automatycznie przy starcie.
