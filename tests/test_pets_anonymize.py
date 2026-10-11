"""Anonimizacja konta (RODO) usuwa to, co użytkownik wpisał, i kończy grę (spec §3.3)."""
from datetime import timedelta

from tests.pets_helpers import T0, zaloz_profil, zaloz_pupila, zaloz_zmarlego, zaloz_jajko


def test_anonymize_user_pets(db, make_user):
    from modules.pets.actions import anonymize_user_pets, perform_action
    from modules.pets.config import PetConfig
    from modules.pets.models import Pet, PetEvent
    user = make_user()
    profil = zaloz_profil(user)
    zywy = zaloz_pupila(user, hunger=10.0)
    zmarly = zaloz_zmarlego(user)
    jajko = zaloz_jajko(user)
    profil.companion_pet_id = zywy.id
    db.session.commit()
    perform_action(user, zywy.id, 'feed', now=T0, cfg=PetConfig())
    assert PetEvent.query.filter_by(user_id=user.id).count() >= 1

    anonymize_user_pets(user, now=T0 + timedelta(days=1))
    db.session.commit()

    assert zywy.status == 'dead' and zywy.died_at == T0 + timedelta(days=1)
    assert zywy.notify_level == 4 and zywy.death_notified_at == T0 + timedelta(days=1)
    assert zywy.name is None and zmarly.name is None
    assert zmarly.died_at == T0                      # stare odejście nietknięte
    assert jajko.status == 'egg'                     # jajko zostaje (bez danych osobowych)
    assert profil.companion_enabled is False and profil.companion_pet_id is None
    assert PetEvent.query.filter_by(user_id=user.id).count() == 0
    assert Pet.query.filter_by(user_id=user.id).count() == 3


def test_user_anonymize_wola_krok_pupili(db, make_user):
    user = make_user()
    zaloz_profil(user)
    zywy = zaloz_pupila(user)
    user.anonymize()
    db.session.commit()
    assert user.is_active is False
    assert zywy.status == 'dead' and zywy.name is None
