"""Testy serwisu sklepu on-hand (logika współdzielona web + mobile API)."""

from decimal import Decimal


def _onhand_type(db):
    from modules.products.models import ProductType
    pt = ProductType.query.filter_by(slug='on-hand').first()
    if not pt:
        pt = ProductType(name='On-hand', slug='on-hand')
        db.session.add(pt)
        db.session.commit()
    return pt


def test_get_on_hand_type(db):
    from modules.client import shop_service
    assert shop_service.get_on_hand_type() is None
    pt = _onhand_type(db)
    assert shop_service.get_on_hand_type().id == pt.id


def test_build_products_query_basic_visibility(db, make_product):
    from modules.client import shop_service
    pt = _onhand_type(db)
    visible = make_product(product_type_id=pt.id, quantity=5)
    make_product(product_type_id=pt.id, quantity=0)        # brak stanu — ukryty
    make_product(product_type_id=pt.id, is_active=False)   # nieaktywny — ukryty
    make_product(quantity=10)                              # bez typu on-hand — ukryty

    ids = [p.id for p in shop_service.build_products_query(pt).all()]
    assert ids == [visible.id]


def test_build_products_query_search_and_sort(db, make_product):
    from modules.client import shop_service
    pt = _onhand_type(db)
    cheap = make_product(name='Lalka Mimi', product_type_id=pt.id, sale_price=Decimal('50.00'))
    pricey = make_product(name='Figurka Toto', product_type_id=pt.id, sale_price=Decimal('150.00'))

    found = shop_service.build_products_query(pt, search='lalka').all()
    assert [p.id for p in found] == [cheap.id]

    by_price = shop_service.build_products_query(pt, sort='price_asc').all()
    assert [p.id for p in by_price] == [cheap.id, pricey.id]


def test_build_products_query_category_and_price(db, make_product):
    from modules.client import shop_service
    from modules.products.models import Manufacturer
    pt = _onhand_type(db)
    mfr = Manufacturer(name='Bratz')
    db.session.add(mfr)
    db.session.commit()
    branded = make_product(product_type_id=pt.id, manufacturer_id=mfr.id,
                           sale_price=Decimal('80.00'))
    make_product(product_type_id=pt.id, sale_price=Decimal('200.00'))

    by_cat = shop_service.build_products_query(pt, category='Bratz').all()
    assert [p.id for p in by_cat] == [branded.id]

    in_range = shop_service.build_products_query(
        pt, price_min=Decimal('70'), price_max=Decimal('100')).all()
    assert [p.id for p in in_range] == [branded.id]


def test_dedupe_variant_groups(db, make_product):
    from modules.client import shop_service
    from modules.products.models import VariantGroup, variant_products
    _onhand_type(db)
    group = VariantGroup(name='Grupa 1')
    db.session.add(group)
    db.session.commit()
    p1 = make_product()
    p2 = make_product()
    p3 = make_product()
    db.session.execute(variant_products.insert().values([
        {'variant_group_id': group.id, 'product_id': p1.id},
        {'variant_group_id': group.id, 'product_id': p2.id},
    ]))
    db.session.commit()

    out = shop_service.dedupe_variant_groups([p1, p2, p3])
    assert [p.id for p in out] == [p1.id, p3.id]


def test_get_variants(db, make_product):
    from modules.client import shop_service
    from modules.products.models import VariantGroup, variant_products
    pt = _onhand_type(db)
    group = VariantGroup(name='Grupa 1')
    db.session.add(group)
    db.session.commit()
    p1 = make_product(product_type_id=pt.id)
    p2 = make_product(product_type_id=pt.id)
    inactive = make_product(product_type_id=pt.id, is_active=False)
    db.session.execute(variant_products.insert().values([
        {'variant_group_id': group.id, 'product_id': p1.id},
        {'variant_group_id': group.id, 'product_id': p2.id},
        {'variant_group_id': group.id, 'product_id': inactive.id},
    ]))
    db.session.commit()

    variants = shop_service.get_variants(p1)
    assert [v.id for v in variants] == [p2.id]


def test_get_filters_data(db, make_product):
    from modules.client import shop_service
    from modules.products.models import Manufacturer, Size
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

    data = shop_service.get_filters_data()
    assert data['categories'] == ['Bratz']
    assert data['sizes'] == ['M']
    assert data['price_min'] == Decimal('50.00')
    assert data['price_max'] == Decimal('150.00')


def test_get_filters_data_without_on_hand_type(db):
    from modules.client import shop_service
    data = shop_service.get_filters_data()
    assert data == {'categories': [], 'sizes': [], 'price_min': None, 'price_max': None}


def test_get_active_shop_product(db, make_product):
    from modules.client import shop_service
    pt = _onhand_type(db)
    ok = make_product(product_type_id=pt.id)
    sold_out = make_product(product_type_id=pt.id, quantity=0)
    inactive = make_product(product_type_id=pt.id, is_active=False)
    no_type = make_product()

    assert shop_service.get_active_shop_product(ok.id).id == ok.id
    # quantity=0 NIE ukrywa karty produktu (parytet z webem — redirect tylko dla
    # nieaktywnych / nie-on-hand)
    assert shop_service.get_active_shop_product(sold_out.id).id == sold_out.id
    assert shop_service.get_active_shop_product(inactive.id) is None
    assert shop_service.get_active_shop_product(no_type.id) is None
    assert shop_service.get_active_shop_product(999999) is None


def test_slugify(db):
    from modules.client.shop_service import slugify
    assert slugify('Żółta Lalka — edycja спец!') == 'zolta-lalka-edycja'
    assert slugify('Figurka  Toto 2') == 'figurka-toto-2'
