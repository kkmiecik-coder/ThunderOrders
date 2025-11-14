"""
Auth Module
ModuB autentykacji: logowanie, rejestracja, reset hasBa
"""

from flask import Blueprint

# Stwórz blueprint
auth_bp = Blueprint('auth', __name__)

# Import routes na koDcu, aby unikn circular imports
from modules.auth import routes
