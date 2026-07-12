"""Testy kaskady statusów zamówień klientów przy zmianach statusów
zamówień produktów (ProxyOrder/PolandOrder).

Regresja produkcyjna (PRX/PL/00006, 2026-07-09): zamówienia exclusive
z payment_stages=4 utknęły w statusie 'oczekujace' (proxy order nigdy nie
dostał 'dostarczone_do_proxy'), przez co kaskada GOM/urząd celny/w drodze
do Polski po cichu je pomijała — filtry dla stages=4 nie zawierały
'oczekujace'.
"""
from datetime import datetime
from decimal import Decimal

import pytest


def _make_poland_batch(db, product_id, qty, status='dostarczone_gom',
                       proxy_status='zamowiono', order_type='proxy'):
    """ProxyOrder+Item oraz PolandOrder+Item dla jednego produktu."""
    from modules.products.models import (
        ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem,
    )
    suffix = f'{product_id}-{status}-{qty}'
    proxy = ProxyOrder(order_number=f'PRX/T{suffix}', order_type=order_type,
                       status=proxy_status)
    db.session.add(proxy)
    db.session.flush()
    pitem = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id,
        quantity=qty, unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(pitem)
    db.session.flush()
    pol = PolandOrder(order_number=f'PRX/PL/T{suffix}', proxy_order_id=proxy.id,
                      status=status)
    db.session.add(pol)
    db.session.flush()
    db.session.add(PolandOrderItem(
        poland_order_id=pol.id, proxy_order_item_id=pitem.id,
        product_id=product_id, quantity=qty,
    ))
    db.session.commit()
    return pol


def _client_order(db, make_user, make_order, product_id, qty=1,
                  order_type='exclusive', payment_stages=4, status='oczekujace'):
    from modules.orders.models import OrderItem
    u = make_user()
    o = make_order(u, status=status, order_type=order_type,
                   payment_stages=payment_stages, offer_page_id=1)
    db.session.add(OrderItem(order_id=o.id, product_id=product_id, quantity=qty,
                             price=Decimal('130'), total=Decimal('130') * qty))
    db.session.commit()
    return o


@pytest.fixture(autouse=True)
def _no_notifications(monkeypatch):
    """Wyłącz maile/push — testujemy wyłącznie zmiany statusów."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    monkeypatch.setattr(EmailManager, 'notify_status_change',
                        staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(PushManager, 'notify_status_change',
                        staticmethod(lambda *a, **k: True))


def test_gom_podbija_exclusive_stages4_oczekujace(db, make_user, make_product, make_order):
    """Regresja PRX/PL/00006: exclusive stages=4 w 'oczekujace' (pominięty etap
    dostarczone_do_proxy) MUSI dostać 'dostarczone_gom' gdy paczka dotarła."""
    from modules.products.routes import _update_client_orders_on_gom_delivery

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id)
    _make_poland_batch(db, p.id, 1, status='dostarczone_gom')

    _update_client_orders_on_gom_delivery()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'dostarczone_gom'


def test_gom_podbija_preorder_stages4_oczekujace(db, make_user, make_product, make_order):
    from modules.products.routes import _update_client_orders_on_gom_delivery

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id, order_type='pre_order')
    _make_poland_batch(db, p.id, 1, status='dostarczone_gom')

    _update_client_orders_on_gom_delivery()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'dostarczone_gom'


def test_urzad_celny_podbija_exclusive_stages4_oczekujace(db, make_user, make_product, make_order):
    from modules.products.routes import _update_client_orders_on_customs

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id)
    _make_poland_batch(db, p.id, 1, status='urzad_celny')

    _update_client_orders_on_customs()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'urzad_celny'


def test_w_drodze_polska_podbija_stages4_oczekujace(db, make_user, make_product, make_order):
    from modules.products.routes import _update_client_orders_on_polska_ordered

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id)
    _make_poland_batch(db, p.id, 1, status='zamowione')

    _update_client_orders_on_polska_ordered()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'w_drodze_polska'


def test_gom_nie_rusza_niepokrytych(db, make_user, make_product, make_order):
    """Zamówienie z 2 szt. przy dostarczonej 1 szt. zostaje w 'oczekujace'."""
    from modules.products.routes import _update_client_orders_on_gom_delivery

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id, qty=2)
    _make_poland_batch(db, p.id, 1, status='dostarczone_gom')

    _update_client_orders_on_gom_delivery()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'oczekujace'


def test_gom_nie_rusza_anulowanych_i_nowych_exclusive(db, make_user, make_product, make_order):
    """'anulowane' oraz exclusive w 'nowe' (nieopłacone) nie są podbijane."""
    from modules.products.routes import _update_client_orders_on_gom_delivery

    p = make_product()
    o_anul = _client_order(db, make_user, make_order, p.id, status='anulowane')
    o_nowe = _client_order(db, make_user, make_order, p.id, status='nowe')
    _make_poland_batch(db, p.id, 5, status='dostarczone_gom')

    _update_client_orders_on_gom_delivery()
    db.session.commit()

    db.session.refresh(o_anul)
    db.session.refresh(o_nowe)
    assert o_anul.status == 'anulowane'
    assert o_nowe.status == 'nowe'


def test_gom_dziala_dalej_dla_dostarczone_proxy(db, make_user, make_product, make_order):
    """Dotychczasowa ścieżka (pełny łańcuch) nadal działa."""
    from modules.products.routes import _update_client_orders_on_gom_delivery

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id, status='dostarczone_proxy')
    _make_poland_batch(db, p.id, 1, status='dostarczone_gom')

    _update_client_orders_on_gom_delivery()
    db.session.commit()

    db.session.refresh(o)
    assert o.status == 'dostarczone_gom'
