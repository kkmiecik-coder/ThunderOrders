"""
Feedback Module
System ankiet i zbierania opinii od użytkowników
"""

from flask import Blueprint

feedback_bp = Blueprint('feedback', __name__)

from . import routes
