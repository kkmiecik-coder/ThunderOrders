"""
Renderowanie szablonów tytułu przelewu i dodatkowych informacji
z podstawieniem placeholderów opartych na danych zamówień.

Obsługiwane placeholdery (case-insensitive, zarówno nowa jak stara konwencja):
    [numer_zamowienia] / [NUMER ZAMÓWIENIA]  → numery zamówień (join ', ')
    [klient]            / [KLIENT]            → imię + nazwisko klienta
    [strona_sprzedazy]  / [STRONA SPRZEDAŻY]  → unikalne nazwy stron sprzedaży

Brakujące wartości zamieniane są na pusty string.
"""

import re


_PLACEHOLDERS = [
    (re.compile(r'\[numer_zamowienia\]', re.IGNORECASE), 'order_numbers'),
    (re.compile(r'\[NUMER ZAMÓWIENIA\]', re.IGNORECASE), 'order_numbers'),
    (re.compile(r'\[klient\]', re.IGNORECASE), 'customer'),
    (re.compile(r'\[KLIENT\]', re.IGNORECASE), 'customer'),
    (re.compile(r'\[strona_sprzedazy\]', re.IGNORECASE), 'offer_page'),
    (re.compile(r'\[STRONA SPRZEDAŻY\]', re.IGNORECASE), 'offer_page'),
]


def _collect_values(orders):
    order_numbers = []
    customers = []
    offer_pages = []

    for order in orders:
        if order.order_number and order.order_number not in order_numbers:
            order_numbers.append(order.order_number)

        customer = _resolve_customer(order)
        if customer and customer not in customers:
            customers.append(customer)

        page = _resolve_offer_page(order)
        if page and page not in offer_pages:
            offer_pages.append(page)

    return {
        'order_numbers': ', '.join(order_numbers),
        'customer': ', '.join(customers),
        'offer_page': ', '.join(offer_pages),
    }


def _resolve_customer(order):
    user = getattr(order, 'user', None)
    if user is None:
        return ''
    first = (getattr(user, 'first_name', None) or '').strip()
    last = (getattr(user, 'last_name', None) or '').strip()
    name = f"{first} {last}".strip()
    return name


def _resolve_offer_page(order):
    page = getattr(order, 'offer_page', None)
    if page and getattr(page, 'name', None):
        return page.name
    preserved = getattr(order, 'offer_page_name', None)
    return preserved or ''


def render_transfer_title(template, orders):
    """
    Podstawia placeholdery w szablonie tytułu/dodatkowych informacji.

    Args:
        template: str — szablon z placeholderami (może być None/"" — zwraca "").
        orders: Order | Iterable[Order] — pojedyncze zamówienie lub lista.

    Returns:
        str — renderowany string.
    """
    if not template:
        return ''

    if not isinstance(orders, (list, tuple, set)):
        orders = [orders]

    values = _collect_values(orders)

    result = template
    for pattern, key in _PLACEHOLDERS:
        result = pattern.sub(values[key], result)
    return result
