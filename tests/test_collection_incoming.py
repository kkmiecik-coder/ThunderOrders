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


def _pozycja(db, order, product, quantity=1, price='50.00', **kw):
    from modules.orders.models import OrderItem
    oi = OrderItem(order_id=order.id, product_id=product.id, quantity=quantity,
                   price=Decimal(price), total=Decimal(price) * quantity, **kw)
    db.session.add(oi)
    db.session.commit()
    return oi


def test_on_hand_bez_platnosci_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


def test_on_hand_po_zatwierdzeniu_e1_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items, STAGE_ORDERED
    u, p = make_user(), make_product(name='Album NCT')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, price='79.00')
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].name == 'Album NCT'
    assert pozycje[0].market_price == Decimal('79.00')
    assert pozycje[0].stage == STAGE_ORDERED
    assert pozycje[0].is_virtual is True and pozycje[0].id is None


def test_pre_order_oplacony_w_statusie_nowe_wchodzi(db, make_user, make_order, make_product):
    """Pre-order klient płaci od razu po złożeniu — status zostaje 'nowe',
    a zamówienie jest już w produkcji. Kryterium to płatność, nie status."""
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='pre_order')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 1


def test_pre_order_nieoplacony_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='pre_order')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


def test_exclusive_wchodzi_od_oczekujace_bez_platnosci(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items, STAGE_UNPAID
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    _pozycja(db, o, p)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].stage == STAGE_UNPAID
    assert pozycje[0].stage_label == 'Do opłacenia'


def test_exclusive_w_statusie_nowe_jeszcze_nie_wchodzi(db, make_user, make_order, make_product):
    """Exclusive przed domknięciem oferty nie ma przydziału — nie jest niczyje."""
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='exclusive')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_anulowane_i_zwroty_nie_wchodza(db, make_user, make_order, make_product, status):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status=status, order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_pozycja_nieprzydzielona_w_secie_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, is_set_fulfilled=False)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_pozycja_z_zerowa_iloscia_zrealizowana_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=2, fulfilled_quantity=0)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_ilosc_wieksza_niz_jeden_daje_osobne_pozycje(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product(name='PC Jisoo')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=3)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert [x.name for x in pozycje] == ['PC Jisoo (1/3)', 'PC Jisoo (2/3)', 'PC Jisoo (3/3)']
    assert len({x.dom_id for x in pozycje}) == 3


def test_czesciowa_realizacja_liczy_sie_po_fulfilled_quantity(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=5, fulfilled_quantity=2)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 2


def test_pozycja_juz_zmaterializowana_nie_duplikuje_sie(db, make_user, make_order, make_product):
    """Po dostarczeniu auto_add tworzy wiersz w collection_items — pozycja
    wirtualna musi wtedy zniknąć, inaczej klient widzi ją dwa razy."""
    from modules.client.collection_incoming import incoming_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    o = make_order(u, status='dostarczone', order_type='on_hand')
    oi = _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 1          # jeszcze niezmaterializowana
    db.session.add(CollectionItem(user_id=u.id, name=p.name, source='order', order_item_id=oi.id))
    db.session.commit()
    assert incoming_items(u.id) == []


def test_dostarczone_bez_materializacji_nadal_widoczne(db, make_user, make_order, make_product):
    """Gdyby auto_add padł, klient nie może stracić rzeczy, którą fizycznie ma."""
    from modules.client.collection_incoming import incoming_items, STAGE_OWNED
    u, p = make_user(), make_product()
    o = make_order(u, status='dostarczone', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1 and pozycje[0].stage == STAGE_OWNED


def test_cudze_zamowienia_nie_wchodza(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    ja, ktos_inny, p = make_user(), make_user(), make_product()
    o = make_order(ktos_inny, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert incoming_items(ja.id) == []


def test_sortowanie_malejaco_po_dacie_zamowienia(db, make_user, make_order, make_product):
    from datetime import datetime
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    stare = make_order(u, status='oczekujace', order_type='on_hand',
                       created_at=datetime(2026, 1, 1, 10, 0))
    nowe = make_order(u, status='oczekujace', order_type='on_hand',
                      created_at=datetime(2026, 6, 1, 10, 0))
    _pozycja(db, stare, p, price='10.00')
    _pozycja(db, nowe, p, price='20.00')
    _potwierdzenie(db, stare)
    _potwierdzenie(db, nowe)
    assert [x.market_price for x in incoming_items(u.id)] == [Decimal('20.00'), Decimal('10.00')]


def test_pozycja_z_glownym_zdjeciem_zwraca_jego_url(db, make_user, make_order, make_product):
    """image_url ma czytać z batch preloadu (_preload_primary_images), nie z
    Product.primary_image — inaczej wraca N+1 na obrazkach przy renderowaniu listy."""
    from modules.client.collection_incoming import incoming_items
    from modules.products.models import ProductImage
    u, p = make_user(), make_product()
    db.session.add(ProductImage(
        product_id=p.id, filename='okladka.jpg',
        path_original='products/original/okladka.jpg',
        path_compressed='products/compressed/okladka.jpg',
        is_primary=True,
    ))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].image_url == '/static/products/compressed/okladka.jpg'


def test_pozycja_bez_zdjecia_produktu_zwraca_placeholder(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].image_url == '/static/img/placeholders/collection-item.svg'
