"""Trasy płatności (metody, potwierdzenia, BULK upload dowodu) dla mobilnego API (E6)."""

import os

from flask import request, current_app, send_from_directory, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename

from extensions import limiter
from modules.payments.models import PaymentMethod
from modules.orders.models import PaymentConfirmation
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze


def _abs_static(path):
    """Względny URL '/static/...' -> absolutny (kontrakt: pełne URL-e)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_payment_method(m):
    d = m.to_dict()
    return {
        'id': d['id'], 'name': d['name'], 'recipient': d['recipient'],
        'account_number': d['account_number'], 'account_number_label': d['account_number_label'],
        'code': d['code'], 'code_label': d['code_label'], 'transfer_title': d['transfer_title'],
        'additional_info': d['additional_info'], 'sort_order': d['sort_order'],
        'logo_light_url': _abs_static(d['logo_light_url']),
        'logo_dark_url': _abs_static(d['logo_dark_url']),
    }


@api_mobile_bp.route('/payment-methods', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def payment_methods():
    methods = PaymentMethod.get_active()
    return json_ok({'methods': [_serialize_payment_method(m) for m in methods]})


def _proof_url(filename):
    """Absolutny URL dowodu przez bliźniaczą trasę JWT (D1=a)."""
    if not filename:
        return None
    return request.url_root.rstrip('/') + url_for('api_mobile.serve_proof_mobile',
                                                   filename=filename)


@api_mobile_bp.route('/payment-confirmations/proof/<path:filename>', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def serve_proof_mobile(filename):
    filename = secure_filename(filename)                      # traversal-guard
    conf = PaymentConfirmation.query.filter_by(proof_file=filename).first()
    if conf is None or conf.order is None or conf.order.user_id != int(get_jwt_identity()):
        return json_err('not_found', 'Plik nie istnieje.', 404)
    folder = os.path.join(current_app.root_path, 'uploads', 'payment_confirmations')
    return send_from_directory(folder, filename)
