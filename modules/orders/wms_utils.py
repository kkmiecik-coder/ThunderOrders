"""
WMS Utilities — Packaging Suggestion Algorithm
================================================

Provides suggest_packaging(order) which analyzes order items' dimensions/weight
and returns ranked packaging material suggestions.
"""

from modules.orders.wms_models import PackagingMaterial


def suggest_packaging(order):
    """
    Analyze order items and suggest best-fit packaging materials.

    Returns dict with keys:
      - suggestions: list of top 3 material dicts (sorted by fit_score desc, cost asc)
      - warnings: list of warning strings
      - total_weight: total product weight in kg (float)
      - total_volume: total needed volume in cm³ (float)
    """
    items = order.items or []

    if not items:
        return {
            'suggestions': [],
            'warnings': ['Zamówienie nie ma pozycji'],
            'total_weight': 0,
            'total_volume': 0,
        }

    # 1. Collect product data
    warnings = []
    total_weight = 0.0
    total_volume = 0.0
    max_dimensions = []  # list of sorted [l, w, h] per item
    items_without_dims = 0
    items_without_weight = 0

    for item in items:
        product = item.product
        qty = item.quantity or 1

        # Weight
        if product and product.weight:
            total_weight += float(product.weight) * qty
        else:
            items_without_weight += 1

        # Dimensions
        if product and product.length and product.width and product.height:
            l = float(product.length)
            w = float(product.width)
            h = float(product.height)
            total_volume += l * w * h * qty
            # Track max single-item dimensions for fit check
            dims_sorted = sorted([l, w, h], reverse=True)
            for _ in range(qty):
                max_dimensions.append(dims_sorted)
        else:
            items_without_dims += 1

    if items_without_dims > 0:
        warnings.append(f'{items_without_dims} {"produkt nie ma" if items_without_dims == 1 else "produktów nie ma"} wymiarów')
    if items_without_weight > 0:
        warnings.append(f'{items_without_weight} {"produkt nie ma" if items_without_weight == 1 else "produktów nie ma"} wagi')

    # 2. Add 30% buffer for protective material
    needed_volume = total_volume * 1.3

    # 3. Get the largest single-item dimensions (for fit check)
    if max_dimensions:
        overall_max = [
            max(d[0] for d in max_dimensions),
            max(d[1] for d in max_dimensions),
            max(d[2] for d in max_dimensions),
        ]
    else:
        overall_max = None

    # 4. Filter active materials with stock
    materials = PackagingMaterial.query.filter(
        PackagingMaterial.is_active == True,
        PackagingMaterial.quantity_in_stock > 0,
    ).order_by(PackagingMaterial.sort_order).all()

    if not materials:
        return {
            'suggestions': [],
            'warnings': warnings + ['Brak dostępnych materiałów pakowania'],
            'total_weight': round(total_weight, 2),
            'total_volume': round(needed_volume, 2),
        }

    # 5. Score each material
    scored = []
    has_product_dims = items_without_dims < len(items)

    for mat in materials:
        mat_volume = mat.inner_volume  # None if no dimensions
        mat_max_weight = float(mat.max_weight) if mat.max_weight else None

        # Weight check
        if mat_max_weight is not None and total_weight > 0 and total_weight > mat_max_weight:
            continue  # Too heavy

        # Dimension fit check
        fits_dimensions = True
        if mat_volume is not None and has_product_dims:
            # Volume check
            if mat_volume < needed_volume:
                fits_dimensions = False

            # Individual dimension check (with rotation)
            if fits_dimensions and overall_max is not None:
                mat_dims = sorted([
                    float(mat.inner_length),
                    float(mat.inner_width),
                    float(mat.inner_height),
                ], reverse=True)
                # Each sorted dimension of the product must fit
                for i in range(3):
                    if overall_max[i] > mat_dims[i]:
                        fits_dimensions = False
                        break

        # Materials without dimensions (e.g. foliopak) — always pass with low score
        if mat_volume is None:
            fit_score = 0.2  # Low default score
        elif not has_product_dims:
            # No product dims — all materials with dimensions get medium score
            fit_score = 0.5
        elif not fits_dimensions:
            continue  # Doesn't fit
        else:
            # Calculate fit score: smaller volume difference = better
            volume_diff = mat_volume - needed_volume
            fit_score = max(0.0, min(1.0, 1.0 - (volume_diff / mat_volume)))

        scored.append({
            'material': mat,
            'fit_score': round(fit_score, 2),
        })

    # 6. Sort: highest fit_score first, then lowest cost
    scored.sort(key=lambda x: (
        -x['fit_score'],
        float(x['material'].cost) if x['material'].cost else 999999,
    ))

    # 7. Take top 3
    top = scored[:3]

    suggestions = []
    for entry in top:
        mat = entry['material']
        suggestions.append({
            'id': mat.id,
            'name': mat.name,
            'type': mat.type,
            'type_display': mat.type_display,
            'dimensions_display': mat.dimensions_display,
            'fit_score': entry['fit_score'],
            'own_weight': float(mat.own_weight) if mat.own_weight else None,
            'cost': float(mat.cost) if mat.cost else None,
            'quantity_in_stock': mat.quantity_in_stock,
            'is_low_stock': mat.is_low_stock,
        })

    return {
        'suggestions': suggestions,
        'warnings': warnings,
        'total_weight': round(total_weight, 2),
        'total_volume': round(needed_volume, 2),
    }


# ====================
# WYSYŁKA ZLECENIA
# ====================


COURIER_NAMES = {
    'inpost': 'InPost', 'dpd': 'DPD', 'dhl': 'DHL', 'gls': 'GLS',
    'poczta_polska': 'Poczta Polska', 'orlen': 'Orlen Paczka',
    'ups': 'UPS', 'fedex': 'FedEx', 'pocztex': 'Pocztex', 'other': 'Inny',
}


class ShippingRequestAlreadyShipped(Exception):
    """Zlecenie ma już status 'wyslane' — drugi raz go nie wysyłamy."""


def ship_shipping_request(sr, *, courier=None, tracking_number=None, parcel_size=None,
                          shipping_cost=None, order_costs=None, user=None, wms_session=None):
    """Oznacza zlecenie wysyłki jako wysłane.

    Wspólne dla panelu w sesji WMS i dla listy zleceń — jedno miejsce, w którym
    zmieniają się statusy, powstaje wpis przesyłki i idą powiadomienia do klienta.

    Numer przesyłki jest nieobowiązkowy. Gdy go nie ma, nie powstaje OrderShipment
    (wpis bez numeru niczego nie wnosi), a klient dostaje powiadomienie o zmianie
    statusu zamiast powiadomienia o trackingu.
    """
    from flask import current_app

    from extensions import db
    from modules.orders.models import Order, OrderShipment, OrderStatus
    from utils.activity_logger import log_activity
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    if sr.status == 'wyslane':
        raise ShippingRequestAlreadyShipped(f'Zlecenie {sr.request_number} jest już wysłane')

    old_status = sr.status
    tracking_number = (tracking_number or '').strip()

    # Puste pole nie kasuje tego, co już jest na zleceniu.
    if courier:
        sr.courier = courier
    if tracking_number:
        sr.tracking_number = tracking_number
    if parcel_size:
        sr.parcel_size = parcel_size
    sr.status = 'wyslane'

    if shipping_cost:
        try:
            sr.total_shipping_cost = float(shipping_cost)
        except (ValueError, TypeError):
            pass

    for cost_data in (order_costs or []):
        oid = cost_data.get('order_id')
        cost = cost_data.get('shipping_cost')
        if oid and cost:
            order = db.session.get(Order, oid)
            if order:
                try:
                    order.shipping_cost = float(cost)
                except (ValueError, TypeError):
                    pass

    # Nazwy starych statusów potrzebne do maila — zbierane przed podmianą.
    old_order_status_names = {o.id: o.status_display_name for o in sr.orders}

    order_status = OrderStatus.query.filter_by(slug='wyslane', is_active=True).first()
    if order_status:
        for o in sr.orders:
            if o.status != 'wyslane':
                o.status = 'wyslane'

    db.session.commit()

    courier_name = COURIER_NAMES.get(sr.courier, sr.courier or 'Kurier')

    for order in sr.orders:
        if tracking_number:
            existing = OrderShipment.query.filter_by(
                order_id=order.id, tracking_number=tracking_number
            ).first()
            if not existing:
                db.session.add(OrderShipment(
                    order_id=order.id,
                    tracking_number=tracking_number,
                    courier=sr.courier,
                    notes=(f'Z sesji WMS #{wms_session.id}, zlecenie {sr.request_number}'
                           if wms_session else f'Zlecenie {sr.request_number}'),
                    created_by=user.id if user else None,
                ))

        try:
            if tracking_number:
                EmailManager.notify_tracking_added(
                    order, tracking_number=tracking_number, courier=sr.courier,
                    courier_name=courier_name, tracking_url=sr.tracking_url)
                PushManager.notify_tracking_added(
                    order, tracking_number=tracking_number, courier_name=courier_name)
            elif order_status:
                old_name = old_order_status_names.get(order.id, '')
                EmailManager.notify_status_change(order, old_name, order_status.name)
                PushManager.notify_status_change(order, old_name, order_status.name)
        except Exception as err:
            current_app.logger.error(
                f'Powiadomienie o wysyłce {sr.request_number}, zam. {order.order_number}: {err}')

    db.session.commit()

    log_activity(
        user=user,
        action='shipping_request_shipped',
        entity_type='shipping_request',
        entity_id=sr.id,
        old_value={'status': old_status},
        new_value={
            'status': 'wyslane',
            'tracking_number': tracking_number or None,
            'courier': sr.courier,
            'wms_session_id': wms_session.id if wms_session else None,
            'source': 'wms_session' if wms_session else 'lista_zlecen',
        },
    )

    return {
        'id': sr.id,
        'request_number': sr.request_number,
        'status': 'wyslane',
        'tracking_number': sr.tracking_number,
    }


# ====================
# POWRÓT DO WMS
# ====================


REOPEN_MODES = ('full', 'repack')


def reopen_orders_for_wms(orders, mode, shipping_requests=()):
    """Cofa spakowane zamówienia do stanu roboczego WMS.

    mode='full'   — czyści też odhaczone pozycje; sesja startuje od zbierania
    mode='repack' — pozycje zostają zebrane; sesja startuje od pakowania

    Opakowanie wraca na stan i przypisanie się czyści, żeby ponowne pakowanie
    odjęło je normalnie — dzięki temu stan magazynowy nie rozjeżdża się przy
    wielokrotnym cofaniu tego samego zlecenia.

    Zamówienia w innym statusie niż 'spakowane' są pomijane bez zmian —
    zlecenie może być mieszane.
    """
    from extensions import db

    for order in orders:
        if order.status != 'spakowane':
            continue

        order.status = 'dostarczone_gom'
        order.packed_at = None
        order.packed_by = None

        if order.packaging_material_id:
            mat = db.session.get(PackagingMaterial, order.packaging_material_id)
            if mat:   # materiał mógł zostać skasowany od czasu pakowania
                mat.quantity_in_stock = (mat.quantity_in_stock or 0) + 1
            order.packaging_material_id = None

        if mode == 'full':
            for item in order.items:
                item.picked = False
                item.picked_quantity = 0
                item.picked_at = None
                item.picked_by = None
                item.wms_status = 'do_zebrania'

    for sr in shipping_requests:
        if sr.status == 'spakowane':
            sr.status = 'oplacone'
