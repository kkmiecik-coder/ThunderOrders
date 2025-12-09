"""
Profile Module
Zarządzanie profilem użytkownika (wspólne dla wszystkich ról)
"""

from flask import Blueprint

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')

from modules.profile import routes
