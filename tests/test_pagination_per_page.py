"""
Selektor „ile pozycji na stronie" (utils/pagination.py).

Wybór żyje w sesji logowania, `?per_page=` w URL go nadpisuje, a wartości spoza
listy opcji są ignorowane — inaczej parametrem w adresie dałoby się kazać bazie
wyciągnąć dowolnie dużą stronę.
"""
import pytest

from utils.pagination import (
    PER_PAGE_ALL,
    PER_PAGE_OPTIONS,
    clear_per_page_preferences,
    paginate_with_choice,
    resolve_per_page,
)


@pytest.fixture
def owner(make_user):
    return make_user(role='admin', email='owner@example.com', profile_completed=True)


@pytest.fixture
def make_page(db, owner):
    def _make(name):
        from modules.offers.models import OfferPage
        p = OfferPage(name=name, token=OfferPage.generate_token(),
                      status='paused', created_by=owner.id)
        db.session.add(p)
        db.session.commit()
        return p
    return _make


def test_url_wins_and_is_remembered(app):
    from flask import session
    with app.test_request_context('/admin/offers?per_page=100'):
        assert resolve_per_page('offers') == 100
        assert session['per_page:offers'] == 100


def test_session_used_when_url_has_no_param(app):
    from flask import session
    with app.test_request_context('/admin/offers'):
        session['per_page:offers'] = 50
        assert resolve_per_page('offers') == 50


def test_default_when_nothing_set(app):
    with app.test_request_context('/admin/offers'):
        assert resolve_per_page('offers', default=20) == 20


def test_all_is_a_valid_choice(app):
    with app.test_request_context('/admin/offers?per_page=all'):
        assert resolve_per_page('offers') == PER_PAGE_ALL


@pytest.mark.parametrize('raw', ['7', '99999', '-5', '0', 'dużo', ''])
def test_value_outside_options_is_ignored(app, raw):
    """Wartość spoza listy nie może przejść — ani do wyniku, ani do sesji."""
    from flask import session
    with app.test_request_context(f'/admin/offers?per_page={raw}'):
        assert resolve_per_page('offers', default=20) == 20
        assert 'per_page:offers' not in session


def test_keys_are_independent_per_list(app):
    from flask import session
    with app.test_request_context('/admin/offers?per_page=300'):
        resolve_per_page('offers')
    with app.test_request_context('/admin/orders/wms'):
        session['per_page:offers'] = 300
        assert resolve_per_page('wms_shipping', default=20) == 20


def test_logout_clears_preferences(app):
    from flask import session
    with app.test_request_context('/'):
        session['per_page:offers'] = 100
        session['per_page:wms_shipping'] = 50
        session['inne_dane'] = 'zostaje'

        clear_per_page_preferences()

        assert 'per_page:offers' not in session
        assert 'per_page:wms_shipping' not in session
        assert session['inne_dane'] == 'zostaje'


def test_all_puts_everything_on_one_page(app, make_page):
    from modules.admin.offers import build_offers_query
    for i in range(25):
        make_page(f'Strona {i:02d}')

    pagination = paginate_with_choice(build_offers_query(False), 1, PER_PAGE_ALL)
    assert len(pagination.items) == 25
    assert pagination.pages == 1


def test_all_on_empty_list_does_not_crash(app):
    """per_page=0 jest odrzucane przez Flask-SQLAlchemy — pusta lista musi przejść."""
    from modules.admin.offers import build_offers_query

    pagination = paginate_with_choice(build_offers_query(False), 1, PER_PAGE_ALL)
    assert pagination.items == []
    assert pagination.total == 0


def test_list_respects_chosen_size(app, make_page, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(25):
        make_page(f'Strona {i:02d}')

    resp = client.get('/admin/offers?per_page=10')
    assert resp.text.count('offer-checkbox"') == 10

    resp = client.get('/admin/offers?per_page=all')
    assert resp.text.count('offer-checkbox"') == 25


def test_choice_survives_next_request(app, make_page, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(25):
        make_page(f'Strona {i:02d}')

    client.get('/admin/offers?per_page=10')
    resp = client.get('/admin/offers')          # bez parametru — z sesji
    assert resp.text.count('offer-checkbox"') == 10


def test_selector_stays_when_everything_fits_on_one_page(app, make_page, client, make_user, login):
    """Bez tego wybór „Wszystkie" chowałby selektor i nie dałoby się wrócić."""
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    make_page('Jedyna strona')

    resp = client.get('/admin/offers?per_page=all')
    assert 'pagination-per-page-select' in resp.text


def test_every_option_is_offered_in_the_selector(app, make_page, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    make_page('Jedyna strona')

    resp = client.get('/admin/offers')
    for option in PER_PAGE_OPTIONS:
        assert f'per_page={option}' in resp.text
    assert 'per_page=all' in resp.text


def test_page_input_knows_its_range_and_url_pattern(app, make_page, client, make_user, login):
    """Pole numeru strony: JS podmienia __PAGE__, więc wzorzec musi tam być."""
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(45):
        make_page(f'Strona {i:02d}')

    resp = client.get('/admin/offers?per_page=20')
    assert 'class="pagination-input"' in resp.text
    assert 'max="3"' in resp.text                       # 45 pozycji / 20 = 3 strony
    assert 'page_current=__PAGE__' in resp.text


# ---- Lista produktów: ten sam komponent ----

def test_products_list_uses_shared_component(app, client, make_user, login, make_product):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(12):
        make_product(name=f'Produkt {i:02d}')

    resp = client.get('/admin/products/?per_page=10')
    assert resp.status_code == 200
    assert 'pagination-per-page-select' in resp.text     # selektor z komponentu
    assert 'page=__PAGE__' in resp.text                  # pole skoku do strony
    assert 'pagination-compact' not in resp.text         # stary markup zniknął
    assert 'onchange="changePerPage' not in resp.text    # i stara obsługa też


def test_products_pagination_keeps_active_filters(app, client, make_user, login, make_product):
    """Stary kod przenosił tylko 4 parametry — filtry z modala ginęły przy zmianie strony."""
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(12):
        make_product(name=f'Produkt {i:02d}')

    resp = client.get('/admin/products/?per_page=10&stock_filter=in_stock&sort=name')
    assert 'stock_filter=in_stock' in resp.text
    assert 'sort=name' in resp.text


# ---- Lista użytkowników: ten sam komponent ----

def test_clients_list_uses_shared_component(app, client, make_user, login):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(12):
        make_user(email=f'klient{i:02d}@example.com')

    resp = client.get('/admin/clients?per_page=10')
    assert resp.status_code == 200
    assert 'pagination-per-page-select' in resp.text
    assert 'page=__PAGE__' in resp.text
    assert 'pagination-compact' not in resp.text
    assert 'onchange="changePerPage' not in resp.text


def test_clients_pagination_keeps_sorting(app, client, make_user, login):
    """Stary kod przenosił tylko search/status/role — sortowanie ginęło przy zmianie strony."""
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(12):
        make_user(email=f'klient{i:02d}@example.com')

    resp = client.get('/admin/clients?per_page=10&sort=email&dir=asc')
    assert 'sort=email' in resp.text
    assert 'dir=asc' in resp.text


def test_products_respect_chosen_size(app, client, make_user, login, make_product):
    login(make_user(role='admin', email='admin@example.com', profile_completed=True))
    for i in range(12):
        make_product(name=f'Produkt {i:02d}')

    assert client.get('/admin/products/?per_page=10').text.count('product-checkbox') >= 10
    resp = client.get('/admin/products/')      # bez parametru — wybór z sesji
    assert 'pagination-per-page-select' in resp.text
