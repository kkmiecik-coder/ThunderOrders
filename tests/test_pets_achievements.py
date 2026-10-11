"""Odznaki za pupile (spec §3.8): metryki, zdarzenie pet_event, cron pet-adults-8."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego


def _seed(db):
    from modules.achievements.seed import seed_achievements
    seed_achievements()
    db.session.commit()


def _odblokowane(user):
    from modules.achievements.models import UserAchievement
    return sorted(ua.achievement.slug for ua in UserAchievement.query.filter_by(user_id=user.id).all())


def test_metryki_pupili_zarejestrowane():
    from modules.achievements.checkers import METRIC_EVALUATORS
    from modules.achievements.services import EVENT_METRICS
    for m in ('pets_hatched', 'pet_species_discovered', 'pet_adult_alive', 'pet_stars_max', 'pet_care_days_max'):
        assert m in METRIC_EVALUATORS
    for m in ('pets_hatched', 'pet_species_discovered', 'pet_stars_max', 'pet_care_days_max', 'all_badges_unlocked'):
        assert m in EVENT_METRICS['pet_event']


def test_pierwsze_wyklucie_odblokowuje(db, make_user):
    from modules.achievements.services import AchievementService
    from modules.pets.common import add_event
    _seed(db)
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    add_event(user.id, 'hatch_new', T0, pet_id=pet.id)
    db.session.commit()
    nowe = AchievementService().check_event(user, 'pet_event')
    assert 'pet-first-hatch' in [a.slug for a in nowe]


def test_species_discovered_liczy_merged(db, make_user):
    """Review Focus 1: duplikat (merged) też odkrywa gatunek; jajko bez gatunku nie."""
    from modules.achievements.checkers import get_metric_value
    user = make_user()
    zaloz_profil(user)
    for s in ('kotek', 'mis', 'piesek'):
        zaloz_pupila(user, species=s)
    zaloz_pupila(user, species='kroliczek', status='merged')
    zaloz_pupila(user, status='egg', species=None, name=None, hatched_at=None)
    wartosc, spelnia = get_metric_value(user, 'pet_species_discovered', {'metric': 'pet_species_discovered', 'threshold': 4})
    assert (wartosc, spelnia) == (4, True)


def test_care_days_max_i_stars_max(db, make_user):
    from modules.achievements.checkers import get_metric_value
    user = make_user()
    zaloz_profil(user)
    zaloz_pupila(user, species='kotek', care_days=12, stars=1)
    zaloz_zmarlego(user, species='mis', care_days=40, stars=3)   # zmarły też się liczy (opieka była)
    assert get_metric_value(user, 'pet_care_days_max', {'threshold': 30}) == (40, True)
    assert get_metric_value(user, 'pet_stars_max', {'threshold': 3}) == (3, True)
    assert get_metric_value(user, 'pet_care_days_max', {'threshold': 100}) == (40, False)


def test_adult_alive_liczy_stan_teraz(db, make_user):
    """Review Focus 2: 8 dorosłych wczoraj, dziś 7 — nie odblokowuje; maluch się nie liczy."""
    from modules.achievements.checkers import get_metric_value
    from modules.pets.species import SPECIES_SLUGS
    user = make_user()
    zaloz_profil(user)
    dawno = T0 - timedelta(days=100)
    for slug in SPECIES_SLUGS[:7]:
        zaloz_pupila(user, species=slug, hatched_at=dawno, now=dawno)
    zaloz_zmarlego(user, species=SPECIES_SLUGS[7], hatched_at=dawno, died_at=T0 - timedelta(hours=1))
    assert get_metric_value(user, 'pet_adult_alive', {'threshold': 8}, {'now': T0}) == (7, False)
    zaloz_pupila(user, species='kotek', name='Nowy', hatched_at=T0 - timedelta(days=1), now=T0, status='alive')
    assert get_metric_value(user, 'pet_adult_alive', {'threshold': 8}, {'now': T0})[0] == 7


def test_cron_check_daily_odblokowuje_osmiu_doroslych(db, make_user):
    from modules.achievements.services import AchievementService
    from modules.pets.species import SPECIES_SLUGS
    _seed(db)
    user = make_user()
    zaloz_profil(user)
    dawno = T0 - timedelta(days=400)
    for slug in SPECIES_SLUGS:
        zaloz_pupila(user, species=slug, hatched_at=dawno, now=dawno)
    AchievementService().run_daily_checks()
    assert 'pet-adults-8' in _odblokowane(user)


def test_seed_ma_komplet_odznak_pupili(db):
    from modules.achievements.models import Achievement
    _seed(db)
    slugi = {a.slug: a for a in Achievement.query.filter_by(category='pets').all()}
    assert set(slugi) == {'pet-first-hatch', 'pet-care-7', 'pet-species-4', 'pet-species-8', 'pet-adults-8',
                          'pet-stars-3', 'pet-care-30', 'pet-care-100', 'pet-care-365'}
    assert slugi['pet-adults-8'].trigger_type == 'cron' and slugi['pet-adults-8'].rarity == 'cosmic'
    assert slugi['pet-species-8'].rarity == 'legendary' and slugi['pet-care-7'].tier_group == 'pet-care'
