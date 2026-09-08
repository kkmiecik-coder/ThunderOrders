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
