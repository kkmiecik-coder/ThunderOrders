"""Przejście zlecenia w „wysłane" ma JEDNO miejsce (scalenie trzech ścieżek).

W kodzie żyły trzy nakładające się implementacje tego samego przejścia:

1. `ship_shipping_request` — pełna: statusy, `shipped_at`, wpisy przesyłki,
   propagacja na źródła, jeden mail na paczkę, log aktywności.
2. `_sync_order_statuses_from_shipping_request` — statusy zamówień i `shipped_at`.
3. blok `powiadom_o_nadaniu` w `_zapisz_zlecenie_wysylki` — wpisy przesyłki i mail.

Ścieżki 2 i 3 razem odtwarzały część 1, ale każda po swojemu i w innym miejscu
trasy. Wzorzec scalenia był już w repo: przejście w „dostarczone" deleguje do
`dostarcz_zlecenie()` z flagą `status_juz_ustawiony`, bo wywołujący zapisuje
status ZANIM zawoła funkcję. Tu jest identycznie.

Te testy pilnują, że po delegacji nic się nie dubluje (jeden mail, jeden wpis
przesyłki na zamówienie) ani nie ginie (`shipped_at`, log aktywności, kaskada
na zamówienia, propagacja na zlecenia źródłowe paczki zbiorczej).
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


def _admin(make_user):
    return make_user(role='admin', email='admin-scalenie@example.com',
                     profile_completed=True)


def _zlecenie(db, make_user, make_order, ile=3, status='spakowane'):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status)
    db.session.add(sr)
    db.session.flush()
    zamowienia = []
    for _ in range(ile):
        o = make_order(user=user, status='spakowane')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


@pytest.fixture
def zliczone(monkeypatch):
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    dane = {'mail_paczka': [], 'push_paczka': [], 'mail_status': []}
    monkeypatch.setattr(EmailManager, 'notify_shipment_sent',
                        staticmethod(lambda sr, **kw: dane['mail_paczka'].append(sr.id)))
    monkeypatch.setattr(PushManager, 'notify_shipment_sent',
                        staticmethod(lambda sr, **kw: dane['push_paczka'].append(sr.id)))
    monkeypatch.setattr(EmailManager, 'notify_shipping_status_change',
                        staticmethod(lambda sr, old: dane['mail_status'].append(sr.id)))
    monkeypatch.setattr(PushManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    monkeypatch.setattr(EmailManager, 'notify_status_change',
                        staticmethod(lambda *a, **kw: dane.setdefault('mail_zamowienie', []).append(1)))
    monkeypatch.setattr(PushManager, 'notify_status_change',
                        staticmethod(lambda *a, **kw: None))
    return dane


# ---------------------------------------------------------------------------
# PUT ze statusem „wysłane" — kompletne przejście, bez duplikatów
# ---------------------------------------------------------------------------

def test_put_wyslane_daje_komplet_skutkow(client, db, make_user, make_order, login, zliczone):
    """Jedno żądanie = statusy, shipped_at, wpisy przesyłki, jeden mail."""
    from modules.orders.models import OrderShipment

    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane', 'tracking_number': 'SCAL1',
                         'courier': 'inpost'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None, 'Bez shipped_at cron dostaw nie zobaczy zlecenia'
    assert all(o.status == 'wyslane' for o in zamowienia)
    assert OrderShipment.query.filter_by(tracking_number='SCAL1').count() == 3


def test_put_wyslane_wysyla_dokladnie_jeden_mail(
        client, db, make_user, make_order, login, zliczone):
    """Sedno scalenia: dwie ścieżki w jednej trasie nie mogą wysłać dwóch maili."""
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'status': 'wyslane', 'tracking_number': 'SCAL2',
                     'courier': 'inpost'})

    assert zliczone['mail_paczka'] == [sr.id], (
        f'Oczekiwano jednego maila o nadaniu; wysłano {len(zliczone["mail_paczka"])}'
    )
    assert zliczone['push_paczka'] == [sr.id]
    assert zliczone.get('mail_zamowienie', []) == [], (
        'Powiadomienie per zamówienie to trzy maile o jednym kartonie'
    )


def test_put_wyslane_zapisuje_log_aktywnosci(
        client, db, make_user, make_order, login, zliczone):
    """Log nadania powstawał tylko na ścieżce WMS — po scaleniu ma być zawsze."""
    from modules.admin.models import ActivityLog

    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'status': 'wyslane', 'tracking_number': 'SCAL3',
                     'courier': 'inpost'})

    wpisy = ActivityLog.query.filter_by(
        action='shipping_request_shipped', entity_id=sr.id).count()
    assert wpisy == 1, f'Oczekiwano jednego wpisu o nadaniu, jest {wpisy}'


def test_put_wyslane_bez_numeru_tez_dziala(
        client, db, make_user, make_order, login, zliczone):
    """Numer przesyłki jest nieobowiązkowy — klient dostaje mail bez trackingu."""
    _seed_statuses(db)
    sr, zamowienia = _zlecenie(db, make_user, make_order, ile=1)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None
    assert zamowienia[0].status == 'wyslane'
    assert zliczone['mail_paczka'] == [sr.id]


def test_put_wyslane_propaguje_na_zrodla_paczki(
        client, db, make_user, make_order, login, zliczone):
    """Uczestnicy paczki zbiorczej muszą zobaczyć, że ich przesyłka pojechała."""
    from test_shipping_consolidation import _konsolidacja, _seed_sr_statuses

    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{zbiorcze.id}',
                   json={'status': 'wyslane', 'tracking_number': 'SCAL4',
                         'courier': 'inpost'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr_a.status == 'wyslane'
    assert sr_b.status == 'wyslane'
    assert sr_a.tracking_number == 'SCAL4'


def test_powtorny_put_wyslane_nie_dubluje_powiadomienia(
        client, db, make_user, make_order, login, zliczone):
    """Zapis zlecenia już wysłanego nie może wysłać drugiego maila."""
    _seed_statuses(db)
    sr, _z = _zlecenie(db, make_user, make_order, ile=1)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'status': 'wyslane', 'tracking_number': 'SCAL5',
                     'courier': 'inpost'})
    ile_po_pierwszym = len(zliczone['mail_paczka'])

    client.put(f'/admin/orders/shipping-requests/{sr.id}',
               json={'status': 'wyslane', 'tracking_number': 'SCAL5',
                     'courier': 'inpost'})

    assert len(zliczone['mail_paczka']) == ile_po_pierwszym, (
        'Drugi zapis wysłał kolejne powiadomienie o tej samej przesyłce'
    )
