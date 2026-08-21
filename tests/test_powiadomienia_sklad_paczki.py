"""Powiadomienia o składzie paczki zbiorczej (P1 i P3 z audytu).

P1 — dopięcie kolejnego zlecenia wysyłało mail o konsolidacji PONOWNIE
wszystkim dotychczasowym uczestnikom: `_powiadom_o_konsolidacji` stało poza
if/else rozróżniającym „utwórz" od „dopnij", a `notify_shipment_consolidated`
iteruje po wszystkich uczestnikach bez znacznika „nowo dopięty". Paczka
budowana etapami przez kilka dni oznaczała tyle maili, ile było dopięć.

P3 — rozwiązanie paczki i zmiana zlecenia wiodącego nie wysyłały NIC. Klient
zostawał z jedyną, nieaktualną wersją prawdy w skrzynce: „Twoje zamówienia
jadą w paczce zbiorczej wysłanej na adres X" — a zmiana lidera realnie
nadpisuje adres odbioru (`_kopiuj_adres`).

Wspólny mianownik: klient ma w skrzynce obraz swojej paczki, który albo się
powtarza, albo przestał być prawdziwy.
"""

import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


def _admin(make_user):
    return make_user(role='admin', email='admin-sklad@example.com',
                     profile_completed=True)


@pytest.fixture
def powiadomieni(monkeypatch):
    """Adresaci maili o składzie paczki — per typ zdarzenia."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    dane = {'scalenie': [], 'rozwiazanie': [], 'zmiana_adresu': []}

    def _scalenie(sr, nowi=None):
        uczestnicy = nowi if nowi is not None else [
            u['source_request'] for u in sr.consolidation_participants]
        dane['scalenie'].extend(z.request_number for z in uczestnicy)

    monkeypatch.setattr(EmailManager, 'notify_shipment_consolidated',
                        staticmethod(_scalenie))
    monkeypatch.setattr(PushManager, 'notify_shipment_consolidated',
                        staticmethod(lambda *a, **kw: None))
    # Wyjście z paczki dostaje listę zleceń w argumencie (relacje są już
    # zerwane), a zmiana adresu czyta uczestników z samej paczki.
    def _rozwiazanie(sr, zrodla=None):
        dane['rozwiazanie'].extend(z.request_number for z in (zrodla or []))

    def _zmiana_adresu(sr, zrodla=None):
        dane['zmiana_adresu'].extend(
            u['source_request'].request_number for u in sr.consolidation_participants)

    for nazwa, podmiana in (('notify_consolidation_dissolved', _rozwiazanie),
                            ('notify_consolidation_address_changed', _zmiana_adresu)):
        if hasattr(EmailManager, nazwa):
            monkeypatch.setattr(EmailManager, nazwa, staticmethod(podmiana))
        if hasattr(PushManager, nazwa):
            monkeypatch.setattr(PushManager, nazwa, staticmethod(lambda *a, **kw: None))
    return dane


# ---------------------------------------------------------------------------
# P1 — dopięcie nie powiadamia ponownie dotychczasowych uczestników
# ---------------------------------------------------------------------------

def test_dopiecie_powiadamia_tylko_nowo_dopietych(
        db, client, login, make_user, make_order, powiadomieni):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_c, _oc = _sr(db, make_user(), make_order)
    login(_admin(make_user))
    powiadomieni['scalenie'].clear()

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_c.id], 'target_id': zbiorcze.id,
    })

    assert r.status_code == 200, r.get_json()
    assert powiadomieni['scalenie'] == [sr_c.request_number], (
        f'Dotychczasowi uczestnicy dostali mail o konsolidacji drugi raz; '
        f'powiadomiono: {powiadomieni["scalenie"]}'
    )


def test_utworzenie_paczki_powiadamia_wszystkich(
        db, client, login, make_user, make_order, powiadomieni):
    """Regresja: przy tworzeniu paczki mail idzie do każdego uczestnika."""
    _seed_sr_statuses(db)
    sr_a, _oa = _sr(db, make_user(), make_order)
    sr_b, _ob = _sr(db, make_user(), make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })

    assert r.status_code == 200, r.get_json()
    assert set(powiadomieni['scalenie']) == {sr_a.request_number, sr_b.request_number}


# ---------------------------------------------------------------------------
# P3 — rozwiązanie paczki i zmiana adresata muszą dotrzeć do klienta
# ---------------------------------------------------------------------------

def test_rozwiazanie_paczki_powiadamia_uczestnikow(
        db, client, login, make_user, make_order, powiadomieni):
    """Klient ma w skrzynce „jedziesz w paczce zbiorczej" — po rozwiązaniu
    ta informacja przestaje być prawdziwa."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.post(
        f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/dissolve',
        json={})

    assert r.status_code == 200, r.get_json()
    assert set(powiadomieni['rozwiazanie']) == {
        sr_a.request_number, sr_b.request_number}, (
        f'Uczestnicy nie wiedzą, że paczka przestała istnieć; '
        f'powiadomiono: {powiadomieni["rozwiazanie"]}'
    )


def test_zmiana_wiodacego_powiadamia_o_nowym_adresie(
        db, client, login, make_user, make_order, powiadomieni):
    """Zmiana lidera nadpisuje adres odbioru — klient dostał wcześniej mail
    ze STARYM adresem i bez powiadomienia zostaje z nieprawdą."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.shipping_city = 'Gdańsk'
    db.session.commit()
    login(_admin(make_user))

    r = client.post(
        f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/lead',
        json={'lead_request_id': sr_b.id})

    assert r.status_code == 200, r.get_json()
    assert set(powiadomieni['zmiana_adresu']) == {
        sr_a.request_number, sr_b.request_number}, (
        f'Uczestnicy nie wiedzą, że paczka jedzie gdzie indziej; '
        f'powiadomiono: {powiadomieni["zmiana_adresu"]}'
    )


def test_wypiecie_uczestnika_powiadamia_wypietego(
        db, client, login, make_user, make_order, powiadomieni):
    """Wypięty klient wraca do samodzielnej wysyłki — jego wcześniejszy mail
    o paczce zbiorczej przestaje obowiązywać."""
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3)
    wypiety = zrodla[2]
    login(_admin(make_user))

    r = client.post(
        f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/detach',
        json={'source_id': wypiety.id})

    assert r.status_code == 200, r.get_json()
    assert wypiety.request_number in powiadomieni['rozwiazanie'], (
        f'Wypięty uczestnik nie wie, że jedzie już osobno; '
        f'powiadomiono: {powiadomieni["rozwiazanie"]}'
    )


# ---------------------------------------------------------------------------
# P2 — spakowanie w WMS powiadamia tak samo jak ręczna zmiana statusu
#
# `update_sr_after_packing` nie wysyłało nic: jedyną bramką było
# `if send_email and photo`, a front bez zdjęcia w ogóle nie wysyła flagi
# (przełącznik `notify_packing_photo` jest na produkcji wyłączony).
# Tymczasem ręczne ustawienie tego samego statusu przez PUT mail wysyłało —
# to samo przejście raz powiadamiało, raz nie.
# ---------------------------------------------------------------------------

@pytest.fixture
def maile_o_statusie(monkeypatch):
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    zebrane = []
    monkeypatch.setattr(EmailManager, 'notify_shipping_status_change',
                        staticmethod(lambda sr, old: zebrane.append((sr.id, old))))
    monkeypatch.setattr(PushManager, 'notify_shipping_status_change',
                        staticmethod(lambda *a, **kw: None))
    return zebrane


def _zlecenie_do_pakowania(db, make_user, make_order):
    from modules.orders.models import (
        OrderStatus, ShippingRequest, ShippingRequestOrder, ShippingRequestStatus)
    for slug, name in [('spakowane', 'Spakowane'), ('dostarczone_gom', 'Dostarczone GOM')]:
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='oplacone')
    db.session.add(sr)
    db.session.flush()
    o = make_order(user=user, status='spakowane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr, o


def test_spakowanie_powiadamia_klienta(db, make_user, make_order, maile_o_statusie):
    from modules.orders.wms_packing import update_sr_after_packing

    _seed_sr_statuses(db)
    sr, zamowienie = _zlecenie_do_pakowania(db, make_user, make_order)

    update_sr_after_packing(zamowienie)

    assert maile_o_statusie == [(sr.id, 'oplacone')], (
        f'Klient nie dowiaduje się, że paczka jest spakowana; '
        f'wysłano: {maile_o_statusie}'
    )


def test_spakowanie_bez_zmiany_statusu_nie_powiadamia(
        db, make_user, make_order, maile_o_statusie):
    """Regresja: powtórne wywołanie na już spakowanym zleceniu milczy."""
    from modules.orders.wms_packing import update_sr_after_packing

    _seed_sr_statuses(db)
    sr, zamowienie = _zlecenie_do_pakowania(db, make_user, make_order)
    sr.status = 'spakowane'
    db.session.commit()

    update_sr_after_packing(zamowienie)

    assert maile_o_statusie == []
