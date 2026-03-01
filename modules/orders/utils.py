"""
Orders Module - Utility Functions
==================================

Helper functions for orders management:
- Order number generation
- Courier detection from tracking number
- Tracking URL generation
- Status badge classes
"""

import re
from extensions import db
from modules.orders.models import Order, OrderType


# ====================
# ORDER NUMBER GENERATION
# ====================

def generate_order_number(order_type_slug):
    """
    Generate unique order number based on order type.

    Format: {PREFIX}/{SEQUENCE}
    Examples: PO/00000001, OH/00000002, EX/00000003

    Args:
        order_type_slug (str): Order type slug ('pre_order', 'on_hand', 'exclusive')

    Returns:
        str: Formatted order number
    """
    # Get order type to retrieve prefix
    order_type = OrderType.query.filter_by(slug=order_type_slug).first()
    if not order_type:
        raise ValueError(f"Invalid order type: {order_type_slug}")

    prefix = order_type.prefix  # PO, OH, or EX

    # Find the highest order number for this type
    last_order = Order.query.filter(
        Order.order_number.like(f"{prefix}/%")
    ).order_by(
        Order.id.desc()
    ).first()

    if last_order:
        # Extract sequence number from last order
        try:
            last_sequence = int(last_order.order_number.split('/')[-1])
            next_sequence = last_sequence + 1
        except (ValueError, IndexError):
            next_sequence = 1
    else:
        next_sequence = 1

    # Format: PREFIX/00000001
    return f"{prefix}/{next_sequence:08d}"


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
        'is_guest': order.is_guest_order,
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
