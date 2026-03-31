"""
Offers Module
Moduł obsługi stron sprzedaży (exclusive, pre-order)
"""

from flask import Blueprint

offers_bp = Blueprint('offers', __name__, url_prefix='/offer')

from . import routes

# Import SocketIO event handlers for offers LIVE dashboard
from . import socket_events
