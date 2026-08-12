"""
WMS Utilities — Packaging Suggestion Algorithm
================================================

Provides suggest_packaging_for_orders(orders), which analyzes the items of one
or more orders packed together and returns ranked packaging suggestions.
Jedno zlecenie wysyłki jedzie w jednej paczce, więc dopasowanie liczymy po
sumie wagi i objętości wszystkich zamówień z paczki.
"""

from modules.orders.wms_models import PackagingMaterial


def suggest_packaging(order):
    """Sugestie opakowań dla pojedynczego zamówienia — cienka nakładka
    na suggest_packaging_for_orders(), zostawiona dla istniejących endpointów."""
    return suggest_packaging_for_orders([order])


def suggest_packaging_for_orders(orders):
    """
    Analyze items of orders packed together and suggest best-fit packaging materials.

    Returns dict with keys:
      - suggestions: list of top 3 material dicts (sorted by fit_score desc, cost asc)
      - warnings: list of warning strings
      - total_weight: total product weight in kg (float)
      - total_volume: total needed volume in cm³ (float)
    """
    items = []
    for order in orders or []:
        items.extend(order.items or [])

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


class ShippingRequestUnpaid(Exception):
    """Zlecenie jest w statusie przedpłatnym (klient jeszcze nie zapłacił) —
    nie da się go wysłać, niezależnie od tego, którą drogą (lista zleceń
    czy panel w sesji WMS)."""


# Statusy przedpłatne — zanim za zlecenie zapłacono, nie wolno go wysłać.
# Celowo NIE blokujemy tu wszystkiego poza 'spakowane': część zamówień
# zlecenia może pakować się w innej, wciąż otwartej sesji WMS, więc samo
# zlecenie nie ma jeszcze statusu 'spakowane' — twardy warunek "tylko
# spakowane" zablokowałby wysyłkę takiego (już opłaconego) zlecenia całkowicie.
UNPAID_SR_STATUSES = ('czeka_na_wycene', 'czeka_na_oplacenie')


def ship_shipping_request(sr, *, courier=None, tracking_number=None, parcel_size=None,
                          shipping_cost=None, order_costs=None, user=None, wms_session=None):
    """Oznacza zlecenie wysyłki jako wysłane.

    Wspólne dla panelu w sesji WMS i dla listy zleceń — jedno miejsce, w którym
    zmieniają się statusy, powstaje wpis przesyłki i idą powiadomienia do klienta.

    Numer przesyłki jest nieobowiązkowy. Gdy go nie ma, nie powstaje OrderShipment
    (wpis bez numeru niczego nie wnosi), a klient dostaje powiadomienie o zmianie
    statusu zamiast powiadomienia o trackingu.

    Numer przesyłki bez wybranego kuriera dostaje kuriera zastępczego 'other'
    ("Inny") — zarówno na zleceniu, jak i we wpisie przesyłki — żeby nie próbować
    zapisać pustego kuriera (kolumna jest NOT NULL).

    Statusy zleceń/zamówień i wpis przesyłki lądują w jednym commicie: albo
    wszystko, albo nic. Powiadomienia idą dopiero po commicie i błąd maila/pusha
    nie cofa już zapisanej wysyłki.
    """
    from flask import current_app

    from extensions import db
    from modules.orders.models import Order, OrderShipment, OrderStatus, get_local_now
    from utils.activity_logger import log_activity
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    if sr.status == 'wyslane':
        raise ShippingRequestAlreadyShipped(f'Zlecenie {sr.request_number} jest już wysłane')

    if sr.status in UNPAID_SR_STATUSES:
        raise ShippingRequestUnpaid(
            f'Zlecenie {sr.request_number} nie zostało jeszcze opłacone '
            f'(status: „{sr.status_display_name}") — nie można go wysłać'
        )

    old_status = sr.status
    tracking_number = (tracking_number or '').strip()

    # Puste pole nie kasuje tego, co już jest na zleceniu.
    if courier:
        sr.courier = courier
    if tracking_number:
        sr.tracking_number = tracking_number
        if not sr.courier:
            sr.courier = 'other'
    if parcel_size:
        sr.parcel_size = parcel_size
    sr.status = 'wyslane'
    sr.shipped_at = get_local_now()

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

    changed_status_order_ids = set()

    order_status = OrderStatus.query.filter_by(slug='wyslane', is_active=True).first()
    if order_status:
        for o in sr.orders:
            if o.status != 'wyslane':
                o.status = 'wyslane'
                changed_status_order_ids.add(o.id)

    courier_name = COURIER_NAMES.get(sr.courier, sr.courier or 'Kurier')

    # Tylko NOWO powstałe wpisy przesyłki uruchamiają powiadomienie o trackingu —
    # inaczej klient, który dostał już maila z okna "Dodaj koszty", dostałby
    # identyczną wiadomość drugi raz przy "Oznacz jako wysłane".
    new_shipment_order_ids = set()
    if tracking_number:
        for order in sr.orders:
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
                new_shipment_order_ids.add(order.id)

    # Paczka zbiorcza wysłana przez WMS: status, tracking i kurier muszą zjechać na
    # zlecenia źródłowe razem z tym samym commitem — inaczej klient źródłowy zostaje
    # ze starym statusem, mimo że jego paczka fizycznie już pojechała.
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(sr)

    # Jeden commit na wszystkie dane — statusy i wpis przesyłki razem albo wcale.
    db.session.commit()

    # Jedna wiadomość na paczkę, nie na zamówienie: klient dostaje fizycznie jeden
    # karton, więc trzy maile o tej samej przesyłce były dla niego szumem.
    try:
        if new_shipment_order_ids:
            EmailManager.notify_shipment_sent(
                sr, tracking_number=tracking_number, courier=sr.courier,
                courier_name=courier_name, tracking_url=sr.tracking_url)
            PushManager.notify_shipment_sent(
                sr, tracking_number=tracking_number, courier_name=courier_name)
        elif order_status and changed_status_order_ids and not sr.tracking_number:
            # Bez numeru przesyłki — ta sama wiadomość, tylko bez bloku śledzenia.
            # Warunek "not sr.tracking_number" jest tu kluczowy: jeśli zlecenie MA już
            # numer przesyłki (dopisany wcześniej przez "Dodaj koszty"), klient dostał
            # już maila z trackingiem i "Oznacz jako wysłane" nie ma mu nic nowego do
            # powiedzenia. Bez tego warunku klient dostawałby DRUGI mail — tym samym
            # szablonem, ale bez numeru przesyłki — co wygląda jak uboższy duplikat,
            # a nie jak druga wiadomość.
            EmailManager.notify_shipment_sent(sr)
            PushManager.notify_shipment_sent(sr)
    except Exception as err:
        current_app.logger.error(
            f'Powiadomienie o wysyłce {sr.request_number}: {err}')

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
# DOSTAWA ZLECENIA
# ====================


class ZlecenieJuzDostarczone(Exception):
    """Zlecenie ma już status 'dostarczone' — drugi raz go nie domykamy."""


class ZlecenieZrodloweNieDomykane(Exception):
    """Zlecenie oddane do paczki zbiorczej domyka się wyłącznie przez tę paczkę.

    Gdyby wolno je było domknąć osobno, uczestnicy jednego kartonu rozjechaliby się
    statusami, a propagacja z paczki zbiorczej i tak nadpisałaby wynik.
    """


def dostarcz_zlecenie(sr, *, source, user=None, powiadom=True, status_juz_ustawiony=False):
    """Oznacza zlecenie wysyłki jako dostarczone.

    Jedyne miejsce, w którym zachodzi to przejście — wołają je panel klienta,
    komenda cron, synchronizacja statusów w adminie i API mobilne. Symetryczne do
    ship_shipping_request(): statusy, kaskady i kolekcja lądują w JEDNYM commicie,
    powiadomienia idą dopiero po nim i ich błąd nie cofa zapisanej dostawy.

    Args:
        sr: obiekt ShippingRequest
        source (str): 'klient' | 'auto' | 'admin' — zapisywane w delivered_source
        user: kto wykonał akcję (do logu aktywności); None dla automatu
        powiadom (bool): False pomija wysyłkę i oddaje dane wołającemu, który wyśle
            zbiorczo jednym połączeniem SMTP (używa tego cron przy zaległościach)
        status_juz_ustawiony (bool): True TYLKO dla synchronizacji statusów w adminie
            (`_sync_order_statuses_from_shipping_request`) — ta jedna ścieżka ustawia
            sr.status na 'dostarczone' i commituje ZANIM w ogóle wywoła tę funkcję,
            więc bez tej flagi strażnik widziałby status już zmieniony i nie odróżniłby
            „to pierwsze domknięcie, tylko wywołujący już zapisał status" od „to
            zlecenie historyczne, dostarczone kiedyś dawno, bez śladu w delivered_at".
            Domyślnie False — kolejne wywołujące (panel klienta, cron, API mobilne)
            NIE ustawiają statusu przed wywołaniem i tej flagi nie podają.

    Returns:
        dict: id, request_number, delivered_at, source, zmienione_zamowienia

    Raises:
        ZlecenieJuzDostarczone, ZlecenieZrodloweNieDomykane
    """
    from flask import current_app

    from extensions import db
    from modules.client.collection_utils import auto_add_order_to_collection
    from modules.orders.consolidation import propaguj_na_zrodla
    from modules.orders.models import OrderStatus, get_local_now
    from utils.activity_logger import log_activity
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    # Dwa niezależne sygnały „już dostarczone", bo żaden sam nie wystarczy:
    # - delivered_at ustawiamy WYŁĄCZNIE w tej funkcji, więc jego obecność zawsze
    #   znaczy „to wywołanie już tu było" — łapie powtórne wywołanie z dowolnej
    #   ścieżki.
    # - Sam sr.status == 'dostarczone' NIE wystarczy jako jedyny warunek: zlecenia
    #   sprzed tej funkcjonalności (aplikacja żyje od kwietnia) mają status
    #   'dostarczone', ale puste delivered_at — nikt go nie backfillował (Task 1
    #   backfillował tylko shipped_at). Bez rozróżnienia taki historyczny rekord
    #   przechodziłby przez strażnik, dostawał nadpisaną datą "teraz" i mailem
    #   z podziękowaniem za odbiór sprzed miesięcy.
    #   Jedyny wyjątek: synchronizacja statusów w adminie, która SAMA zapisała
    #   sr.status='dostarczone' i zacommitowała tuż przed wywołaniem — ona zna
    #   różnicę między „przed chwilą" a „historycznie" i mówi to wprost przez
    #   status_juz_ustawiony=True.
    if sr.delivered_at is not None:
        raise ZlecenieJuzDostarczone(
            f'Zlecenie {sr.request_number} jest już oznaczone jako dostarczone')

    if sr.status == 'dostarczone' and not status_juz_ustawiony:
        raise ZlecenieJuzDostarczone(
            f'Zlecenie {sr.request_number} jest już oznaczone jako dostarczone')

    if sr.is_consolidated_source:
        raise ZlecenieZrodloweNieDomykane(
            f'Zlecenie {sr.request_number} jedzie w paczce zbiorczej — '
            f'potwierdzenie odbioru dotyczy całej paczki')

    old_status = sr.status
    teraz = get_local_now()

    sr.status = 'dostarczone'
    sr.delivered_at = teraz
    sr.delivered_source = source

    propaguj_na_zrodla(sr)

    zmienione = []
    order_status = OrderStatus.query.filter_by(slug='dostarczone', is_active=True).first()
    if order_status:
        for o in sr.orders:
            if o.status != 'dostarczone':
                o.status = 'dostarczone'
                zmienione.append(o)

    # Kolekcja przed commitem — razem ze statusami albo wcale. To właśnie gubiła
    # dotychczasowa synchronizacja statusów zlecenia w adminie.
    for o in zmienione:
        try:
            auto_add_order_to_collection(o)
        except Exception as err:
            current_app.logger.error(
                f'Dopisanie do kolekcji dla {o.order_number}: {err}')

    db.session.commit()

    if powiadom:
        try:
            if source == 'auto':
                EmailManager.notify_delivery_autoclosed(sr)
                PushManager.notify_delivery_autoclosed(sr)
            else:
                EmailManager.notify_delivery_confirmed(sr)
                PushManager.notify_delivery_confirmed(sr)
                EmailManager.notify_admin_delivery_confirmed(sr)
                PushManager.notify_admin_delivery_confirmed(sr)
        except Exception as err:
            current_app.logger.error(
                f'Powiadomienie o dostawie {sr.request_number}: {err}')

    log_activity(
        user=user,
        action='shipping_request_delivered',
        entity_type='shipping_request',
        entity_id=sr.id,
        old_value={'status': old_status},
        new_value={'status': 'dostarczone', 'source': source},
    )

    return {
        'id': sr.id,
        'request_number': sr.request_number,
        'delivered_at': sr.delivered_at,
        'source': source,
        'zmienione_zamowienia': zmienione,
    }


# ====================
# POWRÓT DO WMS
# ====================


REOPEN_MODES = ('full', 'repack')


def reopen_orders_for_wms(orders, mode, shipping_requests=()):
    """Cofa spakowane zamówienia do stanu roboczego WMS.

    mode='full'   — czyści też odhaczone pozycje; sesja startuje od zbierania
    mode='repack' — pozycje zostają zebrane; sesja startuje od pakowania

    Opakowanie wraca na stan raz na paczkę (jedno zlecenie wysyłki = jeden karton)
    i przypisanie się czyści, żeby ponowne pakowanie odjęło je normalnie — dzięki
    temu stan magazynowy nie rozjeżdża się przy wielokrotnym cofaniu.

    Zamówienia w innym statusie niż 'spakowane' są pomijane bez zmian —
    zlecenie może być mieszane.
    """
    from extensions import db

    # Opakowanie schodzi ze stanu raz na paczkę (jedno zlecenie = jeden karton),
    # więc przy cofaniu też oddajemy je raz — inaczej stan rósłby z powietrza.
    returned_packages = set()

    for order in orders:
        if order.status != 'spakowane':
            continue

        order.status = 'dostarczone_gom'
        order.packed_at = None
        order.packed_by = None

        if order.packaging_material_id:
            sr = order.shipping_request
            package_key = ('sr', sr.id) if sr else ('order', order.id)
            if package_key not in returned_packages:
                returned_packages.add(package_key)
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

    from modules.orders.consolidation import propaguj_na_zrodla

    for sr in shipping_requests:
        if sr.status == 'spakowane':
            sr.status = 'oplacone'
            # Zbiorcza paczka cofnięta do WMS musi ściągnąć źródłowe z powrotem —
            # inaczej zostają ze statusem 'spakowane', mimo że paczka wróciła do pakowania.
            propaguj_na_zrodla(sr)
