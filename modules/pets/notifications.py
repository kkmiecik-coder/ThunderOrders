"""Powiadomienia o pupilach (spec §2.9, §3.6): koszyk per użytkownik, zbiorczy push, zbiorczy mail,
przebieg crona `flask pets tick`.

Dlaczego tak:
- `_fire_and_forget` PushManagera to wątek daemon — proces CLI kończy się wcześniej i push ginie,
  więc tu wołamy `send_to_user` synchronicznie;
- `send_to_user` zapisuje wpis w dzwonku PRZED sprawdzeniem preferencji, więc `pet_updates`
  sprawdzamy sami, zanim cokolwiek zawołamy;
- maile ze wszystkich użytkowników idą jednym `send_email_batch_sync` (limit SMTP per IP).
"""
from datetime import timedelta

from flask import current_app

from extensions import db
from modules.pets import rules
from modules.pets.common import (
    cfg_or, egg_progress, lock_profile, next_monthly_at, now_or, persist_death, simulate_pet,
)
from modules.pets.models import PRUNABLE_EVENT_TYPES, Pet, PetEvent, PetProfile
from modules.pets.species import SPECIES_BY_SLUG

LEVEL_SAD, LEVEL_SICK, LEVEL_CRITICAL, LEVEL_DEAD = 1, 2, 3, 4
_LEVEL_BY_MOOD = {'smutny': LEVEL_SAD, 'chory': LEVEL_SICK, 'krytyczny': LEVEL_CRITICAL}
_OPIS_POZIOMU = {
    LEVEL_SAD: 'jest smutny',
    LEVEL_SICK: 'jest chory',
    LEVEL_CRITICAL: 'potrzebuje pomocy — stan krytyczny',
}
PETS_URL_PATH = '/client/pupile'
PUSH_TAG = 'pets'
PUSH_TITLE = 'Twoje pupile'
PREF_FIELD = 'pet_updates'
EMAIL_SWITCH = 'notify_pet_alert'
PRUNE_DAYS = 90
PUSH_BODY_MAX = 200


def level_of(state):
    """Poziom ostrzeżenia z nastroju (spec §2.9): 0 brak, 1 smutny, 2 chory, 3 krytyczny."""
    return _LEVEL_BY_MOOD.get(rules.mood(state), 0)


def pet_updates_enabled(user_id):
    """Brak wiersza preferencji = włączone (jak w PushManager.send_to_user)."""
    from modules.notifications.models import NotificationPreference
    pref = NotificationPreference.query.filter_by(user_id=user_id).first()
    return True if pref is None else bool(getattr(pref, PREF_FIELD, True))


def empty_basket(user):
    return dict(user=user, alerts=[], deaths=[], eggs_ready=[], monthly=False, rescue_reminders=[])


def basket_is_empty(basket):
    return not (basket['alerts'] or basket['deaths'] or basket['eggs_ready'] or basket['monthly']
                or basket['rescue_reminders'])


def _imie(pet):
    if pet.name:
        return pet.name
    gatunek = SPECIES_BY_SLUG.get(pet.species)
    return gatunek.name if gatunek else 'pupil'


def build_push_text(basket):
    """Jeden zbiorczy push: zdania z podmiotem „Pupil {imię}" (rodzaj gramatyczny zawsze zgodny)."""
    zdania = []
    for pet in basket['deaths']:
        zdania.append(f'Pupil {_imie(pet)} odszedł do gwiazd.')
    for pet, poziom in sorted(basket['alerts'], key=lambda para: -para[1]):
        zdania.append(f'Pupil {_imie(pet)} {_OPIS_POZIOMU[poziom]}.')
    gotowe = len(basket['eggs_ready'])
    if gotowe == 1:
        zdania.append('Jajko gotowe do wyklucia!')
    elif gotowe > 1:
        zdania.append(f'{gotowe} jajka gotowe do wyklucia!' if gotowe < 5 else f'{gotowe} jajek gotowych do wyklucia!')
    if basket['monthly']:
        zdania.append('Czeka na Ciebie nowe jajko!')
    tresc = ' '.join(zdania)
    if len(tresc) > PUSH_BODY_MAX:
        tresc = tresc[:PUSH_BODY_MAX - 1].rstrip() + '…'
    return PUSH_TITLE, tresc


def needs_email(basket):
    """Mail tylko przy krytycznym, odejściu i przypomnieniu o ratunkowym (spec §2.9)."""
    return bool(basket['deaths'] or basket['rescue_reminders']
                or any(poziom == LEVEL_CRITICAL for _, poziom in basket['alerts']))


def pets_url():
    base = (current_app.config.get('BASE_URL') or 'https://thunderorders.cloud').rstrip('/')
    return base + PETS_URL_PATH


def _memorial(pet):
    wiek = rules.age_days(pet.hatched_at, pet.died_at) if pet.hatched_at and pet.died_at else 0
    gatunek = SPECIES_BY_SLUG.get(pet.species)
    return {'name': _imie(pet), 'age_days': wiek, 'care_days': int(pet.care_days), 'stars': int(pet.stars),
            'species_name': gatunek.name if gatunek else ''}


def build_email_message(user, basket):
    """Message (bez wysyłki) albo None, gdy koszyk nie wymaga maila. Wymaga kontekstu żądania
    (prepare_email renderuje szablony; CLI owija komendę _with_request_context)."""
    if not needs_email(basket):
        return None
    from utils.email_sender import prepare_email
    krytyczne = [_imie(pet) for pet, poziom in basket['alerts'] if poziom == LEVEL_CRITICAL]
    odeszly = [_memorial(pet) for pet in basket['deaths']]
    ratunkowe = [_imie(pet) for pet in basket['rescue_reminders']]
    if odeszly:
        temat = f"Pupil {odeszly[0]['name']} odszedł do gwiazd"
    elif krytyczne:
        temat = f'Pupil {krytyczne[0]} potrzebuje pomocy — stan krytyczny'
    else:
        temat = 'Jajko ratunkowe czeka na odebranie'
    return prepare_email(
        to=user.email,
        subject=temat,
        template='pets_alert',
        log_context={'entity_type': 'pet_user', 'entity_id': user.id},
        user_name=user.first_name or None,
        critical=krytyczne,
        dead=odeszly,
        rescue=ratunkowe,
        url=pets_url(),
    )


# ---------------------------------------------------------------------------
# Koszyk per użytkownik (spec §3.6 krok 2) — pod blokadą profilu, bez commitu
# ---------------------------------------------------------------------------

def collect_for_user(user, now, cfg):
    """Liczy stan wszystkich pupili użytkownika i zbiera, o czym powiadomić.

    Zapisuje: odejścia (persist_death), podniesione `notify_level`, reset epizodu,
    `egg_ready_notified_at`, `monthly_notified_at`. NIE zapisuje `death_notified_at` ani
    `rescue_reminder_sent_at` — to robi przebieg po wysyłce. Wołający commituje.
    """
    basket = empty_basket(user)
    profil = lock_profile(user, required=False)
    pety = (Pet.query.filter(Pet.user_id == user.id, Pet.status.in_(('egg', 'alive', 'dead')))
            .populate_existing().with_for_update().order_by(Pet.id).all())
    prog_ratunkowe = now - timedelta(days=int(cfg.rescue_reminder_days))

    for pet in pety:
        if pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
                basket['deaths'].append(pet)
                continue
            poziom = level_of(sim.state)
            if poziom > int(pet.notify_level or 0):
                pet.notify_level = poziom
                basket['alerts'].append((pet, poziom))
            elif poziom == 0 and pet.notify_level:
                pet.notify_level = 0          # koniec epizodu: żaden pasek na zerze, zdrowie ≥ 75
        elif pet.status == 'dead':
            if pet.death_notified_at is None:
                basket['deaths'].append(pet)
            if (pet.rescue_egg_claimed_at is None and pet.rescue_reminder_sent_at is None
                    and pet.died_at is not None and pet.died_at <= prog_ratunkowe):
                basket['rescue_reminders'].append(pet)
        else:  # egg
            if pet.egg_ready_notified_at is None and rules.egg_is_ready(egg_progress(pet, now, cfg), pet.egg_hours):
                pet.egg_ready_notified_at = now
                basket['eggs_ready'].append(pet)

    if profil is not None and profil.monthly_notified_at is None and now >= next_monthly_at(profil, cfg):
        profil.monthly_notified_at = now
        basket['monthly'] = True
    return basket
