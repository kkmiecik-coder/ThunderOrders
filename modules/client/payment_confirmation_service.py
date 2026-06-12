"""Wspólny serwis potwierdzeń płatności — web (bulk upload, lista) + mobilne API (E6)."""


def order_stage_keys(order):
    """Zbiór etapów STRUKTURALNIE obecnych dla zamówienia (kanon: web + E5 + walidacja bulku)."""
    keys = {'product', 'domestic_shipping'}
    if order.payment_stages == 4:
        keys.add('korean_shipping')
    if order.order_type != 'on_hand':
        keys.add('customs_vat')
    return keys
