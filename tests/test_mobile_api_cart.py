"""Testy E2: serwis koszyka i checkoutu on-hand (modules/client/cart_service.py).

Sekcja serwisowa — wywołania serwisu wprost (bez HTTP), wewnątrz app context
zapewnionego przez fixturę `app`/`db`. Helpery `_auth`/`_onhand_type` skopiowane
z tests/test_mobile_api_shop.py (przydadzą się testom HTTP w Task 7-9).
"""

from decimal import Decimal


# ---------------------------------------------------------------------------
# Wspólne helpery testów endpointów (JWT + produkty on-hand)
# ---------------------------------------------------------------------------

def _auth(client, db, make_user):
    """Tworzy usera, loguje przez mobile API i zwraca (headers, user)."""
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _onhand_type(db):
    from modules.products.models import ProductType
    pt = ProductType.query.filter_by(slug='on-hand').first()
    if not pt:
        pt = ProductType(name='On-hand', slug='on-hand')
        db.session.add(pt)
        db.session.commit()
    return pt


def _onhand_order_type(db):
    """Seed OrderType('on_hand') wymagany przez generate_order_number przy checkout."""
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='on_hand').first()
    if not ot:
        ot = OrderType(slug='on_hand', name='On-hand', prefix='OH')
        db.session.add(ot)
        db.session.commit()
    return ot


# ---------------------------------------------------------------------------
# Serwis koszyka (Task 4)
# ---------------------------------------------------------------------------

def test_add_to_cart_new_product(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem, ProductInteraction
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('99.00'), quantity=5)

    res = cart_service.add_to_cart(user.id, p.id, 2)

    assert res.ok is True
    assert res.code is None and res.message is None
    assert res.extras['cart_count'] == 2

    items = CartItem.query.filter_by(user_id=user.id, product_id=p.id).all()
    assert len(items) == 1 and items[0].quantity == 2

    interactions = ProductInteraction.query.filter_by(
        user_id=user.id, product_id=p.id, interaction_type='cart_add').count()
    assert interactions == 1


def test_add_to_cart_merges_same_product(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('99.00'), quantity=10)

    cart_service.add_to_cart(user.id, p.id, 2)
    res = cart_service.add_to_cart(user.id, p.id, 3)

    assert res.ok is True
    items = CartItem.query.filter_by(user_id=user.id, product_id=p.id).all()
    assert len(items) == 1 and items[0].quantity == 5
    assert res.extras['cart_count'] == 5


def test_add_to_cart_exceeds_stock(db, make_user, make_product):
    from modules.client import cart_service
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=1)

    res = cart_service.add_to_cart(user.id, p.id, 5)

    assert res.ok is False
    assert res.code == 'exceeds_stock'
    assert res.status == 400
    assert res.extras['available'] == 1


def test_add_to_cart_not_on_hand(db, make_user, make_product):
    from modules.client import cart_service
    _onhand_type(db)
    user = make_user()
    p = make_product(sale_price=Decimal('10.00'), quantity=5)  # brak typu on-hand

    res = cart_service.add_to_cart(user.id, p.id, 1)

    assert res.ok is False
    assert res.code == 'not_on_hand'
    assert res.status == 400


def test_update_cart_item_to_zero_removes(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(user.id, p.id, 2)
    item = CartItem.query.filter_by(user_id=user.id, product_id=p.id).first()

    res = cart_service.update_cart_item(user.id, item.id, 0)

    assert res.ok is True
    assert CartItem.query.filter_by(id=item.id).first() is None


def test_update_cart_item_exceeds_stock(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=3)
    cart_service.add_to_cart(user.id, p.id, 1)
    item = CartItem.query.filter_by(user_id=user.id, product_id=p.id).first()

    res = cart_service.update_cart_item(user.id, item.id, 10)

    assert res.ok is False
    assert res.code == 'exceeds_stock'
    assert res.status == 400
    assert res.extras['available'] == 3


def test_update_cart_item_other_user_not_found(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    pt = _onhand_type(db)
    owner = make_user()
    intruder = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(owner.id, p.id, 1)
    item = CartItem.query.filter_by(user_id=owner.id, product_id=p.id).first()

    res = cart_service.update_cart_item(intruder.id, item.id, 1)

    assert res.ok is False
    assert res.code == 'item_not_found'
    assert res.status == 404


def test_remove_cart_item_other_user_not_found(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    pt = _onhand_type(db)
    owner = make_user()
    intruder = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(owner.id, p.id, 1)
    item = CartItem.query.filter_by(user_id=owner.id, product_id=p.id).first()

    res = cart_service.remove_cart_item(intruder.id, item.id)

    assert res.ok is False
    assert res.code == 'item_not_found'
    assert res.status == 404
    # pozycja właściciela nietknięta
    assert CartItem.query.filter_by(id=item.id).first() is not None


def test_build_cart_data_structure(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import Size
    pt = _onhand_type(db)
    user = make_user()
    size = Size(name='M')
    db.session.add(size)
    db.session.commit()
    p = make_product(name='Lalka Mimi', product_type_id=pt.id,
                     sale_price=Decimal('99.00'), quantity=5)
    p.sizes.append(size)
    db.session.commit()
    cart_service.add_to_cart(user.id, p.id, 2)

    cart_data, total, count = cart_service.build_cart_data(user.id)

    assert count == 2
    assert total == 198.00
    assert len(cart_data) == 1
    entry = cart_data[0]
    assert set(entry.keys()) == {
        'id', 'product_id', 'name', 'price', 'quantity', 'available',
        'image_url', 'is_available', 'slug', 'size',
    }
    assert entry['product_id'] == p.id
    assert entry['name'] == 'Lalka Mimi'
    assert entry['price'] == 99.00
    assert entry['quantity'] == 2
    assert entry['available'] == 5
    assert entry['image_url'] is None
    assert entry['is_available'] is True
    assert entry['slug'] == 'lalka-mimi'
    assert entry['size'] == 'M'


# ---------------------------------------------------------------------------
# Serwis checkoutu (Task 5)
# ---------------------------------------------------------------------------

def test_place_order_happy_path(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import Size, CartItem, ProductInteraction
    from modules.orders.models import Order, OrderItem
    pt = _onhand_type(db)
    _onhand_order_type(db)
    user = make_user()
    size = Size(name='M')
    db.session.add(size)
    db.session.commit()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('99.00'), quantity=5)
    p.sizes.append(size)
    db.session.commit()
    cart_service.add_to_cart(user.id, p.id, 2)

    res = cart_service.place_order_on_hand(user.id)

    assert res.ok is True
    assert res.code is None
    order = res.order
    assert order is not None
    assert order.order_type == 'on_hand'
    assert order.status == 'nowe'
    assert order.payment_stages == 2

    order_items = OrderItem.query.filter_by(order_id=order.id).all()
    assert len(order_items) == 1
    assert order_items[0].selected_size == 'M'
    assert order_items[0].quantity == 2

    # stock zmniejszony
    db.session.refresh(p)
    assert p.quantity == 3

    # koszyk wyczyszczony
    assert CartItem.query.filter_by(user_id=user.id).count() == 0

    # interakcja purchase
    assert ProductInteraction.query.filter_by(
        user_id=user.id, product_id=p.id, interaction_type='purchase').count() == 1

    # komplet extras
    assert res.extras['order_number']
    assert res.extras['total_amount'] == 198.00
    assert res.extras['items_count'] == 2
    assert res.extras['ga_items']
    assert res.extras['shipping_request_number'] is None
    assert order.order_number == res.extras['order_number']


def test_place_order_empty_cart(db, make_user):
    from modules.client import cart_service
    _onhand_type(db)
    user = make_user()

    res = cart_service.place_order_on_hand(user.id)

    assert res.ok is False
    assert res.code == 'cart_empty'
    assert res.status == 400


def test_place_order_stock_too_small(db, make_user, make_product):
    from modules.client import cart_service
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(user.id, p.id, 5)

    # ktoś wykupił stock po dodaniu do koszyka
    p.quantity = 2
    db.session.commit()

    res = cart_service.place_order_on_hand(user.id)

    assert res.ok is False
    assert res.code == 'stock_errors'
    assert res.status == 400
    assert isinstance(res.stock_errors, list) and len(res.stock_errors) == 1
    assert res.stock_errors[0]['product_id'] == p.id
    assert res.stock_errors[0]['available'] == 2


def test_place_order_shipping_without_address_id(db, make_user, make_product):
    from modules.client import cart_service
    pt = _onhand_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(user.id, p.id, 1)

    res = cart_service.place_order_on_hand(user.id, create_shipping=True, address_id=None)

    assert res.ok is False
    assert res.code == 'address_required'
    assert res.status == 400
    assert res.message == 'Wybierz adres dostawy.'


def test_place_order_with_shipping_request(db, make_user, make_product):
    from modules.client import cart_service
    from modules.auth.models import ShippingAddress
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    pt = _onhand_type(db)
    _onhand_order_type(db)
    user = make_user()
    p = make_product(product_type_id=pt.id, sale_price=Decimal('10.00'), quantity=5)
    cart_service.add_to_cart(user.id, p.id, 1)

    addr = ShippingAddress(
        user_id=user.id,
        address_type='home',
        name='Dom',
        shipping_name='Jan Kowalski',
        shipping_address='ul. Testowa 1',
        shipping_postal_code='00-001',
        shipping_city='Warszawa',
        shipping_voivodeship='mazowieckie',
        shipping_country='Polska',
        is_active=True,
    )
    db.session.add(addr)
    db.session.commit()

    res = cart_service.place_order_on_hand(user.id, create_shipping=True, address_id=addr.id)

    assert res.ok is True
    assert res.extras['shipping_request_number']

    sr = ShippingRequest.query.filter_by(
        request_number=res.extras['shipping_request_number']).first()
    assert sr is not None
    assert sr.user_id == user.id
    assert sr.shipping_city == 'Warszawa'

    sro = ShippingRequestOrder.query.filter_by(
        shipping_request_id=sr.id, order_id=res.order.id).first()
    assert sro is not None
