"""Wyzerowane pozycje nie zaśmiecają widoków magazynowych.

Domykanie strony sprzedaży nie kasuje produktu, który nie zmieścił się w
komplecie — zeruje mu ilość, cenę i total (utils/offer_closure.py:190).
Wiersz zostaje, bo klient ma w szczegółach zamówienia widzieć, co przepadło.
Widoki magazynowe pokazywały go jednak na równi z żywym towarem („0x Yunho"),
a licznik produktów liczył wiersze zamiast sztuk — obsługa czytała z karty
więcej rzeczy, niż paczka realnie zawiera.
"""

from decimal import Decimal

import pytest


def _pozycja(db, order, nazwa, ilosc, is_set_fulfilled=None):
    """Pozycja custom — bez Product, bo liczy się tylko ilość i nazwa."""
    from modules.orders.models import OrderItem

    cena = Decimal('10.00') if ilosc else Decimal('0.00')
    item = OrderItem(
        order_id=order.id,
        custom_name=nazwa,
        is_custom=True,
        quantity=ilosc,
        price=cena,
        total=cena * ilosc,
        is_set_fulfilled=is_set_fulfilled,
        fulfilled_quantity=0 if is_set_fulfilled is False else None,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_shippable_items_pomija_wyzerowana_pozycje(db, make_user, make_order):
    order = make_order(user=make_user())
    zywa = _pozycja(db, order, 'Mingi', 1)
    _pozycja(db, order, 'Yunho', 0, is_set_fulfilled=False)

    db.session.expire_all()
    assert [i.id for i in order.shippable_items] == [zywa.id]


def test_shippable_items_zachowuje_kolejnosc_sorted_items(db, make_user, make_order):
    """Zamówienie bez zer wygląda dokładnie tak jak dotąd — ta sama kolejność."""
    order = make_order(user=make_user())
    poza_setem = _pozycja(db, order, 'Poza setem', 2, is_set_fulfilled=False)
    zwykla = _pozycja(db, order, 'Zwykła', 1)
    w_secie = _pozycja(db, order, 'W secie', 3, is_set_fulfilled=True)

    db.session.expire_all()
    # sorted_items: None → True → False
    assert [i.id for i in order.shippable_items] == [zwykla.id, w_secie.id, poza_setem.id]


def test_shippable_items_puste_gdy_same_zera(db, make_user, make_order):
    order = make_order(user=make_user())
    _pozycja(db, order, 'Nic nie weszło', 0, is_set_fulfilled=False)

    db.session.expire_all()
    assert order.shippable_items == []


def _zlecenie(db, make_user, make_order, ile_zamowien=1, status='czeka_na_wycene'):
    """Zlecenie wysyłki widoczne na /admin/orders/wms (nie zbiorcze, nie anulowane)."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status=status,
    )
    db.session.add(sr)
    db.session.flush()

    zamowienia = []
    for _ in range(ile_zamowien):
        o = make_order(user=user)
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


def _zaloguj_admina(login, make_user):
    login(make_user(role='admin', email='admin-wms@example.com'))


def test_karta_wms_nie_pokazuje_wyzerowanej_pozycji(
        db, client, login, make_user, make_order):
    sr, (order,) = _zlecenie(db, make_user, make_order)
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert 'Mingi zywy' in html
    assert 'Yunho wyzerowany' not in html


def test_karta_wms_licznik_liczy_tylko_zywe_pozycje(
        db, client, login, make_user, make_order):
    """Dwa wiersze, jeden zerowy → karta ma mowic „1 produkt", nie „2 produkty"."""
    sr, (order,) = _zlecenie(db, make_user, make_order)
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert '1 produkt<' in html
    assert '2 produkty' not in html


def test_zamowienie_z_samymi_zerami_znika_z_karty(
        db, client, login, make_user, make_order):
    sr, (zywe, martwe) = _zlecenie(db, make_user, make_order, ile_zamowien=2)
    _pozycja(db, zywe, 'Towar', 1)
    _pozycja(db, martwe, 'Nic nie weszlo', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert zywe.order_number in html
    assert martwe.order_number not in html


def test_licznik_pokaz_wiecej_pomija_ukryte_zamowienia(
        db, client, login, make_user, make_order):
    """6 zamowien, 2 z samymi zerami → widocznych 4, wiec ukryte jest 1."""
    sr, zamowienia = _zlecenie(db, make_user, make_order, ile_zamowien=6)
    for i, o in enumerate(zamowienia):
        if i < 2:
            _pozycja(db, o, f'Nic nie weszlo {i}', 0, is_set_fulfilled=False)
        else:
            _pozycja(db, o, f'Towar {i}', 1)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert 'data-hidden-count="1"' in html
    assert 'Pokaż więcej (1)' in html


def test_sesja_kompletacji_nie_dostaje_wyzerowanych_pozycji(
        db, make_user, make_order):
    """Pozycja 0x wchodzila do sesji i od razu liczyla sie jako zebrana —
    pakujaca widziala wiersz, ktorego nie ma czego zdjac z polki."""
    from modules.orders.wms import _build_session_data
    from modules.orders.wms_models import WmsSession, WmsSessionOrder

    user = make_user(role='admin', email='magazyn@example.com')
    order = make_order(user=user)
    _pozycja(db, order, 'Mingi zywy', 2)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)

    sesja = WmsSession(session_token='tok-test-1', user_id=user.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionOrder(session_id=sesja.id, order_id=order.id))
    db.session.commit()

    dane = _build_session_data(sesja)

    pozycje = dane['orders'][0]['items']
    assert [p['product_name'] for p in pozycje] == ['Mingi zywy']
    assert dane['orders'][0]['total_quantity'] == 2
    assert dane['orders'][0]['picked_percentage'] == 0


def test_klient_nie_widzi_wyzerowanej_pozycji_na_liscie_wysylek(
        db, client, login, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    # profile_completed: panel klienta przepuszcza tylko konta z uzupełnionym
    # profilem (modules/client/__init__.py:17) — bez tego test mierzyłby redirect.
    user = make_user(email='klient-wysylki@example.com', profile_completed=True)
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status='czeka_na_wycene',
    )
    db.session.add(sr)
    db.session.flush()
    order = make_order(user=user)
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    login(user)

    html = client.get('/client/shipping/requests').get_data(as_text=True)

    assert 'Mingi zywy' in html
    assert 'Yunho wyzerowany' not in html


def test_zamowienie_bez_zadnych_pozycji_zostaje_w_karcie(
        db, client, login, make_user, make_order):
    """Ukrywamy tylko to, co zostalo WYZEROWANE — zamowienie, ktore nigdy nie
    mialo produktow, wyglada w karcie tak jak dotad („0 produktow")."""
    sr, (order,) = _zlecenie(db, make_user, make_order)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert order.order_number in html
