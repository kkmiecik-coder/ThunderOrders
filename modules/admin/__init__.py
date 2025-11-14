"""
Admin Module
Panel administratora i moderatora
"""

from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

# Import routes na koDcu aby unikn circular imports
from modules.admin import routes
