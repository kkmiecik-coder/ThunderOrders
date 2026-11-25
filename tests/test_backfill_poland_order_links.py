"""Skrypt scripts/backfill_poland_order_links.py — uzupełnianie powiązań partii PL
z zamówieniami klientów (po błędzie mikrosekund od PRX/PL/12)."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

_SCIEZKA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'scripts', 'backfill_poland_order_links.py')
_spec = importlib.util.spec_from_file_location('backfill_poland_order_links', _SCIEZKA)
skrypt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skrypt)

OD = datetime(2026, 8, 8, tzinfo=timezone.utc)
TERAZ = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia powstają z `offer_page_id=1` (FK) — strona musi istnieć."""


@pytest.fixture
def klientka(db, make_user, make_order):
    licznik = {'n': 0}

    def _make(product_id, qty, created_at, **kwargs):
        from modules.orders.models import OrderItem
        licznik['n'] += 1
        o = make_order(make_user(), offer_page_id=1, created_at=created_at, **kwargs)
        db.session.add(OrderItem(order_id=o.id, product_id=product_id, quantity=qty,
                                 price=Decimal('100'), total=Decimal('100') * qty))
        db.session.commit()
        return o
    return _make


@pytest.fixture
def partia(db):
    licznik = {'n': 0}

    def _make(product_id, qty, created_at, status='zamowione', payment_deadline=None,
              customs_payment_deadline=None):
        from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem
        licznik['n'] += 1
        n = licznik['n']
        proxy = ProxyOrder(order_number=f'PRX/B{n}', order_type='proxy')
        db.session.add(proxy)
        db.session.flush()
        proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
                                    unit_price=Decimal('100'), total_price=Decimal('100') * qty)
        db.session.add(proxy_item)
        db.session.flush()
        po = PolandOrder(order_number=f'PRX/PL/B{n}', proxy_order_id=proxy.id, status=status,
                         created_at=created_at, payment_deadline=payment_deadline,
                         customs_payment_deadline=customs_payment_deadline)
        db.session.add(po)
        db.session.flush()
        pozycja = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                                  product_id=product_id, quantity=qty)
        db.session.add(pozycja)
        db.session.commit()
        return pozycja
    return _make


def _powiazania(pozycja_id=None):
    from modules.products.models import PolandOrderItemOrder
    q = PolandOrderItemOrder.query
    if pozycja_id is not None:
        q = q.filter_by(poland_order_item_id=pozycja_id)
    return sorted((l.poland_order_item_id, l.order_id, l.quantity) for l in q.all())


def test_tryb_probny_nic_nie_zapisuje(db, make_product, klientka, partia):
    p = make_product()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    o1 = klientka(p.id, 2, base)
    o2 = klientka(p.id, 1, base + timedelta(hours=1))
    poz = partia(p.id, 3, datetime(2026, 9, 1, tzinfo=timezone.utc))

    plan = skrypt.zaplanuj(od=OD, now=TERAZ)

    assert [(z.rodzaj, z.order_id, z.ilosc) for z in plan.zmiany] == [
        ('dodaj', o1.id, 2), ('dodaj', o2.id, 1)]
    assert plan.partie == 1 and plan.pozycje == 1
    assert _powiazania() == []


def test_apply_tworzy_powiazania_fifo_i_jest_idempotentny(db, make_product, klientka, partia):
    p = make_product()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    o1 = klientka(p.id, 2, base)
    o2 = klientka(p.id, 2, base + timedelta(hours=1))
    poz1 = partia(p.id, 3, datetime(2026, 9, 1, tzinfo=timezone.utc))
    poz2 = partia(p.id, 1, datetime(2026, 9, 2, tzinfo=timezone.utc))

    skrypt.zastosuj(skrypt.zaplanuj(od=OD, now=TERAZ))

    assert _powiazania() == sorted([(poz1.id, o1.id, 2), (poz1.id, o2.id, 1), (poz2.id, o2.id, 1)])

    drugi = skrypt.zaplanuj(od=OD, now=TERAZ)
    assert drugi.zmiany == []


def test_bledne_powiazanie_zastapione_przydzialem_fifo(db, make_product, klientka, partia):
    """Tak wyglądała PRX/PL/52: jedyne powiązanie wskazywało klienta przesuniętego
    o ilość samej partii."""
    from modules.products.models import PolandOrderItemOrder
    p = make_product()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    o1 = klientka(p.id, 1, base)
    o2 = klientka(p.id, 1, base + timedelta(hours=1))
    o3 = klientka(p.id, 1, base + timedelta(hours=2))
    poz = partia(p.id, 2, datetime(2026, 11, 15, tzinfo=timezone.utc))
    db.session.add(PolandOrderItemOrder(poland_order_item_id=poz.id, order_id=o3.id, quantity=1))
    db.session.commit()

    plan = skrypt.zaplanuj(od=OD, now=TERAZ)
    assert sorted((z.rodzaj, z.order_id) for z in plan.zmiany) == sorted(
        [('dodaj', o1.id), ('dodaj', o2.id), ('usun', o3.id)])

    skrypt.zastosuj(plan)
    assert _powiazania(poz.id) == sorted([(poz.id, o1.id, 1), (poz.id, o2.id, 1)])


def test_zla_ilosc_poprawiona(db, make_product, klientka, partia):
    from modules.products.models import PolandOrderItemOrder
    p = make_product()
    o1 = klientka(p.id, 2, datetime(2026, 7, 1, tzinfo=timezone.utc))
    poz = partia(p.id, 2, datetime(2026, 9, 1, tzinfo=timezone.utc))
    db.session.add(PolandOrderItemOrder(poland_order_item_id=poz.id, order_id=o1.id, quantity=1))
    db.session.commit()

    plan = skrypt.zaplanuj(od=OD, now=TERAZ)
    assert [(z.rodzaj, z.ilosc_byla, z.ilosc) for z in plan.zmiany] == [('popraw', 1, 2)]
    skrypt.zastosuj(plan)
    assert _powiazania(poz.id) == [(poz.id, o1.id, 2)]


def test_partie_sprzed_daty_i_anulowane_nietkniete(db, make_product, klientka, partia):
    p = make_product()
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)
    klientka(p.id, 1, base)
    klientka(p.id, 1, base + timedelta(hours=1))
    partia(p.id, 1, datetime(2026, 7, 1, tzinfo=timezone.utc))                     # przed --od
    partia(p.id, 1, datetime(2026, 9, 1, tzinfo=timezone.utc), status='anulowane')

    plan = skrypt.zaplanuj(od=OD, now=TERAZ)
    assert plan.zmiany == []


def test_filtr_numerow_partii(db, make_product, klientka, partia):
    p = make_product()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    klientka(p.id, 1, base)
    o2 = klientka(p.id, 1, base + timedelta(hours=1))
    partia(p.id, 1, datetime(2026, 9, 1, tzinfo=timezone.utc))
    poz2 = partia(p.id, 1, datetime(2026, 9, 2, tzinfo=timezone.utc))

    plan = skrypt.zaplanuj(od=OD, numery_partii=[poz2.poland_order.order_number], now=TERAZ)
    assert [(z.poland_order_item_id, z.order_id) for z in plan.zmiany] == [(poz2.id, o2.id)]


def test_raport_zamowien_od_razu_zaleglych(db, make_product, klientka, partia):
    p = make_product()
    base = datetime(2026, 7, 1, tzinfo=timezone.utc)
    zalegla = klientka(p.id, 1, base, payment_stages=4, proxy_shipping_cost=Decimal('12.50'))
    bez_kosztu = klientka(p.id, 1, base + timedelta(hours=1), payment_stages=4)
    partia(p.id, 2, datetime(2026, 11, 15, tzinfo=timezone.utc),
           payment_deadline=datetime(2026, 11, 22, 22, 59, tzinfo=timezone.utc))

    plan = skrypt.zaplanuj(od=OD, now=TERAZ)

    assert set(plan.od_razu_zalegle) == {zalegla.id}
    etap = plan.od_razu_zalegle[zalegla.id][0]
    assert etap['stage'] == 'shipping_kr' and etap['amount'] == Decimal('12.50')

    linie = []
    skrypt.wypisz(plan, out=linie.append)
    assert any('od razu po terminie' in l and '1 zamówień' in l for l in linie)
    assert bez_kosztu.id not in plan.od_razu_zalegle
