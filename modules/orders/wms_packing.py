"""
WMS — pakowanie zlecenia wysyłki jako jednej paczki
====================================================

Jedno zlecenie wysyłki = jedna paczka. Opakowanie schodzi ze stanu raz,
mail ze zdjęciem idzie raz, a dane paczki (opakowanie, waga, zdjęcie)
kopiowane są na każde zamówienie z grupy — historia zamówienia i mail
czytają je z zamówienia, więc nie ruszamy schematu bazy.

Moduł jest wspólny dla drogi HTTP (desktop, modules/orders/wms.py) i drogi
WebSocket (telefon, modules/orders/wms_events.py) — obie ścieżki muszą
zachowywać się identycznie, inaczej stan magazynowy się rozjedzie.
"""

import json

from flask import current_app

from extensions import db
from modules.orders.models import get_local_now
from modules.orders.wms_models import PackagingMaterial, WmsSessionOrder
from utils.activity_logger import log_activity


class PackingGroupError(Exception):
    """Pakowania nie da się wykonać — np. grupa pusta albo coś niezebrane."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def release_order_lock(order):
    """Release WMS lock from an order."""
    order.wms_locked_at = None
    order.wms_session_id = None


def update_sr_after_packing(order):
    """
    After packing an order, check if all orders in its ShippingRequest are packed.
    If so, change SR status to 'spakowane'.
    Also ensure 'spakowane' is in allowed shipping statuses.
    Returns dict with SR status info or None.
    """
    from modules.auth.models import Settings

    sr = order.shipping_request
    if not sr:
        return None

    all_packed = all(o.status == 'spakowane' for o in sr.orders)

    sr_status_changed = False
    if all_packed and sr.status != 'spakowane':
        sr.status = 'spakowane'
        sr_status_changed = True
        # Paczka zbiorcza spakowana — status i tracking zjeżdżają na źródłowe,
        # żeby ich klienci widzieli, że fizyczna przesyłka jest gotowa.
        from modules.orders.consolidation import propaguj_na_zrodla
        propaguj_na_zrodla(sr)

    # Auto-add 'spakowane' to allowed shipping statuses (one-time)
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    if setting and setting.value:
        try:
            allowed = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed = []
        if 'spakowane' not in allowed:
            allowed.append('spakowane')
            setting.value = json.dumps(allowed)
    elif not setting:
        setting = Settings(
            key='shipping_request_allowed_statuses',
            value=json.dumps(['dostarczone_gom', 'spakowane']),
            type='json',
            description='Lista statusów zamówień kwalifikujących się do zlecenia wysyłki'
        )
        db.session.add(setting)

    return {
        'id': sr.id,
        'request_number': sr.request_number,
        'all_orders_packed': all_packed,
        'sr_status_changed': sr_status_changed,
        'sr_new_status': 'spakowane' if sr_status_changed else sr.status,
    }


def _is_fully_picked(order):
    """Czy zamówienie jest w całości zebrane (po ilościach, nie po flagach)."""
    total = sum(i.quantity for i in order.items)
    picked = sum(i.picked_quantity or 0 for i in order.items)
    return total > 0 and picked >= total


def get_packing_group(session, shipping_request):
    """
    Zamówienia tego zlecenia, które należą do tej sesji WMS i nie są jeszcze
    spakowane — czyli dokładnie to, co fizycznie ląduje w jednym kartonie.
    """
    group = []
    for so in session.session_orders:
        if so.packing_completed_at or not so.order:
            continue
        sr = so.order.shipping_request
        if sr and sr.id == shipping_request.id:
            group.append(so.order)
    return group


def pack_shipping_request_group(session, shipping_request, packaging_material_id=None,
                                total_package_weight=None, send_email=False, user_id=None):
    """
    Pakuje całe zlecenie jako jedną paczkę.

    Zwraca dict: orders (lista dictów zamówień), low_stock_warning, shipping_request,
    packed_at. Rzuca PackingGroupError, gdy grupa jest pusta albo któreś zamówienie
    nie jest do końca zebrane.

    Uwaga: funkcja NIE commituje — commit należy do wywołującego, żeby cała paczka
    weszła do bazy jednym kawałkiem albo wcale.
    """
    group = get_packing_group(session, shipping_request)
    if not group:
        raise PackingGroupError(
            f'{shipping_request.request_number}: brak zamówień do spakowania '
            f'(zlecenie już spakowane albo nie należy do tej sesji)'
        )

    not_picked = [o.order_number for o in group if not _is_fully_picked(o)]
    if not_picked:
        raise PackingGroupError(
            'Nie wszystkie zamówienia są zebrane: ' + ', '.join(not_picked)
        )

    now = get_local_now()
    old_statuses = {o.id: o.status for o in group}

    # Waga paczki — jedna na całą grupę.
    weight_value = None
    if total_package_weight is not None:
        try:
            weight_value = float(total_package_weight)
        except (ValueError, TypeError):
            weight_value = None

    # Opakowanie — jedno na całą grupę, ze stanu schodzi RAZ.
    material = None
    low_stock_warning = None
    if packaging_material_id:
        material = db.session.get(PackagingMaterial, packaging_material_id)
        if material:
            material.quantity_in_stock = max(0, material.quantity_in_stock - 1)
            if material.is_low_stock:
                low_stock_warning = (
                    f'Materiał "{material.name}": stan magazynowy: '
                    f'{material.quantity_in_stock}'
                )
            shipping_request.packaging_material_id = material.id
        else:
            low_stock_warning = 'Wybrane opakowanie już nie istnieje — stan nie został zmieniony'

    # Zdjęcie paczki robione jest raz; kopiujemy je na całą grupę.
    photo = next((o.packing_photo for o in group if o.packing_photo), None)

    for order in group:
        order.status = 'spakowane'
        order.packed_at = now
        order.packed_by = user_id
        if material:
            order.packaging_material_id = material.id
        if weight_value is not None:
            order.total_package_weight = weight_value
        if photo:
            order.packing_photo = photo
        release_order_lock(order)

        session_order = WmsSessionOrder.query.filter_by(
            session_id=session.id, order_id=order.id
        ).first()
        if session_order:
            session_order.packing_completed_at = now

    from modules.auth.models import User  # import odłożony — modele auth ładują się później
    log_activity(
        user=db.session.get(User, user_id) if user_id else None,
        action='shipping_request_packed',
        entity_type='shipping_request',
        entity_id=shipping_request.id,
        old_value={'orders': old_statuses},
        new_value={
            'status': 'spakowane',
            'wms_session_id': session.id,
            'packaging_material_id': material.id if material else None,
            'total_package_weight': weight_value,
            'order_ids': [o.id for o in group],
        },
    )

    sr_info = update_sr_after_packing(group[0])

    if send_email and photo:
        try:
            from utils.email_manager import EmailManager
            from utils.push_manager import PushManager
            EmailManager.notify_packing_photo(group[0])
            PushManager.notify_packing_photo(group[0])
        except Exception as email_err:
            current_app.logger.error(f'WMS packing email error: {email_err}')

    return {
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'status': o.status,
            'status_display_name': o.status_display_name,
            'packed_at': now.isoformat(),
            'packaging_material_name': material.name if material else None,
            'total_package_weight': weight_value,
        } for o in group],
        'low_stock_warning': low_stock_warning,
        'shipping_request': sr_info,
        'packed_at': now.isoformat(),
    }
