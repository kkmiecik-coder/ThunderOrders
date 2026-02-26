"""
Client Module
Panel klienta
"""

from flask import Blueprint

# Stwórz blueprint
client_bp = Blueprint('client', __name__)

# Import routes na końcu, aby uniknąć circular imports
from modules.client import models
from modules.client import routes
from modules.client import shipping
from modules.client import payment_confirmations
from modules.client import collection
