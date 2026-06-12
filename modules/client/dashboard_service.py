"""Statystyki zamówieniowe dashboardu klienta — współdzielone przez web i mobilne API (E5).

Logika wyekstrahowana 1:1 z `modules/client/routes.py::dashboard()` (sekcje 1–5),
z `current_user` zamienionym na parametr `user`. Zwraca surowe dane (obiekty Order +
Decimale + liczby) — mapowanie na kontekst szablonu (web) lub kopertę grosze/ISO
(mobile) robią wywołujący. Zero zmiany zachowania względem dotychczasowej trasy.

Widgety nie-zamówieniowe (offer_pages / contest / tour) NIE należą tu — zostają
w trasie webowej.
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy import func as sql_func

from extensions import db
from modules.orders.models import Order, ShippingRequestOrder
from modules.auth.models import Settings


def get_client_dashboard_stats(user):
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)

    # 1. Liczniki zamówień
    orders_all = Order.query.filter_by(user_id=user.id).count()
    orders_in_progress = Order.query.filter_by(user_id=user.id).filter(
        Order.status.in_(['nowe', 'oczekujace', 'w_realizacji', 'spakowane', 'wyslane'])
    ).count()
    orders_delivered = Order.query.filter_by(user_id=user.id).filter_by(status='dostarczone').count()

    # 2. Statystyki płatności
    paid_total = db.session.query(
        sql_func.coalesce(sql_func.sum(Order.paid_amount), 0)
    ).filter_by(user_id=user.id).scalar() or Decimal('0.00')

    # Pełna należność klienta obejmuje wszystkie etapy (E1 produkt + E2 wysyłka KR +
    # E3 cło/VAT + E4 wysyłka PL, patrz Order.total_to_pay). Filtr DB to bezpieczny
    # nadzbiór (suma kolumn bez warunków etapowych >= total_to_pay), a precyzyjne
    # „pozostało" liczy remaining_to_pay w Pythonie.
    to_pay_orders = Order.query.filter_by(user_id=user.id).filter(
        Order.paid_amount < (
            Order.total_amount
            + Order.shipping_cost
            + sql_func.coalesce(Order.proxy_shipping_cost, 0)
            + sql_func.coalesce(Order.customs_vat_sale_cost, 0)
        )
    ).all()
    # Exclusive bez zamkniętej strony nie jest jeszcze płatne — wyklucz, by widget nie
    # pokazywał kwot, których klient nie może zapłacić.
    to_pay_total = sum(
        (o.remaining_to_pay for o in to_pay_orders
         if not (o.order_type == 'exclusive' and o.offer_page and not o.offer_page.is_fully_closed)),
        Decimal('0.00'),
    )

    # 3. Zamówienia oczekujące na zgłoszenie wysyłki
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    allowed_statuses = ['dostarczone_gom']
    if setting and setting.value:
        try:
            allowed_statuses = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed_statuses = ['dostarczone_gom']

    in_shipping_request = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id
    ).exists()
    orders_awaiting_shipping = Order.query.filter(
        and_(
            Order.user_id == user.id,
            Order.status.in_(allowed_statuses),
            ~in_shipping_request,
        )
    ).count()

    # 4. Ostatnie zamówienia (z obsługą lazy-loadingu — 5 widocznych + 5 bufor)
    recent_orders_all = Order.query.filter_by(user_id=user.id).order_by(
        Order.created_at.desc()
    ).limit(15).all()
    total_orders = Order.query.filter_by(user_id=user.id).count()

    # 5. Dane wykresu (30 dni) — puste dni zerami
    orders_by_day = db.session.query(
        sql_func.date(Order.created_at).label('order_date'),
        sql_func.count(Order.id).label('count')
    ).filter(
        Order.user_id == user.id,
        sql_func.date(Order.created_at) >= thirty_days_ago
    ).group_by(sql_func.date(Order.created_at)).all()

    all_dates = [(thirty_days_ago + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]
    orders_dict = {str(row[0]): row[1] for row in orders_by_day}

    return {
        'orders': {
            'all': orders_all,
            'in_progress': orders_in_progress,
            'delivered': orders_delivered,
            'awaiting_shipping': orders_awaiting_shipping,
        },
        'payment': {'paid': paid_total, 'to_pay': to_pay_total},
        'recent_orders': {
            'visible': recent_orders_all[:5],
            'buffer': recent_orders_all[5:10],
            'total': total_orders,
            'remaining': max(0, total_orders - 5),
        },
        'chart_data': {
            'labels': all_dates,
            'values': [orders_dict.get(d, 0) for d in all_dates],
        },
    }
