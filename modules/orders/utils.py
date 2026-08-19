"""
Orders Module - Utility Functions
==================================

Helper functions for orders management:
- Order number generation (format: {PREFIX}/{ID}, bez zer wiodących)
- Courier detection from tracking number
- Tracking URL generation
- Status badge classes
"""

import re
import uuid

from extensions import db
from modules.orders.models import Order, OrderType


# ====================
# ORDER NUMBER GENERATION
# ====================

def normalize_order_number(order_number):
    """
    Usuwa zera wiodące z części sekwencyjnej numeru.

    Prefiks (także wieloczłonowy) zostaje nietknięty:
    'EX/00001804' -> 'EX/1804', 'PRX/PL/00001' -> 'PRX/PL/1'.
    Numery nieliczbowe (np. placeholder) wracają bez zmian.
    """
    if not order_number or '/' not in order_number:
        return order_number

    prefix, _, sequence = order_number.rpartition('/')
    if not sequence.isdigit():
        return order_number

    return f"{prefix}/{int(sequence)}"


def order_number_placeholder():
    """
    Tymczasowy numer na czas INSERT-a, zanim rekord dostanie ID.

    Musi być unikalny, bo `orders.order_number` ma UNIQUE — dwa równoległe
    zamówienia nie mogą zderzyć się już na placeholderze. Żyje do najbliższego
    `assign_order_number()` w tej samej transakcji.

    Mieści się w VARCHAR(20): 'TMP/' + 12 znaków hex.
    """
    return f"TMP/{uuid.uuid4().hex[:12]}"


def get_order_prefix(order_type_slug):
    """
    Prefiks numeru dla typu zamówienia ('PO', 'OH', 'EX').

    Raises:
        ValueError: gdy typ nie istnieje w słowniku OrderType.
    """
    order_type = OrderType.query.filter_by(slug=order_type_slug).first()
    if not order_type:
        raise ValueError(f"Invalid order type: {order_type_slug}")
    return order_type.prefix


def assign_order_number(order, order_type_slug):
    """
    Nadaje zamówieniu docelowy numer w formacie {PREFIX}/{ID}.

    Numer wynika z klucza głównego, więc kolizja jest niemożliwa nawet przy
    równoległych zamówieniach z tej samej sekundy (ClickUp 869ekw4p0) — stary
    generator czytał ostatni numer zwykłym SELECT-em i przy sprzedaży LIVE
    nadawał ten sam numer kilku klientom.

    Wywołanie MUSI nastąpić po `db.session.flush()`, gdy rekord ma już ID.

    Args:
        order (Order): zamówienie po flushu (z nadanym ID)
        order_type_slug (str): slug typu ('pre_order', 'on_hand', 'exclusive')

    Returns:
        str: nadany numer

    Raises:
        ValueError: nieznany typ zamówienia
        RuntimeError: rekord nie ma jeszcze ID (brak flusha)
    """
    if order.id is None:
        raise RuntimeError(
            "assign_order_number wymaga ID — wywołaj po db.session.flush()"
        )

    prefix = get_order_prefix(order_type_slug)

    # Numer historyczny (sprzed przejścia na ID) może przypadkiem zająć
    # {PREFIX}/{ID} nowego rekordu — wtedy bierzemy pierwszy wolny.
    sequence = order.id
    while True:
        candidate = f"{prefix}/{sequence}"
        zajety = Order.query.filter(
            Order.order_number == candidate,
            Order.id != order.id
        ).first()
        if not zajety:
            break
        sequence += 1

    order.order_number = candidate
    return candidate


# ====================
# COURIER DETECTION
# ====================

# Regex patterns for courier detection
COURIER_PATTERNS = {
    'InPost': r'^\d{24}$',  # 24 digits
    'DPD': r'^\d{14}$',  # 14 digits
    'DHL': r'^\d{10,11}$',  # 10-11 digits
    'Poczta Polska': r'^\d{13}[A-Z]{2}$',  # 13 digits + 2 uppercase letters
}


def detect_courier(tracking_number):
    """
    Detect courier from tracking number using regex patterns.

    Args:
        tracking_number (str): Tracking number to analyze

    Returns:
        dict: {
            'courier': str or None,
            'confidence': 'high' or 'low',
            'url': str or None
        }
    """
    if not tracking_number:
        return {'courier': None, 'confidence': 'low', 'url': None}

    # Clean tracking number (remove spaces, dashes)
    cleaned = tracking_number.replace(' ', '').replace('-', '').strip()

    # Try to match patterns
    for courier, pattern in COURIER_PATTERNS.items():
        if re.match(pattern, cleaned):
            return {
                'courier': courier,
                'confidence': 'high',
                'url': get_tracking_url(courier, cleaned)
            }

    # No match found
    return {'courier': None, 'confidence': 'low', 'url': None}


# ====================
# TRACKING URL GENERATION
# ====================

# Tracking URL templates for each courier (using lowercase slugs as keys)
TRACKING_URLS = {
    'inpost': 'https://inpost.pl/sledzenie-przesylek?number={tracking_number}',
    'dpd': 'https://tracktrace.dpd.com.pl/parcelDetails?p1={tracking_number}',
    'dhl': 'https://www.dhl.com/pl-pl/home/tracking/tracking-parcel.html?submit=1&tracking-id={tracking_number}',
    'gls': 'https://gls-group.com/PL/pl/sledzenie-paczek?match={tracking_number}',
    'poczta_polska': 'https://emonitoring.poczta-polska.pl/?numer={tracking_number}',
    'orlen': 'https://nadaj.orlenpaczka.pl/parcel/{tracking_number}',
    'ups': 'https://www.ups.com/track?tracknum={tracking_number}&loc=pl_PL',
    'fedex': 'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
    # Legacy keys (uppercase) for backwards compatibility
    'InPost': 'https://inpost.pl/sledzenie-przesylek?number={tracking_number}',
    'DPD': 'https://tracktrace.dpd.com.pl/parcelDetails?p1={tracking_number}',
    'DHL': 'https://www.dhl.com/pl-pl/home/tracking/tracking-parcel.html?submit=1&tracking-id={tracking_number}',
    'GLS': 'https://gls-group.com/PL/pl/sledzenie-paczek?match={tracking_number}',
    'Poczta Polska': 'https://emonitoring.poczta-polska.pl/?numer={tracking_number}',
    'UPS': 'https://www.ups.com/track?tracknum={tracking_number}&loc=pl_PL',
    'FedEx': 'https://www.fedex.com/fedextrack/?trknbr={tracking_number}',
}


def get_tracking_url(courier, tracking_number):
    """
    Generate tracking URL for given courier and tracking number.

    Args:
        courier (str): Courier name or slug (e.g., 'inpost', 'InPost', 'poczta_polska')
        tracking_number (str): Tracking number

    Returns:
        str or None: Tracking URL or None if courier not supported
    """
    if not courier or not tracking_number:
        return None

    # Try exact match first, then lowercase
    template = TRACKING_URLS.get(courier) or TRACKING_URLS.get(courier.lower())
    if not template:
        return None

    # Clean tracking number
    cleaned = tracking_number.replace(' ', '').replace('-', '').strip()

    return template.format(tracking_number=cleaned)


# ====================
# STATUS UTILITIES
# ====================

# Status badge class mapping (fallback if database not available)
STATUS_BADGE_CLASSES = {
    'nowe': 'badge-info',
    'oczekujace': 'badge-orange',
    'dostarczone_proxy': 'badge-purple',
    'w_drodze_polska': 'badge-purple',
    'urzad_celny': 'badge-warning',
    'dostarczone_gom': 'badge-purple',
    'spakowane': 'badge-purple',
    'wyslane': 'badge-purple',
    'dostarczone': 'badge-success',
    'anulowane': 'badge-gray',
    'do_zwrotu': 'badge-warning',
    'zwrocone': 'badge-error',
    'czesciowo_zwrocone': 'badge-warning',
}


def get_status_badge_class(status_slug):
    """
    Get CSS badge class for order status.

    Args:
        status_slug (str): Status slug

    Returns:
        str: CSS class name
    """
    return STATUS_BADGE_CLASSES.get(status_slug, 'badge-default')


# Type badge class mapping (fallback)
TYPE_BADGE_CLASSES = {
    'pre_order': 'type-pre-order',
    'on_hand': 'type-on-hand',
    'exclusive': 'type-exclusive',
}


def get_type_badge_class(type_slug):
    """
    Get CSS badge class for order type.

    Args:
        type_slug (str): Type slug

    Returns:
        str: CSS class name
    """
    return TYPE_BADGE_CLASSES.get(type_slug, 'type-default')


# ====================
# ORDER UTILITIES
# ====================

def calculate_order_total(order_items):
    """
    Calculate total amount for order items.

    Args:
        order_items (list): List of OrderItem objects or dicts with 'price' and 'quantity'

    Returns:
        Decimal: Total amount
    """
    from decimal import Decimal

    total = Decimal('0.00')

    for item in order_items:
        if isinstance(item, dict):
            price = Decimal(str(item.get('price', 0)))
            quantity = int(item.get('quantity', 0))
        else:
            price = item.price
            quantity = item.quantity

        total += price * quantity

    return total


def get_order_summary(order):
    """
    Get summary information for order (for emails, notifications).

    Args:
        order (Order): Order object

    Returns:
        dict: Summary information
    """
    return {
        'order_number': order.order_number,
        'customer_name': order.customer_name,
        'customer_email': order.customer_email,
        'status': order.status_display_name,
        'type': order.type_display_name,
        'total_amount': float(order.total_amount),
        'items_count': order.items_count,
        'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'tracking_number': order.tracking_number,
        'courier': order.courier,
    }


# ====================
# COURIER LIST
# ====================

def get_courier_choices():
    """
    Get list of available couriers for dropdown.

    Returns:
        list: List of tuples (value, label)
    """
    return [
        ('', '-- Wybierz kuriera --'),
        ('InPost', 'InPost'),
        ('DPD', 'DPD'),
        ('DHL', 'DHL'),
        ('Poczta Polska', 'Poczta Polska'),
        ('Inny', 'Inny'),
    ]


# ====================
# SLUG GENERATION
# ====================

def generate_slug(text):
    """
    Generate URL-safe slug from text.

    Converts Polish characters, removes special chars, replaces spaces with underscores.

    Args:
        text (str): Text to convert to slug

    Returns:
        str: URL-safe slug

    Examples:
        "Nowe zamówienie" -> "nowe_zamowienie"
        "W drodze - PL" -> "w_drodze_pl"
        "Dostarczone (GOM)" -> "dostarczone_gom"
    """
    if not text:
        return ''

    # Polish character mapping
    polish_map = {
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n',
        'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N',
        'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z'
    }

    # Replace Polish characters
    slug = text
    for polish, ascii_char in polish_map.items():
        slug = slug.replace(polish, ascii_char)

    # Convert to lowercase
    slug = slug.lower()

    # Replace spaces and special characters with underscore
    slug = re.sub(r'[^\w\s-]', '', slug)  # Remove non-alphanumeric except spaces and hyphens
    slug = re.sub(r'[\s-]+', '_', slug)   # Replace spaces and hyphens with underscore
    slug = slug.strip('_')                # Remove leading/trailing underscores

    return slug


# ====================
# DIAGNOSTYKA BŁĘDÓW
# ====================

def zaloguj_blad_z_identyfikatorem(kontekst):
    """Loguje traceback z krótkim identyfikatorem i zwraca ten identyfikator.

    Ten sam ciąg trafia do loga i do komunikatu dla użytkownika, więc zgłoszenie
    „nie zapisało się" da się skorelować z konkretnym wpisem w logu zamiast zgadywać
    po godzinie. Samego tracebacka nigdy nie wypuszczamy do przeglądarki.
    """
    import uuid
    from flask import current_app

    blad_id = uuid.uuid4().hex[:8]
    current_app.logger.exception(f'[{blad_id}] {kontekst}')
    return blad_id


def apply_order_sorting(query, sort_by, sort_order):
    """
    Dokłada sortowanie do zapytania o zamówienia.

    Numer nie nadaje się do sortowania tekstowego, odkąd nie ma zer wiodących
    ('EX/999' > 'EX/1804' leksykograficznie). Sekwencja rośnie razem z ID, więc
    sortujemy po (typ, ID) — kolejność jak po numerze, a numery różnych typów
    nadal trzymają się razem na liście.

    Args:
        query: zapytanie o Order
        sort_by (str): 'order_number', 'total_amount' lub cokolwiek (created_at)
        sort_order (str): 'asc' albo 'desc'

    Returns:
        Zapytanie z ORDER BY
    """
    malejaco = sort_order == 'desc'

    if sort_by == 'order_number':
        kolumny = (Order.order_type, Order.id)
    elif sort_by == 'total_amount':
        kolumny = (Order.total_amount,)
    else:
        kolumny = (Order.created_at,)

    return query.order_by(*(k.desc() if malejaco else k.asc() for k in kolumny))


def plan_number_normalization(rows):
    """
    Układa plan przenumerowania historii: obcięcie zer wiodących + rozbicie
    duplikatów, które narosły przez race condition w starym generatorze
    (ClickUp 869ekw4p0).

    Zasady:
    - numer zachowuje rekord z najniższym ID (to jego numer poszedł w mailach
      jako pierwszy),
    - pozostałe dostają kolejne numery ZA końcem swojej serii. Wciskanie ich
      w luki po skasowanych zamówieniach dałoby lipcowemu zamówieniu numer
      wyglądający na kwietniowy.

    Args:
        rows: iterable par (id, numer), dowolna kolejność

    Returns:
        dict: {id: nowy_numer} — tylko rekordy wymagające UPDATE-u
    """
    rows = sorted(rows, key=lambda r: r[0])

    # Numery, które ktoś już „ma" po normalizacji — zastępczy numer duplikatu
    # nie może zabrać numeru rekordowi, który dostałby go zgodnie z historią.
    zarezerwowane = {normalize_order_number(number) for _, number in rows}

    # Koniec każdej serii, od którego dokładamy numery zastępcze
    nastepny_wolny = {}
    for numer in zarezerwowane:
        prefix, _, sekwencja = numer.rpartition('/')
        if sekwencja.isdigit():
            nastepny_wolny[prefix] = max(
                nastepny_wolny.get(prefix, 0), int(sekwencja) + 1
            )

    plan = {}
    zajete = set()

    for record_id, number in rows:
        docelowy = normalize_order_number(number)

        if docelowy in zajete:
            prefix, _, _ = docelowy.rpartition('/')
            sequence = nastepny_wolny.get(prefix, 1)
            while (f"{prefix}/{sequence}" in zajete
                   or f"{prefix}/{sequence}" in zarezerwowane):
                sequence += 1
            docelowy = f"{prefix}/{sequence}"
            nastepny_wolny[prefix] = sequence + 1

        zajete.add(docelowy)
        if docelowy != number:
            plan[record_id] = docelowy

    return plan
