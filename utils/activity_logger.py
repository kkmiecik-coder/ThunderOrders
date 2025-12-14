"""
Activity Logger Utility
Narzędzie do logowania aktywności użytkowników w systemie
"""

import json
from flask import request
from extensions import db
from modules.admin.models import ActivityLog


def log_activity(user=None, action=None, entity_type=None, entity_id=None, old_value=None, new_value=None):
    """
    Loguje aktywność użytkownika w systemie

    Args:
        user: User object (może być None dla akcji systemowych)
        action (str): Nazwa akcji (np. 'order_created', 'product_updated')
        entity_type (str): Typ encji (np. 'order', 'product', 'user')
        entity_id (int): ID encji
        old_value (dict): Poprzednia wartość (zostanie zamieniona na JSON)
        new_value (dict): Nowa wartość (zostanie zamieniona na JSON)

    Returns:
        ActivityLog: Utworzony log lub None jeśli błąd
    """
    try:
        # Pobierz IP i User-Agent z requestu
        ip_address = None
        user_agent = None

        if request:
            ip_address = request.remote_addr
            user_agent = request.headers.get('User-Agent', '')[:500]  # Max 500 znaków

        # Zamień dictionaries na JSON strings
        old_value_json = json.dumps(old_value, ensure_ascii=False) if old_value else None
        new_value_json = json.dumps(new_value, ensure_ascii=False) if new_value else None

        # Utwórz log
        activity_log = ActivityLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value_json,
            new_value=new_value_json,
            ip_address=ip_address,
            user_agent=user_agent
        )

        db.session.add(activity_log)
        db.session.commit()

        return activity_log

    except Exception as e:
        # W przypadku błędu nie crashuj całej aplikacji
        # Tylko zaloguj błąd (można dodać logging do pliku)
        print(f"[ERROR] ActivityLogger: {str(e)}")
        db.session.rollback()
        return None


def log_login(user):
    """
    Loguje logowanie użytkownika

    Args:
        user: User object
    """
    return log_activity(
        user=user,
        action='login',
        entity_type='user',
        entity_id=user.id
    )


def log_logout(user):
    """
    Loguje wylogowanie użytkownika

    Args:
        user: User object
    """
    return log_activity(
        user=user,
        action='logout',
        entity_type='user',
        entity_id=user.id
    )


def log_order_created(user, order):
    """
    Loguje utworzenie zamówienia

    Args:
        user: User object (może być None dla guest orders)
        order: Order object
    """
    return log_activity(
        user=user,
        action='order_created',
        entity_type='order',
        entity_id=order.id,
        new_value={
            'order_number': order.order_number,
            'total_amount': float(order.total_amount),
            'status': order.status,
            'is_exclusive': order.is_exclusive,
            'is_guest_order': order.is_guest_order
        }
    )


def log_order_status_change(user, order, old_status, new_status):
    """
    Loguje zmianę statusu zamówienia

    Args:
        user: User object
        order: Order object
        old_status (str): Poprzedni status
        new_status (str): Nowy status
    """
    return log_activity(
        user=user,
        action='order_status_change',
        entity_type='order',
        entity_id=order.id,
        old_value={'status': old_status},
        new_value={'status': new_status}
    )


def log_product_created(user, product):
    """
    Loguje dodanie produktu

    Args:
        user: User object
        product: Product object
    """
    return log_activity(
        user=user,
        action='product_created',
        entity_type='product',
        entity_id=product.id,
        new_value={
            'name': product.name,
            'sku': product.sku,
            'sale_price': float(product.sale_price) if product.sale_price else None
        }
    )


def log_product_updated(user, product, changes):
    """
    Loguje edycję produktu

    Args:
        user: User object
        product: Product object
        changes (dict): Słownik zmian {'field_name': {'old': old_value, 'new': new_value}}
    """
    return log_activity(
        user=user,
        action='product_updated',
        entity_type='product',
        entity_id=product.id,
        old_value=changes.get('old', {}),
        new_value=changes.get('new', {})
    )


def log_refund_issued(user, order, refund):
    """
    Loguje wydanie zwrotu

    Args:
        user: User object
        order: Order object
        refund: OrderRefund object
    """
    return log_activity(
        user=user,
        action='refund_issued',
        entity_type='order',
        entity_id=order.id,
        new_value={
            'refund_id': refund.id,
            'amount': float(refund.amount),
            'reason': refund.reason
        }
    )
