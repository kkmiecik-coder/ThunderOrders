"""
Zamówienia produktów: filtry, sortowanie i paginacja po stronie serwera.

Wcześniej robił to JavaScript na wyrenderowanych wierszach — po podzieleniu
listy na strony filtrowałby tylko widoczne pozycje, więc logika musiała trafić
do zapytania.
"""
from datetime import datetime

import pytest


@pytest.fixture
def admin(make_user, login):
    user = make_user(role='admin', email='admin@example.com', profile_completed=True)
    login(user)
    return user


@pytest.fixture
def make_proxy_order(db):
    def _make(number, status='zamowiono', amount=100, created_at=None):
        from modules.products.models import ProxyOrder
        order = ProxyOrder(
            order_number=number,
            order_type='proxy',
            status=status,
            total_amount_pln=amount,
            created_at=created_at or datetime(2026, 5, 10, 12, 0),
        )
        db.session.add(order)
        db.session.commit()
        return order
    return _make


@pytest.fixture
def make_poland_order(db, make_proxy_order):
    licznik = {'n': 0}

    def _make(number, status='zamowione', archived=False, tracking=None):
        from modules.products.models import PolandOrder
        # PolandOrder.proxy_order_id jest NOT NULL — każde zlecenie do Polski
        # wywodzi się z zamówienia proxy.
        licznik['n'] += 1
        zrodlo = make_proxy_order(f'PRX/ZR{licznik["n"]:03d}')
        order = PolandOrder(
            order_number=number,
            proxy_order_id=zrodlo.id,
            status=status,
            is_archived=archived,
            tracking_number=tracking,
            total_amount=50,
            created_at=datetime(2026, 5, 10, 12, 0),
        )
        db.session.add(order)
        db.session.commit()
        return order
    return _make


def _numery(resp, prefix):
    """Numery zamówień widoczne w odpowiedzi, w kolejności renderowania."""
    import re
    return re.findall(rf'data-order-number="({re.escape(prefix)}[^"]*)"', resp.text)


def test_proxy_tab_filters_by_order_number(app, admin, client, make_proxy_order):
    make_proxy_order('PRX/00001')
    make_proxy_order('PRX/00002')

    resp = client.get('/admin/products/stock-orders?tab=proxy&q=00002')
    assert resp.status_code == 200
    assert _numery(resp, 'PRX') == ['PRX/00002']


def test_proxy_tab_filters_by_status(app, admin, client, make_proxy_order):
    make_proxy_order('PRX/00001', status='zamowiono')
    make_proxy_order('PRX/00002', status='anulowane')

    resp = client.get('/admin/products/stock-orders?tab=proxy&status=anulowane')
    assert _numery(resp, 'PRX') == ['PRX/00002']


def test_proxy_tab_filters_by_date_range_includes_whole_end_day(app, admin, client, make_proxy_order):
    """Data „do" ma obejmować cały dzień — created_at trzyma też godzinę."""
    make_proxy_order('PRX/00001', created_at=datetime(2026, 5, 10, 23, 30))
    make_proxy_order('PRX/00002', created_at=datetime(2026, 5, 12, 8, 0))

    resp = client.get('/admin/products/stock-orders?tab=proxy&date_from=2026-05-10&date_to=2026-05-10')
    assert _numery(resp, 'PRX') == ['PRX/00001']


def test_proxy_tab_sorts_by_amount(app, admin, client, make_proxy_order):
    make_proxy_order('PRX/00001', amount=10)
    make_proxy_order('PRX/00002', amount=900)

    rosnaco = client.get('/admin/products/stock-orders?tab=proxy&sort=amount&dir=asc')
    assert _numery(rosnaco, 'PRX') == ['PRX/00001', 'PRX/00002']

    malejaco = client.get('/admin/products/stock-orders?tab=proxy&sort=amount&dir=desc')
    assert _numery(malejaco, 'PRX') == ['PRX/00002', 'PRX/00001']


def test_proxy_tab_paginates(app, admin, client, make_proxy_order):
    for i in range(25):
        make_proxy_order(f'PRX/{i:05d}')

    pierwsza = client.get('/admin/products/stock-orders?tab=proxy&per_page=10')
    assert len(_numery(pierwsza, 'PRX')) == 10

    druga = client.get('/admin/products/stock-orders?tab=proxy&per_page=10&page=3')
    assert len(_numery(druga, 'PRX')) == 5


def test_polska_and_archiwum_are_separate(app, admin, client, make_poland_order):
    make_poland_order('PL/00001', archived=False)
    make_poland_order('PL/00002', archived=True)

    biezace = client.get('/admin/products/stock-orders?tab=polska')
    assert _numery(biezace, 'PL') == ['PL/00001']

    archiwum = client.get('/admin/products/stock-orders?tab=archiwum')
    assert _numery(archiwum, 'PL') == ['PL/00002']


def test_polska_tab_filters_by_tracking(app, admin, client, make_poland_order):
    make_poland_order('PL/00001', tracking='KF-111')
    make_poland_order('PL/00002', tracking='KF-999')

    resp = client.get('/admin/products/stock-orders?tab=polska&tracking=999')
    assert _numery(resp, 'PL') == ['PL/00002']


def test_bad_date_in_url_does_not_break_the_page(app, admin, client, make_proxy_order):
    make_proxy_order('PRX/00001')

    resp = client.get('/admin/products/stock-orders?tab=proxy&date_from=nie-data')
    assert resp.status_code == 200
    assert _numery(resp, 'PRX') == ['PRX/00001']


def test_every_tab_renders_pagination_component(app, admin, client, make_proxy_order, make_poland_order):
    make_proxy_order('PRX/00001')
    make_poland_order('PL/00001')
    make_poland_order('PL/00002', archived=True)

    for tab in ('do_zamowienia', 'proxy', 'polska', 'archiwum'):
        resp = client.get(f'/admin/products/stock-orders?tab={tab}')
        assert resp.status_code == 200, tab
        assert 'data-server-filters' in resp.text, tab


def test_client_side_filtering_is_gone(app, admin, client, make_proxy_order):
    """Filtry w JS chowałyby wiersze tylko na bieżącej stronie — nie mogą wrócić."""
    make_proxy_order('PRX/00001')

    resp = client.get('/admin/products/stock-orders?tab=proxy')
    assert 'onclick="sortTable(' not in resp.text
    assert 'oninput="applyFilters' not in resp.text
    assert 'onchange="updateStatusFilter' not in resp.text
