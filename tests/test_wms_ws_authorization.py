"""Autoryzacja kanału Socket.IO sesji WMS.

Trasy HTTP sesji WMS są chronione `@role_required('admin', 'mod')`
(`wms_session_page`, `wms_session_data`), ale kanał Socket.IO omijał tę bramkę:
`join_session` w gałęzi 'desktop' sprawdzał wyłącznie `is_authenticated`, a
handlery mutujące ufały samej obecności sid w `connected_clients`. Zalogowany
klient mógł więc jednym `emit` pobrać `session_state` (z `session_token`, który
daje pełny dostęp mobilny bez logowania, oraz z nazwiskami i adresami wszystkich
klientów w sesji) i zmieniać stan kompletacji cudzych zamówień.

Te testy pilnują, że kanał WS ma tę samą bramkę roli co trasy HTTP.
"""

import pytest

from extensions import socketio


@pytest.fixture(autouse=True)
def _ws_handlers(app):
    """Re-rejestracja handlerów WMS na świeżym serwerze per-test.

    Powód jak w `tests/test_mobile_api_ws.py`: `app` jest function-scoped, więc
    każdy test tworzy nowy `socketio.server`, a handlery rejestrowane przez
    `register_blueprints` PO `init_app` nie są na niego przenoszone.
    """
    from modules.api_mobile.ws import ws_connect
    from modules.orders.wms_events import (
        handle_join_session,
        handle_update_item_status,
        handle_mark_shipping_request_packed,
        handle_disconnect,
        connected_clients,
    )

    connected_clients.clear()

    socketio.on_event('connect', ws_connect)
    socketio.on_event('disconnect', handle_disconnect)
    socketio.on_event('join_session', handle_join_session)
    socketio.on_event('update_item_status', handle_update_item_status)
    socketio.on_event('mark_shipping_request_packed', handle_mark_shipping_request_packed)
    yield
    connected_clients.clear()


@pytest.fixture
def wms_session(db, make_user):
    """Aktywna sesja WMS założona przez admina."""
    from modules.orders.wms_models import WmsSession

    admin = make_user(role='admin', email='admin-wms@example.com')
    sesja = WmsSession(
        session_token='token-testowy-sesji-wms',
        user_id=admin.id,
        status='active',
    )
    db.session.add(sesja)
    db.session.commit()
    return sesja


def _odbierz(tc):
    """Zdarzenia odebrane przez klienta testowego, pogrupowane po nazwie.

    `get_received()` KONSUMUJE kolejkę, więc wolno go zawołać raz na sprawdzenie
    — stąd jeden odczyt i filtrowanie po nazwie w pamięci.
    """
    odebrane = tc.get_received()

    def _o_nazwie(nazwa):
        return [p for p in odebrane if p['name'] == nazwa]

    return _o_nazwie


# ---------------------------------------------------------------------------
# ODRZUCENIE — rola client
# ---------------------------------------------------------------------------

def test_klient_nie_dolaczy_do_sesji_wms(app, db, client, login, make_user, wms_session):
    """Zalogowany klient nie dostaje `session_state` — dostaje błąd."""
    klient = make_user(role='client', email='klient@example.com')
    login(klient)

    tc = socketio.test_client(app, flask_test_client=client)
    assert tc.is_connected()

    tc.emit('join_session', {'session_id': wms_session.id, 'role': 'desktop'})

    zdarzenia = _odbierz(tc)
    assert zdarzenia('session_state') == [], (
        'Klient nie może dostać stanu sesji WMS — wyciekają w nim session_token, '
        'nazwiska i adresy innych klientów'
    )
    assert zdarzenia('error'), 'Klient powinien dostać komunikat o braku uprawnień'
    tc.disconnect()


def test_klient_nie_zmieni_stanu_kompletacji(app, db, client, login, make_user, wms_session):
    """Klient odrzucony w `join_session` nie może mutować pozycji zamówienia."""
    from modules.orders.wms_events import connected_clients

    klient = make_user(role='client', email='klient2@example.com')
    login(klient)

    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {'session_id': wms_session.id, 'role': 'desktop'})
    tc.get_received()

    assert connected_clients == {}, (
        'Odrzucony klient nie może zostać zarejestrowany jako uczestnik sesji — '
        'handlery mutujące ufają samej obecności w connected_clients'
    )

    tc.emit('update_item_status', {'order_item_id': 1, 'action': 'pick_all'})
    assert _odbierz(tc)('item_status_updated') == [], 'Klient nie może zmieniać stanu kompletacji'
    tc.disconnect()


def test_klient_nie_oznaczy_zlecenia_jako_spakowane(app, db, client, login, make_user, wms_session):
    """Klient nie może odpalić pakowania — to kaskaduje statusy i wysyła maile."""
    klient = make_user(role='client', email='klient3@example.com')
    login(klient)

    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {'session_id': wms_session.id, 'role': 'desktop'})
    tc.get_received()

    tc.emit('mark_shipping_request_packed', {'shipping_request_id': 1})

    zdarzenia = _odbierz(tc)
    assert zdarzenia('shipping_request_packed') == [], (
        'Klient nie może oznaczać zleceń jako spakowane'
    )
    # Odrzucenie musi nastąpić na bramce podłączenia, nie przypadkiem na braku
    # zlecenia o tym ID — inaczej test byłby zielony z niewłaściwego powodu.
    bledy = zdarzenia('error')
    assert bledy, 'Klient powinien dostać błąd'
    assert 'Nie jesteś podłączony' in bledy[0]['args'][0]['message'], (
        f'Klient dotarł za bramkę podłączenia — odrzucono go dopiero na: '
        f'{bledy[0]["args"][0]["message"]!r}'
    )
    tc.disconnect()


def test_niezalogowany_nie_dolaczy_do_sesji_wms(app, db, client, wms_session):
    """Bez logowania nadal nie ma wstępu — regresja istniejącego zachowania."""
    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {'session_id': wms_session.id, 'role': 'desktop'})

    zdarzenia = _odbierz(tc)
    assert zdarzenia('session_state') == []
    assert zdarzenia('error')
    tc.disconnect()


# ---------------------------------------------------------------------------
# AKCEPTACJA — role magazynowe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('rola', ['admin', 'mod'])
def test_role_magazynowe_dolaczaja_do_sesji(app, db, client, login, make_user, wms_session, rola):
    """Admin i mod zachowują dostęp — parytet z `@role_required('admin', 'mod')`."""
    operator = make_user(role=rola, email=f'{rola}-operator@example.com')
    login(operator)

    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {'session_id': wms_session.id, 'role': 'desktop'})

    assert len(_odbierz(tc)('session_state')) == 1, f'Rola {rola} musi dostać stan sesji'
    tc.disconnect()


def test_telefon_z_tokenem_dolacza_bez_logowania(app, db, client, wms_session):
    """Ścieżka mobilna działa na token sesji — niezmieniona."""
    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {
        'session_id': wms_session.id,
        'role': 'mobile',
        'token': wms_session.session_token,
    })

    assert len(_odbierz(tc)('session_state')) == 1, (
        'Skaner mobilny musi działać na sam token sesji'
    )
    tc.disconnect()


def test_telefon_ze_zlym_tokenem_odrzucony(app, db, client, wms_session):
    """Regresja: zły token nadal odrzucany."""
    tc = socketio.test_client(app, flask_test_client=client)
    tc.emit('join_session', {
        'session_id': wms_session.id,
        'role': 'mobile',
        'token': 'nie-ten-token',
    })

    zdarzenia = _odbierz(tc)
    assert zdarzenia('session_state') == []
    assert zdarzenia('error')
    tc.disconnect()
