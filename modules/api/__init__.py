"""
API Module
Internal API endpoints for AJAX requests
"""

from flask import Blueprint

# Create blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Import routes
from . import routes
