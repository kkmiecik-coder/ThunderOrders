"""
Serwer deweloperski z działającymi WebSocketami.

`python app.py` startuje bez eventletowego monkey_patch, a Socket.IO ma
skonfigurowaną kolejkę na Redisie (SOCKETIO_MESSAGE_QUEUE). Redis pod eventletem
bez załatanych bibliotek sieciowych rzuca "Redis requires a monkey patched socket
library" — połączenie WS pada, a serwer przestaje odpowiadać na kolejne żądania.
W efekcie WMS (pakowanie, odhaczanie pozycji) zawiesza się lokalnie.

Ten entry point robi monkey_patch przed importem aplikacji — tak samo jak
wsgi_ws.py na produkcji — więc WebSockety działają jak w prawdziwym środowisku.

Uruchomienie: python run_dev.py
"""

import eventlet
eventlet.monkey_patch()

from app import create_app  # noqa: E402  (import musi być PO monkey_patch)
from extensions import socketio  # noqa: E402

if __name__ == '__main__':
    app = create_app()
    socketio.run(app, host='0.0.0.0', port=5001, debug=True,
                 allow_unsafe_werkzeug=True)
