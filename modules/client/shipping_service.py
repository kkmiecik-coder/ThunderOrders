"""Wspólny serwis wysyłki — web (trasy shipping.py) + mobilne API (E7).

Logika przeniesiona 1:1 z modules/client/shipping.py (adresy + zlecenia). Serwis NIE importuje
nic z modules.api_mobile (brak cyklu). Funkcje zwracają (ok, err[, value]) — kanał serializuje.
"""

from extensions import db
from modules.auth.models import ShippingAddress

_HOME_REQUIRED = ['shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city']
_PICKUP_REQUIRED = ['pickup_courier', 'pickup_point_id', 'pickup_address',
                    'pickup_postal_code', 'pickup_city']


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
