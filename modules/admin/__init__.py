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
from modules.admin import payment_confirmations  # Payment confirmations admin
from modules.admin import statistics  # Statistics page
from modules.admin import popups_models  # Popup models
from modules.admin import popups  # Popup admin routes
