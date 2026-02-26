"""
Moduł publiczny
Strony dostępne bez logowania (kolekcja publiczna, upload QR)
"""

from flask import Blueprint

public_bp = Blueprint('public', __name__)

from modules.public import routes
