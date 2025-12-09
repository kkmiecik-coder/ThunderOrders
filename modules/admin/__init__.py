"""
Admin Module
Panel administratora i moderatora
"""

from flask import Blueprint

admin_bp = Blueprint('admin', __name__)

# Import routes na końcu aby uniknąć circular imports
from modules.admin import routes
from modules.admin import clients
from modules.admin import tasks
from modules.admin import exclusive
from modules.admin import models  # Admin tasks models
