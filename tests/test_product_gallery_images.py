from decimal import Decimal
from modules.products.models import ProductImage


def _img(product_id, name, sort_order, is_primary=False):
    return ProductImage(
        product_id=product_id,
        filename=name,
        path_original=f'uploads/products/{name}_orig.jpg',
        path_compressed=f'uploads/products/{name}.jpg',
        is_primary=is_primary,
        sort_order=sort_order,
    )


def test_gallery_images_puts_primary_first_then_sort_order(db, make_product):
    p = make_product(name='Album', sale_price=Decimal('150.00'))
    # celowo w złej kolejności; główne (is_primary) to slot #1 = sort_order 1
    db.session.add(_img(p.id, 'b', sort_order=2))
    db.session.add(_img(p.id, 'c', sort_order=3))
    db.session.add(_img(p.id, 'a', sort_order=1, is_primary=True))
    db.session.commit()

    imgs = p.gallery_images

    assert [i.filename for i in imgs] == ['a', 'b', 'c']
    assert imgs[0].is_primary is True


def test_gallery_images_without_primary_sorts_by_sort_order(db, make_product):
    p = make_product(name='Album2', sale_price=Decimal('99.00'))
    db.session.add(_img(p.id, 'y', sort_order=5))
    db.session.add(_img(p.id, 'x', sort_order=2))
    db.session.commit()

    assert [i.filename for i in p.gallery_images] == ['x', 'y']


def test_gallery_images_empty_when_no_images(db, make_product):
    p = make_product(name='Album3', sale_price=Decimal('10.00'))
    assert p.gallery_images == []
