"""
Tracking Module
System śledzenia wizyt z kodów QR
"""

from flask import Blueprint

tracking_bp = Blueprint('tracking', __name__)

from . import routes
from . import qr_routes
