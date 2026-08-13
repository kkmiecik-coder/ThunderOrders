"""Surowy slug kuriera nie ma prawa wyjść poza bazę.

Kanoniczna mapa slug → nazwa to `wms_utils.COURIER_NAMES`; obie właściwości
`courier_display_name` (ShippingRequest, OrderShipment) już z niej czytają. Mimo to
żyły jeszcze kopie literału i miejsca renderujące sam slug — wszystkie bez klucza
'pocztex', mimo że ten kurier jest wybieralny w WMS. 'pocztex' jest więc w tych
testach probierzem: dla każdego innego sluga kopia dawała ten sam wynik, co mapa
kanoniczna, i rozjazd nie był widoczny.
"""
from datetime import timedelta

import pytest


def _zlecenie_z_zamowieniem(db, user, make_order, numer, courier='pocztex'):
    """Zlecenie wysyłki z jednym zamówieniem — tak, jak widzą je obie strony detalu."""
    from modules.orders.models import (
        ShippingRequest, ShippingRequestOrder, get_local_now)

    sr = ShippingRequest(
        request_number=numer, user_id=user.id, status='wyslane',
        courier=courier, tracking_number=f'TRK-{numer[-6:]}',
        shipped_at=get_local_now() - timedelta(days=1))
    db.session.add(sr)
    db.session.commit()

    order = make_order(user)
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()
    return sr, order


# ---------- Kopia mapy w mailu o zmianie statusu (jedzie do KLIENTA) ----------

def test_mail_o_zmianie_statusu_tlumaczy_pocztex(app, db, make_user, monkeypatch):
    """`notify_shipping_status_change` miała własną kopię mapy bez klucza 'pocztex',
    więc w mailu do klienta lądował surowy slug zamiast „Pocztex"."""
    from modules.orders.models import ShippingRequest
    from utils import email_sender
    from utils.email_manager import EmailManager

    user = make_user(email='kurier-mail@example.com')
    sr = ShippingRequest(request_number='WYS/000700', user_id=user.id,
                         status='wyslane', courier='pocztex')
    db.session.add(sr)
    db.session.commit()

    przechwycone = {}
    monkeypatch.setattr(email_sender, 'send_shipping_status_change_email',
                        lambda **kw: przechwycone.update(kw))

    with app.test_request_context():
        EmailManager.notify_shipping_status_change(sr, 'spakowane')

    assert przechwycone.get('courier_name') == 'Pocztex', (
        f'mail dostał {przechwycone.get("courier_name")!r} zamiast czytelnej nazwy '
        f'(cała paczka kwargów: {przechwycone})')


@pytest.mark.parametrize('courier', [None, ''], ids=['courier=None', "courier=''"])
def test_mail_o_zmianie_statusu_bez_kuriera_nie_wysyla_pustej_nazwy(
        app, db, make_user, monkeypatch, courier):
    """Brak kuriera ma dać None (szablon pomija wtedy pole), nie pusty łańcuch.

    `courier_display_name` to `COURIER_NAMES.get(self.courier, self.courier)`:
    dla `courier=None` to zwraca None niezależnie od warunku (None nie ma jak
    trafić do mapy jako pasujący klucz z wartością inną niż None) — ten wariant
    testu przechodzi nawet bez `if shipping_request.courier` w
    `utils/email_manager.py`. Warunek jest nośny wyłącznie dla `courier=''`:
    bez niego `courier_display_name` zwróciłaby `''` (fallback `.get` na
    brakujący klucz), a asercja poniżej by tego nie przepuściła. Stąd oba
    warianty w jednym teście — pierwszy pilnuje kontraktu, drugi pilnuje
    warunku."""
    from modules.orders.models import ShippingRequest
    from utils import email_sender
    from utils.email_manager import EmailManager

    user = make_user(email=f'kurier-mail-brak-{courier or "puste"}@example.com')
    sr = ShippingRequest(request_number='WYS/000701', user_id=user.id,
                         status='spakowane', courier=courier)
    db.session.add(sr)
    db.session.commit()

    przechwycone = {}
    monkeypatch.setattr(email_sender, 'send_shipping_status_change_email',
                        lambda **kw: przechwycone.update(kw))

    with app.test_request_context():
        EmailManager.notify_shipping_status_change(sr, 'oplacone')

    assert przechwycone.get('courier_name', 'BRAK KLUCZA') is None


# ---------- Kopia mapy w etykietach wykresu „Kurierzy" ----------

def test_wykres_kurierow_tlumaczy_pocztex(app, db, client, login, make_user, make_order):
    """Wykres kołowy „Kurierzy" w statystykach miał trzecią kopię mapy — również bez
    'pocztex', więc jeden wycinek podpisywał się surowym slugiem obok czytelnych nazw."""
    from modules.orders.models import OrderShipment

    admin = make_user(role='admin', email='admin-kurier@example.com',
                      profile_completed=True)
    klient = make_user(email='klient-kurier@example.com')
    order = make_order(klient)
    db.session.add(OrderShipment(order_id=order.id, tracking_number='POCZTEX-STAT',
                                 courier='pocztex'))
    db.session.commit()

    login(admin)
    dane = client.get('/admin/statistics/api/shipping').get_json()

    etykiety = dane['charts']['pie_couriers']['labels']
    assert 'Pocztex' in etykiety
    assert 'pocztex' not in etykiety


# ---------- Surowy slug renderowany w szablonach detalu zamówienia ----------

def test_klient_widzi_czytelna_nazwe_kuriera_w_detalu_zamowienia(
        app, db, client, login, make_user, make_order):
    """templates/client/orders/detail.html renderowało `{{ sr.courier }}`, czyli
    surowy slug — mimo że `courier_display_name` jest już użyte obok, w
    templates/client/shipping/confirm_delivery.html."""
    user = make_user(profile_completed=True)
    sr, order = _zlecenie_z_zamowieniem(db, user, make_order, 'WYS/000710')
    login(user)

    tresc = client.get(f'/client/orders/{order.id}').get_data(as_text=True)

    assert 'sr-courier-badge">Pocztex<' in tresc
    assert 'sr-courier-badge">pocztex<' not in tresc


def test_admin_widzi_czytelna_nazwe_kuriera_w_detalu_zamowienia(
        app, db, client, login, make_user, make_order):
    """Bliźniak powyższego: templates/admin/orders/detail.html renderował ten sam
    surowy slug w tej samej sekcji „Śledzenie przesyłki"."""
    admin = make_user(role='admin', email='admin-detal@example.com',
                      profile_completed=True)
    klient = make_user(email='klient-detal@example.com')
    sr, order = _zlecenie_z_zamowieniem(db, klient, make_order, 'WYS/000711')
    login(admin)

    tresc = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)

    assert 'sr-courier-badge">Pocztex<' in tresc
    assert 'sr-courier-badge">pocztex<' not in tresc
