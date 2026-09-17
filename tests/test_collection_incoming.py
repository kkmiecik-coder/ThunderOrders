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


def test_bez_zdjecia_glownego_wygrywa_najmniejsze_id_nie_sort_order(db, make_user, make_order, make_product):
    """Fallback Product.primary_image to images.first() bez order_by — czyli
    najmniejsze id. sort_order to numer slotu z uploadu, nie kolejność
    wstawienia, więc nie może decydować o wyborze zdjęcia."""
    from modules.client.collection_incoming import incoming_items
    from modules.products.models import ProductImage
    u, p = make_user(), make_product()
    pierwsze = ProductImage(
        product_id=p.id, filename='pierwsze.jpg',
        path_original='products/original/pierwsze.jpg',
        path_compressed='products/compressed/pierwsze.jpg',
        is_primary=False, sort_order=5,
    )
    db.session.add(pierwsze)
    db.session.commit()
    db.session.add(ProductImage(
        product_id=p.id, filename='drugie.jpg',
        path_original='products/original/drugie.jpg',
        path_compressed='products/compressed/drugie.jpg',
        is_primary=False, sort_order=1,
    ))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].image_url == '/static/products/compressed/pierwsze.jpg'


def test_pozycja_bez_zdjecia_produktu_zwraca_placeholder(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].image_url == '/static/img/placeholders/collection-item.svg'


def test_zmaterializowana_pozycja_ma_etap_w_kolekcji(db, make_user):
    from modules.client.models import CollectionItem
    from modules.client.collection_incoming import STAGE_OWNED
    u = make_user()
    item = CollectionItem(user_id=u.id, name='PC', source='manual')
    db.session.add(item)
    db.session.commit()
    assert item.is_virtual is False
    assert item.stage == STAGE_OWNED
    assert item.stage_label == 'W kolekcji'
    assert item.dom_id == f'ci-{item.id}'


def test_parytet_bez_include_incoming(db, make_user, make_order, make_product):
    """Mobile API woła list_items bez nowych parametrów — nic nie może się zmienić."""
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id)
    assert [x.name for x in strona.items] == ['Reczna']
    assert strona.total == 1


def test_include_incoming_scala_obie_listy(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Album')
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, include_incoming=True)
    assert sorted(x.name for x in strona.items) == ['Album', 'Reczna']
    assert strona.total == 2


def test_filtr_w_drodze_i_w_kolekcji(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items, FILTER_INCOMING, FILTER_OWNED
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Album')
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    w_drodze = list_items(u.id, include_incoming=True, stage_filter=FILTER_INCOMING)
    assert [x.name for x in w_drodze.items] == ['Album']

    posiadane = list_items(u.id, include_incoming=True, stage_filter=FILTER_OWNED)
    assert [x.name for x in posiadane.items] == ['Reczna']


def test_szukanie_obejmuje_pozycje_w_drodze(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Album NCT')
    db.session.add(CollectionItem(user_id=u.id, name='Photocard Jisoo', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, search='nct', include_incoming=True)
    assert [x.name for x in strona.items] == ['Album NCT']


def test_sortowanie_mieszanej_listy_po_nazwie(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Bravo')
    db.session.add(CollectionItem(user_id=u.id, name='Alfa', source='manual'))
    db.session.add(CollectionItem(user_id=u.id, name='Czarli', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, sort='name_asc', include_incoming=True)
    assert [x.name for x in strona.items] == ['Alfa', 'Bravo', 'Czarli']


def test_sortowanie_po_cenie_wrzuca_braki_na_koniec(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Drogi')
    db.session.add(CollectionItem(user_id=u.id, name='Bez ceny', source='manual'))
    db.session.add(CollectionItem(user_id=u.id, name='Tania', market_price=Decimal('10.00')))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, price='999.00')
    _potwierdzenie(db, o)

    strona = list_items(u.id, sort='price_desc', include_incoming=True)
    assert [x.name for x in strona.items][:2] == ['Drogi', 'Tania']
    assert strona.items[-1].name == 'Bez ceny'


def test_paginacja_mieszanej_listy(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    for i in range(3):
        db.session.add(CollectionItem(user_id=u.id, name=f'Reczna {i}', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=4)
    _potwierdzenie(db, o)

    strona1 = list_items(u.id, page=1, per_page=3, include_incoming=True)
    assert len(strona1.items) == 3
    assert strona1.total == 7 and strona1.pages == 3
    assert strona1.has_prev is False and strona1.has_next is True
    assert strona1.next_num == 2

    strona3 = list_items(u.id, page=3, per_page=3, include_incoming=True)
    assert len(strona3.items) == 1
    assert strona3.has_next is False and strona3.prev_num == 2
    assert list(strona3.iter_pages()) == [1, 2, 3]


def test_strona_poza_zakresem_daje_pusta_liste(db, make_user):
    from modules.client.collection_service import list_items
    u = make_user()
    strona = list_items(u.id, page=99, include_incoming=True)
    assert strona.items == [] and strona.total == 0


def test_strona_kolekcji_pokazuje_pozycje_w_drodze(db, client, login, make_user,
                                                    make_order, make_product):
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='w_drodze_polska', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    resp = client.get('/client/collection')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Album NCT' in html


def test_filtr_w_kolekcji_ukrywa_pozycje_w_drodze(db, client, login, make_user,
                                                   make_order, make_product):
    from modules.client.models import CollectionItem
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    db.session.add(CollectionItem(user_id=u.id, name='Photocard Jisoo', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection?filter=owned').get_data(as_text=True)
    assert 'Photocard Jisoo' in html
    assert 'Album NCT' not in html


def test_nieznany_filtr_nie_wywala_strony(db, client, login, make_user):
    u = make_user(profile_completed=True)
    login(u)
    assert client.get('/client/collection?filter=cokolwiek').status_code == 200


def _total_incoming_z_odpowiedzi(app, url, client):
    """Woła trasę i wyciąga total_incoming z kontekstu szablonu (sygnał Flask —
    badge etapu trafia dopiero w Task 6, więc wartości nie ma jeszcze w HTML)."""
    from flask import template_rendered

    captured = []

    def _on_render(sender, template, context, **extra):
        captured.append(context.get('total_incoming'))

    with template_rendered.connected_to(_on_render, app):
        resp = client.get(url)
        assert resp.status_code == 200
    assert len(captured) == 1
    return captured[0]


def test_total_incoming_niezalezny_od_filtra_i_wyszukiwania(db, client, login, make_user,
                                                              make_order, make_product,
                                                              app):
    """Licznik pozycji w drodze ma znaczyć ZAWSZE 'wszystkie pozycje w drodze
    użytkownika' — niezależnie od aktywnego ?filter= i ?search=. Bez tego testu
    regresja w znaczeniu licznika (np. respektowanie filtra) przejdzie niezauważona."""
    from modules.client.models import CollectionItem

    u = make_user(profile_completed=True)
    p1 = make_product(name='Album NCT')
    p2 = make_product(name='Photocard BTS')
    db.session.add(CollectionItem(user_id=u.id, name='Reczna pozycja', source='manual'))
    db.session.commit()

    o1 = make_order(u, status='w_drodze_polska', order_type='on_hand')
    _pozycja(db, o1, p1)
    _potwierdzenie(db, o1)

    o2 = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o2, p2)
    _potwierdzenie(db, o2)

    login(u)

    wartosci = {
        'all': _total_incoming_z_odpowiedzi(app, '/client/collection?filter=all', client),
        'owned': _total_incoming_z_odpowiedzi(app, '/client/collection?filter=owned', client),
        'incoming': _total_incoming_z_odpowiedzi(app, '/client/collection?filter=incoming', client),
        'search_dopasowujace': _total_incoming_z_odpowiedzi(
            app, '/client/collection?search=nct', client),
        'search_bez_wynikow': _total_incoming_z_odpowiedzi(
            app, '/client/collection?search=cosinnego', client),
    }

    assert wartosci['all'] == 2
    assert set(wartosci.values()) == {2}


def test_badge_etapu_widoczny_na_stronie(db, client, login, make_user, make_order, make_product):
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='w_drodze_polska', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection').get_data(as_text=True)
    assert 'W drodze do Polski' in html
    assert 'collection-badge--transit' in html


def test_pozycja_wirtualna_bez_przyciskow_edycji(db, client, login, make_user,
                                                  make_order, make_product):
    # Wirtualna pozycja nie ma wiersza w bazie — edycja i usuwanie nie mają czego dotknąć.
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection?filter=incoming').get_data(as_text=True)
    assert 'openDeleteModal' not in html
    assert 'btn-order-link' in html
