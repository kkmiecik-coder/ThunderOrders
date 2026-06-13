"""Trasy wysyłki (adresy + zlecenia) dla mobilnego API (E7)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.auth.models import User
from modules.client import shipping_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err


def _serialize_address(a):
    return {
        'id': a.id, 'address_type': a.address_type, 'name': a.name,
        'display_name': a.display_name, 'full_address': a.full_address,
        'is_default': bool(a.is_default),
        'shipping_name': a.shipping_name, 'shipping_address': a.shipping_address,
        'shipping_postal_code': a.shipping_postal_code, 'shipping_city': a.shipping_city,
        'shipping_voivodeship': a.shipping_voivodeship, 'shipping_country': a.shipping_country,
        'pickup_courier': a.pickup_courier, 'pickup_point_id': a.pickup_point_id,
        'pickup_address': a.pickup_address, 'pickup_postal_code': a.pickup_postal_code,
        'pickup_city': a.pickup_city,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    }


@api_mobile_bp.route('/shipping/addresses', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_addresses_list():
    addrs = svc.list_active_addresses(int(get_jwt_identity()))
    return json_ok({'addresses': [_serialize_address(a) for a in addrs]})


@api_mobile_bp.route('/shipping/addresses', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_create():
    data = request.get_json(silent=True) or {}
    ok, err = svc.validate_address_payload(data)
    if not ok:
        if err['code'] == 'invalid_address_type':
            return json_err('invalid_input', 'Nieprawidłowy typ adresu.', 400,
                            details={'allowed': ['home', 'pickup_point']})
        return json_err('invalid_input', f"Pole {err['field']} jest wymagane.", 400,
                        details={'field': err['field']})
    user = User.query.get(int(get_jwt_identity()))
    _, _, addr = svc.create_address(user, data)
    return json_ok({'address': _serialize_address(addr)}, 201)


@api_mobile_bp.route('/shipping/addresses/<int:address_id>/default', methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_set_default(address_id):
    ok, err, addr = svc.set_default_address(int(get_jwt_identity()), address_id)
    if not ok:
        return json_err('address_not_found', 'Adres nie istnieje.', 404)
    return json_ok({'address': _serialize_address(addr)})


@api_mobile_bp.route('/shipping/addresses/<int:address_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_delete(address_id):
    ok, err = svc.soft_delete_address(int(get_jwt_identity()), address_id)
    if not ok:
        return json_err('address_not_found', 'Adres nie istnieje.', 404)
    return json_ok({'deleted': True})
