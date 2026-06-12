"""Trasy koszyka i checkoutu on-hand dla mobilnego API."""

from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from . import api_mobile_bp
from .helpers import json_ok, to_grosze, absolute_static_url
from .validators import parse_int
from modules.client import cart_service


def _err(result):
    """Buduje kopertę błędu z opcjonalnym polem details z result.extras."""
    details = result.extras or None
    payload = {'code': result.code, 'message': result.message}
    if details:
        payload['details'] = details
    return jsonify({'success': False, 'error': payload}), result.status


def _serialize_item(d):
    """Serializuje pozycję koszyka: price PLN→grosze, image_url→absolutny URL."""
    img_url = None
    if d['image_url']:
        # build_cart_data zwraca '/static/...' — usuwamy prefix przed podaniem
        # do absolute_static_url, która sama dokłada '/static/'
        img_url = absolute_static_url(d['image_url'].removeprefix('/static/'))
    return {**d, 'price': to_grosze(d['price']), 'image_url': img_url}


# ---------------------------------------------------------------------------
# GET /shop/cart — zawartość koszyka
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/shop/cart', methods=['GET'])
@jwt_required()
def cart_get():
    user_id = int(get_jwt_identity())
    cart_data, total, count = cart_service.build_cart_data(user_id)
    return json_ok({
        'items': [_serialize_item(d) for d in cart_data],
        'total': to_grosze(total),
        'count': count,
    })


# ---------------------------------------------------------------------------
# POST /shop/cart/items — dodaj produkt do koszyka
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/shop/cart/items', methods=['POST'])
@jwt_required()
@limiter.limit("60 per minute")
def cart_add():
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    product_id = parse_int(body.get('product_id'), 'product_id', required=True)
    quantity = parse_int(body.get('quantity'), 'quantity', default=1, min_value=1)
    result = cart_service.add_to_cart(user_id, product_id, quantity)
    if not result.ok:
        return _err(result)
    return json_ok({'cart_count': result.extras['cart_count']}, 201)


# ---------------------------------------------------------------------------
# PATCH /shop/cart/items/<item_id> — zmień ilość pozycji
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/shop/cart/items/<int:item_id>', methods=['PATCH'])
@jwt_required()
@limiter.limit("60 per minute")
def cart_update(item_id):
    user_id = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    quantity = parse_int(body.get('quantity'), 'quantity', required=True)
    result = cart_service.update_cart_item(user_id, item_id, quantity)
    if not result.ok:
        return _err(result)
    return json_ok({'cart_count': result.extras['cart_count']})


# ---------------------------------------------------------------------------
# DELETE /shop/cart/items/<item_id> — usuń pozycję z koszyka
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/shop/cart/items/<int:item_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("60 per minute")
def cart_remove(item_id):
    user_id = int(get_jwt_identity())
    result = cart_service.remove_cart_item(user_id, item_id)
    if not result.ok:
        return _err(result)
    return json_ok({'cart_count': result.extras['cart_count']})


# ---------------------------------------------------------------------------
# GET /shop/checkout/summary — koszyk + adresy dostawy
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/shop/checkout/summary', methods=['GET'])
@jwt_required()
def checkout_summary():
    from modules.auth.models import ShippingAddress
    user_id = int(get_jwt_identity())
    cart_data, total, count = cart_service.build_cart_data(user_id)

    addresses = ShippingAddress.query.filter_by(
        user_id=user_id,
        is_active=True,
    ).all()

    def _serialize_address(a):
        return {
            'id': a.id,
            'address_type': a.address_type,
            'name': a.name,
            'shipping_name': a.shipping_name,
            'shipping_address': a.shipping_address,
            'shipping_postal_code': a.shipping_postal_code,
            'shipping_city': a.shipping_city,
            'shipping_voivodeship': a.shipping_voivodeship,
            'shipping_country': a.shipping_country,
            'pickup_courier': a.pickup_courier,
            'pickup_point_id': a.pickup_point_id,
            'pickup_address': a.pickup_address,
            'pickup_postal_code': a.pickup_postal_code,
            'pickup_city': a.pickup_city,
        }

    return json_ok({
        'items': [_serialize_item(d) for d in cart_data],
        'total': to_grosze(total),
        'count': count,
        'addresses': [_serialize_address(a) for a in addresses],
    })
