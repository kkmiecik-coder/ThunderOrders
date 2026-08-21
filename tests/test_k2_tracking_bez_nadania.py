"""Numer przesyłki sam w sobie nie jest nadaniem paczki (BUG K2).

Pole „Numer przesyłki" renderuje się w modalu w OBU trybach — także w „Dodaj
koszty" — a `payloadFor()` wysyła je przy każdym zapisie. Samo dopisanie numeru
z pustego uruchamiało PEŁNE powiadomienie o nadaniu: mail i push „Twoja paczka
jest w drodze" plus wpisy `OrderShipment`.

Zlecenie zostawało przy tym w swoim dotychczasowym statusie, z pustym
`shipped_at` — czyli poza zasięgiem crona przypomnień i automatycznego
domknięcia dostawy. Klient dostawał informację o nadaniu przesyłki, której
system nie uważał za nadaną.

Naprawa przywraca inwariant, który repo już buduje: przejście w „wysłane" ma
JEDNO miejsce, a mail „w drodze" jest jego skutkiem — nie skutkiem edycji pola.
Numer można zapisać na dowolnym etapie, po cichu.
"""

import pytest


def _seed_statuses(db):
    from modules.orders.models import OrderStatus, ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if not ShippingRequestStatus.query.filter_by(slug=slug).first():
            db.session.add(ShippingRequestStatus(
                slug=slug, name=name, sort_order=i, is_active=True,
                is_initial=(slug == 'czeka_na_wycene')))
    for slug, name in [('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'), ('wyslane', 'Wysłane')]:
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


@pytest.fixture
def powiadomienia(monkeypatch):
    """Zbiera numery przesyłek, z którymi poszło powiadomienie o nadaniu."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    zebrane = {'email': [], 'push': []}
    monkeypatch.setattr(
        EmailManager, 'notify_shipment_sent',
        staticmethod(lambda sr, **kw: zebrane['email'].append(
            kw.get('tracking_number') or sr.tracking_number)))
    monkeypatch.setattr(
        PushManager, 'notify_shipment_sent',
        staticmethod(lambda sr, **kw: zebrane['push'].append(
            kw.get('tracking_number') or sr.tracking_number)))
    monkeypatch.setattr(EmailManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(PushManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    return zebrane


def _zlecenie(db, make_user, make_order, status='oplacone', ile=2):
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


def _admin(make_user):
    return make_user(role='admin', email='admin-k2@example.com', profile_completed=True)


# ---------------------------------------------------------------------------
# Cichy zapis numeru
# ---------------------------------------------------------------------------

def test_sam_numer_nie_wysyla_powiadomienia_o_nadaniu(
        client, db, make_user, make_order, login, powiadomienia):
    """Zlecenie 'oplacone' + numer = zapis, ale bez maila o nadaniu."""
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'tracking_number': 'K2CICHY', 'courier': 'inpost'})

    assert r.status_code == 200, r.get_json()
    assert powiadomienia['email'] == [], (
        'Klient dostawał „paczka w drodze" dla przesyłki, której system nie '
        'uważa za nadaną — zlecenie zostaje w swoim statusie, bez shipped_at'
    )
    assert powiadomienia['push'] == []


def test_sam_numer_zapisuje_sie_na_zleceniu(
        client, db, make_user, make_order, login, powiadomienia):
    """Regresja: cichy zapis nie może znaczyć „zapis pomijany"."""
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'tracking_number': 'K2ZAPIS', 'courier': 'inpost'})

    db.session.expire_all()
    assert sr.tracking_number == 'K2ZAPIS'
    assert sr.status == 'oplacone', 'Sam numer nie zmienia statusu'
    assert sr.shipped_at is None


def test_sam_numer_nie_tworzy_wpisow_przesylki(
        client, db, make_user, make_order, login, powiadomienia):
    """Wpis przesyłki to ślad nadania — powstaje przy przejściu w „wysłane"."""
    from modules.orders.models import OrderShipment

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'tracking_number': 'K2WPISY', 'courier': 'dpd'})

    assert OrderShipment.query.filter_by(tracking_number='K2WPISY').count() == 0


# ---------------------------------------------------------------------------
# Nadanie przez zmianę statusu — z numerem wpisanym wcześniej
# ---------------------------------------------------------------------------

def test_numer_zapisany_wczesniej_trafia_do_maila_o_nadaniu(
        client, db, make_user, make_order, login, powiadomienia):
    """Bez tego powstałby regres „klient nie dostaje NICZEGO": numer zapisany
    po cichu, a potem przejście w „wysłane" bez numeru w żądaniu."""
    from modules.orders.wms_utils import ship_shipping_request

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, status='spakowane')
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'tracking_number': 'K2POZNIEJ', 'courier': 'inpost'})
    assert powiadomienia['email'] == []

    db.session.expire_all()
    ship_shipping_request(sr, user=None)

    assert powiadomienia['email'] == ['K2POZNIEJ'], (
        f'Mail o nadaniu musi nieść numer zapisany wcześniej; '
        f'zebrano {powiadomienia["email"]}'
    )


def test_put_ze_statusem_wyslane_nadal_powiadamia(
        client, db, make_user, make_order, login, powiadomienia):
    """Regresja: pełne nadanie jednym żądaniem działa jak dotąd."""
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, status='spakowane')
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'tracking_number': 'K2PELNY', 'courier': 'inpost',
                         'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    assert powiadomienia['email'] == ['K2PELNY']
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None
