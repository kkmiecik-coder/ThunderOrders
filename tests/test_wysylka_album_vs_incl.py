"""Testy podziału Wysyłki KR na cały album i samo incl.

Model: przy pozycji zamówienia klienta siedzi `incl_only_quantity` (ile sztuk
klient bierze jako samo incl), a przy pozycji partii do Polski dwie stawki za
sztukę. Podział FIFO bez zmian — zmienia się tylko cena sztuki, zależna od typu.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def test_domyslne_wartosci_nowych_kolumn(db, make_user, make_order, make_product):
    """Bez jawnego ustawienia: pozycja klienta ma 0 incl, partia nie ma stawek."""
    from modules.orders.models import OrderItem
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )

    produkt = make_product()
    zamowienie = make_order(make_user(), offer_page_id=1)
    pozycja = OrderItem(
        order_id=zamowienie.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'),
    )
    db.session.add(pozycja)

    proxy = ProxyOrder(order_number='PRX/T1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    )
    db.session.add(proxy_item)
    db.session.flush()
    partia = PolandOrder(
        order_number='PRX/PL/T1', proxy_order_id=proxy.id,
        status='zamowione', shipping_cost=Decimal('100'),
    )
    db.session.add(partia)
    db.session.flush()
    pozycja_partii = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=produkt.id, quantity=2, shipping_cost=Decimal('100'),
    )
    db.session.add(pozycja_partii)
    db.session.commit()

    assert pozycja.incl_only_quantity == 0
    assert pozycja_partii.shipping_cost_album_per_unit is None
    assert pozycja_partii.shipping_cost_incl_per_unit is None


def _partia(db, product_id, qty, shipping, created_at,
            album_rate=None, incl_rate=None, status='zamowione'):
    """Tworzy ProxyOrder+Item oraz PolandOrder+Item — jedną partię danego produktu."""
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )
    suffix = f'{product_id}-{int(created_at.timestamp())}'
    proxy = ProxyOrder(order_number=f'PRX/T{suffix}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
        unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(
        order_number=f'PRX/PL/T{suffix}', proxy_order_id=proxy.id,
        status=status, shipping_cost=Decimal(str(shipping)),
    )
    partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()
    pozycja = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=product_id, quantity=qty, shipping_cost=Decimal(str(shipping)),
        shipping_cost_album_per_unit=(
            None if album_rate is None else Decimal(str(album_rate))),
        shipping_cost_incl_per_unit=(
            None if incl_rate is None else Decimal(str(incl_rate))),
    )
    db.session.add(pozycja)
    db.session.commit()
    return partia


def _zamowienie_klienta(db, make_user, make_order, product_id, qty, created_at,
                        incl=0, price=130):
    """Zamówienie klienta (exclusive) z jedną pozycją i wskazaną liczbą sztuk incl."""
    from modules.orders.models import OrderItem
    zam = make_order(make_user(), offer_page_id=1, created_at=created_at)
    poz = OrderItem(
        order_id=zam.id, product_id=product_id, quantity=qty,
        price=Decimal(str(price)), total=Decimal(str(price)) * qty,
        incl_only_quantity=incl,
    )
    db.session.add(poz)
    db.session.commit()
    return zam


def test_bez_incl_podzial_jak_dotad(db, make_user, make_order, make_product):
    """Regresja: gdy nikt nie bierze incl, wynik jest identyczny jak przed zmianą."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='200', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=2))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('100.00')
    assert alokacja[b.id] == Decimal('100.00')


def test_partia_bez_stawek_stara_logika(db, make_user, make_order, make_product):
    """Stara partia (stawki NULL) dzieli po równo, nawet gdy klient ma incl."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='100', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2), incl=1)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('50.00')
    assert alokacja[b.id] == Decimal('50.00')


def test_klient_w_calosci_na_incl(db, make_user, make_order, make_product):
    """3 szt. samego incl po 12 zł = 36 zł, mimo że album kosztuje 45 zł/szt."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='81', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=2), incl=3)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('36.00')
    assert alokacja[b.id] == Decimal('45.00')


def test_klient_mieszany_album_i_incl(db, make_user, make_order, make_product):
    """Partia 3 szt. dzielona między DWA zamówienia — żadne nie zjada całej partii,
    więc wynik faktycznie zależy od tego, czy incl jest liczony osobno od albumu.

    Zam. A (starsze, 2 szt., w tym 1 incl) = 1 album (45) + 1 incl (12) = 57 zł.
    Zam. B (nowsze, 1 szt., bez incl) = 1 album = 45 zł.

    Dla kontroli: stara logika (podział partii po równo: 102 / 3 = 34 zł/szt.)
    dałaby A = 2 × 34 = 68 zł, B = 1 × 34 = 34 zł — inny wynik niż tutaj, więc
    ten test faktycznie odróżnia starą logikę od nowej (w przeciwieństwie do
    poprzedniej wersji, gdzie jedno zamówienie zjadało całą partię i oba modele
    dawały ten sam wynik 57 zł)."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=3, shipping='102', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('57.00')
    assert alokacja[b.id] == Decimal('45.00')


def test_dwie_partie_rozne_stawki_bez_dublowania(db, make_user, make_order, make_product):
    """Dwie partie, każda ze swoimi stawkami; przeliczenie od zera daje ten sam wynik."""
    from modules.products.routes import (
        _allocate_product_shipping_fifo, _distribute_proxy_shipping_to_client_orders,
    )
    from modules.orders.models import Order

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='57', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    _partia(db, produkt.id, qty=2, shipping='40', created_at=baza + timedelta(days=1),
            album_rate='30.00', incl_rate='10.00')

    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3), incl=1)   # 1. partia: 45 + 12
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=2)   # 2. partia: 10 + 10

    alokacja = _allocate_product_shipping_fifo(produkt.id)
    assert alokacja[a.id] == Decimal('57.00')
    assert alokacja[b.id] == Decimal('20.00')

    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()
    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()

    assert db.session.get(Order, a.id).proxy_shipping_cost == Decimal('57.00')
    assert db.session.get(Order, b.id).proxy_shipping_cost == Decimal('20.00')


def test_incl_przyciete_per_pozycje_a_nie_na_sumie(db, make_user, make_order, make_product):
    """Przycięcie `incl_only_quantity` do ilości efektywnej musi liczyć się PER POZYCJA,
    nie na sumie pozycji zamówienia — ma to znaczenie, gdy ten sam produkt występuje
    w zamówieniu w kilku pozycjach (normalny przypadek: ten sam produkt w kilku setach
    jednego zamówienia; brak unikatu na (order_id, product_id)).

    Jedno zamówienie, dwie pozycje tego samego produktu:
      • poz. 1: quantity=2, fulfilled_quantity=1, incl_only_quantity=2
        → efektywna=1 (przycięta do fulfilled_quantity), incl=min(2, 1)=1
      • poz. 2: quantity=2, incl_only_quantity=0
        → efektywna=2, incl=0
    Razem: ilość=3, incl=1, album=2 → 45 + 45 + 12 = 102.00.

    Liczenie na sumie pozycji (błędne, którego ten test pilnuje) zsumowałoby
    incl_only_quantity BEZ przycięcia per pozycja: incl=2+0=2, album=3-2=1,
    co dałoby 45 + 12 + 12 = 69.00 — inny (błędny) wynik."""
    from modules.orders.models import OrderItem
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=3, shipping='102', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    zam = make_order(make_user(), offer_page_id=1, created_at=baza - timedelta(days=2))
    poz1 = OrderItem(
        order_id=zam.id, product_id=produkt.id, quantity=2, fulfilled_quantity=1,
        price=Decimal('130'), total=Decimal('260'), incl_only_quantity=2,
    )
    poz2 = OrderItem(
        order_id=zam.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'), incl_only_quantity=0,
    )
    db.session.add_all([poz1, poz2])
    db.session.commit()

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[zam.id] == Decimal('102.00')


def test_podglad_przydziela_klientow_do_tworzonej_partii(db, make_user, make_order,
                                                         make_product):
    """Nowa partia trafia na koniec kolejki: pierwsze 2 szt. zjadł klient A z wcześniejszej
    partii, więc podgląd partii na 2 szt. pokazuje klienta B."""
    from modules.products.routes import _preview_batch_allocation

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='90', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)

    podglad = _preview_batch_allocation(produkt.id, quantity=2)

    assert podglad == [(b.id, 2)]
    assert a.id not in [oid for oid, _ in podglad]


def test_podglad_z_offsetem_dla_dwoch_pozycji_tego_samego_produktu(
        db, make_user, make_order, make_product):
    """Dwie pozycje z tym samym produktem w jednym oknie nie mogą wskazać tych samych sztuk."""
    from modules.products.routes import _preview_batch_allocation

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2))

    pierwsza = _preview_batch_allocation(produkt.id, quantity=1, offset=0)
    druga = _preview_batch_allocation(produkt.id, quantity=1, offset=1)

    assert pierwsza == [(a.id, 1)]
    assert druga == [(b.id, 1)]


def test_endpoint_szczegolow_zwraca_klientow(db, client, login, make_user, make_order,
                                             make_product):
    """Okno partii dostaje z backendu listę klientów z ich obecnym `incl_only_quantity`."""
    from modules.products.models import ProxyOrder, ProxyOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    klient = make_user(first_name='Jan', last_name='Kowalski')
    zam = make_order(klient, offer_page_id=1, created_at=baza - timedelta(days=2))
    from modules.orders.models import OrderItem
    poz = OrderItem(
        order_id=zam.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'), incl_only_quantity=1,
    )
    db.session.add(poz)
    db.session.commit()
    a = zam

    proxy = ProxyOrder(order_number='PRX/T99', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    db.session.add(ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    ))
    db.session.commit()

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/get-proxy-orders-details',
                      json={'proxy_order_ids': [proxy.id]})

    assert odp.status_code == 200
    dane = odp.get_json()
    assert dane['success'] is True
    klienci = dane['orders'][0]['items'][0]['clients']
    assert klient.full_name == 'Jan Kowalski'
    assert klienci == [{
        'order_id': a.id,
        'order_number': a.order_number,
        'client_name': klient.full_name,
        'quantity': 2,
        'incl_only_quantity': 1,
    }]


def test_endpoint_offset_dla_dwoch_pozycji_tego_samego_produktu_w_dwoch_zamowieniach_proxy(
        db, client, login, make_user, make_order, make_product):
    """Dwie pozycje tego samego produktu w JEDNEJ odpowiedzi endpointu (w dwóch różnych
    zamówieniach proxy) nie mogą wskazać tych samych sztuk klienta — `offsety` musi
    przeżyć zewnętrzną pętlę po zamówieniach proxy, nie tylko wewnętrzną po pozycjach.

    Kolejność zamówień proxy w odpowiedzi (`orders_data`) NIE jest gwarantowana przez
    zapytanie `ProxyOrder.query.filter(id.in_(...))` (brak `.order_by`) — endpoint
    jednak buduje `orders_data`/inkrementuje `offsety` w JEDNEJ tej samej pętli, więc
    kolejność spłaszczonych pozycji w JSON zawsze odzwierciedla kolejność faktycznego
    przetwarzania. Dlatego test spłaszcza pozycje w kolejności zwróconej przez
    endpoint, zamiast zakładać, który proxy_order_id wyląduje pierwszy."""
    from modules.products.models import ProxyOrder, ProxyOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2))

    proxy1 = ProxyOrder(order_number='PRX/T-OFF-1', order_type='proxy')
    proxy2 = ProxyOrder(order_number='PRX/T-OFF-2', order_type='proxy')
    db.session.add_all([proxy1, proxy2])
    db.session.flush()
    db.session.add(ProxyOrderItem(
        proxy_order_id=proxy1.id, product_id=produkt.id, quantity=1,
        unit_price=Decimal('100'), total_price=Decimal('100'),
    ))
    db.session.add(ProxyOrderItem(
        proxy_order_id=proxy2.id, product_id=produkt.id, quantity=1,
        unit_price=Decimal('100'), total_price=Decimal('100'),
    ))
    db.session.commit()

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/get-proxy-orders-details',
                      json={'proxy_order_ids': [proxy1.id, proxy2.id]})

    assert odp.status_code == 200
    dane = odp.get_json()
    assert dane['success'] is True

    # Spłaszczamy pozycje w kolejności, w jakiej faktycznie wyszły z endpointu —
    # to ta sama kolejność, w jakiej backend przetwarzał je i inkrementował `offsety`.
    pozycje = [poz for zam in dane['orders'] for poz in zam['items']]
    assert len(pozycje) == 2

    pierwsza_klienci = pozycje[0]['clients']
    druga_klienci = pozycje[1]['clients']

    assert [k['order_id'] for k in pierwsza_klienci] == [a.id]
    assert [k['order_id'] for k in druga_klienci] == [b.id]

    # Żaden klient nie może pojawić się w obu pozycjach.
    id_pierwszej = {k['order_id'] for k in pierwsza_klienci}
    id_drugiej = {k['order_id'] for k in druga_klienci}
    assert id_pierwszej.isdisjoint(id_drugiej)
