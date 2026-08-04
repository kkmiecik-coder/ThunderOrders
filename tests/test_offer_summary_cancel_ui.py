"""
Renderowanie elementów masowego anulowania na stronie podsumowania zbiórki.

Admin widzi przycisk zaznaczania, pasek akcji i modal; mod nie widzi nic z tego.
"""
import pytest


@pytest.fixture
def make_page(db, make_user):
    from modules.offers.models import OfferPage

    counter = {'n': 0}

    def _make(**kwargs):
        counter['n'] += 1
        kwargs.setdefault('is_fully_closed', True)
        kwargs.setdefault('status', 'ended')
        page = OfferPage(
            name=f'Zbiorka UI {counter["n"]}',
            token=f'token-ui-{counter["n"]}',
            created_by=make_user(role='admin', profile_completed=True).id,
            **kwargs,
        )
        db.session.add(page)
        db.session.commit()
        return page
    return _make


def _summary_url(page):
    return f'/admin/offers/{page.id}/summary'


def test_admin_widzi_elementy_anulowania(client, db, make_user, make_order, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()
    make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.get(_summary_url(page))
    html = resp.data.decode()

    assert resp.status_code == 200
    assert 'id="selectOrdersBtn"' in html
    assert 'id="ordersSelectionBar"' in html
    assert 'id="cancelOrdersBtn"' in html
    assert 'id="cancelOrdersModal"' in html
    assert 'offer-cancel-orders.js' in html
    assert 'window.CANCEL_ORDERS_URL' in html
    assert f'/admin/offers/{page.id}/orders/cancel' in html


def test_mod_nie_widzi_elementow_anulowania(client, db, make_user, make_order, make_page, login):
    login(make_user(role='mod', profile_completed=True))
    page = make_page()
    make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.get(_summary_url(page))
    html = resp.data.decode()

    assert resp.status_code == 200
    assert 'id="selectOrdersBtn"' not in html
    assert 'id="ordersSelectionBar"' not in html
    assert 'id="cancelOrdersModal"' not in html
    assert 'offer-cancel-orders.js' not in html


def test_dane_zamowien_zawieraja_status_i_oplacenie(
    client, db, make_user, make_order, make_page, login
):
    """Front potrzebuje status + is_paid, żeby wyszarzyć i policzyć podział na grupy."""
    from modules.orders.models import PaymentConfirmation
    from decimal import Decimal

    login(make_user(role='admin', profile_completed=True))
    page = make_page()
    oplacone = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    db.session.add(PaymentConfirmation(
        order_id=oplacone.id, payment_stage='product',
        amount=Decimal('50.00'), status='approved',
    ))
    db.session.commit()

    resp = client.get(_summary_url(page))
    html = resp.data.decode()

    assert '"status": "oczekujace"' in html or '"status":"oczekujace"' in html
    assert '"is_paid": true' in html or '"is_paid":true' in html
