"""Kolejka FIFO partii z Korei a przepisane zamówienia (kotwica `fifo_anchor_order_id`).

Dwie rzeczy naraz:
1. zamówienia BEZ kotwicy — kolejność i kwoty dokładnie jak przed zmianą, także przy
   kilku zamówieniach z tą samą sekundą `created_at` (remis rozstrzyga `id`);
2. zamówienie z kotwicą staje w kolejce tuż za swoim oryginałem, przed zamówieniami
   z tej samej sekundy złożonymi po oryginale.
"""
from datetime import timedelta
from decimal import Decimal

import pytest

from tests.przepisanie_helpers import T0, partia, zamowienie_klientki


@pytest.fixture(autouse=True)
def _strona(strona_sprzedazy):
    """Zamówienia powstają z offer_page_id=1 (FK)."""


def test_kolejka_bez_kotwicy_jak_dotad(db, make_user, make_product, make_order):
    from modules.products.routes import _batch_allocation_for_range

    p = make_product()
    o1 = zamowienie_klientki(db, make_user, make_order, [(p.id, 2, 50)], created_at=T0)
    o2 = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0)
    o3 = zamowienie_klientki(db, make_user, make_order, [(p.id, 3, 50)], created_at=T0)
    o4 = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)],
                             created_at=T0 + timedelta(minutes=1))

    assert _batch_allocation_for_range(p.id, 0, 7) == [
        (o1.id, 2), (o2.id, 1), (o3.id, 3), (o4.id, 1)]
    assert _batch_allocation_for_range(p.id, 2, 5) == [(o2.id, 1), (o3.id, 2)]


def test_kwoty_bez_kotwicy_jak_dotad(db, make_user, make_product, make_order):
    from modules.products.routes import _allocate_product_shipping_fifo

    p = make_product()
    o1 = zamowienie_klientki(db, make_user, make_order, [(p.id, 2, 50)], created_at=T0)
    o2 = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0)
    o3 = zamowienie_klientki(db, make_user, make_order, [(p.id, 3, 50)], created_at=T0)
    o4 = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)],
                             created_at=T0 + timedelta(minutes=1))
    partia(db, p.id, 3, T0 + timedelta(hours=1), koszt=30)   # 10 zł/szt.
    partia(db, p.id, 4, T0 + timedelta(hours=2), koszt=80)   # 20 zł/szt.

    assert _allocate_product_shipping_fifo(p.id) == {
        o1.id: Decimal('20.00'), o2.id: Decimal('10.00'),
        o3.id: Decimal('60.00'), o4.id: Decimal('20.00')}


def test_zamowienie_z_kotwica_staje_za_oryginalem(db, make_user, make_product, make_order):
    from modules.products.routes import _batch_allocation_for_range

    p = make_product()
    a = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0)
    c = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0)
    b = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0,
                            fifo_anchor_order_id=a.id)

    assert _batch_allocation_for_range(p.id, 0, 3) == [(a.id, 1), (b.id, 1), (c.id, 1)]


def test_kotwica_zachowuje_kwoty_innych(db, make_user, make_product, make_order):
    """Ania (2 szt.) oddaje 1 szt. Basi; Celina zamówiła w tej samej sekundzie po Ani.
    Bez kotwicy Basia stanęłaby za Celiną i Celina dostałaby sztukę z tańszej partii."""
    from modules.orders.models import OrderItem
    from modules.products.routes import _allocate_product_shipping_fifo

    p = make_product()
    a = zamowienie_klientki(db, make_user, make_order, [(p.id, 2, 50)], created_at=T0)
    c = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0)
    partia(db, p.id, 2, T0 + timedelta(hours=1), koszt=20)   # 10 zł/szt.
    partia(db, p.id, 1, T0 + timedelta(hours=2), koszt=30)   # 30 zł/szt.
    przed = _allocate_product_shipping_fifo(p.id)
    assert przed == {a.id: Decimal('20.00'), c.id: Decimal('30.00')}

    pozycja = OrderItem.query.filter_by(order_id=a.id).one()
    pozycja.quantity = 1
    pozycja.total = Decimal('50')
    b = zamowienie_klientki(db, make_user, make_order, [(p.id, 1, 50)], created_at=T0,
                            fifo_anchor_order_id=a.id)

    po = _allocate_product_shipping_fifo(p.id)
    assert po[c.id] == przed[c.id]
    assert po[a.id] + po[b.id] == przed[a.id]
    assert po == {a.id: Decimal('10.00'), b.id: Decimal('10.00'), c.id: Decimal('30.00')}


def test_klucz_fifo_w_pythonie(db, make_user, make_order):
    """Zamknięcie sprzedaży sortuje zamówienia w Pythonie — ten sam klucz co w SQL."""
    from modules.orders.models import fifo_klucz

    a = make_order(make_user(), created_at=T0)
    c = make_order(make_user(), created_at=T0)
    b = make_order(make_user(), created_at=T0, fifo_anchor_order_id=a.id)
    d = make_order(make_user(), created_at=T0 - timedelta(seconds=1))

    assert sorted([c, b, a, d], key=fifo_klucz) == [d, a, b, c]
