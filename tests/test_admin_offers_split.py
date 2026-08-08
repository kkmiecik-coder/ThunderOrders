"""
Lista stron sprzedaży: podział na zakładki, kolejność, filtr i paginacja.

Podział/sortowanie/filtrowanie robi baza (build_offers_query), bo lista jest
paginowana — dawna wersja układała strony w Pythonie na pełnym zbiorze.
"""
from datetime import datetime

import pytest


@pytest.fixture
def owner(make_user):
    """Autor stron sprzedaży — OfferPage.created_by jest NOT NULL."""
    return make_user(role='admin', email='owner@example.com', profile_completed=True)


@pytest.fixture
def make_page(db, owner):
    def _make(name, status='draft', is_fully_closed=False, starts_at=None):
        from modules.offers.models import OfferPage
        p = OfferPage(
            name=name,
            token=OfferPage.generate_token(),
            status=status,
            is_fully_closed=is_fully_closed,
            starts_at=starts_at,
            created_by=owner.id,
        )
        db.session.add(p)
        db.session.commit()
        return p
    return _make


def _names(query):
    return [p.name for p in query.all()]


def test_closed_tab_is_only_fully_closed(app, make_page):
    from modules.admin.offers import build_offers_query
    make_page('ended_closed', 'ended', is_fully_closed=True)
    make_page('ended_open', 'ended')
    make_page('active', 'active')

    assert _names(build_offers_query(True)) == ['ended_closed']
    assert set(_names(build_offers_query(False))) == {'ended_open', 'active'}


def test_default_order_follows_status_priority(app, make_page):
    from modules.admin.offers import build_offers_query
    for name, status in [('d', 'draft'), ('e', 'ended'), ('a', 'active'),
                         ('p', 'paused'), ('s', 'scheduled')]:
        make_page(name, status)

    assert _names(build_offers_query(False)) == ['a', 'p', 's', 'd', 'e']


def test_default_order_dates_desc_and_nulls_last(app, make_page):
    from modules.admin.offers import build_offers_query
    make_page('old', 'paused', starts_at=datetime(2026, 1, 1, 10, 0))
    make_page('nodate', 'paused')
    make_page('new', 'paused', starts_at=datetime(2026, 6, 1, 10, 0))
    make_page('mid', 'paused', starts_at=datetime(2026, 3, 1, 10, 0))

    assert _names(build_offers_query(False)) == ['new', 'mid', 'old', 'nodate']


def test_search_filters_by_name(app, make_page):
    from modules.admin.offers import build_offers_query
    make_page('Wielkanoc 2026', 'paused')
    make_page('Boże Narodzenie', 'paused')

    assert _names(build_offers_query(False, search='wielkanoc')) == ['Wielkanoc 2026']


def test_sort_by_name_respects_direction(app, make_page):
    from modules.admin.offers import build_offers_query
    make_page('Beta', 'ended')       # różne statusy, by pokazać, że sortowanie
    make_page('Alfa', 'active')      # po kolumnie wygrywa z priorytetem statusu
    make_page('Gamma', 'draft')

    assert _names(build_offers_query(False, sort='name', direction='asc')) == ['Alfa', 'Beta', 'Gamma']
    assert _names(build_offers_query(False, sort='name', direction='desc')) == ['Gamma', 'Beta', 'Alfa']


def test_unknown_sort_column_falls_back_to_default(app, make_page):
    from modules.admin.offers import build_offers_query
    make_page('draft', 'draft')
    make_page('active', 'active')

    assert _names(build_offers_query(False, sort='cokolwiek')) == ['active', 'draft']


def test_selection_rows_cover_whole_filtered_set(app, make_page):
    """Zaznaczanie działa na całym wyniku filtra, nie na jednej stronie paginacji."""
    from modules.admin.offers import build_offers_query, offers_selection_rows, OFFERS_PER_PAGE
    for i in range(OFFERS_PER_PAGE + 5):
        make_page(f'Strona {i:02d}', 'paused')

    rows = offers_selection_rows(build_offers_query(False))
    assert len(rows) == OFFERS_PER_PAGE + 5
    assert all(row['status'] == 'paused' and row['fullyClosed'] is False for row in rows)


def test_list_paginates_each_tab(app, make_page, client, make_user, login):
    from modules.admin.offers import OFFERS_PER_PAGE
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(OFFERS_PER_PAGE + 3):
        make_page(f'Biezaca {i:02d}', 'paused')

    first = client.get('/admin/offers')
    assert first.status_code == 200
    assert first.text.count('offer-checkbox"') == OFFERS_PER_PAGE

    second = client.get('/admin/offers?page_current=2')
    assert second.status_code == 200
    assert second.text.count('offer-checkbox"') == 3


def test_list_search_narrows_both_tabs(app, make_page, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    make_page('Wielkanoc', 'paused')
    make_page('Wielkanoc zamknieta', 'ended', is_fully_closed=True)
    make_page('Mikolajki', 'paused')

    resp = client.get('/admin/offers?search=wielkanoc')
    assert resp.status_code == 200
    assert 'Mikolajki' not in resp.text
    assert 'Wielkanoc' in resp.text
