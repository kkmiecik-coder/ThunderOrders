"""Testy podziału partii Polska — wydzielenie pozycji do nowej partii.

Projekt: docs/superpowers/specs/2026-09-09-podzial-partii-polska-design.md
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def _zbuduj_partie(db, produkty_i_ilosci, numer='PL/S9', created_at=None,
                   shipping=Decimal('0'), customs=Decimal('0'), status='zamowione',
                   order_type='polska', stawka_za_szt=None):
    """Partia Polska z własnym rodzicem: ProxyOrder + ProxyOrderItem + PolandOrder + PolandOrderItem.

    produkty_i_ilosci: lista (product_id, ilość).
    stawka_za_szt: gdy podana, każda pozycja dostaje shipping_cost = stawka * ilość
                   oraz obie stawki za sztukę (album/incl) równe tej stawce.
    Zwraca (partia, [pozycje]).
    """
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    proxy = ProxyOrder(order_number=f'PRX/{numer.replace("/", "-")}', order_type=order_type)
    db.session.add(proxy)
    db.session.flush()

    partia = PolandOrder(order_number=numer, proxy_order_id=proxy.id, status=status,
                         shipping_cost=shipping, customs_cost=customs)
    if created_at is not None:
        partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()

    pozycje = []
    for product_id, ilosc in produkty_i_ilosci:
        proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id,
                                    quantity=ilosc, unit_price=Decimal('25'),
                                    total_price=Decimal('25') * ilosc)
        db.session.add(proxy_item)
        db.session.flush()
        pozycja = PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                  product_id=product_id, quantity=ilosc)
        if stawka_za_szt is not None:
            pozycja.shipping_cost = Decimal(str(stawka_za_szt)) * ilosc
            pozycja.shipping_cost_album_per_unit = Decimal(str(stawka_za_szt))
            pozycja.shipping_cost_incl_per_unit = Decimal(str(stawka_za_szt))
        db.session.add(pozycja)
        db.session.flush()
        pozycje.append(pozycja)

    db.session.commit()
    return partia, pozycje


def _zamowienie_klienta(db, make_user, make_order, product_id, ilosc, created_at, cena=130):
    """Zamówienie klienta z jedną pozycją (exclusive — offer_page_id ustawione)."""
    from modules.orders.models import OrderItem

    uzytkownik = make_user()
    zamowienie = make_order(uzytkownik, offer_page_id=1, created_at=created_at)
    db.session.add(OrderItem(order_id=zamowienie.id, product_id=product_id, quantity=ilosc,
                             price=Decimal(str(cena)), total=Decimal(str(cena)) * ilosc))
    db.session.commit()
    return zamowienie


def test_przelicz_sumy_partii_sumuje_zakup_wysylke_i_clo(db, make_product):
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem
    from modules.products.routes import _przelicz_sumy_partii

    produkt = make_product(purchase_price_pln=Decimal('25.00'))

    proxy = ProxyOrder(order_number='PRX/S1', order_type='polska')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=produkt.id,
                                quantity=4, unit_price=Decimal('25'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(order_number='PL/S1', proxy_order_id=proxy.id, status='zamowione',
                         shipping_cost=Decimal('30.00'), customs_cost=Decimal('12.00'))
    db.session.add(partia)
    db.session.flush()
    db.session.add(PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                   product_id=produkt.id, quantity=4))
    db.session.commit()

    wartosc_produktow = _przelicz_sumy_partii(partia)

    assert wartosc_produktow == Decimal('100.00')
    assert partia.total_amount == Decimal('142.00')


def test_podglad_podzialu_zwraca_pozycje_i_kwoty(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-split@example.com')
    login(admin)

    p1 = make_product(name='Album A', purchase_price_pln=Decimal('25.00'))
    p2 = make_product(name='Poca B', purchase_price_pln=Decimal('10.00'))
    partia, _ = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S2',
                               shipping=Decimal('80.00'), customs=Decimal('20.00'))

    odpowiedz = client.get(f'/admin/products/api/poland-orders/{partia.id}/split-preview')

    assert odpowiedz.status_code == 200
    dane = odpowiedz.get_json()
    assert dane['success'] is True
    assert dane['numer'] == 'PL/S2'
    assert dane['shipping_cost'] == 80.0
    assert dane['customs_cost'] == 20.0
    assert [p['nazwa'] for p in dane['pozycje']] == ['Album A', 'Poca B']
    assert [p['ilosc'] for p in dane['pozycje']] == [4, 6]
    assert [p['wartosc_zakupu'] for p in dane['pozycje']] == [100.0, 60.0]


def test_podzial_przenosi_zaznaczone_pozycje(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-split2@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    p3 = make_product(purchase_price_pln=Decimal('5.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6), (p3.id, 2)], numer='PL/S3',
                                     shipping=Decimal('100.00'), customs=Decimal('40.00'))
    id_partii = partia.id
    id_do_wydzielenia = [pozycje[1].id, pozycje[2].id]

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': id_do_wydzielenia,
        'shipping_cost_stara': '60.00',
        'shipping_cost_nowa': '40.00',
        'customs_cost_stara': '25.00',
        'customs_cost_nowa': '15.00',
    })

    assert odpowiedz.status_code == 200
    dane = odpowiedz.get_json()
    assert dane['success'] is True

    stara = db.session.get(PolandOrder, id_partii)
    nowa = db.session.get(PolandOrder, dane['nowa_partia_id'])

    assert {i.id for i in stara.items} == {pozycje[0].id}
    assert {i.id for i in nowa.items} == set(id_do_wydzielenia)
    assert nowa.order_number == dane['nowy_numer']
    assert nowa.order_number.startswith('PL/')
    assert nowa.proxy_order_id != stara.proxy_order_id


def test_podzial_dziedziczy_status_date_i_terminy(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-split3@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    data_zalozenia = datetime(2026, 7, 11, 18, 55, 0)
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S4',
                                     created_at=data_zalozenia, status='urzad_celny')
    partia.payment_deadline = datetime(2026, 7, 20, 23, 59, 0)
    partia.customs_payment_deadline = datetime(2026, 7, 25, 23, 59, 0)
    partia.tracking_number = 'ABC123'
    partia.notes = 'notatka oryginalu'
    db.session.commit()

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '0', 'shipping_cost_nowa': '0',
        'customs_cost_stara': '0', 'customs_cost_nowa': '0',
    })

    nowa = db.session.get(PolandOrder, odpowiedz.get_json()['nowa_partia_id'])
    assert nowa.status == 'urzad_celny'
    assert nowa.created_at == data_zalozenia
    assert nowa.payment_deadline == datetime(2026, 7, 20, 23, 59, 0)
    assert nowa.customs_payment_deadline == datetime(2026, 7, 25, 23, 59, 0)
    assert not nowa.tracking_number
    assert not nowa.notes
    assert nowa.is_archived is False


def test_podzial_zapisuje_kwoty_i_przelicza_sumy(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-split4@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S5',
                                     shipping=Decimal('100.00'), customs=Decimal('40.00'))
    id_partii = partia.id

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '70.00',
        'shipping_cost_nowa': '30.00',
        'customs_cost_stara': '25.00',
        'customs_cost_nowa': '15.00',
    })

    stara = db.session.get(PolandOrder, id_partii)
    nowa = db.session.get(PolandOrder, odpowiedz.get_json()['nowa_partia_id'])

    assert stara.shipping_cost == Decimal('70.00')
    assert nowa.shipping_cost == Decimal('30.00')
    assert stara.customs_cost == Decimal('25.00')
    assert nowa.customs_cost == Decimal('15.00')
    # stara: 4 x 25 = 100 zakupu + 70 + 25;  nowa: 6 x 10 = 60 zakupu + 30 + 15
    assert stara.total_amount == Decimal('195.00')
    assert nowa.total_amount == Decimal('105.00')


@pytest.mark.parametrize('ladunek, kod, fragment', [
    ({'item_ids': []}, 400, 'przynajmniej jedną pozycję'),
    ({'item_ids': 'wszystkie'}, 400, 'Nieprawidłowa lista pozycji'),
])
def test_podzial_odrzuca_bledne_zaznaczenie(db, client, login, make_user, make_product,
                                            ladunek, kod, fragment):
    admin = make_user(role='admin', email=f'admin-w-{kod}-{fragment[:5]}@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, _ = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W1')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json=ladunek)

    assert odpowiedz.status_code == kod
    assert fragment in odpowiedz.get_json()['error']


def test_podzial_nie_pozwala_wydzielic_wszystkiego(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-w2@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W2')
    id_partii = partia.id

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': [p.id for p in pozycje],
    })

    assert odpowiedz.status_code == 400
    assert 'musi zostać przynajmniej jedna pozycja' in odpowiedz.get_json()['error']
    assert len(list(db.session.get(PolandOrder, id_partii).items)) == 2
    assert PolandOrder.query.count() == 1


def test_podzial_odrzuca_obca_pozycje(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-w3@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W3')
    obca, obce_pozycje = _zbuduj_partie(db, [(p1.id, 1)], numer='PL/W3B')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id, obce_pozycje[0].id],
    })

    assert odpowiedz.status_code == 409
    assert 'nie są już w tej partii' in odpowiedz.get_json()['error']
    assert PolandOrder.query.count() == 2


def test_podzial_odrzuca_partie_anulowana(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-w4@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W4',
                                     status='anulowane')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
    })

    assert odpowiedz.status_code == 400
    assert 'anulowanej partii' in odpowiedz.get_json()['error']


def test_podzial_odrzuca_ujemna_kwote(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-w5@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W5')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
        'shipping_cost_nowa': '-5',
    })

    assert odpowiedz.status_code == 400
    assert 'Nieprawidłowa kwota' in odpowiedz.get_json()['error']


@pytest.mark.parametrize('rola', ['mod', 'client'])
def test_podzial_tylko_dla_admina(db, client, login, make_user, make_product, rola):
    from modules.products.models import PolandOrder

    uzytkownik = make_user(role=rola, email=f'{rola}-split@example.com')
    login(uzytkownik)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer=f'PL/W6{rola}')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
    })

    assert odpowiedz.status_code in (302, 403)
    assert PolandOrder.query.count() == 1
