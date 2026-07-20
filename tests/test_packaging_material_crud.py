"""Testy CRUD materiałów opakowaniowych z ceną sprzedaży i gabarytem."""


def _admin(make_user):
    return make_user(role='admin')


def test_create_persists_sale_price_and_size(client, db, make_user, login):
    login(_admin(make_user))
    r = client.post('/admin/orders/packaging-materials/create', json={
        'name': 'Karton A', 'type': 'karton', 'sale_price': 19.49, 'size_category': 'A',
    })
    assert r.status_code == 200 and r.get_json()['success']
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial.query.filter_by(name='Karton A').first()
    assert float(m.sale_price) == 19.49 and m.size_category == 'A'


def test_create_rejects_bad_size_category(client, db, make_user, login):
    login(_admin(make_user))
    r = client.post('/admin/orders/packaging-materials/create', json={
        'name': 'Zły gabaryt', 'type': 'karton', 'size_category': 'XL',
    })
    assert r.status_code == 200
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial.query.filter_by(name='Zły gabaryt').first()
    assert m.size_category is None  # niepoprawny gabaryt odrzucony → None


def test_get_and_list_expose_new_fields(client, db, make_user, login):
    login(_admin(make_user))
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Koperta Mini', type='koperta',
                          sale_price=12.99, size_category='mini', is_active=True)
    db.session.add(m); db.session.commit()

    g = client.get(f'/api/orders/packaging-materials/{m.id}').get_json()['material']
    assert g['sale_price'] == 12.99 and g['size_category'] == 'mini'

    lst = client.get('/api/orders/packaging-materials').get_json()['materials']
    row = next(x for x in lst if x['id'] == m.id)
    assert row['sale_price'] == 12.99 and row['size_category'] == 'mini'
    assert row['size_display'] == 'Mini'
