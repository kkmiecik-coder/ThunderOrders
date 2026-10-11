"""Etap 1 pupili: szkielet modułu, gatunki, modele."""
from datetime import datetime


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


def test_profil_pupil_i_zdarzenie_z_domyslnymi(db, make_user):
    from modules.pets.models import PetProfile, Pet, PetEvent
    user = make_user()
    profil = PetProfile(user_id=user.id)
    pupil = Pet(user_id=user.id, egg_source='start', egg_hours=48)
    db.session.add_all([profil, pupil])
    db.session.commit()

    assert user.pet_profile is profil
    assert profil.companion_enabled is True
    assert profil.dupes_in_row == 0
    assert profil.granted_eggs_pending == 0
    assert isinstance(profil.start_egg_claimed_at, datetime)
    assert isinstance(profil.last_monthly_egg_at, datetime)

    assert pupil.status == 'egg'
    assert pupil.species is None
    assert pupil.egg_progress_sec == 0
    assert (pupil.hunger, pupil.fun, pupil.clean, pupil.health) == (100.0, 100.0, 100.0, 100.0)
    assert pupil.stars == 0 and pupil.care_days == 0 and pupil.notify_level == 0
    assert pupil.lights_count == 0
    assert user.pets == [pupil]

    zdarzenie = PetEvent(pet_id=pupil.id, user_id=user.id, type='claim')
    db.session.add(zdarzenie)
    db.session.commit()
    assert zdarzenie.value == 1
    assert pupil.events.count() == 1


def test_profil_moze_wskazywac_towarzysza(db, make_user):
    from modules.pets.models import PetProfile, Pet
    user = make_user()
    pupil = Pet(user_id=user.id, egg_source='monthly', status='alive', species='kotek',
                name='Mruczek', hatched_at=datetime(2026, 10, 1, 12, 0))
    db.session.add(pupil)
    db.session.commit()
    profil = PetProfile(user_id=user.id, companion_pet_id=pupil.id)
    db.session.add(profil)
    db.session.commit()
    assert profil.companion_pet is pupil


def test_merged_jajko_pamieta_w_kogo_sie_wtopilo(db, make_user):
    from modules.pets.models import Pet
    user = make_user()
    zywy = Pet(user_id=user.id, egg_source='start', status='alive', species='mis', name='Puchatek')
    db.session.add(zywy)
    db.session.commit()
    dupl = Pet(user_id=user.id, egg_source='monthly', status='merged', species='mis',
               merged_into_pet_id=zywy.id)
    db.session.add(dupl)
    db.session.commit()
    assert dupl.merged_into is zywy


def test_stale_typow_zdarzen_i_porzadkow():
    from modules.pets.models import EVENT_TYPES, PRUNABLE_EVENT_TYPES, PET_STATUSES, EGG_SOURCES
    # 'alert' (etap 6): wpis crona przy podniesieniu notify_level — do raportu, więc też do porządków
    assert set(PRUNABLE_EVENT_TYPES) == {'feed', 'play', 'wash', 'heal', 'pat', 'wake', 'warm', 'light', 'alert'}
    assert set(PRUNABLE_EVENT_TYPES) < set(EVENT_TYPES)
    assert {'claim', 'grant', 'hatch_new', 'hatch_dupe', 'merge', 'die', 'rename', 'milestone'} < set(EVENT_TYPES)
    assert PET_STATUSES == ('egg', 'alive', 'dead', 'merged')
    assert EGG_SOURCES == ('start', 'monthly', 'rescue', 'granted')


def test_preferencja_pet_updates_domyslnie_wlaczona(db, make_user):
    from modules.notifications.models import NotificationPreference
    user = make_user()
    pref = NotificationPreference(user_id=user.id)
    db.session.add(pref)
    db.session.commit()
    assert pref.pet_updates is True
    assert pref.to_dict()['pet_updates'] is True


def test_enum_kategorii_odznak_zawiera_pets(db):
    """SQLAlchemy nie waliduje nieznanych stringów w Enum (validate_strings=False),
    więc sam INSERT by przeszedł — sprawdzamy definicję typu, a potem zapis."""
    from modules.achievements.models import Achievement
    assert 'pets' in Achievement.__table__.c.category.type.enums
    a = Achievement(slug='pet-test', name='Test', description='x', category='pets',
                    rarity='common', trigger_type='event',
                    trigger_config={'metric': 'pets_hatched', 'threshold': 1})
    db.session.add(a)
    db.session.commit()
    assert Achievement.query.filter_by(category='pets').count() == 1


def test_twarde_usuniecie_usera_kasuje_pupile_kaskada(db, make_user):
    """Recenzja (Important 1): admin ma trasę db.session.delete(client) — backrefy nie mogą
    próbować NULL-ować pets.user_id (NOT NULL); kaskadę robi baza (ondelete=CASCADE)."""
    from modules.pets.models import PetProfile, Pet, PetEvent
    user = make_user()
    profil = PetProfile(user_id=user.id)
    pet = Pet(user_id=user.id, egg_source='start', egg_hours=48)
    db.session.add_all([profil, pet])
    db.session.commit()
    profil.companion_pet_id = pet.id
    db.session.add(PetEvent(pet_id=pet.id, user_id=user.id, type='claim'))
    db.session.commit()
    uid = user.id
    db.session.delete(user)
    db.session.commit()
    assert PetProfile.query.filter_by(user_id=uid).count() == 0
    assert Pet.query.filter_by(user_id=uid).count() == 0
    assert PetEvent.query.filter_by(user_id=uid).count() == 0
