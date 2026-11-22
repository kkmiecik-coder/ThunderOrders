"""Koszyk on-hand: ilość musi być liczbą całkowitą >= 1.

Wcześniej ilość -2 przechodziła sprawdzenie stanu, obniżała sumę zamówienia
i przy checkoucie ZWIĘKSZAŁA stan magazynowy. Walidacja siedzi w serwisie,
więc obejmuje i web, i mobilne API.
"""

from decimal import Decimal

import pytest


def _onhand_type(db):
    from modules.products.models import ProductType
    pt = ProductType.query.filter_by(slug='on-hand').first()
    if not pt:
        pt = ProductType(name='On-hand', slug='on-hand')
        db.session.add(pt)
        db.session.commit()
    return pt


def _onhand_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='on_hand').first()
    if not ot:
        ot = OrderType(slug='on_hand', name='On-hand', prefix='OH')
        db.session.add(ot)
        db.session.commit()
    return ot


def _product(db, make_product, quantity=5):
    pt = _onhand_type(db)
    return make_product(product_type_id=pt.id, sale_price=Decimal('50.00'),
                        quantity=quantity)


# ---------------------------------------------------------------------------
# add_to_cart
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('bad', [-2, 0, -1, 1.5, '1.5', 'abc', None, True, [], {}])
def test_add_to_cart_rejects_invalid_quantity(db, make_user, make_product, bad):
    from modules.client import cart_service
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)

    res = cart_service.add_to_cart(user.id, p.id, bad)

    assert res.ok is False
    assert res.code == 'invalid_quantity'
    assert res.status == 400
    assert CartItem.query.filter_by(user_id=user.id).count() == 0


def test_add_to_cart_negative_does_not_reduce_existing_line(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)
    cart_service.add_to_cart(user.id, p.id, 3)

    res = cart_service.add_to_cart(user.id, p.id, -2)

    assert res.ok is False
    assert CartItem.query.filter_by(user_id=user.id).one().quantity == 3


@pytest.mark.parametrize('good, expected', [(1, 1), (2, 2), ('2', 2), (2.0, 2)])
def test_add_to_cart_accepts_positive_integer(db, make_user, make_product, good, expected):
    from modules.client import cart_service
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)

    res = cart_service.add_to_cart(user.id, p.id, good)

    assert res.ok is True
    assert CartItem.query.filter_by(user_id=user.id).one().quantity == expected


# ---------------------------------------------------------------------------
# update_cart_item (0 / ujemne = usunięcie pozycji — zachowane; ułamki odrzucane)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('bad', [1.5, '2.5', 'abc', None, True])
def test_update_cart_item_rejects_non_integer(db, make_user, make_product, bad):
    from modules.client import cart_service
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)
    cart_service.add_to_cart(user.id, p.id, 2)
    item = CartItem.query.filter_by(user_id=user.id).one()

    res = cart_service.update_cart_item(user.id, item.id, bad)

    assert res.ok is False
    assert res.code == 'invalid_quantity'
    assert CartItem.query.filter_by(user_id=user.id).one().quantity == 2


def test_update_cart_item_negative_never_stored(db, make_user, make_product):
    from modules.client import cart_service
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)
    cart_service.add_to_cart(user.id, p.id, 2)
    item = CartItem.query.filter_by(user_id=user.id).one()

    cart_service.update_cart_item(user.id, item.id, -3)

    assert CartItem.query.filter(CartItem.user_id == user.id,
                                 CartItem.quantity < 1).count() == 0


# ---------------------------------------------------------------------------
# Web API (HTTP)
# ---------------------------------------------------------------------------

def test_web_api_cart_add_negative_quantity_400(client, db, make_user, make_product, login):
    from modules.products.models import CartItem
    user = make_user()
    p = _product(db, make_product)
    login(user)

    r = client.post('/client/shop/api/cart/add',
                    json={'product_id': p.id, 'quantity': -2})

    assert r.status_code == 400
    assert r.get_json()['success'] is False
    assert CartItem.query.filter_by(user_id=user.id).count() == 0


# ---------------------------------------------------------------------------
# Checkout — obrona w głębi: pozycja z ilością < 1 (np. stary rekord w bazie)
# ---------------------------------------------------------------------------

def test_checkout_rejects_non_positive_line_and_keeps_stock(db, make_user, make_product):
    from modules.client import cart_service
    from modules.orders.models import Order
    from modules.products.models import CartItem, Product
    _onhand_order_type(db)
    user = make_user()
    good = _product(db, make_product, quantity=5)
    bad = _product(db, make_product, quantity=5)
    db.session.add(CartItem(user_id=user.id, product_id=good.id, quantity=1))
    db.session.add(CartItem(user_id=user.id, product_id=bad.id, quantity=-2))
    db.session.commit()

    res = cart_service.place_order_on_hand(user.id)

    assert res.ok is False
    assert res.code == 'stock_errors'
    assert any(e['product_id'] == bad.id for e in res.stock_errors)
    assert Order.query.filter_by(user_id=user.id).count() == 0
    assert db.session.get(Product, bad.id).quantity == 5
    assert db.session.get(Product, good.id).quantity == 5
