"""
Admin Module
Panel administratora i moderatora
"""

from flask import Blueprint, redirect, url_for
from flask_login import current_user

admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
def check_profile_completed():
    """Wymuszenie dokończenia profilu przed dostępem do panelu admina."""
    if current_user.is_authenticated and not current_user.profile_completed:
        return redirect(url_for('auth.complete_profile'))


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
from modules.admin import broadcasts  # Broadcast notifications admin
