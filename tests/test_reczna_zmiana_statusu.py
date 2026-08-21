"""Ręczna zmiana statusu zlecenia z panelu admina (zgłoszenie nr 2).

„Chciałbym mieć możliwość dojścia do ostatniego etapu z dowolnego miejsca,
z jakiego znajduje się dane zlecenie."

Backend przyjmował `data['status']` od dawna, ale front nigdy tego klucza nie
wysyłał: w modalu status był samym badge'em, a lista statusów w sidebarze to
filtr, nie akcja. Druga trasa (`admin_bulk_status_shipping_requests`) miała
w docstringu wprost: „trasa jest MARTWA — nic jej nie woła poza testami".

Przejścia w „wysłane" i „dostarczone" delegują do jedynych implementacji tych
przejść (`ship_shipping_request`, `dostarcz_zlecenie`), więc niosą komplet
skutków: znaczniki czasu, kaskadę na zamówienia, wpisy przesyłki, kolekcję
klienta i po jednym powiadomieniu.

Dwie granice, których kontrolka nie wolno jej przekroczyć:
- zlecenie ŹRÓDŁOWE paczki zbiorczej nie przyjmuje statusu logistycznego —
  logistyka jest własnością kartonu i zjeżdża propagacją,
- paczka ZBIORCZA nie przyjmuje statusu finansowego — jej status to minimum ze
  statusów uczestników, więc ręczne „opłacone" przy niezapłaconych uczestnikach
  byłoby kłamstwem, a pierwsze zdarzenie płatnicze i tak by je cofnęło.
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
                       ('spakowane', 'Spakowane'), ('wyslane', 'Wysłane'),
                       ('dostarczone', 'Dostarczone')]:
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _admin(make_user):
    return make_user(role='admin', email='admin-status@example.com',
                     profile_completed=True)


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


@pytest.fixture
def bez_powiadomien(monkeypatch):
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for nazwa in ('notify_shipment_sent', 'notify_shipping_status_change',
                  'notify_status_change', 'notify_delivery_confirmed'):
        if hasattr(EmailManager, nazwa):
            monkeypatch.setattr(EmailManager, nazwa, staticmethod(lambda *a, **kw: None))
        if hasattr(PushManager, nazwa):
            monkeypatch.setattr(PushManager, nazwa, staticmethod(lambda *a, **kw: None))


# ---------------------------------------------------------------------------
# Dojście do stanu końcowego z dowolnego miejsca
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('skad', ['czeka_na_wycene', 'czeka_na_oplacenie',
                                  'oplacone', 'spakowane'])
def test_mozna_oznaczyc_jako_wyslane_z_dowolnego_stanu(
        db, client, login, make_user, make_order, bez_powiadomien, skad):
    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order, status=skad, ile=1)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None, (
        f'Przejście z „{skad}" musi nieść komplet skutków, nie sam zapis kolumny'
    )
    assert zamowienia[0].status == 'wyslane'


@pytest.mark.parametrize('skad', ['oplacone', 'spakowane', 'wyslane'])
def test_mozna_oznaczyc_jako_dostarczone_z_dowolnego_stanu(
        db, client, login, make_user, make_order, bez_powiadomien, skad):
    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order, status=skad, ile=1)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'dostarczone'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'dostarczone'
    assert sr.delivered_at is not None, 'Bez delivered_at statystyki dostaw nie zobaczą zlecenia'
    assert sr.delivered_source == 'admin'


def test_przejscie_na_dostarczone_dopisuje_kolekcje_klienta(
        db, client, login, make_user, make_order, make_product, bez_powiadomien):
    """Regresja: kolekcja to skutek dostarczenia, nie osobny krok."""
    from modules.client.models import CollectionItem
    from modules.orders.models import OrderItem

    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order, status='wyslane', ile=1)
    produkt = make_product()
    db.session.add(OrderItem(
        order_id=zamowienia[0].id, product_id=produkt.id,
        quantity=1, price=10.00, total=10.00))
    db.session.commit()
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'status': 'dostarczone'})

    assert CollectionItem.query.filter_by(user_id=sr.user_id).count() == 1


# ---------------------------------------------------------------------------
# Granice kontrolki
# ---------------------------------------------------------------------------

def test_zrodlo_paczki_nie_przyjmuje_statusu_logistycznego(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Logistyka jest własnością kartonu — zjeżdża propagacją, nie ustawia się
    jej na uczestniku."""
    from test_shipping_consolidation import _konsolidacja, _seed_sr_statuses

    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr_a.id}',
                   json={'status': 'wyslane'})

    # 400, nie 409 — ta trasa odmawia zapisu przez _odmowa_zapisu, spójnie
    # z odmowami przy kosztach i terminie płatności.
    assert r.status_code == 400, r.get_json()
    assert 'paczce zbiorczej' in r.get_json()['error']
    db.session.expire_all()
    assert sr_a.status != 'wyslane'


def test_paczka_zbiorcza_nie_przyjmuje_statusu_finansowego(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Status paczki to MINIMUM ze statusów uczestników.

    Ręczne „opłacone" przy niezapłaconych uczestnikach byłoby kłamstwem, a
    pierwsze zdarzenie płatnicze i tak przeliczyłoby minimum i cofnęło zmianę —
    admin zobaczyłby, że jego zapis „zniknął".
    """
    from test_shipping_consolidation import _konsolidacja, _seed_sr_statuses

    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}',
                   json={'status': 'oplacone'})

    assert r.status_code == 400, r.get_json()
    db.session.expire_all()
    assert zbiorcze.status == 'czeka_na_oplacenie'


def test_paczka_zbiorcza_przyjmuje_status_logistyczny(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Regresja: logistykę paczki ustawia się właśnie na niej."""
    from test_shipping_consolidation import _konsolidacja, _seed_sr_statuses

    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert zbiorcze.status == 'wyslane'
    assert sr_a.status == 'wyslane', 'Logistyka zjeżdża na uczestników propagacją'


def test_nieznany_status_odrzucony(db, client, login, make_user, make_order):
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'nie_ma_takiego_statusu'})

    assert r.status_code == 400, r.get_json()
    db.session.expire_all()
    assert sr.status == 'oplacone'


def test_status_nieaktywny_odrzucony(db, client, login, make_user, make_order):
    """Admin może dezaktywować status w ustawieniach — wtedy znika też z akcji."""
    from modules.orders.models import ShippingRequestStatus

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    st = ShippingRequestStatus.query.filter_by(slug='spakowane').first()
    st.is_active = False
    db.session.commit()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'spakowane'})

    assert r.status_code == 400, r.get_json()
