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


def _entry(name):
    return {
        'src': f'uploads/offers/{name}.jpg',
        'full': f'uploads/offers/{name}_orig.jpg',
        'alt': name,
    }


def test_wspolny_partial_renderuje_galerie_dla_wielu_zdjec(app):
    with app.test_request_context():
        html = render_template('offers/_gallery.html',
                               gallery_images=[_entry('a'), _entry('b'), _entry('c')])

    assert 'data-gallery' in html
    assert html.count('gallery-thumb') >= 3
    assert 'gallery-chevron-prev' in html
    assert 'gallery-main-image' in html


def test_wspolny_partial_dla_jednego_zdjecia_nie_robi_paska(app):
    with app.test_request_context():
        html = render_template('offers/_gallery.html', gallery_images=[_entry('solo')])

    assert 'data-gallery' not in html
    assert 'zoomable-image-wrapper' in html


def test_wspolny_partial_bez_zdjec_domyslnie_nic_nie_renderuje(app):
    with app.test_request_context():
        html = render_template('offers/_gallery.html', gallery_images=[])

    # Żadna gałąź (galeria/pojedyncze zdjęcie/placeholder) się nie uruchamia —
    # po odcięciu białych znaków z {% set %} zostaje pusty string.
    assert html.strip() == ''


def test_wspolny_partial_pokazuje_placeholder_na_zadanie(app):
    with app.test_request_context():
        html = render_template('offers/_gallery.html', gallery_images=[],
                               gallery_show_placeholder=True)

    assert 'no-image' in html


def test_pojedyncze_zdjecie_produktu_ma_alt_bez_numeru(app, db, make_product):
    p = make_product(name='Solo', sale_price=Decimal('50.00'))
    db.session.add(_img(p.id, 'only', 1, is_primary=True))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'alt="Solo"' in html
    assert 'Solo — 1' not in html


def test_duze_zdjecie_w_galerii_ma_alt_bez_numeru(app, db, make_product):
    p = make_product(name='Album', sale_price=Decimal('150.00'))
    db.session.add(_img(p.id, 'a', 1, is_primary=True))
    db.session.add(_img(p.id, 'b', 2))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    # duże zdjęcie: alt bez numeru; miniatury: alt numerowane
    assert 'class="product-image-centered gallery-main-image"' in html
    assert 'alt="Album" class="product-image-centered gallery-main-image"' in html
    assert 'alt="Album — 1"' in html
    assert 'alt="Album — 2"' in html
