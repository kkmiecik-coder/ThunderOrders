"""Testy E1 mobilnego API: helpery + sklep on-hand (odczyt) + kurs walut."""

from decimal import Decimal


# ---------------------------------------------------------------------------
# Helpery (Task 1)
# ---------------------------------------------------------------------------

def test_to_grosze(app):
    from modules.api_mobile.helpers import to_grosze
    assert to_grosze(Decimal('99.00')) == 9900
    assert to_grosze(Decimal('0.01')) == 1
    assert to_grosze(123.45) == 12345
    assert to_grosze(0) == 0
    assert to_grosze(None) is None


def test_absolute_static_url(app):
    from modules.api_mobile.helpers import absolute_static_url
    with app.test_request_context():
        assert absolute_static_url('uploads/products/x.jpg') == \
            'http://localhost/static/uploads/products/x.jpg'
        assert absolute_static_url('/uploads/p.jpg') == \
            'http://localhost/static/uploads/p.jpg'
        assert absolute_static_url(None) is None
        assert absolute_static_url('') is None


def test_json_page_envelope(app):
    from modules.api_mobile.helpers import json_page
    with app.test_request_context():
        resp, status = json_page([{'id': 1}], page=2, per_page=12, total=25, has_next=True)
        body = resp.get_json()
    assert status == 200
    assert body['success'] is True
    assert body['data'] == [{'id': 1}]
    assert body['pagination'] == {'page': 2, 'per_page': 12, 'total': 25, 'has_next': True}


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


# ---------------------------------------------------------------------------
# GET /shop/products (Task 4)
# ---------------------------------------------------------------------------

def test_shop_products_requires_token(client):
    r = client.get('/api/mobile/v1/shop/products')
    assert r.status_code == 401


def test_shop_products_envelope_and_grosze(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    pt = _onhand_type(db)
    make_product(name='Lalka Mimi', product_type_id=pt.id,
                 sale_price=Decimal('99.00'), quantity=3)
    make_product(name='Poza sklepem', quantity=10)  # bez typu on-hand

    r = client.get('/api/mobile/v1/shop/products', headers=headers)
    assert r.status_code == 200
    body = r.get_json()
    assert body['success'] is True
    assert len(body['data']) == 1
    item = body['data'][0]
    assert item['name'] == 'Lalka Mimi'
    assert item['price'] == 9900           # grosze (int)
    assert item['slug'] == 'lalka-mimi'
    assert item['quantity'] == 3
    assert body['pagination'] == {'page': 1, 'per_page': 12, 'total': 1, 'has_next': False}


def test_shop_products_q_filter_and_sort(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    pt = _onhand_type(db)
    make_product(name='Lalka Mimi', product_type_id=pt.id, sale_price=Decimal('50.00'))
    make_product(name='Figurka Toto', product_type_id=pt.id, sale_price=Decimal('150.00'))

    r = client.get('/api/mobile/v1/shop/products?q=lalka', headers=headers)
    assert [p['name'] for p in r.get_json()['data']] == ['Lalka Mimi']

    r = client.get('/api/mobile/v1/shop/products?sort=price_desc', headers=headers)
    assert [p['price'] for p in r.get_json()['data']] == [15000, 5000]


def test_shop_products_price_filter_in_grosze(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    pt = _onhand_type(db)
    make_product(name='Tani', product_type_id=pt.id, sale_price=Decimal('50.00'))
    make_product(name='Drogi', product_type_id=pt.id, sale_price=Decimal('150.00'))

    # price_min/price_max w groszach — spójnie z resztą kwot w API
    r = client.get('/api/mobile/v1/shop/products?price_min=10000', headers=headers)
    assert [p['name'] for p in r.get_json()['data']] == ['Drogi']


def test_shop_products_pagination(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    pt = _onhand_type(db)
    for i in range(3):
        make_product(product_type_id=pt.id)

    r = client.get('/api/mobile/v1/shop/products?per_page=2&page=1', headers=headers)
    body = r.get_json()
    assert len(body['data']) == 2
    assert body['pagination'] == {'page': 1, 'per_page': 2, 'total': 3, 'has_next': True}

    r2 = client.get('/api/mobile/v1/shop/products?per_page=2&page=2', headers=headers)
    body2 = r2.get_json()
    assert len(body2['data']) == 1
    assert body2['pagination']['has_next'] is False


def test_shop_products_per_page_capped(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    _onhand_type(db)
    r = client.get('/api/mobile/v1/shop/products?per_page=500', headers=headers)
    assert r.get_json()['pagination']['per_page'] == 48


# ---------------------------------------------------------------------------
# GET /shop/products/<id> (Task 5)
# ---------------------------------------------------------------------------

def test_shop_product_detail_not_found(client, db, make_user, make_product):
    headers, _ = _auth(client, db, make_user)
    _onhand_type(db)
    other = make_product()  # bez typu on-hand — niewidoczny w sklepie

    r = client.get(f'/api/mobile/v1/shop/products/{other.id}', headers=headers)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'product_not_found'

    r2 = client.get('/api/mobile/v1/shop/products/999999', headers=headers)
    assert r2.status_code == 404


def test_shop_product_detail_full(client, db, make_user, make_product):
    from modules.products.models import (
        ProductImage, Size, Manufacturer, VariantGroup, variant_products,
        ProductInteraction,
    )
    headers, user = _auth(client, db, make_user)
    pt = _onhand_type(db)
    mfr = Manufacturer(name='Bratz')
    size = Size(name='M')
    db.session.add_all([mfr, size])
    db.session.commit()

    p = make_product(name='Lalka Mimi', product_type_id=pt.id,
                     manufacturer_id=mfr.id, sale_price=Decimal('99.00'),
                     description='Opis lalki')
    p.sizes.append(size)
    db.session.add(ProductImage(
        product_id=p.id, filename='mimi.jpg',
        path_original='uploads/products/mimi_orig.jpg',
        path_compressed='uploads/products/mimi.jpg',
        is_primary=True, sort_order=0,
    ))
    variant = make_product(name='Lalka Mimi Blond', product_type_id=pt.id)
    group = VariantGroup(name='Grupa Mimi')
    db.session.add(group)
    db.session.commit()
    db.session.execute(variant_products.insert().values([
        {'variant_group_id': group.id, 'product_id': p.id},
        {'variant_group_id': group.id, 'product_id': variant.id},
    ]))
    db.session.commit()

    r = client.get(f'/api/mobile/v1/shop/products/{p.id}', headers=headers)
    assert r.status_code == 200
    data = r.get_json()['data']['product']
    assert data['name'] == 'Lalka Mimi'
    assert data['price'] == 9900
    assert data['description'] == 'Opis lalki'
    assert data['brand'] == 'Bratz'
    assert data['sizes'] == ['M']
    assert len(data['images']) == 1
    assert data['images'][0]['url'] == \
        'http://localhost/static/uploads/products/mimi.jpg'
    assert data['images'][0]['is_primary'] is True
    assert [v['name'] for v in data['variants']] == ['Lalka Mimi Blond']

    # Wejście na kartę zapisuje interakcję 'view' (parytet z webem — rekomendacje)
    inter = ProductInteraction.query.filter_by(
        user_id=user.id, product_id=p.id, interaction_type='view').count()
    assert inter == 1


def test_shop_product_detail_requires_token(client, db, make_product):
    p = make_product()
    r = client.get(f'/api/mobile/v1/shop/products/{p.id}')
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /shop/filters (Task 6)
# ---------------------------------------------------------------------------

def test_shop_filters_requires_token(client):
    r = client.get('/api/mobile/v1/shop/filters')
    assert r.status_code == 401


def test_shop_filters_data_in_grosze(client, db, make_user, make_product):
    from modules.products.models import Manufacturer, Size
    headers, _ = _auth(client, db, make_user)
    pt = _onhand_type(db)
    mfr = Manufacturer(name='Bratz')
    size = Size(name='M')
    db.session.add_all([mfr, size])
    db.session.commit()
    p = make_product(product_type_id=pt.id, manufacturer_id=mfr.id,
                     sale_price=Decimal('50.00'))
    p.sizes.append(size)
    make_product(product_type_id=pt.id, sale_price=Decimal('150.00'))
    db.session.commit()

    r = client.get('/api/mobile/v1/shop/filters', headers=headers)
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['categories'] == ['Bratz']
    assert data['sizes'] == ['M']
    assert data['price_min'] == 5000    # grosze
    assert data['price_max'] == 15000   # grosze


def test_shop_filters_empty_catalog(client, db, make_user):
    headers, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/shop/filters', headers=headers)
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data == {'categories': [], 'sizes': [], 'price_min': 0, 'price_max': 0}
