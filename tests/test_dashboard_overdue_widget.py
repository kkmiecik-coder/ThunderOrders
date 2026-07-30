from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def test_dashboard_shows_overdue_count(app, db, make_user, make_order, client, login):
    """Dashboard shows overdue payments widget when there are overdue orders."""
    from modules.offers.models import OfferPage

    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    now = get_local_now()
    user = make_user()

    # Create an offer page with a past payment deadline
    deadline = now - timedelta(days=2)
    page = OfferPage(
        name='Test Page',
        token=OfferPage.generate_token(),
        payment_deadline=deadline,
        created_by=admin.id
    )
    db.session.add(page)
    db.session.commit()

    # Create an order linked to this offer page
    order = make_order(user, total_amount=Decimal('100.00'), offer_page_id=page.id)

    resp = client.get('/admin/dashboard')

    assert resp.status_code == 200
    assert b'zalega' in resp.data


def test_dashboard_hides_widget_when_nothing_overdue(app, db, make_user, client, login):
    """Dashboard hides overdue payments widget when there are no overdue orders."""
    admin = make_user(role='admin', profile_completed=True)
    login(admin)

    resp = client.get('/admin/dashboard')

    assert resp.status_code == 200
    assert b'z p\xc5\x82atno\xc5\x9bci\xc4\x85' not in resp.data
