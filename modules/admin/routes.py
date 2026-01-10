"""
Admin Routes
Routing dla panelu administratora
"""

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from modules.admin import admin_bp
from utils.decorators import role_required
from extensions import db
from modules.auth.models import User
from modules.admin.models import AdminTask
from modules.orders.models import Order, OrderItem
from modules.products.models import Product
from sqlalchemy import func, desc, cast, Date, extract
from datetime import datetime, timedelta
from decimal import Decimal
from calendar import month_name


@admin_bp.route('/dashboard')
@login_required
@role_required('admin', 'mod')
def dashboard():
    """
    Admin Dashboard
    Widok główny panelu administratora z podstawowymi metrykami.

    Wyświetla rzeczywiste dane z bazy danych:
    - Statystyki zamówień (wszystkie, dzisiaj, oczekujące)
    - Przychody (dziś, tydzień, miesiąc)
    - Statystyki klientów
    - Wykres sprzedaży (7 dni)
    - Top 5 bestsellery
    - Ostatnie zamówienia
    - Zadania admina
    """

    # ========================================
    # Real Data from Database
    # ========================================

    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    # 1. Orders stats (real data)
    orders_all = Order.query.count()
    orders_today = Order.query.filter(
        func.date(Order.created_at) == today
    ).count()
    orders_week = Order.query.filter(
        func.date(Order.created_at) >= week_ago
    ).count()
    orders_month = Order.query.filter(
        func.date(Order.created_at) >= month_start
    ).count()
    # Pending = zamowienia ze statusem 'nowe' lub 'oczekujace'
    orders_pending = Order.query.filter(
        Order.status.in_(['nowe', 'oczekujace'])
    ).count()

    orders = {
        'all': orders_all,
        'today': orders_today,
        'week': orders_week,
        'month': orders_month,
        'pending': orders_pending
    }

    # 2. Revenue stats (real data - suma total_amount, wykluczając anulowane)
    # Today's revenue
    revenue_today = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) == today,
        Order.status != 'anulowane'  # Exclude cancelled orders
    ).scalar() or Decimal('0.00')

    # Week's revenue (last 7 days)
    revenue_week = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) >= week_ago,
        Order.status != 'anulowane'  # Exclude cancelled orders
    ).scalar() or Decimal('0.00')

    # Month's revenue (current month)
    revenue_month = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        func.date(Order.created_at) >= month_start,
        Order.status != 'anulowane'  # Exclude cancelled orders
    ).scalar() or Decimal('0.00')

    revenue = {
        'today': float(revenue_today),
        'week': float(revenue_week),
        'month': float(revenue_month)
    }

    # 3. Clients stats (real data)
    clients_total = User.query.filter_by(role='client').count()
    clients_active = User.query.filter_by(role='client', is_active=True).count()
    clients_new = User.query\
        .filter_by(role='client')\
        .filter(func.date(User.created_at) >= week_ago)\
        .count()

    clients = {
        'total': clients_total,
        'active': clients_active,
        'new': clients_new
    }

    # 4. Recent orders (real data - last 10 orders)
    recent_orders = Order.query.order_by(
        Order.created_at.desc()
    ).limit(10).all()

    # 5. Sales chart data (real data - last 7 days revenue)
    sales_chart = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        daily_revenue = db.session.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        ).filter(
            func.date(Order.created_at) == date
        ).scalar() or Decimal('0.00')

        sales_chart.append({
            'date': date.strftime('%Y-%m-%d'),
            'date_label': date.strftime('%d.%m'),
            'revenue': float(daily_revenue)
        })

    # 6. Top products (real data - bestsellers by quantity sold)
    top_products_query = db.session.query(
        Product.id,
        Product.name,
        Product.sku,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.total).label('total_revenue')
    ).join(
        OrderItem, OrderItem.product_id == Product.id
    ).group_by(
        Product.id, Product.name, Product.sku
    ).order_by(
        desc('total_sold')
    ).limit(5).all()

    top_products = []
    for product in top_products_query:
        # Get primary image URL
        product_obj = Product.query.get(product.id)
        image_url = '/static/img/placeholders/product.svg'
        if product_obj and product_obj.primary_image:
            img_path = product_obj.primary_image.path_compressed
            if img_path:
                image_url = f'/static/{img_path}' if not img_path.startswith('/static/') else img_path

        top_products.append({
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'total_sold': product.total_sold or 0,
            'total_revenue': float(product.total_revenue or 0),
            'image_url': image_url
        })

    # 7. Tasks summary (real data!)
    user_tasks = AdminTask.query.filter(
        db.or_(
            AdminTask.assignees.any(id=current_user.id),
            AdminTask.created_by == current_user.id
        )
    ).all()

    pending = [t for t in user_tasks if t.status == 'pending']
    in_progress = [t for t in user_tasks if t.status == 'in_progress']
    completed = [t for t in user_tasks if t.status == 'completed']
    overdue = [t for t in user_tasks if t.is_overdue()]

    tasks = {
        'total': len(user_tasks),
        'pending': len(pending),
        'in_progress': len(in_progress),
        'completed': len(completed),
        'overdue': len(overdue),
        'recent_tasks': user_tasks[:5]
    }

    return render_template(
        'admin/dashboard.html',
        title='Panel Administratora',
        revenue=revenue,
        orders=orders,
        clients=clients,
        recent_orders=recent_orders,
        sales_chart=sales_chart,
        top_products=top_products,
        tasks=tasks
    )


@admin_bp.route('/dashboard/sales-data')
@login_required
@role_required('admin', 'mod')
def get_sales_data():
    """
    API endpoint zwracający dane sprzedaży dla wybranego zakresu

    Query params:
    - range: 7d, 14d, 30d, 3m, 12m, ytd

    Returns JSON:
    {
        "success": true,
        "labels": ["01.01", "02.01", ...],
        "values": [1234.56, 2345.67, ...]
    }
    """

    range_param = request.args.get('range', '7d')
    today = datetime.now().date()

    labels = []
    values = []

    # Parse range parameter
    if range_param == '7d':
        # 7 dni - rozbicie dzienne
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            daily_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) == date,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            labels.append(date.strftime('%d.%m'))
            values.append(float(daily_revenue))

    elif range_param == '14d':
        # 14 dni - rozbicie dzienne
        for i in range(13, -1, -1):
            date = today - timedelta(days=i)
            daily_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) == date,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            labels.append(date.strftime('%d.%m'))
            values.append(float(daily_revenue))

    elif range_param == '30d':
        # 30 dni - rozbicie dzienne
        for i in range(29, -1, -1):
            date = today - timedelta(days=i)
            daily_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) == date,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            labels.append(date.strftime('%d.%m'))
            values.append(float(daily_revenue))

    elif range_param == '3m':
        # 3 miesiące - rozbicie miesięczne
        for i in range(2, -1, -1):
            # Calculate first day of month
            if i == 0:
                month_start = today.replace(day=1)
            else:
                # Go back i months
                year = today.year
                month = today.month - i
                if month <= 0:
                    month += 12
                    year -= 1
                month_start = datetime(year, month, 1).date()

            # Calculate last day of month
            if i == 0:
                month_end = today
            else:
                next_month = month_start.replace(day=28) + timedelta(days=4)
                month_end = next_month - timedelta(days=next_month.day)

            monthly_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) >= month_start,
                func.date(Order.created_at) <= month_end,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            # Polish month names
            polish_months = [
                'Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze',
                'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru'
            ]
            labels.append(polish_months[month_start.month - 1])
            values.append(float(monthly_revenue))

    elif range_param == '12m':
        # 12 miesięcy - rozbicie miesięczne
        for i in range(11, -1, -1):
            # Calculate first day of month
            if i == 0:
                month_start = today.replace(day=1)
            else:
                year = today.year
                month = today.month - i
                if month <= 0:
                    month += 12
                    year -= 1
                month_start = datetime(year, month, 1).date()

            # Calculate last day of month
            if i == 0:
                month_end = today
            else:
                next_month = month_start.replace(day=28) + timedelta(days=4)
                month_end = next_month - timedelta(days=next_month.day)

            monthly_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) >= month_start,
                func.date(Order.created_at) <= month_end,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            polish_months = [
                'Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze',
                'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru'
            ]
            labels.append(polish_months[month_start.month - 1])
            values.append(float(monthly_revenue))

    elif range_param == 'ytd':
        # Bieżący rok - rozbicie miesięczne
        year_start = today.replace(month=1, day=1)
        current_month = today.month

        for month_num in range(1, current_month + 1):
            month_start = datetime(today.year, month_num, 1).date()

            # Calculate last day of month
            if month_num == current_month:
                month_end = today
            else:
                next_month = month_start.replace(day=28) + timedelta(days=4)
                month_end = next_month - timedelta(days=next_month.day)

            monthly_revenue = db.session.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            ).filter(
                func.date(Order.created_at) >= month_start,
                func.date(Order.created_at) <= month_end,
                Order.status != 'anulowane'
            ).scalar() or Decimal('0.00')

            polish_months = [
                'Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze',
                'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru'
            ]
            labels.append(polish_months[month_num - 1])
            values.append(float(monthly_revenue))

    return jsonify({
        'success': True,
        'labels': labels,
        'values': values
    })
