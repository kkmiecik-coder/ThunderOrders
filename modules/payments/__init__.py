from flask import Blueprint

payments_bp = Blueprint('payments', __name__)

from . import routes

# Import SocketIO event handlers
from . import socket_events
