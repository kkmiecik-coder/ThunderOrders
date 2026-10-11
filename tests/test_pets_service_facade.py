"""Fasada eksportuje cały kontrakt serwisu — etap 3/4/6 importują tylko stąd."""


def test_fasada_eksportuje_kontrakt():
    from modules.pets import service
    for nazwa in ('claim_egg', 'warm_egg', 'hatch_egg', 'perform_action', 'light_candle', 'rename_pet',
                  'validate_name', 'set_companion', 'admin_grant_egg', 'anonymize_user_pets',
                  'state_for_user', 'most_in_need', 'eggs_available', 'next_monthly_at', 'get_profile',
                  'PetError'):
        assert callable(getattr(service, nazwa)), nazwa


def test_scenariusz_od_jajka_do_opieki(db, make_user):
    """Smoke przez fasadę: start → ogrzej → wykluj → nakarm → stan."""
    from datetime import timedelta
    from modules.pets import service
    from modules.pets.config import PetConfig
    from tests.pets_helpers import T0, RngStaly
    cfg = PetConfig()
    user = make_user()
    jajko = service.claim_egg(user, 'start', now=T0, cfg=cfg)
    service.warm_egg(user, jajko.id, now=T0, cfg=cfg)
    # 48 h startowego: 8 h ×2 + 32 h = 48 h → gotowe po 40 h
    wynik = service.hatch_egg(user, jajko.id, now=T0 + timedelta(hours=40), cfg=cfg, rng=RngStaly('mis'))
    assert wynik['result'] == 'new' and wynik['pet'].species == 'mis'
    pet = wynik['pet']
    service.rename_pet(user, pet.id, 'Puchatek', now=T0 + timedelta(hours=40))
    # T0+40 h = środa 00:00 (noc, pupil śpi) — opieka dopiero rano, T0+48 h = środa 08:00
    service.perform_action(user, pet.id, 'pat', count=10, now=T0 + timedelta(hours=48), cfg=cfg)
    stan = service.state_for_user(user, now=T0 + timedelta(hours=48), cfg=cfg)
    assert stan['pets'][0]['name'] == 'Puchatek' and stan['pets'][0]['care_days'] == 1
    assert stan['album'][7]['status'] == 'alive'   # 'mis' jest ostatni w SPECIES_SLUGS
