"""
Client Module - Routes
Endpointy panelu klienta
"""

import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from modules.orders.models import Order, ShippingRequestOrder
from modules.auth.models import Settings
from modules.exclusive.models import ExclusivePage
from sqlalchemy import func as sql_func, and_
from datetime import datetime, timedelta
from decimal import Decimal

from modules.client import client_bp


@client_bp.route('/dashboard')
@login_required
def dashboard():
    """
    Client Dashboard
    Główny panel klienta z rzeczywistymi danymi z bazy
    """
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)

    # 1. Orders stats
    orders_all = Order.query.filter_by(user_id=current_user.id).count()
    orders_in_progress = Order.query.filter_by(user_id=current_user.id).filter(
        Order.status.in_(['nowe', 'oczekujace', 'w_realizacji', 'spakowane', 'wyslane'])
    ).count()
    orders_delivered = Order.query.filter_by(user_id=current_user.id).filter_by(status='dostarczone').count()

    # 2. Payment stats
    paid_total = db.session.query(
        sql_func.coalesce(sql_func.sum(Order.paid_amount), 0)
    ).filter_by(user_id=current_user.id).scalar() or Decimal('0.00')

    to_pay_orders = Order.query.filter_by(user_id=current_user.id).filter(
        Order.total_amount > Order.paid_amount
    ).all()
    to_pay_total = sum((o.total_amount - o.paid_amount) for o in to_pay_orders)

    # 3. Orders waiting for shipping request
    # Get allowed order statuses from settings
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    allowed_statuses = []
    if setting and setting.value:
        try:
            allowed_statuses = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed_statuses = ['dostarczone_gom']
    else:
        allowed_statuses = ['dostarczone_gom']

    # Subquery to check if order is in any shipping request
    in_shipping_request = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id
    ).exists()

    orders_awaiting_shipping = Order.query.filter(
        and_(
            Order.user_id == current_user.id,
            Order.status.in_(allowed_statuses),
            ~in_shipping_request
        )
    ).count()

    # 4. Recent orders (with lazy loading support)
    recent_orders_all = Order.query.filter_by(user_id=current_user.id).order_by(
        Order.created_at.desc()
    ).limit(15).all()  # Fetch up to 15 for initial load (5 visible + 5 buffer + 5 for API)

    total_orders = Order.query.filter_by(user_id=current_user.id).count()

    recent_orders = {
        'visible': recent_orders_all[:5],  # First 5 visible
        'buffer': recent_orders_all[5:10],  # Next 5 in buffer (hidden)
        'total': total_orders,
        'remaining': max(0, total_orders - 5)
    }

    # 5. Chart data (30 days)
    # Grupuj zamówienia po dniach (ostatnie 30 dni)
    orders_by_day = db.session.query(
        sql_func.date(Order.created_at).label('order_date'),
        sql_func.count(Order.id).label('count')
    ).filter(
        Order.user_id == current_user.id,
        sql_func.date(Order.created_at) >= thirty_days_ago
    ).group_by(sql_func.date(Order.created_at)).all()

    # Wypełnij puste dni zerami
    chart_data = {
        'labels': [],  # ['2025-12-01', '2025-12-02', ...]
        'values': []   # [3, 0, 5, ...]
    }

    # Wszystkie dni ostatniego miesiąca
    all_dates = [(thirty_days_ago + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]
    # Użyj indeksowania zamiast atrybutów (row[0] = date, row[1] = count)
    orders_dict = {str(row[0]): row[1] for row in orders_by_day}

    for date_str in all_dates:
        chart_data['labels'].append(date_str)
        chart_data['values'].append(orders_dict.get(date_str, 0))

    # 6. Exclusive pages (client sees all except drafts)
    exclusive_pages_all = ExclusivePage.query.filter(
        ExclusivePage.status != 'draft'
    ).all()

    # Update status for each page (check dates)
    for page in exclusive_pages_all:
        page.check_and_update_status()

    # Sort by priority: 1. active (LIVE), 2. scheduled, 3. ended (not closed), 4. closed, 5. paused
    def get_sort_priority(page):
        if page.status == 'active':
            return 0
        elif page.status == 'scheduled':
            return 1
        elif page.status == 'ended' and not page.is_fully_closed:
            return 2  # Zakończona
        elif page.status == 'ended' and page.is_fully_closed:
            return 3  # Zamknięta
        elif page.status == 'paused':
            return 4
        return 99

    exclusive_pages_all.sort(key=get_sort_priority)

    exclusive_pages = {
        'visible': exclusive_pages_all[:5],  # First 5 visible
        'buffer': exclusive_pages_all[5:10],  # Next 5 in buffer (hidden)
        'total': len(exclusive_pages_all),
        'remaining': max(0, len(exclusive_pages_all) - 5)
    }

    return render_template(
        'client/dashboard.html',
        title='Panel Klienta',
        orders={
            'all': orders_all,
            'in_progress': orders_in_progress,
            'delivered': orders_delivered,
            'awaiting_shipping': orders_awaiting_shipping
        },
        payment={
            'paid': float(paid_total),
            'to_pay': float(to_pay_total)
        },
        recent_orders=recent_orders,
        chart_data=chart_data,
        exclusive_pages=exclusive_pages
    )


@client_bp.route('/api/chart-data')
@login_required
def get_chart_data():
    """
    API endpoint dla danych wykresu z parametrem period (dni)
    Inteligentne grupowanie:
    - 7, 14, 30 dni: po dniach
    - 90, 180, 365 dni: po miesiącach
    """
    period = request.args.get('period', 30, type=int)

    # Walidacja okresu (dozwolone wartości)
    allowed_periods = [7, 14, 30, 90, 180, 365]
    if period not in allowed_periods:
        period = 30

    today = datetime.now().date()
    start_date = today - timedelta(days=period - 1)

    chart_data = {
        'labels': [],
        'values': []
    }

    # Grupowanie po dniach (7, 14, 30 dni)
    if period <= 30:
        orders_by_day = db.session.query(
            sql_func.date(Order.created_at).label('order_date'),
            sql_func.count(Order.id).label('count')
        ).filter(
            Order.user_id == current_user.id,
            sql_func.date(Order.created_at) >= start_date
        ).group_by(sql_func.date(Order.created_at)).all()

        # Wypełnij puste dni zerami
        all_dates = [(start_date + timedelta(days=i)) for i in range(period)]
        orders_dict = {str(row[0]): row[1] for row in orders_by_day}

        for date in all_dates:
            date_str = date.strftime('%Y-%m-%d')
            # Format label: "22.12" (dzień.miesiąc)
            label = date.strftime('%d.%m')
            chart_data['labels'].append(label)
            chart_data['values'].append(orders_dict.get(date_str, 0))

    # Grupowanie po miesiącach (90, 180, 365 dni)
    else:
        orders_by_month = db.session.query(
            sql_func.date_format(Order.created_at, '%Y-%m').label('month'),
            sql_func.count(Order.id).label('count')
        ).filter(
            Order.user_id == current_user.id,
            sql_func.date(Order.created_at) >= start_date
        ).group_by(sql_func.date_format(Order.created_at, '%Y-%m')).all()

        # Wygeneruj wszystkie miesiące w okresie
        current_date = start_date.replace(day=1)
        end_date = today.replace(day=1)
        months = []

        while current_date <= end_date:
            months.append(current_date.strftime('%Y-%m'))
            # Przejdź do następnego miesiąca
            if current_date.month == 12:
                current_date = current_date.replace(year=current_date.year + 1, month=1)
            else:
                current_date = current_date.replace(month=current_date.month + 1)

        orders_dict = {str(row[0]): row[1] for row in orders_by_month}

        for month_str in months:
            # Format label: "12/2024" (miesiąc/rok) lub "Gru 2024"
            year, month = month_str.split('-')
            month_names = ['Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze',
                          'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru']
            label = f"{month_names[int(month) - 1]} {year}"
            chart_data['labels'].append(label)
            chart_data['values'].append(orders_dict.get(month_str, 0))

    return jsonify(chart_data)


@client_bp.route('/api/recent-orders')
@login_required
def get_recent_orders():
    """
    API endpoint zwracający ostatnie zamówienia z paginacją

    Query params:
    - offset: od którego zamówienia zacząć (domyślnie 0)
    - limit: ile zamówień pobrać (domyślnie 5)

    Returns JSON z listą zamówień i flagą czy są kolejne
    """
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 5, type=int)

    # Pobierz zamówienia z paginacją
    orders = Order.query.filter_by(user_id=current_user.id).order_by(
        Order.created_at.desc()
    ).offset(offset).limit(limit).all()

    total = Order.query.filter_by(user_id=current_user.id).count()
    remaining = max(0, total - offset - limit)

    # Serialize orders
    orders_data = []
    for order in orders:
        orders_data.append({
            'id': order.id,
            'order_number': order.order_number,
            'customer_name': order.customer_name,
            'status': order.status,
            'status_display_name': order.status_display_name,
            'status_badge_color': order.status_badge_color,
            'effective_grand_total': float(order.effective_grand_total),
            'detail_url': url_for('orders.client_detail', order_id=order.id)
        })

    return jsonify({
        'success': True,
        'orders': orders_data,
        'remaining': remaining,
        'total': total
    })


@client_bp.route('/api/exclusive-pages')
@login_required
def get_exclusive_pages():
    """
    API endpoint zwracający strony exclusive z paginacją dla klienta

    Query params:
    - offset: od której strony zacząć (domyślnie 0)
    - limit: ile stron pobrać (domyślnie 5)

    Returns JSON z listą stron i flagą czy są kolejne
    """
    from flask import url_for

    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 5, type=int)

    # Pobierz wszystkie strony (bez drafts)
    exclusive_pages_all = ExclusivePage.query.filter(
        ExclusivePage.status != 'draft'
    ).all()

    # Update status for each page
    for page in exclusive_pages_all:
        page.check_and_update_status()

    # Sort by priority
    def get_sort_priority(page):
        if page.status == 'active':
            return 0
        elif page.status == 'scheduled':
            return 1
        elif page.status == 'ended' and not page.is_fully_closed:
            return 2
        elif page.status == 'ended' and page.is_fully_closed:
            return 3
        elif page.status == 'paused':
            return 4
        return 99

    exclusive_pages_all.sort(key=get_sort_priority)

    # Paginacja
    pages_slice = exclusive_pages_all[offset:offset + limit]
    has_more = len(exclusive_pages_all) > offset + limit
    remaining = max(0, len(exclusive_pages_all) - offset - limit)

    # Serialize pages
    pages_data = []
    for page in pages_slice:
        # Determine status display
        if page.status == 'active':
            status_class = 'live'
            status_text = 'LIVE'
            is_live = True
        elif page.status == 'ended' and page.is_fully_closed:
            status_class = 'closed'
            status_text = 'Zamknięta'
            is_live = False
        elif page.status == 'ended':
            status_class = 'ended'
            status_text = 'Zakończona'
            is_live = False
        elif page.status == 'scheduled':
            status_class = 'scheduled'
            status_text = 'Zaplanowana'
            is_live = False
        elif page.status == 'paused':
            status_class = 'paused'
            status_text = 'Wstrzymana'
            is_live = False
        else:
            status_class = page.status
            status_text = page.status
            is_live = False

        pages_data.append({
            'id': page.id,
            'name': page.name,
            'status': page.status,
            'status_class': status_class,
            'status_text': status_text,
            'is_live': is_live,
            'is_important': page.status in ['active', 'scheduled'],
            'starts_at': page.starts_at.isoformat() if page.starts_at else None,
            'ends_at': page.ends_at.isoformat() if page.ends_at else None,
            'page_url': url_for('exclusive.order_page', token=page.token)
        })

    return jsonify({
        'success': True,
        'pages': pages_data,
        'has_more': has_more,
        'remaining': remaining,
        'total': len(exclusive_pages_all)
    })
