"""
Orders Module
=============

Blueprint for orders management.
Handles both admin and client order operations.
"""

from flask import Blueprint

# Create blueprint
orders_bp = Blueprint('orders', __name__)

# Import routes (at the end to avoid circular imports)
from modules.orders import routes

# Import WMS routes
from modules.orders import wms

# Import WMS models so Flask-Migrate can discover them
from modules.orders import wms_models

# Import WMS SocketIO event handlers
from modules.orders import wms_events
