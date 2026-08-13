from modules.offers.models import OfferPage, OfferSection, OfferSectionImage


def _page(db, make_user):
    autor = make_user(role='admin', email=f'autor-{OfferPage.generate_token()[:8]}@example.com')
    page = OfferPage(name='Drop ze zdjęciami', token=OfferPage.generate_token(),
                     status='draft', created_by=autor.id)
    db.session.add(page)
    db.session.commit()
    return page


def _section_with_images(db, page, paths):
    section = OfferSection(offer_page_id=page.id, section_type='image', sort_order=0)
    db.session.add(section)
    db.session.flush()
    for idx, path in enumerate(paths):
        db.session.add(OfferSectionImage(section_id=section.id, path=path, sort_order=idx))
    db.session.commit()
    return section


def test_sekcja_image_zwraca_zdjecia_w_kolejnosci(db, make_user):
    page = _page(db, make_user)
    section = _section_with_images(db, page, [
        'uploads/offers/a.jpg', 'uploads/offers/b.jpg', 'uploads/offers/c.jpg',
    ])

    assert section.is_image is True
    assert [img.path for img in section.get_images_ordered()] == [
        'uploads/offers/a.jpg', 'uploads/offers/b.jpg', 'uploads/offers/c.jpg',
    ]


def test_kolejnosc_wynika_z_sort_order_a_nie_z_id(db, make_user):
    page = _page(db, make_user)
    section = OfferSection(offer_page_id=page.id, section_type='image', sort_order=0)
    db.session.add(section)
    db.session.flush()
    # wstawiane odwrotnie do docelowej kolejności
    db.session.add(OfferSectionImage(section_id=section.id, path='uploads/offers/druga.jpg', sort_order=1))
    db.session.add(OfferSectionImage(section_id=section.id, path='uploads/offers/pierwsza.jpg', sort_order=0))
    db.session.commit()

    assert [img.path for img in section.get_images_ordered()] == [
        'uploads/offers/pierwsza.jpg', 'uploads/offers/druga.jpg',
    ]


def test_usuniecie_sekcji_kasuje_jej_zdjecia(db, make_user):
    page = _page(db, make_user)
    section = _section_with_images(db, page, ['uploads/offers/a.jpg', 'uploads/offers/b.jpg'])
    section_id = section.id

    db.session.delete(section)
    db.session.commit()

    pozostale = OfferSectionImage.query.filter_by(section_id=section_id).all()
    assert pozostale == []


def test_inne_typy_sekcji_nie_sa_image(db, make_user):
    page = _page(db, make_user)
    section = OfferSection(offer_page_id=page.id, section_type='paragraph', content='tekst')
    db.session.add(section)
    db.session.commit()

    assert section.is_image is False
    assert section.get_images_ordered() == []
