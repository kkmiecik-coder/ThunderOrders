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
