from flask import jsonify
from . import payments_bp
from .models import PaymentMethod

@payments_bp.route('/api/payment-methods/active')
def api_get_active_payment_methods():
    """API: zwraca aktywne metody płatności"""
    methods = PaymentMethod.get_active()
    return jsonify([method.to_dict() for method in methods])
