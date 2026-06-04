"""
WSGI entry point dla procesu HTTP (gthread workers).

NIE robi eventlet monkey_patch — HTTP korzysta ze standardowych threadów.
SocketIO jest zainicjalizowane (potrzebne do socketio.emit() przez Redis
message_queue do procesu WS), ale ten proces NIE obsługuje /socket.io/*
requestów — kieruje je nginx do osobnego procesu (wsgi_ws.py).
"""

from app import create_app

application = create_app()
