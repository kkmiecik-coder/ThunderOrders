"""Panel klienta przy paczce zbiorczej — brak wycieków i blokada anulowania."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


def test_klient_wiodacy_nie_widzi_paczki_zbiorczej(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    # make_user() z _konsolidacji nie ustawia profile_completed — bez tego
    # client_bp.before_request przekierowuje każdy /client/* na complete-profile.
    sr_a.user.profile_completed = True
    db.session.commit()
    login(sr_a.user)

    tresc = client.get('/client/shipping/requests').get_data(as_text=True)
    assert sr_a.request_number in tresc
    assert zbiorcze.request_number not in tresc


def test_json_listy_tez_nie_ujawnia_zbiorczego(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.user.profile_completed = True
    db.session.commit()
    login(sr_a.user)

    dane = client.get('/client/shipping/requests/list').get_json()
    numery = {r['request_number'] for r in dane['requests']}
    assert zbiorcze.request_number not in numery
    assert sr_a.request_number in numery


def test_mobile_nie_ujawnia_zbiorczego(db, client, make_user, make_order):
    from test_mobile_api_shipping import _auth
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    # Logujemy właściciela zlecenia wiodącego — to on jest user_id paczki zbiorczej.
    sr_a.user.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': sr_a.user.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    dane = client.get('/api/mobile/v1/shipping/requests',
                      headers={'Authorization': f'Bearer {token}'}).get_json()
    numery = {r['request_number'] for r in dane['data']['requests']}
    assert zbiorcze.request_number not in numery
    assert sr_a.request_number in numery


def test_klient_nie_anuluje_skonsolidowanego_web(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.status = 'czeka_na_wycene'
    sr_b.user.profile_completed = True
    db.session.commit()
    login(sr_b.user)

    r = client.post(f'/client/shipping/requests/{sr_b.id}/cancel',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400
    assert 'zbiorcz' in r.get_json()['error'].lower()

    from modules.orders.models import ShippingRequest
    assert db.session.get(ShippingRequest, sr_b.id) is not None


def test_klient_nie_anuluje_skonsolidowanego_mobile(db, client, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.user.set_password('Haslo123!')
    sr_b.status = 'czeka_na_wycene'
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': sr_b.user.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    r = client.post(f'/api/mobile/v1/shipping/requests/{sr_b.id}/cancel',
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'consolidated'


def test_klient_zrodlowy_widzi_swoje_zamowienia_i_tracking(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'wyslane'
    zbiorcze.tracking_number = '622111222'
    zbiorcze.courier = 'inpost'
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    sr_b.user.profile_completed = True
    db.session.commit()
    login(sr_b.user)

    tresc = client.get('/client/shipping/requests').get_data(as_text=True)
    assert '622111222' in tresc
    assert sr_b.display_orders[0].order_number in tresc
    # …ale nie zamówienie drugiego klienta.
    assert sr_a.display_orders[0].order_number not in tresc


def test_karta_zamowienia_nie_pokazuje_cudzego_adresu(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.shipping_address = 'ul. Tajna 7'
    sr_a.shipping_name = 'Adresat Wiodacy'
    from modules.orders.consolidation import zmien_wiodace
    zmien_wiodace(zbiorcze, sr_a.id)
    db.session.commit()

    zamowienie_b = sr_b.display_orders[0]
    login(sr_b.user)
    tresc = client.get(f'/client/orders/{zamowienie_b.id}').get_data(as_text=True)

    assert 'ul. Tajna 7' not in tresc
    assert 'Adresat Wiodacy' not in tresc
    assert sr_a.display_orders[0].order_number not in tresc
    assert sr_b.request_number in tresc
