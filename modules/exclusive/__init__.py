"""
Exclusive Module
Modul obslugi stron ekskluzywnych zamowien (pre-order)
"""

from flask import Blueprint

exclusive_bp = Blueprint('exclusive', __name__, url_prefix='/exclusive')

from . import routes
