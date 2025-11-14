"""
Client Module
Panel klienta
"""

from flask import Blueprint

# Stwórz blueprint
client_bp = Blueprint('client', __name__)

# Import routes na koDcu, aby unikn circular imports
from modules.client import routes
