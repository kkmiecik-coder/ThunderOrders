"""Testy powiadomień o kosztach rozdzielanych HURTOWO (VAT / wysyłka KR).

Regresja: modale "Zamów do Polski" i "Cło/VAT" rozdzielały koszty na zamówienia
klientów bez żadnego powiadomienia (email szedł tylko przy ręcznej edycji pola).
Emaile muszą iść JEDNYM połączeniem SMTP (batch) — limit AUTH Hostingera.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


def _client_order(db, make_user, make_order, product_id, qty=1, price=130, **user_kwargs):
    from modules.orders.models import OrderItem
    u = make_user(**user_kwargs)
    o = make_order(u, offer_page_id=1)
    it = OrderItem(
        order_id=o.id, product_id=product_id, quantity=qty,
        price=Decimal(str(price)), total=Decimal(str(price)) * qty,
    )
    db.session.add(it)
    db.session.commit()
    return o


@pytest.fixture
def batch_capture(monkeypatch):
    """Przechwytuje send_email_batch — zwraca listę wywołań (każde = lista Message)."""
    import utils.email_sender as es
    calls = []
    monkeypatch.setattr(es, 'send_email_batch', lambda msgs: calls.append(msgs))
    return calls


# ============================================
# EmailManager.notify_costs_added_bulk
# ============================================

def test_bulk_wysyla_jednym_batchem(app, db, make_user, make_product, make_order, batch_capture):
    """N zamówień = jedno wywołanie send_email_batch z N wiadomościami."""
    from utils.email_manager import EmailManager

    p = make_product()
    orders = [_client_order(db, make_user, make_order, p.id) for _ in range(3)]

    with app.test_request_context():
        sent = EmailManager.notify_costs_added_bulk(
            [(o, 12.34) for o in orders], 'customs_vat'
        )

    assert sent == 3
    assert len(batch_capture) == 1  # jeden batch, nie trzy osobne wysyłki
    msgs = batch_capture[0]
    assert len(msgs) == 3
    recipients = {m.recipients[0] for m in msgs}
    assert recipients == {o.customer_email for o in orders}
    assert all('cła i VAT' in m.subject.lower() or 'Koszt cła i VAT' in m.subject
               for m in msgs)


def test_bulk_respektuje_toggle(app, db, make_user, make_product, make_order,
                                batch_capture, monkeypatch):
    """Wyłączony toggle notify_cost_added = zero maili."""
    from utils.email_manager import EmailManager

    monkeypatch.setattr(EmailManager, 'is_email_enabled',
                        classmethod(lambda cls, key: False))
    p = make_product()
    o = _client_order(db, make_user, make_order, p.id)

    with app.test_request_context():
        sent = EmailManager.notify_costs_added_bulk([(o, 10.0)], 'proxy_shipping')

    assert sent == 0
    assert batch_capture == []


def test_bulk_pomija_zamowienia_bez_emaila(app, db, make_user, make_product,
                                           make_order, batch_capture):
    """Zamówienie klienta bez adresu email jest pomijane, reszta idzie."""
    from utils.email_manager import EmailManager

    p = make_product()
    o_ok = _client_order(db, make_user, make_order, p.id)
    o_bez = _client_order(db, make_user, make_order, p.id)
    o_bez.user.email = ''  # fixture nadaje domyślny email, czyścimy po fakcie
    db.session.commit()

    with app.test_request_context():
        sent = EmailManager.notify_costs_added_bulk(
            [(o_ok, 5.0), (o_bez, 5.0)], 'proxy_shipping'
        )

    assert sent == 1
    assert len(batch_capture) == 1
    assert batch_capture[0][0].recipients == [o_ok.customer_email]


def test_bulk_temat_wg_typu_kosztu(app, db, make_user, make_product, make_order,
                                   batch_capture):
    """Temat maila odpowiada typowi kosztu (parytet z send_cost_added_email)."""
    from utils.email_manager import EmailManager

    p = make_product()
    o = _client_order(db, make_user, make_order, p.id)

    with app.test_request_context():
        EmailManager.notify_costs_added_bulk([(o, 7.0)], 'proxy_shipping')

    assert 'Koszt wysyłki z proxy' in batch_capture[0][0].subject
    assert o.order_number in batch_capture[0][0].subject


# ============================================
# _notify_distributed_costs (products/routes)
# ============================================

def test_notify_distributed_filtruje_niezmienione_i_zerowe(
        app, db, make_user, make_product, make_order, monkeypatch):
    """Powiadamiamy tylko zamówienia ze ZMIENIONYM kosztem > 0 (idempotentny
    przelicznik nie może spamować klientów, których koszt się nie zmienił)."""
    from modules.products.routes import _notify_distributed_costs
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    email_calls, push_calls = [], []
    monkeypatch.setattr(EmailManager, 'notify_costs_added_bulk',
                        staticmethod(lambda oc, ct: email_calls.append((oc, ct))))
    monkeypatch.setattr(PushManager, 'notify_cost_added',
                        staticmethod(lambda o, ct, amt: push_calls.append((o.id, ct, amt))))

    p = make_product()
    o_changed = _client_order(db, make_user, make_order, p.id)
    o_same = _client_order(db, make_user, make_order, p.id)
    o_zero = _client_order(db, make_user, make_order, p.id)

    distributed = {
        o_changed.id: {'old': 0.0, 'new': 19.34},
        o_same.id: {'old': 19.34, 'new': 19.34},  # bez zmiany — bez maila
        o_zero.id: {'old': 0.0, 'new': 0.0},      # zero — bez maila
    }

    with app.test_request_context():
        _notify_distributed_costs(distributed, 'proxy_shipping')

    assert len(email_calls) == 1
    orders_costs, cost_type = email_calls[0]
    assert cost_type == 'proxy_shipping'
    assert [(o.id, amt) for o, amt in orders_costs] == [(o_changed.id, 19.34)]
    assert push_calls == [(o_changed.id, 'proxy_shipping', 19.34)]


def test_notify_distributed_pusty_slownik(app, monkeypatch):
    """Pusty/None wynik dystrybucji nie wybucha i nic nie wysyła."""
    from modules.products.routes import _notify_distributed_costs
    from utils.email_manager import EmailManager

    monkeypatch.setattr(EmailManager, 'notify_costs_added_bulk',
                        staticmethod(lambda oc, ct: pytest.fail('nie powinno wysyłać')))

    with app.test_request_context():
        _notify_distributed_costs({}, 'customs_vat')
        _notify_distributed_costs(None, 'customs_vat')


# ============================================
# Integracja: endpoint Cło/VAT wysyła powiadomienia
# ============================================

def test_update_poland_customs_vat_powiadamia_batchem(
        app, db, client, make_user, make_product, make_order, login, monkeypatch):
    """Zapis Cła/VAT w modalu rozdziela koszt na zamówienia klientów
    i wysyła powiadomienia (email batch + push)."""
    from modules.products.models import (
        ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem,
    )
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    email_calls, push_calls = [], []
    monkeypatch.setattr(EmailManager, 'notify_costs_added_bulk',
                        staticmethod(lambda oc, ct: email_calls.append((oc, ct))))
    monkeypatch.setattr(PushManager, 'notify_cost_added',
                        staticmethod(lambda o, ct, amt: push_calls.append((o.id, ct, amt))))

    login(make_user(role='admin'))

    p = make_product(purchase_price_pln=Decimal('100'))
    # Zamówienie klienta: 1 szt po 130 PLN, VAT 10% od ceny sprzedaży = 13.00
    o = _client_order(db, make_user, make_order, p.id, qty=1, price=130)

    proxy = ProxyOrder(order_number='PRX/T1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    pitem = ProxyOrderItem(proxy_order_id=proxy.id, product_id=p.id, quantity=1,
                           unit_price=Decimal('100'), total_price=Decimal('100'))
    db.session.add(pitem)
    db.session.flush()
    pol = PolandOrder(order_number='PRX/PL/T1', proxy_order_id=proxy.id,
                      status='zamowione')
    db.session.add(pol)
    db.session.flush()
    poli = PolandOrderItem(poland_order_id=pol.id, proxy_order_item_id=pitem.id,
                           product_id=p.id, quantity=1)
    db.session.add(poli)
    db.session.commit()

    deadline = (datetime.now() + timedelta(days=7)).isoformat()
    resp = client.put('/admin/products/api/update-poland-customs-vat', json={
        'items': [{'poland_order_item_id': poli.id, 'customs_vat_percentage': 10}],
        'customs_payment_deadline': deadline,
    })

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()['success'] is True

    assert len(email_calls) == 1
    orders_costs, cost_type = email_calls[0]
    assert cost_type == 'customs_vat'
    assert [(ord_.id, amt) for ord_, amt in orders_costs] == [(o.id, 13.0)]
    assert push_calls == [(o.id, 'customs_vat', 13.0)]
