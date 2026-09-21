"""
Unikalność produktu-kompletu (set_product_id) w sekcjach setu.

Ten sam produkt-komplet przypisany do dwóch stron ofertowych to zawsze błąd.
Tak powstał przypadek, w którym strona „Whos fans" wskazywała na OT8 z albumu
„Jump up": lista „Do zamówienia" agreguje po produkcie ponad stronami, więc
zsumowała dwie sztuki jednego OT8 i u dostawcy poszło zamówienie na zły album.
"""
import pytest


@pytest.fixture
def owner(make_user):
    """OfferPage.created_by jest NOT NULL."""
    return make_user(role='admin', email='owner@example.com', profile_completed=True)


@pytest.fixture
def make_page(db, owner):
    def _make(name):
        from modules.offers.models import OfferPage
        p = OfferPage(
            name=name,
            token=OfferPage.generate_token(),
            status='draft',
            created_by=owner.id,
        )
        db.session.add(p)
        db.session.commit()
        return p
    return _make


@pytest.fixture
def make_set_section(db):
    def _make(page, set_product_id, set_name='Set'):
        from modules.offers.models import OfferSection
        s = OfferSection(
            offer_page_id=page.id,
            section_type='set',
            sort_order=0,
            set_name=set_name,
            set_product_id=set_product_id,
        )
        db.session.add(s)
        db.session.commit()
        return s
    return _make


def _dane_sekcji_set(set_product_id, section_id=None, set_name='Set'):
    """Payload sekcji-setu w formacie, jaki przysyła page builder."""
    return {
        'id': section_id,
        'type': 'set',
        'set_name': set_name,
        'set_product_id': set_product_id,
        'set_items': [],
    }


def test_produkt_komplet_zajety_przez_inna_strone(app, db, make_page, make_product, make_set_section):
    """Kolizja z inną stroną: komunikat musi wskazać, gdzie szukać konfliktu."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona_a = make_page('Ateez GH5 - Jump up 1.0 (album) photobook ver')
    make_set_section(strona_a, ot8.id)
    strona_b = make_page('Ateez GH5 - Whos fans 1.0 (album) cheek heart ver')

    with pytest.raises(ValueError) as blad:
        _update_sections(strona_b, [_dane_sekcji_set(ot8.id)])

    komunikat = str(blad.value)
    assert 'Jump up 1.0 (album) photobook ver' in komunikat
    assert 'GH5 - Jump up 1.0 (Album) Photobook ver - OT8' in komunikat


def test_produkt_komplet_w_dwoch_setach_tej_samej_strony(app, db, make_page, make_product):
    """Kolizja wewnątrz jednego żądania — sekcje jeszcze nie istnieją w bazie."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona = make_page('Strona z dwoma setami')

    with pytest.raises(ValueError) as blad:
        _update_sections(strona, [
            _dane_sekcji_set(ot8.id, set_name='Set A'),
            _dane_sekcji_set(ot8.id, set_name='Set B'),
        ])

    assert 'dwóch setach' in str(blad.value)


def test_ponowny_zapis_wlasnej_strony_przechodzi(app, db, make_page, make_product, make_set_section):
    """Sekcja nie może blokować się na własnym produkcie-komplecie."""
    from modules.admin.offers import _update_sections
    ot8 = make_product(name='GH5 - Jump up 1.0 (Album) Photobook ver - OT8')
    strona = make_page('Ateez GH5 - Jump up 1.0 (album) photobook ver')
    sekcja = make_set_section(strona, ot8.id)

    _update_sections(strona, [_dane_sekcji_set(ot8.id, section_id=sekcja.id)])
    db.session.commit()

    assert sekcja.set_product_id == ot8.id


def test_sety_bez_produktu_kompletu_nie_koliduja(app, db, make_page):
    """Puste set_product_id nie jest kolizją — wiele setów może go nie mieć."""
    from modules.admin.offers import _update_sections
    strona = make_page('Strona bez kompletów')

    _update_sections(strona, [
        _dane_sekcji_set(None, set_name='Set A'),
        _dane_sekcji_set(None, set_name='Set B'),
    ])
    db.session.commit()

    assert strona.sections.count() == 2
