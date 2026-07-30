from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def test_overdue_payments_page_lists_order(app, db, make_user, make_order, client, login):
    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    now = get_local_now()
    customer = make_user(email='klient@example.com')
    order = make_order(customer, total_amount=Decimal('150.00'))
    order.get_product_deadline = lambda: now - timedelta(days=4)

    resp = client.get('/admin/payments/overdue')

    assert resp.status_code == 200
    assert order.order_number.encode() in resp.data


def test_overdue_payments_page_empty_state(app, db, make_user, client, login):
    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    resp = client.get('/admin/payments/overdue')

    assert resp.status_code == 200


def test_overdue_payments_page_requires_login(app, db, client):
    resp = client.get('/admin/payments/overdue')
    assert resp.status_code in (302, 401)
