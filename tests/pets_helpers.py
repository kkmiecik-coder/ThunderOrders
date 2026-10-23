"""Wspólne klocki testów serwisu pupili (etap 2). Import: `from tests.pets_helpers import …`
(działa, bo `python -m pytest` dodaje katalog repo do sys.path)."""
from datetime import datetime, timezone

from extensions import db
from modules.pets.models import Pet, PetProfile

T0 = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)      # poniedziałek, dzień
NOC = datetime(2026, 10, 12, 23, 30, tzinfo=timezone.utc)   # noc 23–07


def zaloz_profil(user, now=T0):
    profil = PetProfile(user_id=user.id, start_egg_claimed_at=now, last_monthly_egg_at=now, created_at=now)
    db.session.add(profil)
    db.session.commit()
    return profil


def zaloz_pupila(user, species='kotek', now=T0, **pola):
    dane = dict(user_id=user.id, status='alive', species=species, name='Mruczek', egg_source='start',
                egg_hours=48, hatched_at=now, egg_progress_at=now, state_at=now, created_at=now)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


def zaloz_jajko(user, now=T0, source='monthly', hours=168, **pola):
    dane = dict(user_id=user.id, status='egg', egg_source=source, egg_hours=hours,
                egg_progress_sec=0, egg_progress_at=now, state_at=now, created_at=now)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


def zaloz_zmarlego(user, species='mis', died_at=T0, **pola):
    dane = dict(user_id=user.id, status='dead', species=species, name='Puszek', egg_source='monthly',
                egg_hours=168, hatched_at=died_at, egg_progress_at=died_at, state_at=died_at,
                created_at=died_at, died_at=died_at, health=0.0, hunger=0.0, notify_level=4)
    dane.update(pola)
    pet = Pet(**dane)
    db.session.add(pet)
    db.session.commit()
    return pet


class RngStaly:
    """Atrapa random: zawsze wybiera `slug`, jeśli jest wśród kandydatów; zapamiętuje kandydatów."""

    def __init__(self, slug):
        self.slug = slug
        self.ostatni_wybor_z = None

    def choice(self, seq):
        self.ostatni_wybor_z = list(seq)
        return self.slug if self.slug in seq else seq[0]
