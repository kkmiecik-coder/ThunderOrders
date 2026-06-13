"""
Testy Socket.IO dla aplikacji mobilnej (E9).

Część 1 (Task 2): autoryzacja połączenia `connect` przez JWT + wiązanie sid→user
(`_ws_users`) + czyszczenie przy disconnect. Handler jest PERMISYWNY — połączenia
bez tokenu (web/WMS/payment) są akceptowane; odrzucane są wyłącznie połączenia
z niepoprawnym JWT (śmieć/wygasły/refresh/blocklista/inactive).
"""

from datetime import timedelta

import pytest

from extensions import socketio


# Import odłożony do czasu wykonania testu — `modules.api_mobile` ładuje się poprawnie
# dopiero po `create_app` (fixture `app`); kolejność importów blueprintu rozwiązuje
# cykle, których import na poziomie modułu (przy collection) by nie rozwiązał.
def _bound_uids():
    from modules.api_mobile.ws import _ws_users
    return _ws_users.values()


@pytest.fixture(autouse=True)
def _ws_handlers(app):
    """Re-rejestracja handlerów Socket.IO na świeżym serwerze per-test.

    `app` jest function-scoped → każdy test woła `create_app` → `socketio.init_app`
    tworzy NOWY `socketio.server`. flask-socketio re-aplikuje tylko `self.handlers`
    (handlery zarejestrowane gdy serwer jeszcze nie istniał). W tym repo wszystkie
    handlery rejestrują się przez `register_blueprints` PO `init_app` → lądują wprost
    na serwerze pierwszego testu i nie są przenoszone na kolejne. W produkcji
    `create_app` jest wołane RAZ, więc problem nie występuje. Tu re-bindujemy handlery,
    których ta suita używa, na bieżący serwer (idempotentne — nadpisuje ten sam slot).

    Część 2 (Task 3) dokłada PRAWDZIWE handlery rezerwacji z `socket_events.py`
    (`join_offer_reservation`/`reserve_product`/`release_product`/`extend_reservation`)
    — bez nich zdarzenia rezerwacji nie zadziałają na świeżym serwerze testowym.

    Dodatkowo wymuszamy in-memory backend stanu ofert (`init_state(None)`): `create_app`
    woła `init_state(REDIS_URL)`, a gdy lokalny Redis jest podniesiony, stan rezerwacji
    (user_session/reservation_session, TTL 1h) byłby WSPÓŁDZIELONY i kontaminowałby testy
    takeover między testami i uruchomieniami. Backend jest wymienny (ten sam interfejs),
    więc logika takeover/transferu jest identyczna — in-memory daje hermetyczność.
    """
    from modules.api_mobile.ws import ws_connect, _ws_users
    from modules.orders.wms_events import handle_disconnect
    from modules.offers.socket_events import (
        handle_join_offer_reservation,
        handle_reserve_product,
        handle_release_product,
        handle_extend_reservation,
    )
    from modules.offers.redis_state import init_state

    # Hermetyczny, deterministyczny stan ofert per-test (bez kontaminacji Redis).
    init_state(None)
    # Wiązanie sid→user (`_ws_users`) to moduł-global, nieresetowany między testami;
    # user.id powtarza się (DB resetowana per-test) → czyścimy, by uniknąć kontaminacji.
    _ws_users.clear()

    socketio.on_event('connect', ws_connect)
    socketio.on_event('disconnect', handle_disconnect)
    socketio.on_event('join_offer_reservation', handle_join_offer_reservation)
    socketio.on_event('reserve_product', handle_reserve_product)
    socketio.on_event('release_product', handle_release_product)
    socketio.on_event('extend_reservation', handle_extend_reservation)
    yield


# ---------------------------------------------------------------------------
# Helpery tokenów (parytet z apką: identity=str(user.id), claim 'pwd')
# ---------------------------------------------------------------------------

def _access_token(app, user, expires_delta=None):
    from flask_jwt_extended import create_access_token
    with app.app_context():
        return create_access_token(
            identity=str(user.id),
            additional_claims={'pwd': 'x'},
            expires_delta=expires_delta,
        )


def _refresh_token(app, user):
    from flask_jwt_extended import create_refresh_token
    with app.app_context():
        return create_refresh_token(
            identity=str(user.id),
            additional_claims={'pwd': 'x'},
        )


def _jti_of(app, token):
    from flask_jwt_extended import decode_token
    with app.app_context():
        return decode_token(token)['jti']


# ---------------------------------------------------------------------------
# AKCEPTACJA
# ---------------------------------------------------------------------------

def test_ws_connect_with_jwt_in_auth(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert tc.is_connected()
    assert u.id in _bound_uids()
    tc.disconnect()


def test_ws_connect_with_jwt_in_query_string(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, query_string=f'token={token}')
    assert tc.is_connected()
    assert u.id in _bound_uids()
    tc.disconnect()


def test_ws_connect_without_token_accepted(app, db):
    # Parytet web/WMS — brak tokenu nie odrzuca połączenia.
    tc = socketio.test_client(app)
    assert tc.is_connected()
    tc.disconnect()


def test_ws_connect_with_session_cookie_accepted(app, db, make_user, client, login):
    # Połączenie webowe (cookie sesji, bez JWT) musi przejść — connect bez tokenu akceptuje.
    u = make_user()
    login(u)
    tc = socketio.test_client(app, flask_test_client=client)
    assert tc.is_connected()
    # Web NIE jest wiązany w _ws_users (tylko JWT).
    assert u.id not in _bound_uids()
    tc.disconnect()


# ---------------------------------------------------------------------------
# ODRZUCENIE
# ---------------------------------------------------------------------------

def test_ws_connect_garbage_token_rejected(app, db):
    tc = socketio.test_client(app, auth={'token': 'to-nie-jest-jwt'})
    assert not tc.is_connected()


def test_ws_connect_expired_token_rejected(app, db, make_user):
    u = make_user()
    token = _access_token(app, u, expires_delta=timedelta(seconds=-10))
    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_refresh_token_rejected(app, db, make_user):
    u = make_user()
    token = _refresh_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_blocklisted_token_rejected(app, db, make_user):
    from modules.api_mobile.models import MobileTokenBlocklist
    from modules.orders.models import get_local_now

    u = make_user()
    token = _access_token(app, u)
    jti = _jti_of(app, token)
    db.session.add(MobileTokenBlocklist(
        jti=jti, token_type='access', user_id=u.id,
        expires_at=get_local_now() + timedelta(hours=1),
    ))
    db.session.commit()

    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


def test_ws_connect_inactive_user_rejected(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    u.is_active = False
    db.session.commit()

    tc = socketio.test_client(app, auth={'token': token})
    assert not tc.is_connected()
    assert u.id not in _bound_uids()


# ---------------------------------------------------------------------------
# CLEANUP PRZY DISCONNECT
# ---------------------------------------------------------------------------

def test_ws_disconnect_unbinds_sid(app, db, make_user):
    u = make_user()
    token = _access_token(app, u)
    tc = socketio.test_client(app, auth={'token': token})
    assert tc.is_connected()
    assert u.id in _bound_uids()

    tc.disconnect()
    assert u.id not in _bound_uids()


# ===========================================================================
# CZĘŚĆ 2 (Task 3) — rezerwacja apki przez WS (reuse zdarzeń web) +
# cross-device takeover. Apka EMITUJE TE SAME zdarzenia co web; tożsamość
# pochodzi z TOKENU (JWT-związany sid), payloadowy user_id jest ignorowany.
# ===========================================================================

# --- Setup strony/sekcji jak E3 (OfferPage exclusive active + OfferSection) ---

def _make_offer_page(db, creator, status='active'):
    from modules.offers.models import OfferPage
    p = OfferPage(
        name='E9 Drop',
        token=OfferPage.generate_token(),
        status=status,
        page_type='exclusive',
        payment_stages=4,
        created_by=creator.id,
    )
    db.session.add(p)
    db.session.commit()
    return p


def _add_product_section(db, page, product, max_quantity=10):
    from modules.offers.models import OfferSection
    db.session.add(OfferSection(
        offer_page_id=page.id, section_type='product',
        product_id=product.id, max_quantity=max_quantity, sort_order=0,
    ))
    db.session.commit()


def _connect_app(app, user):
    """Połączenie apki: sid uwierzytelniony JWT przy connect (tożsamość w _ws_users)."""
    return socketio.test_client(app, auth={'token': _access_token(app, user)})


def _connect_web(app):
    """Połączenie webowe: BEZ tokenu (parytet) — sid NIE jest JWT-związany."""
    return socketio.test_client(app)


def _join(tc, page, session_id, user_id):
    return tc.emit('join_offer_reservation', {
        'page_id': page.id,
        'session_id': session_id,
        'user_id': user_id,
        'token': page.token,
    }, callback=True)


def _reserve(tc, page, session_id, product, quantity=1):
    return tc.emit('reserve_product', {
        'page_id': page.id,
        'session_id': session_id,
        'product_id': product.id,
        'quantity': quantity,
    }, callback=True)


def _names(received):
    return [ev['name'] for ev in received]


def _reservation(page, product):
    from modules.offers.models import OfferReservation
    return OfferReservation.query.filter_by(
        offer_page_id=page.id, product_id=product.id,
    ).one()


# ---------------------------------------------------------------------------
# Anti-spoofing: tożsamość z tokenu, nie z payloadu
# ---------------------------------------------------------------------------

def test_ws_app_reserve_uses_identity_from_token_not_payload(app, db, make_user, make_product):
    owner = make_user()
    attacker = make_user()
    page = _make_offer_page(db, owner)
    prod = make_product()
    _add_product_section(db, page, prod, max_quantity=10)

    tc = _connect_app(app, owner)
    assert tc.is_connected()

    # Payload podszywa się pod attackera — musi zostać ZIGNOROWANY (JWT = owner).
    join_ack = _join(tc, page, 'app-S', user_id=attacker.id)
    assert join_ack['success'] is True

    res_ack = _reserve(tc, page, 'app-S', prod, quantity=3)
    assert res_ack['success'] is True

    r = _reservation(page, prod)
    assert r.user_id == owner.id          # z TOKENU, nie attacker
    assert r.quantity == 3
    assert r.session_id == 'app-S'
    tc.disconnect()


# ---------------------------------------------------------------------------
# Parytet web: dedup po session_id bez JWT (zachowanie 1:1 z dziś)
# ---------------------------------------------------------------------------

def test_ws_web_session_id_takeover_unchanged(app, db, make_user, make_product):
    u = make_user()
    page = _make_offer_page(db, u)
    prod = make_product()
    _add_product_section(db, page, prod, max_quantity=10)

    web1 = _connect_web(app)
    web2 = _connect_web(app)
    assert not (u.id in _bound_uids())  # web nie jest JWT-wiązany

    assert _join(web1, page, 'shared-S', user_id=u.id)['success'] is True
    web1.get_received()  # wyczyść bufor (visitor/availability)

    # Drugie połączenie z tym samym session_id → wyrzuca pierwsze (force_disconnect).
    assert _join(web2, page, 'shared-S', user_id=u.id)['success'] is True
    assert 'force_disconnect' in _names(web1.get_received())

    assert _reserve(web2, page, 'shared-S', prod, quantity=1)['success'] is True
    r = _reservation(page, prod)
    assert r.user_id == u.id              # payload user_id użyty (brak JWT)
    assert r.session_id == 'shared-S'
    web1.disconnect()
    web2.disconnect()


# ---------------------------------------------------------------------------
# Cross-device takeover — apka przejmuje web
# ---------------------------------------------------------------------------

def test_ws_cross_device_takeover_app_takes_over_web(app, db, make_user, make_product):
    u = make_user()
    page = _make_offer_page(db, u)
    prod = make_product()
    _add_product_section(db, page, prod, max_quantity=10)

    # (1) web (bez JWT) rezerwuje qty=2 na 'web-S' z payload user_id=U.
    web = _connect_web(app)
    assert _join(web, page, 'web-S', user_id=u.id)['success'] is True
    assert _reserve(web, page, 'web-S', prod, quantity=2)['success'] is True
    web.get_received()  # wyczyść bufor przed takeover

    # (2) apka (JWT usera U) joinuje 'app-S' BEZ user_id w payloadzie — tożsamość z tokenu.
    apk = _connect_app(app, u)
    assert apk.is_connected()
    app_join = _join(apk, page, 'app-S', user_id=None)
    assert app_join['success'] is True

    # web dostaje force_disconnect; rezerwacja przetransferowana na 'app-S'.
    assert 'force_disconnect' in _names(web.get_received())
    r = _reservation(page, prod)
    assert r.session_id == 'app-S'        # transfer
    assert r.user_id == u.id
    assert r.quantity == 2

    # web wyrzucony z user_session; teraz user_session wskazuje sesję apki.
    from modules.offers.redis_state import get_state
    assert get_state().get_reservation_session(page.id, 'web-S') is None
    assert get_state().get_user_session(page.id, u.id) is not None

    # Apka rezerwuje dalej na tej samej (przejętej) sesji.
    assert _reserve(apk, page, 'app-S', prod, quantity=1)['success'] is True
    assert _reservation(page, prod).quantity == 3
    web.disconnect()
    apk.disconnect()


# ---------------------------------------------------------------------------
# Cross-device takeover — web przejmuje apkę (kierunek odwrotny)
# ---------------------------------------------------------------------------

def test_ws_cross_device_takeover_web_takes_over_app(app, db, make_user, make_product):
    u = make_user()
    page = _make_offer_page(db, u)
    prod = make_product()
    _add_product_section(db, page, prod, max_quantity=10)

    # (1) apka (JWT usera U) rezerwuje qty=2 na 'app-S' BEZ user_id w payloadzie.
    apk = _connect_app(app, u)
    assert _join(apk, page, 'app-S', user_id=None)['success'] is True
    assert _reserve(apk, page, 'app-S', prod, quantity=2)['success'] is True
    apk.get_received()

    # (2) web (bez JWT) joinuje 'web-S' z payload user_id=U → przejmuje sesję apki.
    web = _connect_web(app)
    assert _join(web, page, 'web-S', user_id=u.id)['success'] is True

    assert 'force_disconnect' in _names(apk.get_received())
    r = _reservation(page, prod)
    assert r.session_id == 'web-S'        # transfer w drugą stronę
    assert r.user_id == u.id
    assert r.quantity == 2
    apk.disconnect()
    web.disconnect()


# ---------------------------------------------------------------------------
# KRYTYCZNY parytet: pełna webowa ścieżka WS rezerwacji 1:1 jak przed E9
# ---------------------------------------------------------------------------

def test_ws_web_reserve_still_works_1to1(app, db, make_user, make_product):
    u = make_user()
    page = _make_offer_page(db, u)
    prod = make_product()
    _add_product_section(db, page, prod, max_quantity=10)

    web = _connect_web(app)
    assert _join(web, page, 'web-S', user_id=u.id)['success'] is True
    assert _reserve(web, page, 'web-S', prod, quantity=3)['success'] is True

    r = _reservation(page, prod)
    assert r.user_id == u.id              # payload user_id (brak JWT) — jak przed E9
    assert r.session_id == 'web-S'
    assert r.quantity == 3
    web.disconnect()
