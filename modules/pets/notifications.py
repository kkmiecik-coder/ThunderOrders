"""Powiadomienia o pupilach (spec §2.9, §3.6): koszyk per użytkownik, zbiorczy push, zbiorczy mail,
przebieg crona `flask pets tick`.

Dlaczego tak:
- `_fire_and_forget` PushManagera to wątek daemon — proces CLI kończy się wcześniej i push ginie,
  więc tu wołamy `send_to_user` synchronicznie;
- `send_to_user` zapisuje wpis w dzwonku PRZED sprawdzeniem preferencji, więc `pet_updates`
  sprawdzamy sami, zanim cokolwiek zawołamy;
- maile ze wszystkich użytkowników idą jednym `send_email_batch_sync` (limit SMTP per IP).
"""
import os
from datetime import timedelta

from flask import current_app

from extensions import db
from modules.pets import rules
from modules.pets.config import PetConfig
from modules.pets.common import (
    add_event, egg_progress, lock_profile, next_monthly_at, now_or, persist_death, persist_discharge,
    simulate_pet,
)
from modules.pets.models import PRUNABLE_EVENT_TYPES, Pet, PetEvent, PetProfile
from modules.pets.species import SPECIES_BY_SLUG

LEVEL_SAD, LEVEL_SICK, LEVEL_CRITICAL, LEVEL_DEAD = 1, 2, 3, 4
_LEVEL_BY_MOOD = {'smutny': LEVEL_SAD, 'chory': LEVEL_SICK, 'krytyczny': LEVEL_CRITICAL}
_OPIS_POZIOMU = {
    LEVEL_SAD: 'jest smutny',
    LEVEL_SICK: 'jest chory — zabierz go do szpitala',
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
    return dict(user=user, alerts=[], deaths=[], eggs_ready=[], monthly=False, rescue_reminders=[], healed=[])


def basket_is_empty(basket):
    return not (basket['alerts'] or basket['deaths'] or basket['eggs_ready'] or basket['monthly']
                or basket['rescue_reminders'] or basket['healed'])


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
    for pet in basket['healed']:
        zdania.append(f'Pupil {_imie(pet)} wyzdrowiał — odbierz go ze szpitala.')
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


def push_path(basket):
    """Gdzie prowadzi zbiorczy push (spec v3.1 §5): prosto do sali, w której da się pomóc."""
    if any(poziom >= LEVEL_SICK for _, poziom in basket['alerts']):
        return PETS_URL_PATH + '/szpital/izba-przyjec'
    if basket['deaths']:                      # przypomnienie o ratunkowym idzie mailem — nie steruje pushem
        return PETS_URL_PATH + '/ogrod'
    if basket['healed']:
        return PETS_URL_PATH + '/szpital/izba-przyjec'
    if basket['eggs_ready']:
        return PETS_URL_PATH + '/szpital/inkubatorium'
    if basket['monthly']:
        return PETS_URL_PATH + '/szpital'
    return PETS_URL_PATH + '/domek'


def needs_email(basket):
    """Mail tylko przy krytycznym, odejściu i przypomnieniu o ratunkowym (spec §2.9)."""
    return bool(basket['deaths'] or basket['rescue_reminders']
                or any(poziom == LEVEL_CRITICAL for _, poziom in basket['alerts']))


def pets_url():
    base = (current_app.config.get('BASE_URL') or os.getenv('APP_BASE_URL') or 'https://thunderorders.cloud').rstrip('/')
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
        log_context={'entity_type': 'user', 'entity_id': user.id},
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

    Zapisuje: odejścia (persist_death) + `death_notified_at`, podniesione `notify_level`, reset
    epizodu, `egg_ready_notified_at`, `monthly_notified_at` — wszystko pod blokadą profilu, żeby dwa
    równoległe przebiegi nie powiadomiły dwa razy. NIE zapisuje `rescue_reminder_sent_at` (jedyny
    kanał to mail — flaga po udanej wysyłce). Wołający commituje.
    """
    basket = empty_basket(user)
    profil = lock_profile(user, required=False)
    pety = (Pet.query.filter(Pet.user_id == user.id, Pet.status.in_(('egg', 'alive', 'dead')))
            .populate_existing().with_for_update().order_by(Pet.id).all())
    prog_ratunkowe = now - timedelta(days=int(cfg.rescue_reminder_days))

    for pet in pety:
        if pet.status == 'alive':
            sim = simulate_pet(pet, now, cfg)
            if sim.discharged_at is not None:
                persist_discharge(pet, sim, now)
            if sim.died_at is not None:
                persist_death(pet, sim, now)
                pet.death_notified_at = now      # pod blokadą: drugi przebieg nie zrobi drugiego pushu
                basket['deaths'].append(pet)
                continue
            if pet.hospital_since is not None:
                if pet.hospital_ready_notified_at is None and now >= pet.hospital_healed_at:
                    pet.hospital_ready_notified_at = now
                    basket['healed'].append(pet)
                continue                                  # w szpitalu: bez alertów (spec v3 §6.4)
            poziom = level_of(sim.state)
            if poziom > int(pet.notify_level or 0):
                pet.notify_level = poziom
                add_event(user.id, 'alert', now, pet_id=pet.id, value=poziom)   # raport: czas reakcji na ostrzeżenie
                basket['alerts'].append((pet, poziom))
            elif poziom == 0 and pet.notify_level:
                pet.notify_level = 0          # koniec epizodu: żaden pasek na zerze, zdrowie ≥ 75
        elif pet.status == 'dead':
            if pet.death_notified_at is None:
                pet.death_notified_at = now
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


# ---------------------------------------------------------------------------
# Przebieg crona (spec §3.6)
# ---------------------------------------------------------------------------

def users_to_check(now, cfg):
    """Jedno zapytanie o listę użytkowników, u których może być coś do zgłoszenia (bez yield_per)."""
    from sqlalchemy import and_, or_
    from modules.auth.models import User
    prog_ratunkowe = now - timedelta(days=int(cfg.rescue_reminder_days))
    z_pupilami = db.session.query(Pet.user_id).filter(or_(
        Pet.status.in_(('alive', 'egg')),
        and_(Pet.status == 'dead', Pet.death_notified_at.is_(None)),
        and_(Pet.status == 'dead', Pet.rescue_egg_claimed_at.is_(None),
             Pet.rescue_reminder_sent_at.is_(None), Pet.died_at <= prog_ratunkowe),
    )).distinct()
    z_miesiecznym = db.session.query(PetProfile.user_id).filter(
        PetProfile.monthly_notified_at.is_(None),
        PetProfile.last_monthly_egg_at <= now - timedelta(days=int(cfg.monthly_days)),
    )
    ids = {r[0] for r in z_pupilami.all()} | {r[0] for r in z_miesiecznym.all()}
    if not ids:
        return []
    users = (User.query.filter(User.id.in_(ids), User.is_active == True)  # noqa: E712
             .order_by(User.id).all())
    # Rollout jak w pets_feature_for: admin/mod zawsze, klient gdy id % 100 < rollout_pct — cron nie
    # może powiadamiać kogoś, kto funkcji nie widzi (link prowadziłby do 404)
    pct = int(cfg.rollout_pct)
    return [u for u in users if u.role in ('admin', 'mod') or (u.id % 100) < pct]


def prune_events(now, days=PRUNE_DAYS):
    """Porządki: zdarzenia akcji starsze niż `days`; trwałe (claim/grant/hatch/merge/die/rename/milestone) zostają."""
    prog = now - timedelta(days=days)
    usuniete = (PetEvent.query.filter(PetEvent.type.in_(PRUNABLE_EVENT_TYPES), PetEvent.created_at < prog)
                .delete(synchronize_session=False))
    db.session.commit()
    return int(usuniete or 0)


def _wyslij_push(user, basket):
    from utils.push_manager import PushManager
    tytul, tresc = build_push_text(basket)
    if not tresc:
        return False
    # Synchronicznie: _fire_and_forget to wątek daemon, który ginie z procesem CLI
    PushManager.send_to_user(user.id, tytul, tresc, url=push_path(basket), tag=PUSH_TAG,
                             notification_type=PREF_FIELD)
    return True


def run_tick(now=None, cfg=None, dry_run=False):
    """Godzinny przebieg: koszyki per użytkownik → push → jeden batch maili → flagi → porządki.

    Liczniki: `pushes` = użytkownicy, dla których zawołano send_to_user (wpis w dzwonku powstaje
    także bez subskrypcji push); `emails_prepared` = zbudowane wiadomości; `emails_sent` =
    potwierdzone przez SMTP; `errors` = użytkownicy pominięci przez wyjątek (szczegóły w logu).

    Odporność (recenzja etapu 3): wyjątek u jednego użytkownika nie zatrzymuje reszty, a batch maili
    i porządki idą w `finally` — przygotowane wiadomości nigdy nie zostają w `queued`.
    """
    from utils.email_manager import EmailManager
    # Cron to osobny proces: czyta Settings na świeżo, nie z cache w `g` (w testach jeden kontekst
    # aplikacji obsługuje kilka wywołań komendy i stara konfiguracja przeżywałaby zmianę flagi)
    now, cfg = now_or(now), (cfg if cfg is not None else PetConfig.load(force=True))
    wynik = {'users': 0, 'pushes': 0, 'emails_prepared': 0, 'emails_sent': 0, 'deaths': 0,
             'eggs_ready': 0, 'monthly': 0, 'rescue_reminders': 0, 'pruned': 0, 'errors': 0,
             'skipped_disabled': False, 'dry_run': dry_run, 'koszyki': []}
    if not cfg.enabled:
        # Kill-switch funkcji (spec §7): wyłączona = cisza. Po włączeniu cron nadrobi z flag i notify_level.
        wynik['skipped_disabled'] = True
        return wynik
    maile_wlaczone = EmailManager.is_email_enabled(EMAIL_SWITCH)
    do_wyslania = []   # (user, basket, Message)
    try:
        for user in users_to_check(now, cfg):
            try:
                _przetworz_uzytkownika(user, now, cfg, dry_run, maile_wlaczone, wynik, do_wyslania)
            except Exception:  # noqa: BLE001 — jeden użytkownik nie może ubić przebiegu dla reszty
                db.session.rollback()
                wynik['errors'] += 1
                current_app.logger.exception('pets tick: użytkownik %s pominięty', getattr(user, 'id', '?'))
    finally:
        if not dry_run:
            _wyslij_maile(do_wyslania, now, wynik)
            try:
                wynik['pruned'] = prune_events(now)
            except Exception:  # noqa: BLE001
                db.session.rollback()
                wynik['errors'] += 1
                current_app.logger.exception('pets tick: porządki nie powiodły się')
    return wynik


def _przetworz_uzytkownika(user, now, cfg, dry_run, maile_wlaczone, wynik, do_wyslania):
    basket = collect_for_user(user, now, cfg)
    if basket_is_empty(basket):
        # Mogły zostać zmiany bez powiadomienia (reset epizodu) — zapisujemy je mimo pustego koszyka
        if dry_run:
            db.session.rollback()
        else:
            db.session.commit()
        return
    wynik['users'] += 1
    wynik['deaths'] += len(basket['deaths'])
    wynik['eggs_ready'] += len(basket['eggs_ready'])
    wynik['monthly'] += int(basket['monthly'])
    wynik['rescue_reminders'] += len(basket['rescue_reminders'])
    if dry_run:
        wynik['koszyki'].append((user.email, build_push_text(basket)[1], needs_email(basket)))
        db.session.rollback()
        return
    db.session.commit()   # krok 2: zapis poziomów/odejść/flag, zanim cokolwiek wyślemy

    wlaczone = pet_updates_enabled(user.id)
    if wlaczone:
        if _wyslij_push(user, basket):
            wynik['pushes'] += 1
        if maile_wlaczone and needs_email(basket):
            msg = build_email_message(user, basket)
            if msg is not None:
                do_wyslania.append((user, basket, msg))
                wynik['emails_prepared'] += 1
    if basket['rescue_reminders'] and not (wlaczone and maile_wlaczone):
        # Bez kanału mailowego przypomnienie nie ma jak wyjść — oznaczamy, żeby nie krążyć co godzinę
        for pet in basket['rescue_reminders']:
            pet.rescue_reminder_sent_at = now
        db.session.commit()


def _wyslij_maile(do_wyslania, now, wynik):
    if not do_wyslania:
        return
    from utils.email_sender import send_email_batch_sync   # import w funkcji: testy monkeypatchują moduł
    try:
        wyniki = send_email_batch_sync([msg for _, _, msg in do_wyslania])
    except Exception:  # noqa: BLE001
        wynik['errors'] += 1
        current_app.logger.exception('pets tick: batch maili nie powiódł się')
        return
    for (user, basket, _), ok in zip(do_wyslania, wyniki):
        if ok:
            wynik['emails_sent'] += 1
            for pet in basket['rescue_reminders']:
                pet.rescue_reminder_sent_at = now   # tylko po udanej wysyłce — jedyny kanał tego przypomnienia
    db.session.commit()
