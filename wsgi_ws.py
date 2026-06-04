"""
WSGI entry point dla procesu Socket.IO (eventlet workers).

KRYTYCZNE: monkey_patch MUSI być przed jakimkolwiek innym importem,
inaczej eventlet nie pacthuje standardowych socket/threading API
i WebSockety się rozpadają pod obciążeniem.

Ten proces obsługuje WYŁĄCZNIE /socket.io/* requests (kierowane przez
nginx). HTTP traffic idzie do osobnego procesu (wsgi.py).
"""

import eventlet
eventlet.monkey_patch()

from app import create_app

application = create_app()
