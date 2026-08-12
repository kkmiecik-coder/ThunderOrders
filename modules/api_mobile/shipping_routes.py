"""Trasy wysyłki (adresy + zlecenia) dla mobilnego API (E7)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import db, limiter
from modules.auth.models import User
from modules.client import shipping_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze
from .validators import parse_int
from .idempotency import idempotent


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
    user = db.session.get(User, int(get_jwt_identity()))
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
        # Gate Cło/VAT (task 869e674fd): False → zablokowane do zlecenia wysyłki
        'customs_vat_paid': order.is_customs_vat_settled,
        # Powód blokady: True = cło jeszcze nieustalone (klient nie ma czego
        # opłacić), False = naliczone, ale nieopłacone. Parytet z webem.
        'customs_vat_not_set': order.is_customs_vat_not_set,
        'items': [{'name': it.product_name, 'selected_size': it.selected_size,
                   'image_url': _abs_image(it.product_image_url),
                   'quantity': it.quantity, 'price': to_grosze(it.price)}
                  for it in order.items if it.quantity > 0],
    }


def _moze_potwierdzic(req):
    """Czy właściciel TEGO zlecenia (req.user_id) może z niego potwierdzić odbiór.

    Uczestnik paczki zbiorczej, który nie jest klientem wiodącym, nie może — karton
    fizycznie odbiera osoba, na której adres został nadany (zlecenie zbiorcze).
    Parytet z `zlecenie_do_potwierdzenia()` w panelu webowym (modules/client/delivery.py),
    ale bez zapytań do bazy dla cudzych zleceń — tu req już należy do żądającego.
    """
    if req.status != 'wyslane':
        return False
    if not req.is_consolidated_source:
        return True
    zbiorcze = req.consolidated_into
    return bool(zbiorcze and zbiorcze.lead_source_request_id == req.id)


def _serialize_request(req):
    # Paczka zbiorcza: bez tych dwóch pól apka pokazywała `full_address` (WŁASNY
    # adres klienta) jako adres dostawy, choć karton jedzie do innej osoby — czyli
    # dokładnie scenariusz, przed którym ostrzega spec („inaczej ktoś będzie czekał
    # pod własnymi drzwiami"). Web ma tu badge „Wysyłka zbiorcza" i zdanie „Paczka
    # jedzie na adres: <adresat>"; to jest parytet dla apki.
    # Adresat WYŁĄCZNIE przez short_addressee_name — pełne imię i nazwisko obcej
    # osoby to dane osobowe, których uczestnik nie ma prawa zobaczyć.
    zbiorcza = req.consolidated_into if req.is_consolidated_source else None
    return {
        'id': req.id, 'request_number': req.request_number, 'status': req.status,
        'status_display_name': req.status_display_name, 'status_badge_color': req.status_badge_color,
        'address_type': req.address_type, 'short_address': req.short_address,
        'full_address': req.full_address,
        'total_shipping_cost': to_grosze(req.display_shipping_cost),
        'tracking_number': req.tracking_number, 'tracking_url': req.tracking_url,
        'can_cancel': req.can_cancel, 'orders_count': req.orders_count,
        'is_consolidated': zbiorcza is not None,
        'consolidation_addressee_name': zbiorcza.short_addressee_name if zbiorcza else None,
        # display_orders, nie orders — dla zlecenia źródłowego w paczce zbiorczej
        # request_orders wisi już przy paczce, nie tutaj (parytet z webem).
        'orders': [{'id': o.id, 'order_number': o.order_number} for o in req.display_orders],
        'created_at': req.created_at.isoformat() if req.created_at else None,
        # Dostawa (task 869efhwph) — parytet z panelem webowym.
        'shipped_at': req.shipped_at.isoformat() if req.shipped_at else None,
        'delivered_at': req.delivered_at.isoformat() if req.delivered_at else None,
        'delivered_source': req.delivered_source,
        'can_confirm_delivery': _moze_potwierdzic(req),
        'review': ({
            'rating': req.review.rating,
            'comment': req.review.comment,
            'can_edit': req.review.mozna_edytowac,
        } if req.review else None),
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
    # list_client_requests filtruje paczki zbiorcze (parytet web) — bez tego
    # klient wiodący widziałby w apce zamówienia obcych osób z paczki.
    reqs = svc.list_client_requests(int(get_jwt_identity()))
    return json_ok({'requests': [_serialize_request(r) for r in reqs]})


# ============================================================================
# ZLECENIA WYSYŁKI — mutacje
# ============================================================================

_CREATE_REQUEST_ERR_STATUS = {
    'no_orders': 400, 'no_address': 400,
    'orders_not_found': 404, 'orders_not_available': 409, 'address_not_found': 404,
    'customs_vat_unpaid': 409,
    'customs_vat_not_set': 409,
}
_CREATE_REQUEST_ERR_MSG = {
    'no_orders': 'Wybierz przynajmniej jedno zamówienie.',
    'no_address': 'Wybierz adres dostawy.',
    'orders_not_found': 'Zamówienie nie istnieje.',
    'orders_not_available': 'Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki.',
    'address_not_found': 'Adres dostawy nie istnieje.',
    'customs_vat_unpaid': 'Najpierw opłać Cło/VAT dla wybranych zamówień.',
    'customs_vat_not_set': 'Trwa ustalanie Cła/VAT — wysyłkę zlecisz, gdy będzie gotowe.',
}
_CREATE_REQUEST_ERR_DETAILS = {
    'orders_not_found': 'missing_order_ids', 'orders_not_available': 'unavailable_order_ids',
    'customs_vat_unpaid': 'customs_vat_unpaid_order_ids',
    'customs_vat_not_set': 'customs_vat_not_set_order_ids',
}


@api_mobile_bp.route('/shipping/requests', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('shipping_request_create')
def shipping_request_create():
    from flask import jsonify
    p = request.get_json(silent=True) or {}
    order_ids = p.get('order_ids') or []
    if not isinstance(order_ids, list):
        return json_err('invalid_input', 'Pole order_ids musi być listą.', 400)
    try:
        order_ids = [int(x) for x in order_ids]
    except (TypeError, ValueError):
        return json_err('invalid_input', 'Pole order_ids musi zawierać liczby.', 400)
    address_id = parse_int(p.get('address_id'), 'address_id', required=False)
    user = db.session.get(User, int(get_jwt_identity()))
    client_package_preference = p.get('client_package_preference')
    client_notes = p.get('client_notes')
    ok, err, req = svc.validate_and_create_request(
        user, order_ids, address_id,
        client_package_preference=client_package_preference,
        client_notes=client_notes,
    )
    if not ok:
        code = err['code']
        payload = {'code': code, 'message': _CREATE_REQUEST_ERR_MSG[code]}
        dkey = _CREATE_REQUEST_ERR_DETAILS.get(code)
        if dkey and dkey in err:
            payload['details'] = {dkey: err[dkey]}
        return jsonify({'success': False, 'error': payload}), _CREATE_REQUEST_ERR_STATUS[code]
    return json_ok({'request_id': req.id, 'request_number': req.request_number}, 201)


@api_mobile_bp.route('/shipping/requests/<int:request_id>/cancel', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_request_cancel(request_id):
    ok, err = svc.cancel_request(int(get_jwt_identity()), request_id)
    if not ok:
        if err['code'] == 'not_found':
            return json_err('request_not_found', 'Zlecenie nie istnieje.', 404)
        if err['code'] == 'consolidated':
            return json_err(
                'consolidated',
                'To zlecenie jedzie w paczce zbiorczej — aby je anulować, '
                'skontaktuj się z obsługą.',
                409,
            )
        return json_err('cannot_cancel', 'Nie można anulować zlecenia w tym statusie.', 409)
    return json_ok({'cancelled': True})


# ============================================================================
# DOSTAWA (task 869efhwph) — potwierdzenie odbioru i ocena, parytet z webem
# ============================================================================

@api_mobile_bp.route('/shipping/requests/<int:request_id>/confirm-delivery', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
@idempotent('shipping_confirm_delivery')
def shipping_confirm_delivery(request_id):
    """Potwierdzenie odbioru paczki (opcjonalnie z oceną). Parytet z panelem webowym
    (modules/client/delivery.py: confirm_delivery_submit)."""
    from modules.client.delivery import zapisz_ocene, zlecenie_do_potwierdzenia
    from modules.orders.wms_utils import (
        ZlecenieJuzDostarczone, ZlecenieZrodloweNieDomykane, dostarcz_zlecenie)

    user_id = int(get_jwt_identity())
    sr, do_domkniecia = zlecenie_do_potwierdzenia(user_id, request_id)
    if sr is None:
        # Cudze zlecenie jest nieodróżnialne od nieistniejącego — nie zdradzamy,
        # które numery zleceń istnieją w systemie.
        return json_err('request_not_found', 'Zlecenie nie istnieje.', 404)
    if do_domkniecia is None:
        return json_err(
            'consolidated_lead_only',
            'Tę paczkę potwierdza osoba, na której adres została nadana.', 403)

    # Poprawka do briefu (zgodna z wersją webową): strona GET jedynie UKRYWA przycisk,
    # gdy status != 'wyslane' — samego POST-a nic nie broni bez tego warunku. Bez niego
    # klient mógłby domknąć zlecenie, które fizycznie nigdy nie zostało wysłane (np.
    # 'nowe', 'anulowane', 'w_magazynie'). Sprawdzamy do_domkniecia (nie sr) — to on
    # faktycznie przechodzi przez dostarcz_zlecenie(); dla zlecenia niekonsolidowanego
    # to ten sam obiekt, dla lidera paczki zbiorczej to zlecenie zbiorcze, którego
    # status jest zsynchronizowany ze źródłem przez propaguj_na_zrodla().
    if do_domkniecia.status != 'wyslane':
        return json_err(
            'not_ready',
            f'Zlecenie {sr.request_number} nie jest gotowe do potwierdzenia '
            f'odbioru (status: {do_domkniecia.status}).', 409)

    dane = request.get_json(silent=True) or {}

    # Ocena PRZED domknięciem: dostarcz_zlecenie() wysyła mail z jej treścią, więc
    # musi ją już widzieć w sesji (parytet z webem).
    opinia, blad, kod = zapisz_ocene(sr, dane)
    if blad:
        db.session.rollback()
        return json_err('invalid_input', blad, kod)

    user = db.session.get(User, user_id)
    try:
        dostarcz_zlecenie(do_domkniecia, source='klient', user=user)
    except ZlecenieJuzDostarczone:
        # Podwójne potwierdzenie (np. duplikat idempotency albo klik po odświeżeniu) —
        # nie traktujemy jako błąd, tylko zapisujemy ewentualną ocenę i zwracamy 200.
        db.session.commit()
    except ZlecenieZrodloweNieDomykane as err:
        db.session.rollback()
        return json_err('consolidated_lead_only', str(err), 403)

    return json_ok({'request': _serialize_request(sr)})


@api_mobile_bp.route('/shipping/requests/<int:request_id>/review', methods=['PUT'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_delivery_review(request_id):
    """Wystawienie albo zmiana oceny dostawy, bez zmiany statusu zlecenia. Parytet
    z panelem webowym (modules/client/delivery.py: delivery_review_submit)."""
    from modules.client.delivery import zapisz_ocene, zlecenie_do_potwierdzenia

    sr, _ = zlecenie_do_potwierdzenia(int(get_jwt_identity()), request_id)
    if sr is None:
        return json_err('request_not_found', 'Zlecenie nie istnieje.', 404)

    dane = request.get_json(silent=True) or {}
    if dane.get('rating') in (None, ''):
        return json_err('invalid_input', 'Podaj ocenę od 1 do 5.', 400)

    opinia, blad, kod = zapisz_ocene(sr, dane)
    if blad:
        db.session.rollback()
        return json_err('invalid_input', blad, kod)

    db.session.commit()
    return json_ok({'request': _serialize_request(sr)})
