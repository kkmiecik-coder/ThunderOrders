from decimal import Decimal
from flask import render_template
from modules.products.models import ProductImage


def _img(product_id, name, sort_order, is_primary=False):
    return ProductImage(
        product_id=product_id, filename=name,
        path_original=f'uploads/products/{name}_orig.jpg',
        path_compressed=f'uploads/products/{name}.jpg',
        is_primary=is_primary, sort_order=sort_order,
    )


def test_gallery_partial_renders_strip_for_multiple_images(app, db, make_product):
    p = make_product(name='Album', sale_price=Decimal('150.00'))
    db.session.add(_img(p.id, 'a', 1, is_primary=True))
    db.session.add(_img(p.id, 'b', 2))
    db.session.add(_img(p.id, 'c', 3))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'data-gallery' in html
    assert html.count('gallery-thumb') >= 3
    assert 'gallery-chevron-prev' in html
    assert 'gallery-main-image' in html


def test_gallery_partial_single_image_has_no_strip(app, db, make_product):
    p = make_product(name='Solo', sale_price=Decimal('50.00'))
    db.session.add(_img(p.id, 'only', 1, is_primary=True))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'data-gallery' not in html
    assert 'zoomable-image-wrapper' in html


def test_gallery_partial_no_images_shows_placeholder(app, db, make_product):
    p = make_product(name='Pusty', sale_price=Decimal('50.00'))

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'no-image' in html
    assert 'data-gallery' not in html
