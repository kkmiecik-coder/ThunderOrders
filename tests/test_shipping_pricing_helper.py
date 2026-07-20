"""Helper cennika liczony z aktywnych materiałów."""


def test_pricing_min_and_rows(db):
    from modules.orders.wms_models import PackagingMaterial
    from modules.client.shipping_service import get_shipping_pricing
    db.session.add_all([
        PackagingMaterial(name='Koperta Mini', type='koperta', sale_price=12.99,
                          size_category='mini', is_active=True),
        PackagingMaterial(name='Karton A', type='karton', sale_price=19.49,
                          size_category='A', is_active=True),
        PackagingMaterial(name='Nieaktywny', type='karton', sale_price=5.00,
                          size_category='A', is_active=False),   # pominięty
        PackagingMaterial(name='Bez ceny', type='karton', sale_price=None,
                          size_category='B', is_active=True),    # pominięty
    ])
    db.session.commit()
    p = get_shipping_pricing()
    assert p['min_price'] == 12.99
    names = [(r['size_display'], r['type_display'], r['sale_price']) for r in p['rows']]
    assert ('Mini', 'Koperta', 12.99) in names
    assert ('Gabaryt A', 'Karton', 19.49) in names
    assert all(r['sale_price'] != 5.00 for r in p['rows'])       # nieaktywny pominięty
    assert p['rows'][0]['sale_price'] <= p['rows'][-1]['sale_price']  # sortowanie rosnąco


def test_pricing_empty_when_no_materials(db):
    from modules.client.shipping_service import get_shipping_pricing
    p = get_shipping_pricing()
    assert p == {'min_price': None, 'rows': []}
