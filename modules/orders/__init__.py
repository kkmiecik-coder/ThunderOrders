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
