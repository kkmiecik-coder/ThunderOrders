"""Etap 1 pupili: szkielet modułu, gatunki, modele."""


def test_blueprinty_pupili_sa_zarejestrowane(app):
    assert 'pets' in app.blueprints
    assert 'pets_admin' in app.blueprints
    assert app.blueprints['pets'].url_prefix == '/client/pupile'
    assert app.blueprints['pets_admin'].url_prefix == '/admin/pupile'


def test_osiem_gatunkow_z_unikalnymi_slugami():
    from modules.pets.species import SPECIES, SPECIES_BY_SLUG, SPECIES_SLUGS
    assert len(SPECIES) == 8
    assert len(set(SPECIES_SLUGS)) == 8
    assert set(SPECIES_SLUGS) == {
        'wiewiorka', 'kroliczek', 'szczeniak', 'piesek',
        'kotek', 'kurczaczek', 'czarny-kotek', 'mis',
    }
    assert SPECIES_BY_SLUG['mis'].name == 'Miś'


def test_kazdy_gatunek_ma_pelna_palete():
    from modules.pets.species import SPECIES
    for s in SPECIES:
        assert set(s.palette) == {'base', 'light', 'dark', 'cheek'}, s.slug
        for kolor in s.palette.values():
            assert kolor.startswith('#') and len(kolor) == 7, (s.slug, kolor)
        assert isinstance(s.extras, tuple)
