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
    assert any('od razu PO TERMINIE' in l and '1 zamówień' in l for l in linie)
    assert bez_kosztu.id not in plan.od_razu_zalegle


NOWY = datetime(2026, 12, 2, 22, 59, tzinfo=timezone.utc)   # 2.12.2026 23:59 czasu polskiego
MINIONY = datetime(2026, 11, 22, 22, 59, tzinfo=timezone.utc)
PRZYSZLY = datetime(2026, 12, 20, 22, 59, tzinfo=timezone.utc)


def test_nowy_termin_tylko_dla_minionych_i_niepustych(db, make_product, klientka, partia):
    from modules.products.models import PolandOrder
    p = make_product()
    klientka(p.id, 3, datetime(2026, 7, 1, tzinfo=timezone.utc))
    a = partia(p.id, 1, datetime(2026, 9, 1, tzinfo=timezone.utc),
               payment_deadline=MINIONY, customs_payment_deadline=MINIONY)
    b = partia(p.id, 1, datetime(2026, 9, 2, tzinfo=timezone.utc),
               payment_deadline=MINIONY, customs_payment_deadline=None)
    c = partia(p.id, 1, datetime(2026, 9, 3, tzinfo=timezone.utc),
               payment_deadline=PRZYSZLY, customs_payment_deadline=MINIONY)

    plan = skrypt.zaplanuj(od=OD, now=TERAZ, nowy_termin=NOWY)

    assert sorted((t.poland_order_id, t.pole) for t in plan.zmiany_terminow) == sorted([
        (a.poland_order_id, 'payment_deadline'), (a.poland_order_id, 'customs_payment_deadline'),
        (b.poland_order_id, 'payment_deadline'),
        (c.poland_order_id, 'customs_payment_deadline'),
    ])
    # tryb próbny niczego nie zmienia
    db.session.expire_all()
    assert db.session.get(PolandOrder, a.poland_order_id).payment_deadline == MINIONY

    skrypt.zastosuj(plan)
    db.session.expire_all()
    pa = db.session.get(PolandOrder, a.poland_order_id)
    pb = db.session.get(PolandOrder, b.poland_order_id)
    pc = db.session.get(PolandOrder, c.poland_order_id)
    assert (pa.payment_deadline, pa.customs_payment_deadline) == (NOWY, NOWY)
    assert (pb.payment_deadline, pb.customs_payment_deadline) == (NOWY, None)
    assert (pc.payment_deadline, pc.customs_payment_deadline) == (PRZYSZLY, NOWY)

    drugi = skrypt.zaplanuj(od=OD, now=TERAZ, nowy_termin=NOWY)
    assert drugi.zmiany == [] and drugi.zmiany_terminow == []


def test_nowy_termin_zamienia_zaleglosc_na_przypomnienie(db, make_user, make_product, partia):
    from modules.orders.models import OrderItem
    from modules.orders.payment_overdue_service import get_order_overdue_stages
    p = make_product()
    klientka = make_user()
    zamowienia = []
    for i in range(2):   # ta sama klientka, dwa zamówienia
        from modules.orders.models import Order
        o = Order(order_number=f'PO/NT{i}', user_id=klientka.id, status='nowe', total_amount=100,
                  offer_page_id=1, order_type='pre_order', payment_stages=4,
                  proxy_shipping_cost=Decimal('10.00'),
                  customs_vat_sale_cost=Decimal('5.00'),
                  created_at=datetime(2026, 7, 1, i, tzinfo=timezone.utc))
        db.session.add(o)
        db.session.flush()
        db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=1,
                                 price=Decimal('100'), total=Decimal('100')))
        zamowienia.append(o)
    db.session.commit()
    partia(p.id, 2, datetime(2026, 11, 13, tzinfo=timezone.utc),
           payment_deadline=MINIONY, customs_payment_deadline=MINIONY)

    bez = skrypt.zaplanuj(od=OD, now=TERAZ)
    assert len(bez.od_razu_zalegle) == 2 and bez.przypomnienia == {}

    plan = skrypt.zaplanuj(od=OD, now=TERAZ, nowy_termin=NOWY)
    assert plan.od_razu_zalegle == {}
    assert set(plan.przypomnienia) == {o.id for o in zamowienia}
    assert {e['stage'] for e in plan.przypomnienia[zamowienia[0].id]} == {'shipping_kr', 'customs_vat'}

    linie = []
    skrypt.wypisz(plan, out=linie.append)
    assert any('dostanie: 2 zamówień, 1 klientek, łącznie 30.00 zł' in l for l in linie)
    assert any(l.startswith('TERMIN') and '22.11.2026 23:59 -> 02.12.2026 23:59' in l for l in linie)

    skrypt.zastosuj(plan)
    db.session.expire_all()
    o = db.session.get(Order, zamowienia[0].id)
    assert o.get_shipping_kr_deadline() == NOWY
    assert o.get_customs_vat_deadline() == NOWY
    assert get_order_overdue_stages(o, now=TERAZ) == []


def test_stare_logi_przypomnien_raportowane_a_null_nie_blokuje(db, make_product, klientka, partia):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog
    p = make_product()
    o = klientka(p.id, 1, datetime(2026, 7, 1, tzinfo=timezone.utc),
                 payment_stages=4, proxy_shipping_cost=Decimal('10.00'))
    partia(p.id, 1, datetime(2026, 11, 13, tzinfo=timezone.utc), payment_deadline=MINIONY)
    r24 = PaymentReminderConfig(reminder_type='before_deadline', hours=24, payment_stage='product')
    r5 = PaymentReminderConfig(reminder_type='before_deadline', hours=5, payment_stage='product')
    db.session.add_all([r24, r5])
    db.session.flush()
    db.session.add(PaymentReminderLog(order_id=o.id, config_id=r24.id, stage='shipping_kr'))
    db.session.add(PaymentReminderLog(order_id=o.id, config_id=r5.id, stage=None))  # sprzed migracji
    db.session.commit()

    plan = skrypt.zaplanuj(od=OD, now=TERAZ, nowy_termin=NOWY)

    assert plan.zablokowane_logami == {(o.id, 'shipping_kr'): [24]}


def test_zastosuj_nie_nadpisuje_terminu_zmienionego_w_miedzyczasie(db, make_product, klientka, partia):
    from modules.products.models import PolandOrder
    p = make_product()
    klientka(p.id, 1, datetime(2026, 7, 1, tzinfo=timezone.utc))
    poz = partia(p.id, 1, datetime(2026, 11, 13, tzinfo=timezone.utc), payment_deadline=MINIONY)

    plan = skrypt.zaplanuj(od=OD, now=TERAZ, nowy_termin=NOWY)
    partia_db = db.session.get(PolandOrder, poz.poland_order_id)
    partia_db.payment_deadline = PRZYSZLY      # ktoś zmienił ręcznie po próbie
    db.session.commit()

    skrypt.zastosuj(plan)
    db.session.expire_all()
    assert db.session.get(PolandOrder, poz.poland_order_id).payment_deadline == PRZYSZLY
