"""Testy rozróżnienia NULL (cło nieustalone) od 0 (cło ustalone na zero)."""
from decimal import Decimal


def test_new_order_has_null_customs_by_default(db, make_user, make_order):
    # NULL = "jeszcze nie ustalono"; wcześniej domyślną wartością było 0.00
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None


def test_order_accepts_explicit_zero(db, make_user, make_order):
    # 0 = "ustalono: bez podatku" — musi dać się zapisać i odczytać jako zero, nie NULL
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is not None
    assert o.customs_vat_sale_cost == 0


def test_poland_order_item_customs_defaults_to_null(db, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem
    p = make_product()
    proxy = ProxyOrder(order_number='PRX/TEST/1', order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=p.id,
                                quantity=1, unit_price=10, total_price=10)
    db.session.add(proxy_item)
    db.session.flush()
    po = PolandOrder(order_number='PL/TEST/1', proxy_order_id=proxy.id, status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                           product_id=p.id, quantity=1)
    db.session.add(item)
    db.session.commit()
    assert item.customs_vat_percentage is None
    assert item.customs_vat_amount is None


def test_stage_keys_omit_customs_when_zero(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in order_stage_keys(o)


def test_stage_keys_include_customs_when_null(db, make_user, make_order):
    # NULL = nie ustalono → etap nadal obecny (klient widzi "Zablokowane")
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert 'customs_vat' in order_stage_keys(o)


def test_stage_keys_include_customs_when_positive(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert 'customs_vat' in order_stage_keys(o)


def test_upload_rejected_for_zero_customs(db, make_user, make_order):
    # Brak etapu → brak możliwości opłacenia (wymóg właścicielki)
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    ok, err = validate_bulk_upload(u.id, [{'order_id': o.id, 'stages': ['customs_vat']}])
    assert not ok and err['code'] == 'stage_not_applicable'


def test_mobile_stages_omit_customs_when_zero(db, make_user, make_order):
    # API mobilne czyta order_stage_keys — zmiana propaguje się bez osobnego kodu
    from modules.api_mobile.orders_routes import _serialize_payment_stages
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in [s['stage'] for s in _serialize_payment_stages(o)]


def test_settled_false_when_customs_not_set(db, make_user, make_order):
    # Decyzja właścicielki: dopóki cło nie jest ustalone, wysyłki zlecić nie można
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert o.is_customs_vat_settled is False


def test_settled_true_when_customs_zero(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert o.is_customs_vat_settled is True


def test_settled_false_when_customs_due_unpaid(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert o.is_customs_vat_settled is False


def test_settled_true_for_on_hand_regardless(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='on_hand')
    assert o.is_customs_vat_settled is True


def test_shipping_blocked_with_not_set_code(db, make_user, make_order):
    # "Nieustalone" musi mieć własny kod — komunikat "opłać" byłby mylący,
    # bo klient nie ma czego opłacić
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive')
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_not_set'
    assert o.id in err['customs_vat_not_set_order_ids'] and req is None


def test_shipping_allowed_when_customs_zero(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('0.00'))
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert ok and req is not None


def test_shipping_unpaid_code_unchanged_for_due_customs(db, make_user, make_order):
    # Kwota > 0 nieopłacona → nadal stary kod, bez zmiany zachowania
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('50.00'))
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_unpaid'


def _client_order_with_product(db, make_user, make_order, make_product, price, qty=1):
    """Zamówienie klienta z jedną pozycją danego produktu — wspólne dla testów dystrybucji."""
    from modules.orders.models import OrderItem
    from modules.offers.models import OfferPage
    u = make_user()
    admin = make_user(role='admin')
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.flush()
    p = make_product()
    o = make_order(u, order_type='exclusive', offer_page_id=page.id)
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=price, total=price * qty))
    db.session.commit()
    return o, p


def test_zero_percentage_clears_client_amount(db, make_user, make_order, make_product):
    # Scenariusz właścicielki: najpierw 23%, potem poprawka na "bez podatku"
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)

    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0          # zero, nie NULL — to zapisana decyzja
    assert o.customs_vat_sale_cost is not None


def test_zeroing_sends_no_notifications(db, make_user, make_order, make_product, monkeypatch):
    # Decyzja właścicielki: przy zejściu kwoty do zera nie wysyłamy nic
    from modules.products import routes as product_routes
    sent = []
    monkeypatch.setattr('utils.email_manager.EmailManager.notify_costs_added_bulk',
                        lambda *a, **kw: sent.append('email'), raising=False)
    product_routes._notify_distributed_costs({1: {'old': 230.0, 'new': 0.0}}, 'customs_vat')
    assert sent == []


def test_zero_customs_order_reaches_fully_paid(db, make_user, make_order):
    # Zamówienie bez cła nie może wisieć w "do zapłaty" czekając na wpłatę, której nie ma
    from modules.orders.models import PaymentConfirmation
    from modules.offers.models import OfferPage
    from modules.client.payment_confirmation_service import get_confirmation_orders
    u = make_user()
    admin = make_user(role='admin')
    # get_confirmation_orders bierze pod uwagę tylko zamówienia z oferty (offer_page_id)
    # albo on_hand — bez strony oferty zamówienie nie trafia do żadnego koszyka.
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.commit()
    o = make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
                   offer_page_id=page.id,
                   customs_vat_sale_cost=Decimal('0.00'), shipping_cost=Decimal('15.00'))
    for stage in ('product', 'domestic_shipping'):
        db.session.add(PaymentConfirmation(order_id=o.id, payment_stage=stage,
                                           amount=Decimal('10.00'), status='approved'))
    db.session.commit()
    buckets = get_confirmation_orders(u.id)
    assert o.id in [x.id for x in buckets['recent_paid']]
    assert o.id not in [x.id for x in buckets['payable']]


def test_positive_rate_does_not_clear_unfulfilled_item(db, make_user, make_order, make_product):
    # Decyzja właścicielki: zwykła korekta stawki nie może kasować kwoty
    # na pozycji, której klient i tak nie dostaje
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    o.items[0].is_set_fulfilled = False          # klient jednak nie dostaje tej pozycji
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('25')})   # korekta stawki
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')   # kwota nietknięta


def test_zero_rate_clears_even_unfulfilled_item(db, make_user, make_order, make_product):
    # Stawka 0 = "bez podatku" — zeruje niezależnie od realizacji pozycji
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    o.items[0].is_set_fulfilled = False
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0


def _poland_setup(db, order, product, percentage):
    """Paczka do Polski z jedną pozycją — minimalne dane dla endpointu cła."""
    from modules.products.models import (PolandOrder, PolandOrderItem,
                                          ProxyOrder, ProxyOrderItem)
    proxy = ProxyOrder(order_number=f'PRX/T/{order.id}',
                       order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    pi = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                        quantity=1, unit_price=10, total_price=10)
    db.session.add(pi)
    db.session.flush()
    po = PolandOrder(order_number=f'PL/T/{order.id}', proxy_order_id=proxy.id,
                     status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=pi.id,
                           product_id=product.id, quantity=1,
                           customs_vat_percentage=percentage)
    db.session.add(item)
    db.session.commit()
    return po, item


DEADLINE = '2026-12-31T23:59'   # termin w przyszłości — endpoint go dziś wymaga


def _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                              login, stage3_status):
    """Wspólny scenariusz: cło 230 zł opłacone/oczekujące, próba zejścia do zera."""
    from modules.orders.models import PaymentConfirmation
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    o.customs_vat_sale_cost = Decimal('230.00')
    db.session.add(PaymentConfirmation(order_id=o.id, payment_stage='customs_vat',
                                       amount=Decimal('230.00'), status=stage3_status))
    _, item = _poland_setup(db, o, p, Decimal('23'))
    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'customs_payment_deadline': DEADLINE})
    return o, r


def test_zeroing_blocked_when_stage3_approved(client, db, make_user, make_order,
                                              make_product, login):
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'approved')
    assert r.status_code == 409
    assert r.get_json()['success'] is False
    assert o.order_number in r.get_json()['error']


def test_zeroing_blocked_when_stage3_pending(client, db, make_user, make_order,
                                             make_product, login):
    # Wgrane potwierdzenie = przelew najpewniej już wyszedł
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'pending')
    assert r.status_code == 409


def test_zeroing_allowed_when_stage3_untouched(client, db, make_user, make_order,
                                               make_product, login):
    # Brak potwierdzenia → wyzerowanie przechodzi normalnie
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'rejected')
    assert r.status_code == 200 and r.get_json()['success'] is True


def test_no_customs_saves_zero_not_null(client, db, make_user, make_order,
                                        make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'no_customs': True})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item)
    assert item.customs_vat_percentage == 0        # zapisana decyzja, nie brak decyzji
    assert item.customs_vat_percentage is not None
    assert item.customs_vat_amount == 0


def test_no_customs_clears_payment_deadline(client, db, make_user, make_order,
                                            make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, Decimal('23'))
    from datetime import datetime
    po.customs_payment_deadline = datetime(2026, 12, 31, 23, 59)
    db.session.commit()

    client.put('/admin/products/api/update-poland-customs-vat',
               json={'items': [{'poland_order_item_id': item.id,
                                'customs_vat_percentage': 0}],
                     'no_customs': True})
    db.session.refresh(po)
    assert po.customs_payment_deadline is None     # nie ma płatności → nie ma terminu


def test_deadline_still_required_with_customs(client, db, make_user, make_order,
                                              make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 23}]})
    assert r.status_code == 400
    assert 'Termin' in r.get_json()['error']
