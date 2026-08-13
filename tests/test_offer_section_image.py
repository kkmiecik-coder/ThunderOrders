import os

import pytest

from modules.admin.offers import _update_sections, _validate_section_data
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


def test_zapis_tworzy_sekcje_ze_zdjeciami_w_podanej_kolejnosci(db, make_user):
    page = _page(db, make_user)

    _update_sections(page, [{
        'id': None, 'type': 'image',
        'images': ['uploads/offers/a.jpg', 'uploads/offers/b.jpg'],
    }])
    db.session.commit()

    sekcje = page.get_sections_ordered()
    assert len(sekcje) == 1
    assert [img.path for img in sekcje[0].get_images_ordered()] == [
        'uploads/offers/a.jpg', 'uploads/offers/b.jpg',
    ]


def test_zapis_zmienia_kolejnosc_zdjec(db, make_user):
    page = _page(db, make_user)
    _update_sections(page, [{
        'id': None, 'type': 'image',
        'images': ['uploads/offers/a.jpg', 'uploads/offers/b.jpg'],
    }])
    db.session.commit()
    section_id = page.get_sections_ordered()[0].id

    _update_sections(page, [{
        'id': section_id, 'type': 'image',
        'images': ['uploads/offers/b.jpg', 'uploads/offers/a.jpg'],
    }])
    db.session.commit()

    section = page.get_sections_ordered()[0]
    assert [img.path for img in section.get_images_ordered()] == [
        'uploads/offers/b.jpg', 'uploads/offers/a.jpg',
    ]
    assert OfferSectionImage.query.filter_by(section_id=section_id).count() == 2


def test_zapis_usuwa_zdjecia_ktorych_nie_ma_w_zadaniu(db, make_user):
    page = _page(db, make_user)
    _update_sections(page, [{
        'id': None, 'type': 'image',
        'images': ['uploads/offers/a.jpg', 'uploads/offers/b.jpg'],
    }])
    db.session.commit()
    section_id = page.get_sections_ordered()[0].id

    _update_sections(page, [{
        'id': section_id, 'type': 'image', 'images': ['uploads/offers/a.jpg'],
    }])
    db.session.commit()

    assert [img.path for img in page.get_sections_ordered()[0].get_images_ordered()] == [
        'uploads/offers/a.jpg',
    ]


def test_sekcja_bez_zdjec_jest_dopuszczalna(db, make_user):
    page = _page(db, make_user)

    _update_sections(page, [{'id': None, 'type': 'image', 'images': []}])
    db.session.commit()

    assert page.get_sections_ordered()[0].get_images_ordered() == []


@pytest.mark.parametrize('zla_sciezka', [
    '../../etc/passwd',
    'uploads/products/cudze.jpg',
    '/etc/passwd',
    'http://zewnetrzny.example.com/a.jpg',
    'uploads/offers/../../secrets.env',
])
def test_walidacja_odrzuca_sciezki_spoza_uploads_offers(zla_sciezka):
    ok, blad = _validate_section_data({'type': 'image', 'images': [zla_sciezka]})

    assert ok is False
    assert 'zdjęc' in blad.lower() or 'ścieżk' in blad.lower()


def test_walidacja_przepuszcza_poprawne_sciezki():
    ok, blad = _validate_section_data({
        'type': 'image', 'images': ['uploads/offers/abc123.jpg'],
    })

    assert ok is True
    assert blad is None


def test_duplikacja_strony_daje_kopii_wlasne_pliki_zdjec(app, db, client, make_user, login):
    admin = make_user(role='admin', email='admin-duplikacja@example.com', profile_completed=True)
    page = _page(db, make_user)

    # Prawdziwy plik na dysku — duplikacja kopiuje zawartość, nie tylko ścieżkę
    nazwa = 'test_duplikacja_src.jpg'
    rel = f'uploads/offers/{nazwa}'
    katalog = os.path.join(app.static_folder, 'uploads', 'offers')
    os.makedirs(katalog, exist_ok=True)
    sciezka = os.path.join(katalog, nazwa)
    with open(sciezka, 'wb') as f:
        f.write(b'zawartosc-testowa')

    section = OfferSection(offer_page_id=page.id, section_type='image', sort_order=0)
    db.session.add(section)
    db.session.flush()
    db.session.add(OfferSectionImage(section_id=section.id, path=rel, sort_order=0))
    db.session.commit()

    try:
        login(admin)
        resp = client.post(f'/admin/offers/{page.id}/duplicate')
        assert resp.status_code in (200, 302)

        kopia = OfferPage.query.filter(OfferPage.id != page.id).order_by(OfferPage.id.desc()).first()
        sekcja_kopii = kopia.get_sections_ordered()[0]
        zdjecia_kopii = sekcja_kopii.get_images_ordered()

        assert len(zdjecia_kopii) == 1
        nowa_sciezka = zdjecia_kopii[0].path
        assert nowa_sciezka != rel, 'kopia współdzieli plik z oryginałem'
        assert nowa_sciezka.startswith('uploads/offers/')

        plik_kopii = os.path.join(app.static_folder, nowa_sciezka)
        assert os.path.exists(plik_kopii)
        with open(plik_kopii, 'rb') as f:
            assert f.read() == b'zawartosc-testowa'
        os.remove(plik_kopii)
    finally:
        if os.path.exists(sciezka):
            os.remove(sciezka)
