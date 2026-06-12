"""Trasy odczytu zamówień klienta + dashboard dla mobilnego API (E5)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from modules.orders.models import Order
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze
from .validators import parse_int, ValidationError

ALLOWED_ORDER_TYPES = ('on_hand', 'exclusive', 'pre_order')


def _abs_image(path):
    """item.product_image_url zawiera już '/static/...' — dokleja origin (URL absolutny)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_order_brief(order):
    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_type': order.order_type,
        'status': order.status,
        'status_display_name': order.status_display_name,
        'status_badge_color': order.status_badge_color,
        'total': to_grosze(order.effective_grand_total),     # parytet z webową listą
        'items_count': order.items_count,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'offer_page_name': order.offer_page_name,
    }


@api_mobile_bp.route('/orders', methods=['GET'])
@jwt_required()
def orders_list():
    user_id = int(get_jwt_identity())
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page', default=20, min_value=1), 50)

    query = Order.query.filter_by(user_id=user_id)

    status = (request.args.get('status') or '').strip()
    if status:                                            # pass-through (parytet web; nieznany → pusto)
        query = query.filter(Order.status == status)

    order_type = (request.args.get('type') or '').strip()
    if order_type:                                        # D1(a): zamknięty enum → walidacja
        if order_type not in ALLOWED_ORDER_TYPES:
            raise ValidationError(f'Nieznany typ zamówienia: {order_type}.')
        query = query.filter(Order.order_type == order_type)

    query = query.order_by(Order.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return json_page(
        [_serialize_order_brief(o) for o in pagination.items],
        page=pagination.page, per_page=pagination.per_page,
        total=pagination.total, has_next=pagination.has_next,
    )
