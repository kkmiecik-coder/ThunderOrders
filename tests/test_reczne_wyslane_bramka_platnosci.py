"""Ręczna zmiana statusu na „Wysłane" nie omija bramki płatności.

Kontrolka ręcznej zmiany statusu (zgłoszenie nr 2) i bramka „nieopłacona paczka
nie wyjedzie" powstały w tym samym wdrożeniu — i rozminęły się.

Bramka stoi w `ship_shipping_request`, ale `_zapisz_zlecenie_wysylki` zapisuje
`sr.status` i COMMITUJE, zanim to wywoła. Gdy bramka odrzuca przejście, wyjątek
łapie `_sync_order_statuses_from_shipping_request` i loguje go jako „Pominięto
nadanie zlecenia" — cicho, bo z jego perspektywy to normalny przypadek.

Efekt na zleceniu nieopłaconym: etykieta zmienia się na „Wysłane", ale nadania
nie ma — pusty `shipped_at`, brak wpisów przesyłki, brak maila do klienta.
Zlecenie wygląda na wysłane i wypada z kolejki roboczej magazynu, a paczka stoi.
Lista statusów w modalu też nie usuwała „Wysłane" dla nieopłaconych, więc panel
sam podpowiadał tę drogę.

Naprawa domyka obie strony, w parytecie z regułą dla paczek zbiorczych, która
już tak działa: backend nie PODAJE statusu, którego nie przyjmie, i drugi raz
sprawdza go przy zapisie (stara karta może wysłać nieaktualną listę).
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
    return make_user(role='admin', email='admin-bramka@example.com',
                     profile_completed=True)


def _zlecenie(db, make_user, make_order, koszt_wysylki, wplata=None,
              status='spakowane'):
    """Zlecenie z JEDNYM zamówieniem o zadanym koszcie wysyłki.

    `koszt_wysylki=0` → rozliczone z definicji. `wplata` podana → zatwierdzone
    potwierdzenie E4 na tę kwotę (częściowe, gdy mniejsze od kosztu).
    """
    from decimal import Decimal
    from modules.orders.models import (
        ShippingRequest, ShippingRequestOrder, PaymentConfirmation)

    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status)
    db.session.add(sr)
    db.session.flush()

    o = make_order(user=user, status='dostarczone_gom')
    o.shipping_cost = Decimal(str(koszt_wysylki))
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))

    if wplata is not None:
        db.session.add(PaymentConfirmation(
            order_id=o.id, payment_stage='domestic_shipping',
            amount=Decimal(str(wplata)), status='approved'))

    db.session.commit()
    return sr, o


@pytest.fixture
def bez_powiadomien(monkeypatch):
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    for nazwa in ('notify_shipment_sent', 'notify_shipping_status_change',
                  'notify_status_change'):
        if hasattr(EmailManager, nazwa):
            monkeypatch.setattr(EmailManager, nazwa, staticmethod(lambda *a, **kw: None))
        if hasattr(PushManager, nazwa):
            monkeypatch.setattr(PushManager, nazwa, staticmethod(lambda *a, **kw: None))


# ---------------------------------------------------------------------------
# Panel nie podpowiada statusu, którego nie przyjmie
# ---------------------------------------------------------------------------

def test_lista_statusow_nie_zawiera_wyslane_dla_nieoplaconego(
        db, client, login, make_user, make_order):
    """Backend podaje liście rozwijanej tylko statusy, które faktycznie ustawi."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=None)
    login(_admin(make_user))

    r = client.get(f'/admin/orders/shipping-requests/{sr.id}')

    assert r.status_code == 200
    slugi = [s['slug'] for s in r.get_json()['available_statuses']]
    assert 'wyslane' not in slugi, (
        'Panel podpowiadał „Wysłane" dla zlecenia z nieopłaconą wysyłką — '
        f'a przy zapisie i tak pomija nadanie. Dostępne: {slugi}'
    )


def test_lista_statusow_zawiera_wyslane_dla_oplaconego(
        db, client, login, make_user, make_order):
    """Regresja: rozliczone zlecenie nadal da się oznaczyć ręcznie."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=30)
    login(_admin(make_user))

    r = client.get(f'/admin/orders/shipping-requests/{sr.id}')

    slugi = [s['slug'] for s in r.get_json()['available_statuses']]
    assert 'wyslane' in slugi


def test_lista_statusow_zawiera_wyslane_przy_zerowym_koszcie(
        db, client, login, make_user, make_order):
    """Koszt 0 zł to rozliczenie — ta sama reguła co w `zlecenie_rozliczone`."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=0)
    login(_admin(make_user))

    r = client.get(f'/admin/orders/shipping-requests/{sr.id}')

    slugi = [s['slug'] for s in r.get_json()['available_statuses']]
    assert 'wyslane' in slugi


# ---------------------------------------------------------------------------
# Zapis odrzucony — także ze starej karty z nieaktualną listą
# ---------------------------------------------------------------------------

def test_zapis_wyslane_odrzucony_dla_nieoplaconego(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Druga bramka: żądanie może przyjść z pominięciem listy."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=None)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 400, (
        f'Zapis „Wysłane" na nieopłaconym zleceniu musi zostać odrzucony, '
        f'a nie zapisać etykietę i po cichu pominąć nadanie. '
        f'Dostano {r.status_code}: {r.get_json()}'
    )
    assert '30' in r.get_json().get('error', ''), (
        f'Komunikat ma podać brakującą kwotę, tak jak bramka wysyłki: '
        f'{r.get_json()}'
    )


def test_po_odmowie_zlecenie_zostaje_w_swoim_statusie(
        db, client, login, make_user, make_order, bez_powiadomien):
    """To jest sedno buga: etykieta zmieniała się mimo braku nadania."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=None)
    login(_admin(make_user))

    client.put(f'/admin/orders/shipping-requests/{sr.id}', json={'status': 'wyslane'})

    db.session.expire_all()
    assert sr.status == 'spakowane', (
        f'Zlecenie zostało oznaczone jako „{sr.status}" mimo odmowy nadania — '
        f'wypada z kolejki magazynu, a paczka stoi'
    )
    assert sr.shipped_at is None


def test_czesciowa_wplata_nie_wystarcza(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Rozliczenie liczy się z KWOTY, nie z istnienia potwierdzenia."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=20)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 400
    assert '10' in r.get_json().get('error', ''), (
        f'Brakuje 10 zł (30 należne − 20 wpłacone): {r.get_json()}'
    )


# ---------------------------------------------------------------------------
# Regresje — naprawa nie może zablokować legalnych przejść
# ---------------------------------------------------------------------------

def test_oplacone_zlecenie_nadal_przechodzi_recznie(
        db, client, login, make_user, make_order, bez_powiadomien):
    _seed_statuses(db)
    sr, o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=30)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'wyslane'
    assert sr.shipped_at is not None, 'Przejście musi nieść komplet skutków'
    assert o.status == 'wyslane'


def test_zerowy_koszt_nadal_przechodzi_recznie(
        db, client, login, make_user, make_order, bez_powiadomien):
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=0)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'wyslane'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.shipped_at is not None


def test_inne_statusy_nie_sa_ruszane_bramka(
        db, client, login, make_user, make_order, bez_powiadomien):
    """Bramka dotyczy wyłącznie „Wysłane" — nieopłacone zlecenie nadal wolno
    przestawić na etap wcześniejszy."""
    _seed_statuses(db)
    sr, _o = _zlecenie(db, make_user, make_order, koszt_wysylki=30, wplata=None)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'status': 'czeka_na_oplacenie'})

    assert r.status_code == 200, r.get_json()
    db.session.expire_all()
    assert sr.status == 'czeka_na_oplacenie'
