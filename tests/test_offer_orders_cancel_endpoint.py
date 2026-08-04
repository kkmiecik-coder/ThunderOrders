"""
Endpoint masowego anulowania zamówień: POST /admin/offers/<page_id>/orders/cancel.

Dostęp tylko dla roli admin. Walidacja: niepusty powód, niepusta lista zamówień,
zamknięta strona, wyłącznie zamówienia należące do tej strony.
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
            name=f'Zbiorka {counter["n"]}',
            token=f'token-endpoint-{counter["n"]}',
            created_by=make_user(role='admin', profile_completed=True).id,
            **kwargs,
        )
        db.session.add(page)
        db.session.commit()
        return page
    return _make


def _url(page):
    return f'/admin/offers/{page.id}/orders/cancel'


def test_admin_moze_anulowac(client, db, make_user, make_order, make_page, login):
    admin = make_user(role='admin', profile_completed=True)
    login(admin)
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': 'Wyprzedane u dostawcy',
        'notify': False,
    })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['cancelled'] == 1
    assert order.status == 'anulowane'


def test_mod_nie_moze_anulowac(client, db, make_user, make_order, make_page, login):
    mod = make_user(role='mod', profile_completed=True)
    login(mod)
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 403
    assert order.status == 'oczekujace'


def test_klient_nie_moze_anulowac(client, db, make_user, make_order, make_page, login):
    login(make_user(role='client', profile_completed=True))
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 403
    assert order.status == 'oczekujace'


def test_pusty_powod_zwraca_400(client, db, make_user, make_order, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': '   ',
        'notify': False,
    })

    assert resp.status_code == 400
    assert order.status == 'oczekujace'


def test_pusta_lista_zwraca_400(client, db, make_user, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()

    resp = client.post(_url(page), json={
        'order_ids': [],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 400


def test_zamowienie_spoza_strony_zwraca_400(client, db, make_user, make_order, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()
    obca = make_order(make_user(), status='oczekujace')

    resp = client.post(_url(page), json={
        'order_ids': [obca.id],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 400
    assert obca.status == 'oczekujace'


def test_niezamknieta_strona_zwraca_400(client, db, make_user, make_order, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page(is_fully_closed=False, status='active')
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 400
    assert order.status == 'oczekujace'


def test_zbyt_dlugi_powod_zwraca_400(client, db, make_user, make_order, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()
    order = make_order(make_user(), status='oczekujace', offer_page_id=page.id)

    resp = client.post(_url(page), json={
        'order_ids': [order.id],
        'reason': 'x' * 501,
        'notify': False,
    })

    assert resp.status_code == 400
    assert order.status == 'oczekujace'


def test_odpowiedz_zawiera_podzial_na_grupy(
    client, db, make_user, make_order, make_page, login
):
    from modules.orders.models import PaymentConfirmation
    from decimal import Decimal

    login(make_user(role='admin', profile_completed=True))
    page = make_page()

    nieoplacone = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    oplacone = make_order(make_user(), status='oczekujace', offer_page_id=page.id)
    db.session.add(PaymentConfirmation(
        order_id=oplacone.id, payment_stage='product',
        amount=Decimal('50.00'), status='approved',
    ))
    juz_anulowane = make_order(make_user(), status='anulowane', offer_page_id=page.id)
    db.session.commit()

    resp = client.post(_url(page), json={
        'order_ids': [nieoplacone.id, oplacone.id, juz_anulowane.id],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    data = resp.get_json()
    assert data['cancelled'] == 1
    assert data['to_refund'] == 1
    assert data['skipped'] == 1


def test_nieprawidlowe_id_zwraca_400(client, db, make_user, make_page, login):
    login(make_user(role='admin', profile_completed=True))
    page = make_page()

    resp = client.post(_url(page), json={
        'order_ids': ['abc'],
        'reason': 'Wyprzedane',
        'notify': False,
    })

    assert resp.status_code == 400
