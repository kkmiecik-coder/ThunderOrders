"""Trasy wysyłki (adresy + zlecenia) dla mobilnego API (E7)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.auth.models import User
from modules.client import shipping_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze


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


# ============================================================================
# ZLECENIA WYSYŁKI — odczyt
# ============================================================================

def _abs_image(path):
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_available_order(order):
    return {
        'id': order.id, 'order_number': order.order_number,
        'total_amount': to_grosze(order.total_amount),
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'items_count': order.items_count,
        'items': [{'name': it.product_name, 'selected_size': it.selected_size,
                   'image_url': _abs_image(it.product_image_url),
                   'quantity': it.quantity, 'price': to_grosze(it.price)}
                  for it in order.items if it.quantity > 0],
    }


def _serialize_request(req):
    return {
        'id': req.id, 'request_number': req.request_number, 'status': req.status,
        'status_display_name': req.status_display_name, 'status_badge_color': req.status_badge_color,
        'address_type': req.address_type, 'short_address': req.short_address,
        'full_address': req.full_address,
        'total_shipping_cost': to_grosze(req.calculated_shipping_cost),
        'tracking_number': req.tracking_number, 'tracking_url': req.tracking_url,
        'can_cancel': req.can_cancel, 'orders_count': req.orders_count,
        'orders': [{'id': o.id, 'order_number': o.order_number} for o in req.orders],
        'created_at': req.created_at.isoformat() if req.created_at else None,
    }


@api_mobile_bp.route('/shipping/requests/available-orders', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_available_orders():
    orders = svc.get_available_orders(int(get_jwt_identity()))
    return json_ok({'orders': [_serialize_available_order(o) for o in orders]})


@api_mobile_bp.route('/shipping/requests', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_requests_list():
    from modules.orders.models import ShippingRequest
    reqs = ShippingRequest.query.filter_by(user_id=int(get_jwt_identity())).order_by(
        ShippingRequest.created_at.desc()).all()
    return json_ok({'requests': [_serialize_request(r) for r in reqs]})
