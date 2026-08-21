"""Anulowanie zlecenia zamiast fizycznego DELETE.

Słownik statusów zlecenia nie miał stanu negatywnego, więc jedyną operacją
destrukcyjną było skasowanie rekordu. Skutki: znika ślad po anulowaniu (kto,
kiedy, dlaczego) i powstają dziury w numeracji WYS/N — na produkcji 19 dziur
przy 62 żywych zleceniach.

Po zablokowaniu kasowania zleceń już wysłanych DELETE dotyczy wyłącznie zleceń
przed wysyłką, ale nadal kasuje historię.

Anulowanie ZWALNIA zamówienia (usuwa wiersze junction), żeby klient mógł je
włożyć do nowego zlecenia — samo zlecenie zostaje jako ślad.
"""

import pytest


def _seed(db):
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
        ('anulowane', 'Anulowane'),
    ]):
        if not ShippingRequestStatus.query.filter_by(slug=slug).first():
            db.session.add(ShippingRequestStatus(
                slug=slug, name=name, sort_order=i, is_active=True,
                is_initial=(slug == 'czeka_na_wycene')))
    db.session.commit()


def _admin(make_user):
    return make_user(role='admin', email='admin-anulowanie@example.com',
                     profile_completed=True)


def _zlecenie(db, make_user, make_order, status='czeka_na_wycene', ile=2):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status)
    db.session.add(sr)
    db.session.flush()
    zamowienia = []
    for _ in range(ile):
        o = make_order(user=user, status='dostarczone_gom')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


URL = '/admin/orders/shipping-requests/{}/cancel'


# ---------------------------------------------------------------------------
# Anulowanie zachowuje historię
# ---------------------------------------------------------------------------

def test_anulowanie_zostawia_zlecenie_w_bazie(db, client, login, make_user, make_order):
    from modules.orders.models import ShippingRequest

    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    sr_id, numer = sr.id, sr.request_number
    login(_admin(make_user))

    r = client.post(URL.format(sr_id), json={'reason': 'klient zrezygnował'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    zapisane = db.session.get(ShippingRequest, sr_id)
    assert zapisane is not None, 'Zlecenie ma zostać jako ślad, nie zniknąć'
    assert zapisane.status == 'anulowane'
    assert zapisane.request_number == numer, 'Numer zostaje — bez dziur w numeracji'


def test_anulowanie_zwalnia_zamowienia(db, client, login, make_user, make_order):
    """Zamówienia muszą móc trafić do nowego zlecenia."""
    from modules.orders.models import ShippingRequestOrder

    _seed(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order)
    sr_id = sr.id
    login(_admin(make_user))

    client.post(URL.format(sr_id), json={})

    db.session.expire_all()
    assert ShippingRequestOrder.query.filter_by(shipping_request_id=sr_id).count() == 0
    for o in zamowienia:
        assert o.shipping_request is None, (
            'Zamówienie zostało uwięzione w anulowanym zleceniu'
        )


def test_anulowanie_zapisuje_powod_w_historii(db, client, login, make_user, make_order):
    from modules.admin.models import ActivityLog

    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    sr_id = sr.id
    login(_admin(make_user))

    client.post(URL.format(sr_id), json={'reason': 'duplikat zlecenia'})

    wpis = ActivityLog.query.filter_by(
        action='shipping_request_cancelled', entity_id=sr_id).first()
    assert wpis is not None, 'Anulowanie bez śladu w historii to ta sama strata co DELETE'


# ---------------------------------------------------------------------------
# Granice
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('status', ['wyslane', 'dostarczone'])
def test_nie_mozna_anulowac_po_wysylce(db, client, login, make_user, make_order, status):
    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order, status=status)
    login(_admin(make_user))

    r = client.post(URL.format(sr.id), json={})

    assert r.status_code == 409, r.get_json()
    db.session.expire_all()
    assert sr.status == status


def test_nie_mozna_anulowac_dwa_razy(db, client, login, make_user, make_order):
    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    assert client.post(URL.format(sr.id), json={}).status_code == 200
    r = client.post(URL.format(sr.id), json={})

    assert r.status_code == 409


def test_anulowanie_paczki_zbiorczej_zwalnia_uczestnikow(
        db, client, login, make_user, make_order):
    """Zamówienia uczestników wracają do ich własnych zleceń."""
    from test_shipping_consolidation import _konsolidacja, _seed_sr_statuses

    _seed_sr_statuses(db)
    _seed(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post(URL.format(zbiorcze.id), json={})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr_a.consolidated_into_id is None
    assert sr_b.consolidated_into_id is None
    assert len(sr_a.display_orders) == 1, 'Uczestnik odzyskuje swoje zamówienia'


def test_anulowane_zlecenie_znika_z_listy_do_spakowania(
        db, client, login, make_user, make_order):
    """Anulowane nie może zaśmiecać kolejki roboczej magazynu."""
    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order, status='oplacone')
    login(_admin(make_user))

    client.post(URL.format(sr.id), json={})

    r = client.get('/admin/orders/wms')
    assert r.status_code == 200
    assert sr.request_number not in r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Klient anuluje tak samo jak admin
#
# `cancel_request` po stronie klienta robiło twardy DELETE i — w odróżnieniu od
# tras admina — NIE czyściło wiersza `WmsSessionShippingRequest`. FK
# `shipping_request_id` nie ma `ondelete`, więc kasowanie zlecenia, które trafiło
# do sesji WMS, wywracało się na ograniczeniu (na SQLite w testach objawiało się
# to błędem zależnym od kolejności, na MariaDB byłby IntegrityError u klienta).
#
# Anulowanie zamiast kasowania rozwiązuje to u źródła i daje obu stronom tę samą
# semantykę: zlecenie zostaje w historii, zamówienia wracają do puli.
# ---------------------------------------------------------------------------

def test_klient_anuluje_zlecenie_zamiast_kasowac(db, make_user, make_order):
    from modules.client.shipping_service import cancel_request
    from modules.orders.models import ShippingRequest

    _seed(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order)
    sr_id, user_id = sr.id, sr.user_id

    ok, err = cancel_request(user_id, sr_id)

    assert ok is True, err
    db.session.expire_all()
    zapisane = db.session.get(ShippingRequest, sr_id)
    assert zapisane is not None, 'Zlecenie klienta też ma zostać w historii'
    assert zapisane.status == 'anulowane'
    assert len(zapisane.request_orders) == 0, 'Zamówienia wracają do puli'


def test_klient_anuluje_zlecenie_z_sesji_wms(db, make_user, make_order):
    """Zlecenie w sesji WMS: twardy DELETE wywracał się na kluczu obcym."""
    from modules.client.shipping_service import cancel_request
    from modules.orders.models import ShippingRequest
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest

    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    operator = make_user(role='admin', email='operator-anul@example.com')
    sesja = WmsSession(session_token='token-sesji-anulowanie',
                       user_id=operator.id, status='completed')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionShippingRequest(
        session_id=sesja.id, shipping_request_id=sr.id))
    db.session.commit()
    sr_id, user_id = sr.id, sr.user_id

    ok, err = cancel_request(user_id, sr_id)

    assert ok is True, err
    db.session.expire_all()
    assert db.session.get(ShippingRequest, sr_id).status == 'anulowane'


def test_klient_nie_anuluje_cudzego_zlecenia(db, make_user, make_order):
    """Regresja: autoryzacja bez zmian."""
    from modules.client.shipping_service import cancel_request

    _seed(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    obcy = make_user(email='obcy-anul@example.com')

    ok, err = cancel_request(obcy.id, sr.id)

    assert ok is False
    assert err['code'] == 'not_found'
