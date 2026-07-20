"""Testy rozszerzenia PackagingMaterial o cenę sprzedaży i gabaryt."""


def test_sale_price_and_size_category_persist(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Karton A', type='karton',
                          sale_price=19.49, size_category='A')
    db.session.add(m)
    db.session.commit()
    db.session.refresh(m)
    assert float(m.sale_price) == 19.49
    assert m.size_category == 'A'


def test_size_display_maps_known_and_unknown(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Koperta Mini', type='koperta', size_category='mini')
    assert m.size_display == 'Mini'
    m2 = PackagingMaterial(name='Bez gabarytu', type='karton', size_category=None)
    assert m2.size_display is None


def test_size_choices_contains_expected_keys(db):
    from modules.orders.wms_models import PackagingMaterial
    assert set(PackagingMaterial.SIZE_CHOICES.keys()) == {'mini', 'A', 'B', 'C'}
