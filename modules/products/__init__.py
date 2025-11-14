"""
Products Module
Blueprint for product management
"""

from flask import Blueprint

products_bp = Blueprint('products', __name__, url_prefix='/admin/products')

from modules.products import routes
