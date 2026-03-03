"""
Client Module
Panel klienta
"""

from flask import Blueprint, redirect, url_for
from flask_login import current_user

# Stwórz blueprint
client_bp = Blueprint('client', __name__)


@client_bp.before_request
def check_profile_completed():
    """Wymuszenie dokończenia profilu przed dostępem do panelu klienta."""
    if current_user.is_authenticated and not current_user.profile_completed:
        return redirect(url_for('auth.complete_profile'))


# Import routes na końcu, aby uniknąć circular imports
from modules.client import models
from modules.client import routes
from modules.client import shipping
from modules.client import payment_confirmations
from modules.client import collection
