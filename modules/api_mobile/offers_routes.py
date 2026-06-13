"""Trasy stron ofertowych (exclusive + preorder read + availability) dla mobilnego API — E3."""
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import db, limiter
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze, absolute_static_url
from .validators import parse_int, ValidationError
from .idempotency import idempotent
from modules.offers.models import OfferPage
from modules.auth.models import User
from modules.client import shop_service  # slugify

# Mapowanie kontrakt → enum bazy (D1: live obejmuje active + paused)
_STATUS_MAP = {
    'live': ('active', 'paused'),
    'upcoming': ('scheduled',),
    'closed': ('ended',),
}


def _public_status(page):
    if page.status in ('active', 'paused'):
        return 'live'
    if page.status == 'scheduled':
        return 'upcoming'
    return 'closed'  # ended


def _serialize_page_summary(page):
    return {
        'token': page.token,
        'name': page.name,
        'page_type': page.page_type,
        'status': _public_status(page),
        'can_order': page.can_order,
        'starts_at': page.starts_at.isoformat() if page.starts_at else None,
        'ends_at': page.ends_at.isoformat() if page.ends_at else None,
        'payment_stages': page.payment_stages,
    }


# ---------------------------------------------------------------------------
# Task 4: GET /offers/offer-pages (lista + mapowanie statusów)
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/offers/offer-pages', methods=['GET'])
@jwt_required()
def offer_pages_list():
    status = (request.args.get('status') or 'live').strip().lower()
    if status not in _STATUS_MAP:
        return json_err(
            'invalid_input',
            'Nieobsługiwany status. Dozwolone: live, upcoming, closed.',
            400,
        )
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(
        parse_int(request.args.get('per_page'), 'per_page', default=12, min_value=1),
        48,
    )

    q = OfferPage.query.filter(
        OfferPage.status.in_(_STATUS_MAP[status])   # draft nigdy nie wchodzi
    ).order_by(OfferPage.id.desc())                 # deterministyczny sort (sqlite-safe)
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return json_page(
        [_serialize_page_summary(p) for p in pagination.items],
        page=pagination.page,
        per_page=pagination.per_page,
        total=pagination.total,
        has_next=pagination.has_next,
    )


# ---------------------------------------------------------------------------
# Task 5: GET /offers/offer-pages/<token> (struktura) + GET .../availability
# ---------------------------------------------------------------------------

def _brief(p):
    """Zwięzła serializacja produktu (cena→grosze, obraz absolutny)."""
    img = p.primary_image
    return {
        'id': p.id,
        'name': p.name,
        'slug': shop_service.slugify(p.name),
        'sku': p.sku,
        'price': to_grosze(p.sale_price),
        'quantity': p.quantity,
        'image_url': absolute_static_url(img.path_compressed) if img else None,
        'sizes': [s.name for s in p.sizes],
    }


def _serialize_bonus(b):
    bp = b.bonus_product
    return {
        'id': b.id,
        'trigger_type': b.trigger_type,
        'threshold_value': float(b.threshold_value) if b.threshold_value is not None else None,
        'bonus_product': _brief(bp) if bp else None,
        'bonus_quantity': b.bonus_quantity,
        'max_available': b.max_available,
        'when_exhausted': b.when_exhausted,
        'count_full_set': b.count_full_set,
        'repeatable': b.repeatable,
        'required_products': [
            {'product_id': rp.product_id, 'min_quantity': rp.min_quantity}
            for rp in b.required_products
        ],
    }


def _serialize_section(s):
    base = {'id': s.id, 'section_type': s.section_type, 'sort_order': s.sort_order}
    if s.section_type in ('heading', 'paragraph'):
        base['content'] = s.content
    elif s.section_type == 'product':
        base.update({
            'product': _brief(s.product) if s.product else None,
            'min_quantity': s.min_quantity,
            'max_quantity': s.max_quantity,
        })
    elif s.section_type == 'variant_group':
        vg = s.variant_group
        base.update({
            'variant_group': {'id': vg.id, 'name': vg.name} if vg else None,
            'max_quantity': s.max_quantity,
            'products': [_brief(p) for p in s.get_variant_group_products() if p.is_active],
        })
    elif s.section_type == 'set':
        base.update({
            'set_name': s.set_name,
            'set_image': absolute_static_url(s.set_image) if s.set_image else None,
            'set_max_sets': s.set_max_sets,
            'set_max_per_product': s.set_max_per_product,
            'set_product': _brief(s.set_product) if s.set_product else None,
            'set_items': [
                {
                    'quantity_per_set': it.quantity_per_set,
                    'products': [_brief(p) for p in it.get_products()],
                }
                for it in s.get_set_items_ordered()
            ],
            'bonuses': [_serialize_bonus(b) for b in s.bonuses if b.is_active],
        })
    elif s.section_type == 'bonus':
        base['bonuses'] = [_serialize_bonus(b) for b in s.bonuses if b.is_active]
    return base


@api_mobile_bp.route('/offers/offer-pages/<token>', methods=['GET'])
@jwt_required()
def offer_page_detail(token):
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    page.check_and_update_status()
    if page.status == 'draft':              # niepubliczny — nigdy nie eksponowany
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    return json_ok({
        **_serialize_page_summary(page),
        'description': page.description,
        'footer_content': page.footer_content,
        'payment_deadline': page.payment_deadline.isoformat() if page.payment_deadline else None,
        'sections': [_serialize_section(s) for s in page.get_sections_ordered()],
    })


@api_mobile_bp.route('/offers/offer-pages/<token>/availability', methods=['GET'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_availability(token):
    from modules.offers.reservation import get_section_products_map, get_availability_snapshot
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    session_id = request.args.get('session_id')
    section_products = get_section_products_map(page.id)
    products_data, session_info = get_availability_snapshot(page.id, section_products, session_id)
    return json_ok({'products': products_data, 'session': session_info})


# ---------------------------------------------------------------------------
# Task 6: POST /offers/<token>/{reserve,extend,release} (+ emisje Socket.IO)
# ---------------------------------------------------------------------------

def _emit_safe(page_id, *, reservations=False, availability=False, schedule=False):
    """Powtarza emisje Socket.IO tras webowych (best-effort, try/except dla testów)."""
    try:
        from modules.offers.socket_events import (
            emit_reservations_update, broadcast_availability_update, _schedule_expiry_timer)
        if reservations:
            emit_reservations_update(page_id)
        if availability:
            broadcast_availability_update(page_id)
        if schedule:
            _schedule_expiry_timer(page_id)
    except Exception:
        pass


@api_mobile_bp.route('/offers/<token>/reserve', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_reserve(token):
    from modules.offers.reservation import reserve_product, get_section_max_for_product
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    # Fair-access: rezerwować można tylko na aktywnej stronie (parytet z bramką
    # join weba — socket_events.handle_join_offer_reservation odrzuca nieaktywne).
    page.check_and_update_status()
    if page.status == 'draft':                  # niepubliczny — spójnie z offer_page_detail
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if not page.is_active:
        # 403 — spójnie z place-order i webowym guardem (kod błędu bez zmian)
        return json_err('page_not_active', 'Strona ofertowa nie jest aktywna.', 403)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    product_id = parse_int(body.get('product_id'), 'product_id', required=True)
    quantity = parse_int(body.get('quantity'), 'quantity', default=1, min_value=1)
    selected_size = body.get('selected_size')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    user_id = int(get_jwt_identity())
    section_max = get_section_max_for_product(page.id, product_id)
    ok, result = reserve_product(session_id=session_id, page_id=page.id, product_id=product_id,
                                 quantity=quantity, section_max=section_max, user_id=user_id,
                                 selected_size=selected_size)
    if ok:
        _emit_safe(page.id, reservations=True, availability=True, schedule=True)
        return json_ok(result)
    details = {k: result[k] for k in ('available_quantity', 'check_back_at') if k in result}
    return jsonify({'success': False, 'error': {
        'code': result.get('error', 'reserve_failed'), 'message': result.get('message', ''),
        **({'details': details} if details else {})}}), 409


@api_mobile_bp.route('/offers/<token>/release', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_release(token):
    from modules.offers.reservation import release_product
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    product_id = parse_int(body.get('product_id'), 'product_id', required=True)
    quantity = parse_int(body.get('quantity'), 'quantity', default=1, min_value=1)
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    # Wiązanie z właścicielem: zwolnić można tylko własną rezerwację (user_id z JWT)
    ok, result = release_product(session_id, page.id, product_id, quantity,
                                 user_id=int(get_jwt_identity()))
    if ok:
        _emit_safe(page.id, reservations=True, availability=True)
    return json_ok(result)


@api_mobile_bp.route('/offers/<token>/extend', methods=['POST'])
@jwt_required()
@limiter.limit("60 per minute")
def offer_extend(token):
    from modules.offers.reservation import extend_reservation
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    # Wiązanie z właścicielem: przedłużyć można tylko własną rezerwację (user_id z JWT)
    ok, result = extend_reservation(session_id, page.id, user_id=int(get_jwt_identity()))
    if not ok:
        return json_err(result.get('error', 'extend_failed'), result.get('message', ''), 400)
    _emit_safe(page.id, schedule=True)   # D4(a): tylko korekta timera serwera
    return json_ok(result)


# ---------------------------------------------------------------------------
# Task 7: POST /offers/<token>/place-order (exclusive + idempotency)
# ---------------------------------------------------------------------------

# Mapowanie kodów błędu serwisu place_offer_order -> status HTTP koperty mobilnej.
_PLACE_ORDER_ERR_STATUS = {
    'no_reservations': 400,
    'size_required': 400,
    'insufficient_availability': 409,
    'order_number_failed': 500,
    'database_error': 500,
    'server_error': 500,
}


@api_mobile_bp.route('/offers/<token>/place-order', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('offer_place_order')
def offer_place_order(token):
    """Złożenie zamówienia exclusive (parytet z webowym place_order trasy).

    Bramka strony: draft -> 404 page_not_found (parytet z reserve/detail — niepubliczny),
    nieaktywna -> 403 page_not_active (parytet z webowym guardem trasy). Idempotency-Key
    (opcjonalny) gwarantuje jednokrotne złożenie. Serwis sam emituje Socket.IO i wysyła
    maile/push (apka webowa + dashboard LIVE muszą zobaczyć zamówienie z telefonu).
    """
    from modules.offers.place_order import place_offer_order
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type == 'preorder':
        return json_err('wrong_page_type',
                        'Ta strona obsługiwana jest osobnym endpointem (pre-order).', 400)
    if page.status == 'draft':                  # niepubliczny — spójnie z detail/reserve
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if not page.is_active:
        return json_err('page_not_active', 'Sprzedaż nie jest aktywna.', 403)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    order_note = body.get('order_note')
    full_set_items = body.get('full_set_items', []) or []
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:                            # spójnie z konwencją /auth/me
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    ok, result = place_offer_order(page=page, session_id=session_id, order_note=order_note,
                                   full_set_items=full_set_items, user=user, bind_user=True)
    if not ok:
        code = result.get('error', 'place_order_failed')
        status = _PLACE_ORDER_ERR_STATUS.get(code, 400)
        details = {k: result[k] for k in ('available', 'product_name', 'product_id') if k in result}
        payload = {'code': code, 'message': result.get('message', '')}
        if details:
            payload['details'] = details
        return jsonify({'success': False, 'error': payload}), status
    data = {
        'order_id': result['order_id'],
        'order_number': result['order_number'],
        'total': to_grosze(result['total_amount']),
        'items_count': result['items_count'],
    }
    if result.get('already_placed'):
        # Double-submit guard serwisu: zamówienie już istnieje — 200, nie 201.
        data['already_placed'] = True
        return json_ok(data, 200)
    return json_ok(data, 201)


# ---------------------------------------------------------------------------
# Task 8 (E4): POST /offers/<token>/validate-cart (pre-order, read-only)
# ---------------------------------------------------------------------------

@api_mobile_bp.route('/offers/<token>/validate-cart', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_validate_cart(token):
    """Walidacja koszyka pre-order (koszyk żyje w apce jak localStorage w webie).

    Pre-order-only (wrong_page_type dla exclusive). Sprawdza istnienie i aktywność produktów;
    zwraca poprawne pozycje (cena→grosze) + listę odrzuconych. Bez bramki is_active (D1a) —
    parytet z webowym /restore; odrzuca tylko draft (404). Zero mutacji → bez idempotency.
    """
    from modules.products.models import Product
    from modules.offers.place_order import preorder_page_product_ids
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type != 'preorder':
        return json_err('wrong_page_type',
                        'Walidacja koszyka dotyczy tylko stron pre-order.', 400)
    if page.status == 'draft':                  # niepubliczny — parytet z detail/place-order
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    items = body.get('cart_items') or []
    allowed_ids = preorder_page_product_ids(page)   # przynależność do sekcji strony
    valid, removed = [], []
    for it in items:
        pid = it.get('product_id')
        qty = it.get('quantity', 1)
        product = db.session.get(Product, pid) if pid else None
        if product is None:
            removed.append({'product_id': pid, 'reason': 'not_found'})
        elif product.id not in allowed_ids:
            removed.append({'product_id': pid, 'reason': 'not_in_offer'})
        elif not product.is_active:
            removed.append({'product_id': pid, 'reason': 'inactive'})
        else:
            img = product.primary_image
            entry = {
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'price': to_grosze(product.sale_price),     # grosze
                'quantity': qty,                            # ilość zamawiana (parytet z webem)
                'image_url': absolute_static_url(img.path_compressed) if img else None,
                'sizes': [s.name for s in product.sizes],
            }
            if it.get('selected_size') is not None:
                entry['selected_size'] = it.get('selected_size')
            valid.append(entry)
    return json_ok({'cart_items': valid, 'removed': removed})


# ---------------------------------------------------------------------------
# Task 9 (E4): POST /offers/<token>/place-order-preorder (+ @idempotent)
# ---------------------------------------------------------------------------

# Mapowanie kodów błędu serwisu place_preorder_order -> status HTTP koperty mobilnej.
_PREORDER_ERR_STATUS = {
    'empty_cart': 400,
    'size_required': 400,
    'order_number_failed': 500,
    'database_error': 500,
    'server_error': 500,
}


@api_mobile_bp.route('/offers/<token>/place-order-preorder', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('offer_place_order_preorder')
def offer_place_order_preorder(token):
    """Złożenie zamówienia pre-order (koszyk z body, brak rezerwacji).

    Bramka (parytet/odwrotność E3): page_not_found 404 → exclusive → wrong_page_type 400 →
    draft 404 → not is_active → 403 page_not_active. Idempotency-Key (opcjonalny) gwarantuje
    jednokrotne złożenie. Serwis sam emituje Socket.IO i wysyła maile/push (apka webowa +
    dashboard LIVE muszą zobaczyć zamówienie z telefonu).
    """
    from modules.offers.place_order import place_preorder_order
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type != 'preorder':
        return json_err('wrong_page_type',
                        'Ta strona obsługiwana jest osobnym endpointem (exclusive).', 400)
    if page.status == 'draft':                  # niepubliczny — parytet z detail/place-order
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if not page.is_active:
        return json_err('page_not_active', 'Sprzedaż nie jest aktywna.', 403)
    body = request.get_json(silent=True) or {}
    raw_items = body.get('cart_items') or []
    if not raw_items:
        return json_err('empty_cart', 'Koszyk jest pusty.', 400)
    # Walidacja pozycji koszyka (parytet z E3 reserve): product_id wymagany, quantity >= 1.
    cart_items = []
    for it in raw_items:
        if not isinstance(it, dict):
            raise ValidationError('Pozycja koszyka musi być obiektem.')
        entry = {
            'product_id': parse_int(it.get('product_id'), 'product_id', required=True),
            'quantity': parse_int(it.get('quantity'), 'quantity', default=1, min_value=1),
        }
        selected_size = it.get('selected_size')
        if selected_size is not None:
            entry['selected_size'] = selected_size
        cart_items.append(entry)
    order_note = body.get('order_note')
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:                            # spójnie z konwencją /auth/me
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    ok, result = place_preorder_order(page=page, cart_items=cart_items,
                                      order_note=order_note, user=user)
    if not ok:
        code = result.get('error', 'place_order_failed')
        status = _PREORDER_ERR_STATUS.get(code, 400)
        details = {k: result[k] for k in ('product_name',) if k in result}
        payload = {'code': code, 'message': result.get('message', '')}
        if details:
            payload['details'] = details
        return jsonify({'success': False, 'error': payload}), status
    data = {
        'order_id': result['order_id'],
        'order_number': result['order_number'],
        'total': to_grosze(result['total_amount']),
        'items_count': result['items_count'],
    }
    return json_ok(data, 201)
