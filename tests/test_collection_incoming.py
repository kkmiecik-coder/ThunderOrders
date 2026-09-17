"""Testy pozycji kolekcji wyliczanych z zamówień (produkty w drodze)."""
from decimal import Decimal

import pytest


def _potwierdzenie(db, order, stage='product', status='approved', amount='100.00'):
    """Potwierdzenie płatności dla etapu — domyślnie zatwierdzone E1."""
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=Decimal(amount), status=status)
    db.session.add(pc)
    db.session.commit()
    return pc


def test_mapowanie_statusow_na_etapy(db, make_user, make_order):
    from modules.client.collection_incoming import (
        stage_for_order, STAGE_ORDERED, STAGE_TRANSIT, STAGE_WAREHOUSE, STAGE_SHIPPED, STAGE_OWNED)
    u = make_user()
    oczekiwane = {
        'nowe': STAGE_ORDERED,
        'oczekujace': STAGE_ORDERED,
        'dostarczone_proxy': STAGE_ORDERED,
        'w_drodze_polska': STAGE_TRANSIT,
        'urzad_celny': STAGE_TRANSIT,
        'dostarczone_gom': STAGE_WAREHOUSE,
        'spakowane': STAGE_WAREHOUSE,
        'wyslane': STAGE_SHIPPED,
        'dostarczone': STAGE_OWNED,
    }
    for status, etap in oczekiwane.items():
        o = make_order(u, status=status, order_type='on_hand')
        _potwierdzenie(db, o)
        assert stage_for_order(o) == etap, f'status {status}'


def test_wyslane_ma_wlasny_etap_nie_magazynowy(db, make_user, make_order):
    """Rozdział spakowane/wyslane: paczka w drodze do klienta to inny komunikat."""
    from modules.client.collection_incoming import stage_for_order, STAGE_WAREHOUSE, STAGE_SHIPPED
    u = make_user()
    spakowane = make_order(u, status='spakowane', order_type='on_hand')
    wyslane = make_order(u, status='wyslane', order_type='on_hand')
    _potwierdzenie(db, spakowane)
    _potwierdzenie(db, wyslane)
    assert stage_for_order(spakowane) == STAGE_WAREHOUSE
    assert stage_for_order(wyslane) == STAGE_SHIPPED


def test_exclusive_bez_zatwierdzonego_e1_jest_do_oplacenia(db, make_user, make_order):
    from modules.client.collection_incoming import stage_for_order, STAGE_UNPAID
    u = make_user()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    assert stage_for_order(o) == STAGE_UNPAID


def test_exclusive_po_zatwierdzeniu_e1_przestaje_byc_do_oplacenia(db, make_user, make_order):
    from modules.client.collection_incoming import stage_for_order, STAGE_ORDERED
    u = make_user()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    _potwierdzenie(db, o)
    assert stage_for_order(o) == STAGE_ORDERED


def test_exclusive_w_transporcie_nie_wraca_do_do_oplacenia(db, make_user, make_order):
    """Nieopłacone E1 przy zamówieniu, które już jedzie, to zaległość admina —
    klientowi nie mówimy 'Do opłacenia' o paczce w drodze."""
    from modules.client.collection_incoming import stage_for_order, STAGE_TRANSIT
    u = make_user()
    o = make_order(u, status='w_drodze_polska', order_type='exclusive')
    assert stage_for_order(o) == STAGE_TRANSIT


def test_nieznany_status_ladnie_degraduje_do_zamowione(db, make_user, make_order):
    """Admin może dodać status z panelu ustawień — kolekcja nie może się wywalić."""
    from modules.client.collection_incoming import stage_for_order, STAGE_ORDERED
    from modules.orders.models import OrderStatus
    db.session.add(OrderStatus(slug='nowy_dziwny_status', name='Dziwny', sort_order=99, is_active=True))
    db.session.commit()
    u = make_user()
    o = make_order(u, status='nowy_dziwny_status', order_type='on_hand')
    assert stage_for_order(o) == STAGE_ORDERED


def test_etykiety_istnieja_dla_kazdego_etapu():
    from modules.client.collection_incoming import STAGE_LABELS, STAGE_BY_STATUS, STAGE_UNPAID
    etapy = set(STAGE_BY_STATUS.values()) | {STAGE_UNPAID}
    assert etapy <= set(STAGE_LABELS)
    assert STAGE_LABELS[STAGE_UNPAID] == 'Do opłacenia'
