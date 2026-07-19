"""Wspólny serwis wysyłki — web (trasy shipping.py) + mobilne API (E7).

Logika przeniesiona 1:1 z modules/client/shipping.py (adresy + zlecenia). Serwis NIE importuje
nic z modules.api_mobile (brak cyklu). Funkcje zwracają (ok, err[, value]) — kanał serializuje.
"""

import json

from extensions import db
from modules.auth.models import ShippingAddress, Settings
from modules.orders.models import Order, ShippingRequest, ShippingRequestOrder
from modules.client.cart_service import get_initial_shipping_status
from utils.activity_logger import log_activity

_HOME_REQUIRED = ['shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city']
_PICKUP_REQUIRED = ['pickup_courier', 'pickup_point_id', 'pickup_address',
                    'pickup_postal_code', 'pickup_city']

_SNAPSHOT_FIELDS = ('shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city',
                    'shipping_voivodeship', 'shipping_country', 'pickup_courier', 'pickup_point_id',
                    'pickup_address', 'pickup_postal_code', 'pickup_city')


def validate_address_payload(data):
    """(True, None) lub (False, {'code': ...}). Parytet web l. 52-101."""
    atype = (data or {}).get('address_type')
    if atype not in ('home', 'pickup_point'):
        return False, {'code': 'invalid_address_type'}
    required = _HOME_REQUIRED if atype == 'home' else _PICKUP_REQUIRED
    for field in required:
        if not data.get(field):
            return False, {'code': 'missing_field', 'field': field}
    return True, None


def list_active_addresses(user_id):
    """Aktywne adresy usera, default first, potem najnowsze (parytet web l. 30-33)."""
    return ShippingAddress.query.filter_by(user_id=user_id, is_active=True).order_by(
        ShippingAddress.is_default.desc(), ShippingAddress.created_at.desc()).all()


def _clear_default(user_id):
    ShippingAddress.query.filter_by(user_id=user_id, is_default=True).update(
        {'is_default': False})
    db.session.flush()


def create_address(user, data):
    """(True, None, address). Zakłada walidację (validate_address_payload). Parytet web l. 44-117."""
    is_default = bool(data.get('is_default', False))
    if is_default:
        _clear_default(user.id)
    addr = ShippingAddress(user_id=user.id, address_type=data['address_type'],
                           is_default=is_default, name=data.get('name'))
    if data['address_type'] == 'pickup_point':
        for f in _PICKUP_REQUIRED:
            setattr(addr, f, data.get(f))
    else:
        for f in _HOME_REQUIRED:
            setattr(addr, f, data.get(f))
        addr.shipping_voivodeship = data.get('shipping_voivodeship')
        addr.shipping_country = data.get('shipping_country', 'Polska')
    db.session.add(addr)
    db.session.commit()
    try:                                                       # achievement hook (parytet l. 106-111)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'address_added')
    except Exception:
        pass
    return True, None, addr


def set_default_address(user_id, address_id):
    """(ok, err, address). Cudzy/nieaktywny → not_found (maskowanie). Parytet web l. 131-145."""
    addr = ShippingAddress.query.filter_by(id=address_id, user_id=user_id, is_active=True).first()
    if not addr:
        return False, {'code': 'not_found'}, None
    _clear_default(user_id)
    addr.is_default = True
    db.session.commit()
    return True, None, addr


def soft_delete_address(user_id, address_id):
    """(ok, err). is_active=False; cudzy/nieaktywny → not_found. Parytet web l. 161-169."""
    addr = ShippingAddress.query.filter_by(id=address_id, user_id=user_id, is_active=True).first()
    if not addr:
        return False, {'code': 'not_found'}
    addr.is_active = False
    db.session.commit()
    return True, None


# ============================================================================
# ZLECENIA WYSYŁKI (ekstrakcja z shipping.py — parytet)
# ============================================================================

def allowed_request_statuses():
    """Verbatim z web l. 262-270 (NIE Settings.get_value — typ settingu niepewny)."""
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            return ['dostarczone_gom']
    return ['dostarczone_gom']


def _orders_in_request_ids(order_ids):
    rows = ShippingRequestOrder.query.filter(ShippingRequestOrder.order_id.in_(order_ids)).all()
    return {r.order_id for r in rows}


def get_available_orders(user_id):
    """Zamówienia usera w dozwolonym statusie i bez aktywnego zlecenia (parytet web l. 277-288)."""
    allowed = allowed_request_statuses()
    from sqlalchemy import and_
    in_req = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id).exists()
    return Order.query.filter(and_(Order.user_id == user_id, Order.status.in_(allowed),
                                   ~in_req)).order_by(Order.created_at.desc()).all()


def _delivery_method_for(address):
    """Parytet web l. 425-437."""
    if address.address_type == 'home':
        return 'kurier'
    if address.address_type == 'pickup_point' and address.pickup_courier:
        c = address.pickup_courier.lower()
        if 'inpost' in c or 'paczkomat' in c:
            return 'paczkomat'
        if 'orlen' in c:
            return 'orlen_paczka'
        if 'dpd' in c:
            return 'dpd_pickup'
    return None


def validate_and_create_request(user, order_ids, address_id):
    """(ok, err, request). All-or-nothing; dedupe (D5). Parytet web l. 330-479 z rozbiciem kodów.

    Status początkowy: reużywa get_initial_shipping_status() z cart_service (E2) — funkcja jest
    verbatim równoważna webowemu fallbackowi (Settings -> is_initial -> sort_order -> 'nowe').
    NIE duplikujemy jej (plan zakładał lokalny _resolve_initial_status_slug; reuse > kopia).
    """
    if not order_ids:
        return False, {'code': 'no_orders'}, None
    if not address_id:
        return False, {'code': 'no_address'}, None
    order_ids = list(dict.fromkeys(order_ids))                 # dedupe (D5)
    allowed = allowed_request_statuses()
    owned = {o.id: o for o in Order.query.filter(
        Order.id.in_(order_ids), Order.user_id == user.id).all()}
    missing = sorted(set(order_ids) - set(owned))
    if missing:
        return False, {'code': 'orders_not_found', 'missing_order_ids': missing}, None
    in_req = _orders_in_request_ids(order_ids)
    unavailable = sorted(oid for oid in order_ids
                         if owned[oid].status not in allowed or oid in in_req)
    if unavailable:
        return False, {'code': 'orders_not_available', 'unavailable_order_ids': unavailable}, None
    # Gate Cło/VAT (task 869e674fd): zlecenie wysyłki dopiero po opłaceniu podatku (E3 approved).
    unpaid_tax = sorted(oid for oid in order_ids if not owned[oid].is_customs_vat_settled)
    if unpaid_tax:
        return False, {'code': 'customs_vat_unpaid', 'customs_vat_unpaid_order_ids': unpaid_tax}, None
    address = ShippingAddress.query.filter_by(
        id=address_id, user_id=user.id, is_active=True).first()
    if not address:
        return False, {'code': 'address_not_found'}, None

    req = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                          user_id=user.id, status=get_initial_shipping_status(),
                          address_type=address.address_type)
    for f in _SNAPSHOT_FIELDS:
        setattr(req, f, getattr(address, f))
    db.session.add(req)
    db.session.flush()
    dm = _delivery_method_for(address)
    orders = [owned[oid] for oid in order_ids]
    for order in orders:
        db.session.add(ShippingRequestOrder(shipping_request_id=req.id, order_id=order.id))
        if dm and not order.delivery_method:
            order.delivery_method = dm
    db.session.commit()
    for order in orders:                                       # log per order (parytet l. 453-464)
        log_activity(user=user, action='shipping_requested', entity_type='order',
                     entity_id=order.id,
                     new_value={'request_number': req.request_number,
                                'order_number': order.order_number,
                                'address_type': address.address_type})
    try:                                                       # notify (parytet l. 466-473)
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        EmailManager.notify_shipping_request_created(req, user)
        PushManager.notify_admin_shipping_request(req)
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f'Shipping request notify failed: {e}')
    return True, None, req


def cancel_request(user_id, request_id):
    """(ok, err). Cudzy/brak → not_found; nie can_cancel → cannot_cancel. Parytet web l. 493-515."""
    req = ShippingRequest.query.filter_by(id=request_id, user_id=user_id).first()
    if not req:
        return False, {'code': 'not_found'}
    if not req.can_cancel:
        return False, {'code': 'cannot_cancel'}
    db.session.delete(req)
    db.session.commit()
    return True, None
