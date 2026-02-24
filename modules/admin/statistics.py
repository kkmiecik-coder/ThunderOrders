"""
Admin Statistics Routes
Endpointy API i widok strony statystyk admina.
Każda zakładka ładuje dane via AJAX (lazy loading).
"""

from flask import render_template, request, jsonify
from flask_login import login_required
from modules.admin import admin_bp
from utils.decorators import role_required
from extensions import db
from modules.auth.models import User
from modules.orders.models import Order, OrderItem, OrderShipment, ShippingRequest, ShippingRequestOrder, PaymentConfirmation
from modules.products.models import Product, ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem
from modules.exclusive.models import ExclusivePage
from sqlalchemy import func, desc, asc, case
from datetime import datetime, timedelta
from decimal import Decimal


# ========================================
# Pomocnicze funkcje
# ========================================

def _parse_range(range_param):
    """Zwraca (start_date, end_date) na podstawie parametru zakresu."""
    today = datetime.now().date()
    end_date = today

    if range_param == '7d':
        start_date = today - timedelta(days=6)
    elif range_param == '14d':
        start_date = today - timedelta(days=13)
    elif range_param == '30d':
        start_date = today - timedelta(days=29)
    elif range_param == '3m':
        start_date = today - timedelta(days=89)
    elif range_param == '12m':
        start_date = today - timedelta(days=364)
    elif range_param == 'ytd':
        start_date = today.replace(month=1, day=1)
    else:
        start_date = today - timedelta(days=6)

    return start_date, end_date


def _format_currency(value):
    """Formatuje wartość jako PLN z separatorem tysięcy."""
    if value is None:
        value = 0
    val = float(value)
    if val >= 1000:
        return f"{val:,.2f} PLN".replace(",", " ")
    return f"{val:.2f} PLN"


def _generate_date_labels(start_date, end_date):
    """Generuje listę dat (labels) i dat do filtrowania."""
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


# ========================================
# Widok główny
# ========================================

@admin_bp.route('/statistics')
@login_required
@role_required('admin', 'mod')
def statistics():
    """Strona statystyk - renderuje shell z zakładkami."""
    return render_template(
        'admin/statistics/index.html',
        title='Statystyki'
    )


# ========================================
# API: Przychody
# ========================================

@admin_bp.route('/statistics/api/revenue')
@login_required
@role_required('admin', 'mod')
def statistics_revenue():
    """Dane dla zakładki Przychody."""
    range_param = request.args.get('range', '30d')
    start_date, end_date = _parse_range(range_param)
    today = datetime.now().date()
    week_ago = today - timedelta(days=6)
    month_start = today.replace(day=1)

    # KPI: Przychód dziś
    revenue_today = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) == today,
        Order.status != 'anulowane'
    ).scalar() or Decimal('0')

    # KPI: Przychód ten tydzień
    revenue_week = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) >= week_ago,
        Order.status != 'anulowane'
    ).scalar() or Decimal('0')

    # KPI: Przychód ten miesiąc
    revenue_month = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) >= month_start,
        Order.status != 'anulowane'
    ).scalar() or Decimal('0')

    # Wykres liniowy: przychody w czasie
    dates = _generate_date_labels(start_date, end_date)
    chart_labels = []
    chart_values = []

    # Pobierz dane grupowane po dacie za jednym razem
    daily_revenue = db.session.query(
        func.date(Order.created_at).label('day'),
        func.coalesce(func.sum(Order.total_amount), 0).label('revenue')
    ).filter(
        func.date(Order.created_at) >= start_date,
        func.date(Order.created_at) <= end_date,
        Order.status != 'anulowane'
    ).group_by(func.date(Order.created_at)).all()

    revenue_map = {str(row.day): float(row.revenue) for row in daily_revenue}

    for d in dates:
        chart_labels.append(d.strftime('%d.%m'))
        chart_values.append(revenue_map.get(str(d), 0))

    # Tabela: Top 10 dni z najwyższym przychodem
    top_days = db.session.query(
        func.date(Order.created_at).label('day'),
        func.sum(Order.total_amount).label('revenue'),
        func.count(Order.id).label('orders_count')
    ).filter(
        Order.status != 'anulowane'
    ).group_by(
        func.date(Order.created_at)
    ).order_by(desc('revenue')).limit(10).all()

    top_days_rows = []
    for row in top_days:
        top_days_rows.append([
            str(row.day),
            _format_currency(row.revenue),
            row.orders_count
        ])

    # Metryki dodatkowe
    total_orders_non_cancelled = Order.query.filter(Order.status != 'anulowane').count()
    total_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status != 'anulowane').scalar() or Decimal('0')

    avg_order_value = float(total_revenue) / total_orders_non_cancelled if total_orders_non_cancelled > 0 else 0

    # Średnia marża z produktów które mają margin
    avg_margin = db.session.query(
        func.avg(Product.margin)
    ).filter(Product.margin.isnot(None)).scalar() or 0

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Przychód dziś', 'value': _format_currency(revenue_today), 'raw': float(revenue_today)},
            {'label': 'Przychód ten tydzień', 'value': _format_currency(revenue_week), 'raw': float(revenue_week)},
            {'label': 'Przychód ten miesiąc', 'value': _format_currency(revenue_month), 'raw': float(revenue_month)},
        ],
        'charts': {
            'main': {'labels': chart_labels, 'values': chart_values}
        },
        'tables': [{
            'title': 'Top 10 dni z najwyższym przychodem',
            'headers': ['Data', 'Przychód', 'Zamówień'],
            'rows': top_days_rows
        }],
        'metrics': {
            'avg_order_value': _format_currency(avg_order_value),
            'avg_margin': f"{float(avg_margin):.1f}%"
        }
    })


# ========================================
# API: Zamówienia
# ========================================

@admin_bp.route('/statistics/api/orders')
@login_required
@role_required('admin', 'mod')
def statistics_orders():
    """Dane dla zakładki Zamówienia."""
    range_param = request.args.get('range', '30d')
    start_date, end_date = _parse_range(range_param)

    # KPI
    total_orders = Order.query.count()
    in_progress = Order.query.filter(
        Order.status.in_(['nowe', 'oczekujace', 'w_realizacji', 'spakowane'])
    ).count()
    cancelled = Order.query.filter(Order.status == 'anulowane').count()

    # Wykres słupkowy: zamówienia per dzień
    dates = _generate_date_labels(start_date, end_date)
    daily_orders = db.session.query(
        func.date(Order.created_at).label('day'),
        func.count(Order.id).label('count')
    ).filter(
        func.date(Order.created_at) >= start_date,
        func.date(Order.created_at) <= end_date
    ).group_by(func.date(Order.created_at)).all()

    orders_map = {str(row.day): row.count for row in daily_orders}
    bar_labels = [d.strftime('%d.%m') for d in dates]
    bar_values = [orders_map.get(str(d), 0) for d in dates]

    # Wykres kołowy: podział po typach
    type_counts = db.session.query(
        Order.order_type,
        func.count(Order.id)
    ).group_by(Order.order_type).all()

    type_labels_map = {
        'on_hand': 'On-Hand',
        'pre_order': 'Pre-Order',
        'exclusive': 'Exclusive'
    }
    pie_type_labels = [type_labels_map.get(t[0], t[0] or 'Brak') for t in type_counts]
    pie_type_values = [t[1] for t in type_counts]

    # Wykres kołowy: podział po statusach
    status_counts = db.session.query(
        Order.status,
        func.count(Order.id)
    ).group_by(Order.status).all()

    pie_status_labels = [s[0] or 'Brak' for s in status_counts]
    pie_status_values = [s[1] for s in status_counts]

    # Metryki
    total_non_cancelled = Order.query.filter(Order.status != 'anulowane').count()
    total_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status != 'anulowane').scalar() or Decimal('0')
    avg_order = float(total_revenue) / total_non_cancelled if total_non_cancelled > 0 else 0

    # % w pełni opłaconych
    fully_paid = db.session.query(func.count(Order.id)).filter(
        Order.status != 'anulowane',
        Order.paid_amount >= (Order.total_amount + Order.shipping_cost)
    ).scalar() or 0
    pct_fully_paid = (fully_paid / total_non_cancelled * 100) if total_non_cancelled > 0 else 0

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Łącznie zamówień', 'value': str(total_orders), 'raw': total_orders},
            {'label': 'W realizacji', 'value': str(in_progress), 'raw': in_progress},
            {'label': 'Anulowane', 'value': str(cancelled), 'raw': cancelled},
        ],
        'charts': {
            'bar': {'labels': bar_labels, 'values': bar_values},
            'pie_types': {'labels': pie_type_labels, 'values': pie_type_values},
            'pie_statuses': {'labels': pie_status_labels, 'values': pie_status_values},
        },
        'metrics': {
            'avg_order_value': _format_currency(avg_order),
            'pct_fully_paid': f"{pct_fully_paid:.1f}%"
        }
    })


# ========================================
# API: Produkty
# ========================================

@admin_bp.route('/statistics/api/products')
@login_required
@role_required('admin', 'mod')
def statistics_products():
    """Dane dla zakładki Produkty."""
    # KPI
    active_products = Product.query.filter_by(is_active=True).count()

    total_sold = db.session.query(
        func.coalesce(func.sum(OrderItem.quantity), 0)
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Order.status != 'anulowane'
    ).scalar() or 0

    total_product_revenue = db.session.query(
        func.coalesce(func.sum(OrderItem.total), 0)
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Order.status != 'anulowane'
    ).scalar() or Decimal('0')

    # Tabela: Top 20 bestselerów
    bestsellers = db.session.query(
        Product.name,
        Product.sku,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total).label('total_revenue')
    ).join(
        OrderItem, OrderItem.product_id == Product.id
    ).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Order.status != 'anulowane'
    ).group_by(
        Product.id, Product.name, Product.sku
    ).order_by(desc('total_sold')).limit(20).all()

    bestsellers_rows = []
    for b in bestsellers:
        bestsellers_rows.append([
            b.name,
            b.sku or '-',
            int(b.total_sold),
            _format_currency(b.total_revenue)
        ])

    # Tabela: Najgorzej sprzedające się (aktywne, ale 0 lub mało sprzedaży)
    # Subquery: produkty z ich sprzedażą
    sold_subq = db.session.query(
        OrderItem.product_id,
        func.sum(OrderItem.quantity).label('qty')
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Order.status != 'anulowane',
        OrderItem.product_id.isnot(None)
    ).group_by(OrderItem.product_id).subquery()

    worst_sellers = db.session.query(
        Product.name,
        Product.sku,
        func.coalesce(sold_subq.c.qty, 0).label('total_sold')
    ).outerjoin(
        sold_subq, sold_subq.c.product_id == Product.id
    ).filter(
        Product.is_active == True
    ).order_by(asc('total_sold')).limit(20).all()

    worst_rows = []
    for w in worst_sellers:
        worst_rows.append([
            w.name,
            w.sku or '-',
            int(w.total_sold)
        ])

    # Wykres słupkowy: Top 10 produktów per przychód
    top_revenue = db.session.query(
        Product.name,
        func.sum(OrderItem.total).label('revenue')
    ).join(
        OrderItem, OrderItem.product_id == Product.id
    ).join(
        Order, Order.id == OrderItem.order_id
    ).filter(
        Order.status != 'anulowane'
    ).group_by(
        Product.id, Product.name
    ).order_by(desc('revenue')).limit(10).all()

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Aktywne produkty', 'value': str(active_products), 'raw': active_products},
            {'label': 'Łączna sprzedaż (szt.)', 'value': str(int(total_sold)), 'raw': int(total_sold)},
            {'label': 'Łączny przychód', 'value': _format_currency(total_product_revenue), 'raw': float(total_product_revenue)},
        ],
        'charts': {
            'bar_revenue': {
                'labels': [r.name[:30] for r in top_revenue],
                'values': [float(r.revenue) for r in top_revenue]
            }
        },
        'tables': [
            {
                'title': 'Top 20 bestselerów',
                'headers': ['Nazwa', 'SKU', 'Sprzedanych szt.', 'Przychód'],
                'rows': bestsellers_rows
            },
            {
                'title': 'Najgorzej sprzedające się produkty',
                'headers': ['Nazwa', 'SKU', 'Sprzedanych szt.'],
                'rows': worst_rows
            }
        ]
    })


# ========================================
# API: Klienci
# ========================================

@admin_bp.route('/statistics/api/clients')
@login_required
@role_required('admin', 'mod')
def statistics_clients():
    """Dane dla zakładki Klienci."""
    range_param = request.args.get('range', '30d')
    start_date, end_date = _parse_range(range_param)
    today = datetime.now().date()
    month_start = today.replace(day=1)

    # KPI
    total_clients = User.query.filter_by(role='client').count()
    active_clients = User.query.filter_by(role='client', is_active=True).count()
    new_this_month = User.query.filter(
        User.role == 'client',
        func.date(User.created_at) >= month_start
    ).count()

    # Wykres liniowy: rejestracje w czasie
    dates = _generate_date_labels(start_date, end_date)
    daily_regs = db.session.query(
        func.date(User.created_at).label('day'),
        func.count(User.id).label('count')
    ).filter(
        User.role == 'client',
        func.date(User.created_at) >= start_date,
        func.date(User.created_at) <= end_date
    ).group_by(func.date(User.created_at)).all()

    regs_map = {str(row.day): row.count for row in daily_regs}
    chart_labels = [d.strftime('%d.%m') for d in dates]
    chart_values = [regs_map.get(str(d), 0) for d in dates]

    # Tabela: Top 10 klientów per wydana kwota
    top_clients = db.session.query(
        User.first_name,
        User.last_name,
        User.email,
        func.count(Order.id).label('orders_count'),
        func.sum(Order.total_amount).label('total_spent')
    ).join(
        Order, Order.user_id == User.id
    ).filter(
        User.role == 'client',
        Order.status != 'anulowane'
    ).group_by(
        User.id, User.first_name, User.last_name, User.email
    ).order_by(desc('total_spent')).limit(10).all()

    top_clients_rows = []
    for c in top_clients:
        top_clients_rows.append([
            f"{c.first_name} {c.last_name}",
            c.email,
            c.orders_count,
            _format_currency(c.total_spent)
        ])

    # Metryki
    # Średnia wartość klienta (łączny przychód / klientów z zamówieniami)
    clients_with_orders = db.session.query(
        func.count(func.distinct(Order.user_id))
    ).filter(
        Order.status != 'anulowane',
        Order.user_id.isnot(None)
    ).scalar() or 0

    total_rev = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.status != 'anulowane', Order.user_id.isnot(None)).scalar() or Decimal('0')

    avg_client_value = float(total_rev) / clients_with_orders if clients_with_orders > 0 else 0

    # % klientów z >1 zamówieniem
    repeat_clients = db.session.query(
        func.count()
    ).select_from(
        db.session.query(
            Order.user_id
        ).filter(
            Order.status != 'anulowane',
            Order.user_id.isnot(None)
        ).group_by(Order.user_id).having(func.count(Order.id) > 1).subquery()
    ).scalar() or 0

    pct_repeat = (repeat_clients / clients_with_orders * 100) if clients_with_orders > 0 else 0

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Łącznie klientów', 'value': str(total_clients), 'raw': total_clients},
            {'label': 'Aktywnych', 'value': str(active_clients), 'raw': active_clients},
            {'label': 'Nowych (ten miesiąc)', 'value': str(new_this_month), 'raw': new_this_month},
        ],
        'charts': {
            'main': {'labels': chart_labels, 'values': chart_values}
        },
        'tables': [{
            'title': 'Top 10 klientów per wydana kwota',
            'headers': ['Imię i nazwisko', 'Email', 'Zamówień', 'Wydano'],
            'rows': top_clients_rows
        }],
        'metrics': {
            'avg_client_value': _format_currency(avg_client_value),
            'pct_repeat': f"{pct_repeat:.1f}%"
        }
    })


# ========================================
# API: Exclusive
# ========================================

@admin_bp.route('/statistics/api/exclusive')
@login_required
@role_required('admin', 'mod')
def statistics_exclusive():
    """Dane dla zakładki Exclusive."""
    # KPI
    total_pages = ExclusivePage.query.count()
    active_pages = ExclusivePage.query.filter_by(status='active').count()

    total_exclusive_revenue = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.is_exclusive == True,
        Order.status != 'anulowane'
    ).scalar() or Decimal('0')

    # Tabela: porównanie stron
    pages = ExclusivePage.query.all()
    pages_rows = []
    chart_labels = []
    chart_values = []

    for page in pages:
        page_orders = Order.query.filter(
            Order.exclusive_page_id == page.id,
            Order.status != 'anulowane'
        )
        orders_count = page_orders.count()
        page_revenue = db.session.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            Order.exclusive_page_id == page.id,
            Order.status != 'anulowane'
        ).scalar() or Decimal('0')

        avg_value = float(page_revenue) / orders_count if orders_count > 0 else 0

        status_map = {
            'draft': 'Szkic',
            'scheduled': 'Zaplanowana',
            'active': 'Aktywna',
            'paused': 'Wstrzymana',
            'ended': 'Zakończona'
        }

        pages_rows.append([
            page.name,
            status_map.get(page.status, page.status),
            orders_count,
            _format_currency(page_revenue),
            _format_currency(avg_value)
        ])

        if float(page_revenue) > 0:
            chart_labels.append(page.name[:25])
            chart_values.append(float(page_revenue))

    # Sortuj tabelę po przychodzie (malejąco)
    pages_rows.sort(key=lambda x: float(x[3].replace(' PLN', '').replace(' ', '').replace(',', '.')), reverse=True)

    # Sortuj wykres i ogranicz do top 10
    combined = sorted(zip(chart_labels, chart_values), key=lambda x: x[1], reverse=True)[:10]
    if combined:
        chart_labels, chart_values = zip(*combined)
        chart_labels = list(chart_labels)
        chart_values = list(chart_values)
    else:
        chart_labels = []
        chart_values = []

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Łącznie stron', 'value': str(total_pages), 'raw': total_pages},
            {'label': 'Aktywnych', 'value': str(active_pages), 'raw': active_pages},
            {'label': 'Łączny przychód Exclusive', 'value': _format_currency(total_exclusive_revenue), 'raw': float(total_exclusive_revenue)},
        ],
        'charts': {
            'bar_revenue': {'labels': chart_labels, 'values': chart_values}
        },
        'tables': [{
            'title': 'Porównanie stron Exclusive',
            'headers': ['Nazwa', 'Status', 'Zamówień', 'Przychód', 'Śr. wartość'],
            'rows': pages_rows
        }]
    })


# ========================================
# API: Wysyłka
# ========================================

@admin_bp.route('/statistics/api/shipping')
@login_required
@role_required('admin', 'mod')
def statistics_shipping():
    """Dane dla zakładki Wysyłka."""
    # KPI
    total_requests = ShippingRequest.query.count()
    pending_requests = ShippingRequest.query.filter(
        ShippingRequest.status.in_(['czeka_na_wycene', 'wycenione'])
    ).count()
    total_shipping_cost = db.session.query(
        func.coalesce(func.sum(ShippingRequest.total_shipping_cost), 0)
    ).scalar() or Decimal('0')

    # Wykres kołowy: metody dostawy (z zamówień)
    delivery_counts = db.session.query(
        Order.delivery_method,
        func.count(Order.id)
    ).filter(
        Order.delivery_method.isnot(None),
        Order.status != 'anulowane'
    ).group_by(Order.delivery_method).all()

    delivery_labels_map = {
        'kurier': 'Kurier',
        'paczkomat': 'Paczkomat',
        'odbior_osobisty': 'Odbiór osobisty',
        'poczta': 'Poczta'
    }
    pie_delivery_labels = [delivery_labels_map.get(d[0], d[0]) for d in delivery_counts]
    pie_delivery_values = [d[1] for d in delivery_counts]

    # Wykres kołowy: kurierzy (z OrderShipment)
    courier_counts = db.session.query(
        OrderShipment.courier,
        func.count(OrderShipment.id)
    ).group_by(OrderShipment.courier).all()

    courier_names = {
        'inpost': 'InPost', 'dpd': 'DPD', 'dhl': 'DHL', 'gls': 'GLS',
        'poczta_polska': 'Poczta Polska', 'orlen': 'Orlen Paczka',
        'ups': 'UPS', 'fedex': 'FedEx', 'other': 'Inny'
    }
    pie_courier_labels = [courier_names.get(c[0], c[0]) for c in courier_counts]
    pie_courier_values = [c[1] for c in courier_counts]

    # Tabela: ostatnie zlecenia wysyłki
    recent_requests = ShippingRequest.query.order_by(
        desc(ShippingRequest.created_at)
    ).limit(15).all()

    recent_rows = []
    for r in recent_requests:
        recent_rows.append([
            r.request_number,
            r.status_display_name,
            _format_currency(r.total_shipping_cost) if r.total_shipping_cost else '-',
            r.orders_count,
            r.created_at.strftime('%d.%m.%Y') if r.created_at else '-'
        ])

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Łącznie zleceń wysyłki', 'value': str(total_requests), 'raw': total_requests},
            {'label': 'Oczekujących', 'value': str(pending_requests), 'raw': pending_requests},
            {'label': 'Łączny koszt wysyłki', 'value': _format_currency(total_shipping_cost), 'raw': float(total_shipping_cost)},
        ],
        'charts': {
            'pie_delivery': {'labels': pie_delivery_labels, 'values': pie_delivery_values},
            'pie_couriers': {'labels': pie_courier_labels, 'values': pie_courier_values},
        },
        'tables': [{
            'title': 'Ostatnie zlecenia wysyłki',
            'headers': ['Nr zlecenia', 'Status', 'Koszt', 'Zamówień', 'Data'],
            'rows': recent_rows
        }]
    })


# ========================================
# API: Proxy/Korea
# ========================================

@admin_bp.route('/statistics/api/proxy')
@login_required
@role_required('admin', 'mod')
def statistics_proxy():
    """Dane dla zakładki Proxy/Korea."""
    # KPI
    total_proxy = ProxyOrder.query.count()
    delivered_proxy = ProxyOrder.query.filter_by(status='dostarczone_do_proxy').count()
    total_proxy_cost = db.session.query(
        func.coalesce(func.sum(ProxyOrder.total_amount_pln), 0)
    ).scalar() or Decimal('0')

    # Wykres kołowy: statusy proxy orders
    proxy_statuses = db.session.query(
        ProxyOrder.status,
        func.count(ProxyOrder.id)
    ).group_by(ProxyOrder.status).all()

    proxy_status_map = {
        'zamowiono': 'Zamówiono',
        'dostarczone_do_proxy': 'Dostarczone do proxy',
        'anulowane': 'Anulowane'
    }
    pie_proxy_labels = [proxy_status_map.get(s[0], s[0]) for s in proxy_statuses]
    pie_proxy_values = [s[1] for s in proxy_statuses]

    # Wykres kołowy: statusy poland orders
    poland_statuses = db.session.query(
        PolandOrder.status,
        func.count(PolandOrder.id)
    ).group_by(PolandOrder.status).all()

    poland_status_map = {
        'zamowione': 'Zamówione',
        'urzad_celny': 'Urząd celny',
        'dostarczone_gom': 'Dostarczone (GOM)',
        'anulowane': 'Anulowane'
    }
    pie_poland_labels = [poland_status_map.get(s[0], s[0]) for s in poland_statuses]
    pie_poland_values = [s[1] for s in poland_statuses]

    # Metryki
    avg_shipping_kr = db.session.query(
        func.avg(ProxyOrder.shipping_cost_total)
    ).filter(
        ProxyOrder.shipping_cost_total > 0
    ).scalar() or 0

    avg_customs = db.session.query(
        func.avg(PolandOrder.customs_cost)
    ).filter(
        PolandOrder.customs_cost > 0
    ).scalar() or 0

    return jsonify({
        'success': True,
        'kpis': [
            {'label': 'Łącznie proxy zamówień', 'value': str(total_proxy), 'raw': total_proxy},
            {'label': 'Dostarczone do proxy', 'value': str(delivered_proxy), 'raw': delivered_proxy},
            {'label': 'Łączny koszt', 'value': _format_currency(total_proxy_cost), 'raw': float(total_proxy_cost)},
        ],
        'charts': {
            'pie_proxy': {'labels': pie_proxy_labels, 'values': pie_proxy_values},
            'pie_poland': {'labels': pie_poland_labels, 'values': pie_poland_values},
        },
        'metrics': {
            'avg_shipping_kr': _format_currency(avg_shipping_kr),
            'avg_customs': _format_currency(avg_customs)
        }
    })
