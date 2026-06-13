"""Testy serwisu place_preorder_order (E4 Task 1, pierwsze pokrycie).

Wołają serwis WPROST (bez HTTP), przekazując jawny parametr `user` — regresja
chroniąca refaktor `current_user` -> `user`.
"""
from decimal import Decimal


def _po_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='pre_order').first()
    if not ot:
        ot = OrderType(slug='pre_order', name='Pre-order', prefix='PO')
        db.session.add(ot); db.session.commit()
    return ot


def _preorder_page(db, payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Preorder Drop', token=OfferPage.generate_token(), status='active',
                  page_type='preorder', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _product_section(db, page, product):
    """Sekcja 'product' wiążąca produkt ze stroną (zamawialny na pre-order)."""
    from modules.offers.models import OfferSection
    s = OfferSection(offer_page_id=page.id, section_type='product',
                     product_id=product.id, sort_order=0)
    db.session.add(s); db.session.commit()
    return s


def test_place_preorder_happy_path(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()  # created_by=1 istnieje
    page = _preorder_page(db, payment_stages=3)
    prod = make_product(sale_price=Decimal('50.00'))
    _product_section(db, page, prod)
    cart = [{'product_id': prod.id, 'quantity': 2}]

    ok, result = place_preorder_order(page=page, cart_items=cart, order_note='hej', user=user)

    assert ok is True
    order = db.session.get(Order, result['order_id'])
    assert order.order_type == 'pre_order'
    assert order.user_id == user.id
    assert order.payment_stages == 3
    assert order.status == 'nowe'
    assert order.order_number.startswith('PO/')
    assert float(order.total_amount) == 100.0
    assert result['items_count'] == 2
    assert OrderItem.query.filter_by(order_id=order.id).count() == 1


def test_place_preorder_empty_cart(db, make_user):
    from modules.offers.place_order import place_preorder_order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    ok, result = place_preorder_order(page=page, cart_items=[], user=user)
    assert ok is False
    assert result['error'] == 'empty_cart'


def test_place_preorder_size_required(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    from modules.products.models import Size
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    _product_section(db, page, prod)
    size = Size(name='M'); db.session.add(size); db.session.commit()
    prod.sizes.append(size); db.session.commit()
    cart = [{'product_id': prod.id, 'quantity': 1}]  # brak selected_size
    ok, result = place_preorder_order(page=page, cart_items=cart, user=user)
    assert ok is False
    assert result['error'] == 'size_required'
    assert result['product_name'] == prod.name


def test_place_preorder_bonus_quantity_threshold(db, make_user, make_product):
    """Sekcja 'bonus' + trigger quantity_threshold: kup >=2 szt -> +1 gratis (is_bonus)."""
    from modules.offers.place_order import place_preorder_order
    from modules.offers.models import OfferSection, OfferSetBonus
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    gift = make_product(sale_price=Decimal('5.00'))  # bonus dodaje serwis — bez sekcji
    _product_section(db, page, prod)
    sec = OfferSection(offer_page_id=page.id, section_type='bonus', sort_order=0)
    db.session.add(sec); db.session.commit()
    bonus = OfferSetBonus(section_id=sec.id, trigger_type='quantity_threshold',
                          threshold_value=Decimal('2'), bonus_product_id=gift.id,
                          bonus_quantity=1, repeatable=False, is_active=True,
                          when_exhausted='hide')
    db.session.add(bonus); db.session.commit()
    cart = [{'product_id': prod.id, 'quantity': 2}]

    ok, result = place_preorder_order(page=page, cart_items=cart, user=user)

    assert ok is True
    order = db.session.get(Order, result['order_id'])
    bonus_items = OrderItem.query.filter_by(order_id=order.id, is_bonus=True).all()
    assert len(bonus_items) == 1
    assert bonus_items[0].product_id == gift.id
    assert bonus_items[0].quantity == 1
    assert result['items_count'] == 2  # bonus nie wlicza się do items_count


def test_preorder_database_error_is_logged_and_generic(app, db, make_user, make_product, monkeypatch):
    """Padły commit: rollback, stały komunikat (bez szczegółów SQL/constraintów)."""
    from modules.offers.place_order import place_preorder_order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('50.00'))
    _product_section(db, page, prod)

    real_commit = db.session.commit
    state = {'armed': False}

    def boom():
        if state['armed']:
            raise RuntimeError('SQL: INSERT INTO orders ... constraint uq_secret')
        return real_commit()

    monkeypatch.setattr(db.session, 'commit', boom)
    state['armed'] = True
    with app.test_request_context():
        ok, result = place_preorder_order(
            page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=user)
    state['armed'] = False

    assert ok is False
    assert result['error'] == 'database_error'
    assert 'SQL' not in result.get('message', '') and 'uq_secret' not in result.get('message', '')


# ---------------------------------------------------------------------------
# Przynależność produktu do strony (pre-order tylko na produkty z oferty)
# ---------------------------------------------------------------------------

def test_place_preorder_skips_product_outside_offer(db, make_user, make_product):
    """Produkt spoza sekcji strony jest pomijany — zamówienie tylko z prawidłowych."""
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    in_offer = make_product(sale_price=Decimal('50.00'))
    foreign = make_product(sale_price=Decimal('30.00'))  # NIE jest w żadnej sekcji strony
    _product_section(db, page, in_offer)
    cart = [{'product_id': in_offer.id, 'quantity': 1},
            {'product_id': foreign.id, 'quantity': 3}]

    ok, result = place_preorder_order(page=page, cart_items=cart, user=user)

    assert ok is True
    order = db.session.get(Order, result['order_id'])
    assert float(order.total_amount) == 50.0
    items = OrderItem.query.filter_by(order_id=order.id).all()
    assert [i.product_id for i in items] == [in_offer.id]
    assert result['items_count'] == 1


def test_place_preorder_only_foreign_products_empty_cart(db, make_user, make_product):
    """Sam obcy produkt -> empty_cart, zero zamówień w bazie."""
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    foreign = make_product(sale_price=Decimal('30.00'))  # bez sekcji
    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': foreign.id, 'quantity': 1}], user=user)
    assert ok is False
    assert result['error'] == 'empty_cart'
    assert Order.query.filter_by(order_type='pre_order').count() == 0


def test_place_preorder_variant_group_product_allowed(db, make_user, make_product):
    """Produkt z grupy wariantowej sekcji variant_group jest zamawialny."""
    from modules.offers.place_order import place_preorder_order
    from modules.offers.models import OfferSection
    from modules.products.models import VariantGroup
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('20.00'))
    vg = VariantGroup(name='Kolory'); db.session.add(vg); db.session.commit()
    vg.products.append(prod); db.session.commit()
    sec = OfferSection(offer_page_id=page.id, section_type='variant_group',
                       variant_group_id=vg.id, sort_order=0)
    db.session.add(sec); db.session.commit()

    ok, result = place_preorder_order(
        page=page, cart_items=[{'product_id': prod.id, 'quantity': 1}], user=user)

    assert ok is True
    assert result['items_count'] == 1
    assert float(result['total_amount']) == 20.0
