from flask import render_template
from modules.offers.models import OfferPage, OfferSection, OfferSectionImage


def _page_z_sekcja_zdjeciowa(db, make_user, paths):
    autor = make_user(role='admin', email=f'autor-{OfferPage.generate_token()[:8]}@example.com')
    page = OfferPage(name='Drop ze zdjęciami', token=OfferPage.generate_token(),
                     status='active', created_by=autor.id)
    db.session.add(page)
    db.session.flush()
    section = OfferSection(offer_page_id=page.id, section_type='image', sort_order=0)
    db.session.add(section)
    db.session.flush()
    for idx, path in enumerate(paths):
        db.session.add(OfferSectionImage(section_id=section.id, path=path, sort_order=idx))
    db.session.commit()
    return page, section


def test_exclusive_renderuje_galerie_dla_wielu_zdjec(app, db, make_user):
    page, section = _page_z_sekcja_zdjeciowa(db, make_user, [
        'uploads/offers/a.jpg', 'uploads/offers/b.jpg',
    ])

    with app.test_request_context():
        html = render_template('offers/order_page.html', page=page, sections=[section],
                               bonuses_config_json='{}')

    assert 'image-section' in html
    assert 'data-gallery' in html
    assert 'uploads/offers/a.jpg' in html
    assert 'uploads/offers/b.jpg' in html


def test_preorder_renderuje_pojedyncze_zdjecie_bez_paska(app, db, make_user):
    page, section = _page_z_sekcja_zdjeciowa(db, make_user, ['uploads/offers/solo.jpg'])
    page.page_type = 'preorder'
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/order_page_preorder.html', page=page, sections=[section],
                               bonuses_config_json='{}')

    assert 'image-section' in html
    assert 'data-gallery' not in html
    assert 'zoomable-image-wrapper' in html


def test_sekcja_bez_zdjec_nie_renderuje_pustego_kontenera(app, db, make_user):
    page, section = _page_z_sekcja_zdjeciowa(db, make_user, [])

    with app.test_request_context():
        html = render_template('offers/order_page.html', page=page, sections=[section],
                               bonuses_config_json='{}')

    assert 'image-section' not in html
    assert 'no-image' not in html


def test_podglad_countdown_pokazuje_pierwsze_zdjecie_bez_galerii(app, db, make_user):
    page, section = _page_z_sekcja_zdjeciowa(db, make_user, [
        'uploads/offers/pierwsza.jpg', 'uploads/offers/druga.jpg',
    ])

    with app.test_request_context():
        html = render_template('offers/_preview_sections.html', sections=[section])

    assert 'preview-image' in html
    assert 'uploads/offers/pierwsza.jpg' in html
    assert 'data-gallery' not in html
    assert 'uploads/offers/druga.jpg' not in html
