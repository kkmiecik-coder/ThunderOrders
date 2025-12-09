"""
Admin Routes
Routing dla panelu administratora
"""

from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from modules.admin import admin_bp
from utils.decorators import role_required
from extensions import db
from modules.auth.models import User
from modules.admin.models import AdminTask
from sqlalchemy import func, desc
from datetime import datetime, timedelta


@admin_bp.route('/dashboard')
@login_required
@role_required('admin', 'mod')
def dashboard():
    """
    Admin Dashboard
    Widok główny panelu administratora z podstawowymi metrykami

    NOTE: Moduły orders i products będą dodane w przyszłości.
    Na razie używamy mock data dla demonstracji UI.
    """

    # ========================================
    # Mock Data (będzie zastąpione prawdziwymi danymi)
    # ========================================

    # 1. Revenue stats (mock)
    revenue = {
        'today': 0.0,
        'week': 0.0,
        'month': 0.0
    }

    # 2. Orders stats (mock)
    orders = {
        'all': 0,
        'today': 0,
        'pending': 0
    }

    # 3. Clients stats (real data!)
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)

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

    # 4. Recent orders (mock - empty list)
    recent_orders = []

    # 5. Sales chart data (mock - 7 days with 0 revenue)
    sales_chart = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        sales_chart.append({
            'date': date.strftime('%Y-%m-%d'),
            'date_label': date.strftime('%d.%m'),
            'revenue': 0.0
        })

    # 6. Top products (mock - empty list)
    top_products = []

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
