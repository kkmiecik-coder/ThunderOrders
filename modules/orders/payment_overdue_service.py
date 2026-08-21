"""
Jedyne źródło prawdy o tym, które etapy płatności (E1-E4) danego zamówienia
są zaległe — termin minął, kwota nieopłacona. Używane przez kafelek i stronę
zaległości w panelu admina, cron przypomnień i builder maila przypomnienia.
"""
from modules.orders.models import get_local_now

STAGE_DEFINITIONS = {
    'product': {
        'label': 'Płatność za produkt',
        'status': lambda order: order.product_payment_status,
        'amount': lambda order: order.total_amount,
        'deadline': lambda order: order.get_product_deadline(),
        'applies': lambda order: True,
    },
    'shipping_kr': {
        'label': 'Płatność za wysyłkę z Korei',
        'status': lambda order: order.stage_2_status,
        'amount': lambda order: order.proxy_shipping_cost,
        'deadline': lambda order: order.get_shipping_kr_deadline(),
        'applies': lambda order: order.payment_stages == 4,
    },
    'customs_vat': {
        'label': 'Cło/VAT',
        'status': lambda order: order.stage_3_status,
        'amount': lambda order: order.customs_vat_sale_cost,
        'deadline': lambda order: order.get_customs_vat_deadline(),
        'applies': lambda order: order.has_customs_vat_stage,
    },
    'domestic_shipping': {
        'label': 'Wysyłka krajowa (PL)',
        'status': lambda order: order.stage_4_status,
        'amount': lambda order: order.shipping_cost,
        'deadline': lambda order: order.get_shipping_pl_deadline(),
        'applies': lambda order: True,
    },
}

# Statusy etapu, przy których zamówienie NIGDY nie jest liczone jako zaległe:
# 'pending' (klient już wgrał dowód, czeka na weryfikację admina) i 'approved'.
_NOT_OVERDUE_STATUSES = ('pending', 'approved')


def get_order_overdue_stages(order, now=None):
    """Zwraca listę zaległych etapów jednego zamówienia.

    Etap liczy się jako zaległy, gdy: dotyczy zamówienia (`applies`), ma
    ustalony termin (`deadline` nie jest None), termin minął, kwota > 0
    i status etapu to 'none' lub 'rejected'. Brak ustalonego terminu NIE
    jest zaległością (nie da się przekroczyć terminu, którego nie ma).
    """
    now = now or get_local_now()
    overdue = []

    for stage, definition in STAGE_DEFINITIONS.items():
        if not definition['applies'](order):
            continue

        status = definition['status'](order)
        if status in _NOT_OVERDUE_STATUSES:
            continue

        deadline = definition['deadline'](order)
        if deadline is None or deadline >= now:
            continue

        amount = definition['amount'](order)
        if not amount or amount <= 0:
            continue

        overdue.append({
            'stage': stage,
            'stage_label': definition['label'],
            'amount': amount,
            'deadline': deadline,
            'days_overdue': (now - deadline).days,
        })

    return overdue


def get_overdue_orders_summary():
    """Zwraca aktywne zamówienia z >=1 zaległym etapem, najdłużej zalegające pierwsze.

    Dociąga relacje (offer_page, shipping_request_orders,
    PolandOrderItemOrder → PolandOrderItem → PolandOrder, PaymentConfirmation)
    zbiorczo przed pętlą, zamiast per-zamówienie —
    inaczej to N+1 zapytań (2000+ zamówień x kilka lazy-loadów w
    get_order_overdue_stages = kilkanaście tysięcy zapytań, kilkanaście
    sekund na dashboardzie admina).
    """
    from sqlalchemy.orm import joinedload, selectinload
    from modules.orders.models import Order, ShippingRequestOrder, PaymentConfirmation
    from modules.products.models import PolandOrderItem, PolandOrderItemOrder

    now = get_local_now()
    results = []

    from utils.offer_closure import CLOSED_ORDER_STATUSES

    orders = Order.query.filter(~Order.status.in_(CLOSED_ORDER_STATUSES)).options(
        joinedload(Order.offer_page),
        selectinload(Order.shipping_request_orders).joinedload(ShippingRequestOrder.shipping_request),
    ).all()

    order_ids = [order.id for order in orders]
    poland_items_by_order_id = {}
    confirmations_by_order_id = {}
    if order_ids:
        links = (
            PolandOrderItemOrder.query
            .filter(PolandOrderItemOrder.order_id.in_(order_ids))
            .options(joinedload(PolandOrderItemOrder.poland_order_item).joinedload(PolandOrderItem.poland_order))
            .order_by(PolandOrderItemOrder.id)
            .all()
        )
        for link in links:
            poland_items_by_order_id.setdefault(link.order_id, []).append(link.poland_order_item)

        confirmations = (
            PaymentConfirmation.query
            .filter(PaymentConfirmation.order_id.in_(order_ids))
            .order_by(PaymentConfirmation.id)
            .all()
        )
        for conf in confirmations:
            # Nadpisujemy, nie setdefault: przy rosnącym `id` wygrywa NAJNOWSZY
            # wiersz etapu — parytet z `stage_4_confirmation`. E4 dopuszcza
            # dopłatę, więc potwierdzeń bywa kilka, a setdefault zostawiał tu
            # najstarsze i serwis zaległości pokazywałby stan sprzed korekty.
            confirmations_by_order_id.setdefault(conf.order_id, {})[conf.payment_stage] = conf

    for order in orders:
        order._cached_poland_items = poland_items_by_order_id.get(order.id, [])
        order._cached_payment_confirmations = confirmations_by_order_id.get(order.id, {})
        stages = get_order_overdue_stages(order, now=now)
        if not stages:
            continue
        primary_stage = max(stages, key=lambda s: s['days_overdue'])
        results.append({
            'order': order,
            'overdue_stages': stages,
            'primary_stage': primary_stage,
        })

    results.sort(key=lambda r: r['primary_stage']['days_overdue'], reverse=True)
    return results
