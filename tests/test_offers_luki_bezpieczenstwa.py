"""
Luki bezpieczeństwa na stronach sprzedaży (moduł `modules/offers/`).

1. Podszywanie się w Socket.IO — dla połączeń webowych tożsamość brana była z
   payloadu (`user_id` wysyłany przez przeglądarkę). Każdy mógł rezerwować na
   cudze konto i przejmować cudze sesje (force_disconnect + transfer rezerwacji).
   Teraz: web → sesja Flask-Login, apka → JWT; payloadowy `user_id` ignorowany.
   Do tego bramka odbiorców strony prywatnej (jak w trasie HTTP) i bramka roli
   na pokoju LIVE dashboardu admina (wyciekały w nim imiona i nazwiska klientów).

2. Ilość i przynależność produktu — ujemna/zerowa ilość w rezerwacji dawała ujemną
   kwotę zamówienia, ujemne „zwolnienie" zwiększało rezerwację z pominięciem limitu,
   a produkt spoza strony był rezerwowany bez limitu i trafiał do zamówienia.

3. Koniec sprzedaży — status strony przełącza się na 'ended' leniwie (przy wejściu
   na stronę), więc rezerwacja/zamówienie po `ends_at` przechodziły, póki nikt nie
   odświeżył strony. Teraz serwer sam sprawdza datę końca.
"""

import time
from datetime import timedelta
from decimal import Decimal

import pytest

from extensions import socketio
from utils.timeutil import utcnow


# ---------------------------------------------------------------------------
# Fixture: handlery Socket.IO na świeżym serwerze testowym
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _ws_handlers(app):
    """Re-rejestracja handlerów na serwerze per-test (powód: tests/test_mobile_api_ws.py)."""
    from modules.api_mobile.ws import ws_connect, _ws_users
    from modules.orders.wms_events import handle_disconnect
    from modules.offers.socket_events import (
        handle_join_offer_reservation,
        handle_reserve_product,
        handle_release_product,
        handle_extend_reservation,
        handle_join_offer_admin,
    )
    from modules.offers.redis_state import init_state

    init_state(None)
    _ws_users.clear()

    socketio.on_event('connect', ws_connect)
    socketio.on_event('disconnect', handle_disconnect)
    socketio.on_event('join_offer_reservation', handle_join_offer_reservation)
    socketio.on_event('reserve_product', handle_reserve_product)
    socketio.on_event('release_product', handle_release_product)
    socketio.on_event('extend_reservation', handle_extend_reservation)
    socketio.on_event('join_offer_admin', handle_join_offer_admin)
    yield


# ---------------------------------------------------------------------------
# Helpery
# ---------------------------------------------------------------------------

def _page(db, creator, status='active', is_private=False, ends_at=None, page_type='exclusive'):
    from modules.offers.models import OfferPage
    p = OfferPage(
        name='Drop luki',
        token=OfferPage.generate_token(),
        status=status,
        page_type=page_type,
        payment_stages=4,
        is_private=is_private,
        ends_at=ends_at,
        created_by=creator.id,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _section(db, page, product, max_quantity=10):
    from modules.offers.models import OfferSection
    db.session.add(OfferSection(
        offer_page_id=page.id, section_type='product',
        product_id=product.id, max_quantity=max_quantity, sort_order=0,
    ))
    db.session.commit()


def _db_reservation(db, page, product, session_id, qty, user):
    from modules.offers.models import OfferReservation
    now = int(time.time())
    r = OfferReservation(session_id=session_id, offer_page_id=page.id, product_id=product.id,
                         quantity=qty, reserved_at=now, expires_at=now + 120, user_id=user.id)
    db.session.add(r)
    db.session.commit()
    return r


def _reservations(page):
    from modules.offers.models import OfferReservation
    return OfferReservation.query.filter_by(offer_page_id=page.id).all()


def _ex_order_type(db):
    from modules.orders.models import OrderType
    if not OrderType.query.filter_by(slug='exclusive').first():
        db.session.add(OrderType(slug='exclusive', name='Exclusive', prefix='EX'))
        db.session.commit()


def _web_socket(app, user=None):
    """Połączenie webowe (bez JWT); z `user` — zalogowane cookie sesji Flask-Login."""
    fc = app.test_client()
    if user is not None:
        with fc.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
    return socketio.test_client(app, flask_test_client=fc)


def _app_socket(app, user):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity=str(user.id), additional_claims={'pwd': 'x'})
    return socketio.test_client(app, auth={'token': token})


def _join(tc, page, session_id, user_id=None):
    return tc.emit('join_offer_reservation', {
        'page_id': page.id, 'session_id': session_id,
        'user_id': user_id, 'token': page.token,
    }, callback=True)


def _ws_reserve(tc, page, session_id, product_id, quantity=1):
    return tc.emit('reserve_product', {
        'page_id': page.id, 'session_id': session_id,
        'product_id': product_id, 'quantity': quantity,
    }, callback=True)


def _names(received):
    return [ev['name'] for ev in received]


# ===========================================================================
# 1. TOŻSAMOŚĆ W SOCKET.IO
# ===========================================================================

def test_web_join_bez_logowania_odrzucony_mimo_user_id_w_payloadzie(app, db, make_user, make_product):
    ofiara = make_user()
    page = _page(db, ofiara)
    _section(db, page, make_product())

    anon = _web_socket(app)
    ack = _join(anon, page, 'anon-S', user_id=ofiara.id)

    assert ack['success'] is False
    assert ack['error'] == 'login_required'
    anon.disconnect()


def test_web_rezerwacja_idzie_na_zalogowanego_nie_na_user_id_z_payloadu(app, db, make_user, make_product):
    ofiara = make_user()
    atakujacy = make_user()
    page = _page(db, ofiara)
    prod = make_product()
    _section(db, page, prod)

    tc = _web_socket(app, atakujacy)
    assert _join(tc, page, 'atak-S', user_id=ofiara.id)['success'] is True
    assert _ws_reserve(tc, page, 'atak-S', prod.id, 2)['success'] is True

    [r] = _reservations(page)
    assert r.user_id == atakujacy.id
    tc.disconnect()


def test_web_cudzy_user_id_nie_przejmuje_sesji_ofiary(app, db, make_user, make_product):
    ofiara = make_user()
    atakujacy = make_user()
    page = _page(db, ofiara)
    prod = make_product()
    _section(db, page, prod)

    tc_ofiara = _web_socket(app, ofiara)
    assert _join(tc_ofiara, page, 'ofiara-S', user_id=ofiara.id)['success'] is True
    assert _ws_reserve(tc_ofiara, page, 'ofiara-S', prod.id, 1)['success'] is True
    tc_ofiara.get_received()

    tc_atak = _web_socket(app, atakujacy)
    assert _join(tc_atak, page, 'atak-S', user_id=ofiara.id)['success'] is True

    assert 'force_disconnect' not in _names(tc_ofiara.get_received())
    [r] = _reservations(page)
    assert r.session_id == 'ofiara-S'   # rezerwacja ofiary nie została przeniesiona
    tc_ofiara.disconnect()
    tc_atak.disconnect()


def test_web_join_strona_prywatna_poza_odbiorcami_odrzucony(app, db, make_user, make_product):
    admin = make_user(role='admin')
    obcy = make_user()
    page = _page(db, admin, is_private=True)
    _section(db, page, make_product())

    tc = _web_socket(app, obcy)
    ack = _join(tc, page, 'obcy-S')
    assert ack['success'] is False
    tc.disconnect()


def test_web_join_strona_prywatna_odbiorca_wpuszczony(app, db, make_user, make_product):
    admin = make_user(role='admin')
    czlonek = make_user()
    page = _page(db, admin, is_private=True)
    page.allowed_users.append(czlonek)
    db.session.commit()
    _section(db, page, make_product())

    tc = _web_socket(app, czlonek)
    assert _join(tc, page, 'czlonek-S')['success'] is True
    tc.disconnect()


def test_apka_join_strona_prywatna_poza_odbiorcami_odrzucony(app, db, make_user, make_product):
    admin = make_user(role='admin')
    obcy = make_user()
    page = _page(db, admin, is_private=True)
    _section(db, page, make_product())

    tc = _app_socket(app, obcy)
    assert tc.is_connected()
    ack = _join(tc, page, 'obcy-app-S')
    assert ack['success'] is False
    tc.disconnect()


def test_pokoj_live_admina_niedostepny_dla_klienta(app, db, make_user):
    from modules.offers.redis_state import get_state
    admin = make_user(role='admin')
    klient = make_user()
    page = _page(db, admin)

    tc = _web_socket(app, klient)
    tc.emit('join_offer_admin', {'page_id': page.id})
    names = _names(tc.get_received())

    assert 'visitor_count_update' not in names
    assert 'error' in names
    assert not get_state().has_admins(page.id)
    tc.disconnect()


def test_pokoj_live_admina_niedostepny_dla_anonima(app, db, make_user):
    admin = make_user(role='admin')
    page = _page(db, admin)

    tc = _web_socket(app)
    tc.emit('join_offer_admin', {'page_id': page.id})
    assert 'visitor_count_update' not in _names(tc.get_received())
    tc.disconnect()


def test_pokoj_live_admina_dostepny_dla_admina(app, db, make_user, monkeypatch):
    from modules.offers import socket_events
    monkeypatch.setattr(socket_events, '_start_broadcast_thread', lambda page_id: None)
    admin = make_user(role='admin')
    page = _page(db, admin)

    tc = _web_socket(app, admin)
    tc.emit('join_offer_admin', {'page_id': page.id})
    assert 'visitor_count_update' in _names(tc.get_received())
    tc.disconnect()


# ===========================================================================
# 2. ILOŚĆ >= 1 I PRODUKT Z TEJ STRONY
# ===========================================================================

@pytest.mark.parametrize('quantity', [-5, 0, 'abc', 1.5])
def test_http_reserve_odrzuca_niepoprawna_ilosc(app, db, client, login, make_user, make_product, quantity):
    u = make_user()
    page = _page(db, u)
    prod = make_product()
    _section(db, page, prod)
    login(u)

    resp = client.post(f'/offer/{page.token}/reserve', json={
        'session_id': 'S1', 'product_id': prod.id, 'quantity': quantity,
    })

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_quantity'
    assert _reservations(page) == []


def test_http_reserve_odrzuca_produkt_spoza_strony(app, db, client, login, make_user, make_product):
    u = make_user()
    page = _page(db, u)
    _section(db, page, make_product())
    obcy_produkt = make_product()
    login(u)

    resp = client.post(f'/offer/{page.token}/reserve', json={
        'session_id': 'S1', 'product_id': obcy_produkt.id, 'quantity': 1,
    })

    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'product_not_on_page'
    assert _reservations(page) == []


def test_http_release_ujemna_ilosc_nie_zwieksza_rezerwacji(app, db, client, login, make_user, make_product):
    u = make_user()
    page = _page(db, u)
    prod = make_product()
    _section(db, page, prod, max_quantity=2)
    _db_reservation(db, page, prod, 'S1', 1, u)
    login(u)

    resp = client.post(f'/offer/{page.token}/release', json={
        'session_id': 'S1', 'product_id': prod.id, 'quantity': -100,
    })

    assert resp.status_code == 400
    [r] = _reservations(page)
    assert r.quantity == 1


def test_ws_reserve_odrzuca_ujemna_ilosc(app, db, make_user, make_product):
    u = make_user()
    page = _page(db, u)
    prod = make_product()
    _section(db, page, prod)

    tc = _web_socket(app, u)
    assert _join(tc, page, 'S1')['success'] is True
    ack = _ws_reserve(tc, page, 'S1', prod.id, -3)

    assert ack['success'] is False
    assert ack['error'] == 'invalid_quantity'
    assert _reservations(page) == []
    tc.disconnect()


def test_ws_reserve_odrzuca_produkt_spoza_strony(app, db, make_user, make_product):
    u = make_user()
    page = _page(db, u)
    _section(db, page, make_product())
    obcy_produkt = make_product()

    tc = _web_socket(app, u)
    assert _join(tc, page, 'S1')['success'] is True
    ack = _ws_reserve(tc, page, 'S1', obcy_produkt.id, 1)

    assert ack['success'] is False
    assert ack['error'] == 'product_not_on_page'
    assert _reservations(page) == []
    tc.disconnect()


def test_ws_release_ujemna_ilosc_nie_zwieksza_rezerwacji(app, db, make_user, make_product):
    u = make_user()
    page = _page(db, u)
    prod = make_product()
    _section(db, page, prod, max_quantity=2)

    tc = _web_socket(app, u)
    assert _join(tc, page, 'S1')['success'] is True
    assert _ws_reserve(tc, page, 'S1', prod.id, 1)['success'] is True
    tc.emit('release_product', {
        'page_id': page.id, 'session_id': 'S1', 'product_id': prod.id, 'quantity': -100,
    })

    [r] = _reservations(page)
    assert r.quantity == 1
    tc.disconnect()


def test_serwis_reserve_odrzuca_produkt_spoza_strony(app, db, make_user, make_product):
    """Serwis jest wspólny dla weba, socketu i apki — bramka musi być w nim samym."""
    from modules.offers.reservation import reserve_product
    u = make_user()
    page = _page(db, u)
    _section(db, page, make_product())
    obcy_produkt = make_product()

    ok, result = reserve_product('S1', page.id, obcy_produkt.id, 1, section_max=None, user_id=u.id)

    assert ok is False
    assert result['error'] == 'product_not_on_page'
    assert _reservations(page) == []


def test_place_order_odrzuca_rezerwacje_produktu_spoza_strony(app, db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    from modules.orders.models import Order
    _ex_order_type(db)
    u = make_user()
    page = _page(db, u)
    _section(db, page, make_product())
    obcy_produkt = make_product(sale_price=Decimal('500.00'))
    _db_reservation(db, page, obcy_produkt, 'S1', 1, u)

    with app.test_request_context():
        ok, result = place_offer_order(page=page, session_id='S1', user=u)

    assert ok is False
    assert result['error'] == 'product_not_on_page'
    assert Order.query.filter_by(offer_page_id=page.id).count() == 0


@pytest.mark.parametrize('qty', [0, -3])
def test_place_order_odrzuca_rezerwacje_z_niedodatnia_iloscia(app, db, make_user, make_product, qty):
    from modules.offers.place_order import place_offer_order
    from modules.orders.models import Order
    _ex_order_type(db)
    u = make_user()
    page = _page(db, u)
    prod = make_product(sale_price=Decimal('50.00'))
    _section(db, page, prod)
    _db_reservation(db, page, prod, 'S1', qty, u)

    with app.test_request_context():
        ok, result = place_offer_order(page=page, session_id='S1', user=u)

    assert ok is False
    assert result['error'] == 'invalid_quantity'
    assert Order.query.filter_by(offer_page_id=page.id).count() == 0


def test_place_order_smieciowa_ilosc_kompletu_nie_wywraca_zamowienia(app, db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    _ex_order_type(db)
    u = make_user()
    page = _page(db, u)
    prod = make_product(sale_price=Decimal('50.00'))
    _section(db, page, prod)
    _db_reservation(db, page, prod, 'S1', 1, u)

    with app.test_request_context():
        ok, result = place_offer_order(page=page, session_id='S1', user=u,
                                       full_set_items=[{'product_id': prod.id, 'quantity': 'abc'}])

    assert ok is True
    assert result['total_amount'] == 50.0


# ===========================================================================
# 3. KONIEC SPRZEDAŻY PILNOWANY PRZEZ SERWER
# ===========================================================================

def _po_czasie():
    return utcnow() - timedelta(minutes=5)


def test_http_place_order_po_dacie_konca_odrzucony(app, db, client, login, make_user, make_product):
    from modules.orders.models import Order
    _ex_order_type(db)
    u = make_user()
    page = _page(db, u, status='active', ends_at=_po_czasie())
    prod = make_product()
    _section(db, page, prod)
    _db_reservation(db, page, prod, 'S1', 1, u)
    login(u)

    resp = client.post(f'/offer/{page.token}/place-order', json={'session_id': 'S1'})

    assert resp.status_code == 403
    assert resp.get_json()['error'] == 'page_not_active'
    assert Order.query.filter_by(offer_page_id=page.id).count() == 0


def test_http_reserve_po_dacie_konca_odrzucony(app, db, client, login, make_user, make_product):
    u = make_user()
    page = _page(db, u, status='active', ends_at=_po_czasie())
    prod = make_product()
    _section(db, page, prod)
    login(u)

    resp = client.post(f'/offer/{page.token}/reserve', json={
        'session_id': 'S1', 'product_id': prod.id, 'quantity': 1,
    })

    assert resp.status_code == 403
    assert resp.get_json()['error'] == 'page_not_active'
    assert _reservations(page) == []


@pytest.mark.parametrize('status', ['paused', 'ended', 'scheduled'])
def test_http_reserve_na_nieaktywnej_stronie_odrzucony(app, db, client, login, make_user, make_product, status):
    u = make_user()
    page = _page(db, u, status=status)
    prod = make_product()
    _section(db, page, prod)
    login(u)

    resp = client.post(f'/offer/{page.token}/reserve', json={
        'session_id': 'S1', 'product_id': prod.id, 'quantity': 1,
    })

    assert resp.status_code == 403
    assert _reservations(page) == []


def test_ws_join_po_dacie_konca_odrzucony(app, db, make_user, make_product):
    u = make_user()
    page = _page(db, u, status='active', ends_at=_po_czasie())
    _section(db, page, make_product())

    tc = _web_socket(app, u)
    assert _join(tc, page, 'S1')['success'] is False
    tc.disconnect()


def test_ws_reserve_po_zakonczeniu_w_trakcie_odrzucony(app, db, make_user, make_product):
    u = make_user()
    page = _page(db, u, status='active')
    prod = make_product()
    _section(db, page, prod)

    tc = _web_socket(app, u)
    assert _join(tc, page, 'S1')['success'] is True
    page.ends_at = _po_czasie()       # czas minął, status nadal 'active'
    db.session.commit()

    ack = _ws_reserve(tc, page, 'S1', prod.id, 1)
    assert ack['success'] is False
    assert ack['error'] == 'page_not_active'
    assert _reservations(page) == []
    tc.disconnect()


def test_serwis_place_offer_order_po_dacie_konca_odrzucony(app, db, make_user, make_product):
    """Apka woła serwis bez odświeżenia statusu — bramka musi być w serwisie."""
    from modules.offers.place_order import place_offer_order
    from modules.orders.models import Order
    _ex_order_type(db)
    u = make_user()
    page = _page(db, u, status='active', ends_at=_po_czasie())
    prod = make_product()
    _section(db, page, prod)
    _db_reservation(db, page, prod, 'S1', 1, u)

    with app.test_request_context():
        ok, result = place_offer_order(page=page, session_id='S1', user=u)

    assert ok is False
    assert result['error'] == 'page_not_active'
    assert Order.query.filter_by(offer_page_id=page.id).count() == 0


def test_serwis_place_preorder_order_po_dacie_konca_odrzucony(app, db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order
    u = make_user()
    page = _page(db, u, status='active', ends_at=_po_czasie(), page_type='preorder')
    prod = make_product()
    _section(db, page, prod)

    with app.test_request_context():
        ok, result = place_preorder_order(page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=u)

    assert ok is False
    assert result['error'] == 'page_not_active'
    assert Order.query.filter_by(offer_page_id=page.id).count() == 0
