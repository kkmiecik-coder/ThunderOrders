"""
Client Module - Routes
Endpointy panelu klienta
"""

from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from modules.orders.models import Order
from sqlalchemy import func as sql_func
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

    # 3. Recent orders (5 last)
    recent_orders = Order.query.filter_by(user_id=current_user.id).order_by(
        Order.created_at.desc()
    ).limit(5).all()

    # 4. Chart data (30 days)
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

    return render_template(
        'client/dashboard.html',
        title='Panel Klienta',
        orders={
            'all': orders_all,
            'in_progress': orders_in_progress,
            'delivered': orders_delivered
        },
        payment={
            'paid': float(paid_total),
            'to_pay': float(to_pay_total)
        },
        recent_orders=recent_orders,
        chart_data=chart_data
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
