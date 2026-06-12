"""Trasy odczytu zamówień klienta + dashboard dla mobilnego API (E5)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from modules.orders.models import Order
from modules.client.payment_confirmation_service import order_stage_keys
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


_STAGE_LABELS = {
    'product': 'Płatność za produkt',
    'korean_shipping': 'Wysyłka z Korei',
    'customs_vat': 'Cło i VAT',
    'domestic_shipping': 'Wysyłka krajowa',
}


def _stage_entry(stage, stage_index, name, amount, status, can_upload, deadline, conf):
    from .payments_routes import _proof_url   # import LOKALNY (uniknięcie cyklu modułów)
    return {
        'stage': stage,
        'stage_index': stage_index,
        'name': name,
        'amount': to_grosze(amount),
        'status': status,                                 # 'none'|'pending'|'approved'|'rejected'
        'can_upload': bool(can_upload),
        'deadline': deadline.isoformat() if deadline else None,
        'has_proof': bool(conf.has_proof) if conf else False,
        'proof_url': _proof_url(conf.proof_file) if (conf and conf.proof_file) else None,  # [D1=a]
        'rejection_reason': conf.rejection_reason if conf else None,
    }


def _serialize_payment_stages(order):
    """Lista etapów OBECNYCH dla zamówienia (czyta properties Order — jedno źródło prawdy).

    on_hand: E1+E4 (2). exclusive/pre_order: E1(+E2 gdy payment_stages==4)+E3+E4 (3 lub 4).
    """
    keys = order_stage_keys(order)                        # kanon obecności etapów (serwis)
    stages = []
    # E1 — zawsze
    stages.append(_stage_entry(
        'product', 'E1', _STAGE_LABELS['product'], order.effective_total,
        order.product_payment_status, order.can_upload_product_payment,
        None, order.product_payment_confirmation))
    # E2 — tylko 4-etapowe
    if 'korean_shipping' in keys:
        stages.append(_stage_entry(
            'korean_shipping', 'E2', _STAGE_LABELS['korean_shipping'], order.proxy_shipping_total,
            order.stage_2_status, order.can_upload_stage_2,
            order.get_shipping_kr_deadline(), order.stage_2_confirmation))
    # E3 — nie dotyczy on_hand
    if 'customs_vat' in keys:
        stages.append(_stage_entry(
            'customs_vat', 'E3', _STAGE_LABELS['customs_vat'], order.customs_vat_total,
            order.stage_3_status, order.can_upload_stage_3,
            order.get_customs_vat_deadline(), order.stage_3_confirmation))
    # E4 — zawsze
    stages.append(_stage_entry(
        'domestic_shipping', 'E4', _STAGE_LABELS['domestic_shipping'], order.shipping_cost,
        order.stage_4_status, order.can_upload_stage_4,
        order.get_shipping_pl_deadline(), order.stage_4_confirmation))
    return stages


def _serialize_order_item(item):
    return {
        'id': item.id,
        'product_id': item.product_id,
        'name': item.product_name,
        'sku': item.product_sku,
        'image_url': _abs_image(item.product_image_url),
        'selected_size': item.selected_size,
        'quantity': item.quantity,
        'price': to_grosze(item.price),
        'total': to_grosze(item.total),
        'is_bonus': bool(item.is_bonus),
        'is_full_set': bool(item.is_full_set),
        'set_number': item.set_number,
        'is_set_fulfilled': item.is_set_fulfilled,        # True / False / None
        'fulfilled_quantity': item.fulfilled_quantity,
    }


def _serialize_order_detail(order):
    stages = _serialize_payment_stages(order)
    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_type': order.order_type,
        'order_type_display': order.type_display_name,
        'status': order.status,
        'status_display_name': order.status_display_name,
        'status_badge_color': order.status_badge_color,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'offer_page_name': order.offer_page_name,
        'custom_name': order.custom_name,
        'notes': order.notes,
        # Finanse (grosze)
        'total_amount': to_grosze(order.total_amount),
        'shipping_cost': to_grosze(order.shipping_cost),
        'proxy_shipping_cost': to_grosze(order.proxy_shipping_cost),
        'customs_vat_cost': to_grosze(order.customs_vat_sale_cost),
        'total_to_pay': to_grosze(order.total_to_pay),
        'paid_amount': to_grosze(order.paid_amount),
        'remaining_to_pay': to_grosze(order.remaining_to_pay),
        'items': [_serialize_order_item(i) for i in order.sorted_items],
        'payment_stages': stages,
        # Faktyczna liczba etapów (surowa kolumna Order.payment_stages bywa NULL dla on_hand)
        'payment_stages_count': len(stages),
    }


def _get_owned_order_or_404(order_id):
    """Zamówienie usera z JWT albo None — cudze/nieistniejące traktujemy identycznie (bez wycieku)."""
    order = Order.query.get(order_id)
    if order is None or order.user_id != int(get_jwt_identity()):
        return None
    return order


@api_mobile_bp.route('/orders/<int:order_id>', methods=['GET'])
@jwt_required()
def order_detail(order_id):
    order = _get_owned_order_or_404(order_id)
    if order is None:
        return json_err('order_not_found', 'Zamówienie nie istnieje.', 404)
    return json_ok(_serialize_order_detail(order))


@api_mobile_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def client_dashboard():
    from modules.auth.models import User
    from modules.client.dashboard_service import get_client_dashboard_stats
    user = User.query.get(int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    stats = get_client_dashboard_stats(user)
    return json_ok({
        'orders': stats['orders'],
        'payment': {
            'paid': to_grosze(stats['payment']['paid']),
            'to_pay': to_grosze(stats['payment']['to_pay']),
        },
        'recent_orders': [_serialize_order_brief(o) for o in stats['recent_orders']['visible']],
        'recent_orders_total': stats['recent_orders']['total'],
        'chart': stats['chart_data'],
    })
