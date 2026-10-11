# modules/pets/config.py
"""Konfiguracja pupili: domyślne liczby ze specu (§3.4) + nadpisania z Settings.

Klucze Settings: snake_case z prefiksem `pets_` (np. `pets_egg_hours`), typy
integer/boolean/json. Wartości json zapisuj przez json.dumps — Settings.set_value
robi str(), a str(dict) nie jest JSON-em; taki wiersz jest tu ignorowany z ostrzeżeniem.

PetConfig.load() robi JEDNO zapytanie (LIKE 'pets_%') i cache'uje wynik w flask.g
na czas żądania. Flagi włączenia/rolloutu mają osobny cache w procesie (10 s, jak
app.maintenance_cache), bo sprawdza je context processor na każdej stronie.
"""
import json
import math
import time
from dataclasses import dataclass, field, fields
from typing import ClassVar

from flask import current_app, g

SETTINGS_PREFIX = 'pets_'

_DICT_DEFAULTS = {
    'decay_hours': {'hunger': 24, 'fun': 30, 'clean': 48},
    'night': {'start': 23, 'end': 7, 'factor': 0.25},
    'boost': {'hours': 8, 'factor': 2},
    'stage_days': {'child': 24, 'adult': 80},
    'actions': {
        'feed': 50, 'play': 50, 'heal': 40, 'heal_cooldown_h': 12, 'allow_below': 80,
        'pat_gain': 0.25, 'pat_per_hour': 60, 'wake_penalty': 10, 'awake_minutes': 20,
    },
}


def _slownik(nazwa):
    return field(default_factory=lambda: dict(_DICT_DEFAULTS[nazwa]))


@dataclass(frozen=True)
class PetConfig:
    enabled: bool = False
    rollout_pct: int = 0
    decay_hours: dict = _slownik('decay_hours')
    night: dict = _slownik('night')
    health_drop_hours: int = 72
    health_regen_hours: int = 24
    egg_hours: int = 168
    start_egg_hours: int = 48
    boost: dict = _slownik('boost')
    monthly_days: int = 30
    rescue_hours: int = 0
    rescue_reminder_days: int = 7
    pity_after: int = 2
    max_stars: int = 5
    stage_days: dict = _slownik('stage_days')
    actions: dict = _slownik('actions')

    # Pola, które mogą być zerem (reszta liczb musi być dodatnia)
    _ZERO_OK: ClassVar[frozenset] = frozenset({'rollout_pct', 'rescue_hours', 'pity_after', 'max_stars'})

    @classmethod
    def load(cls, force=False):
        """Konfiguracja z Settings, cache w g na czas żądania."""
        if not force:
            cached = getattr(g, '_pet_config', None)
            if cached is not None:
                return cached
        from modules.auth.models import Settings
        rows = Settings.query.filter(Settings.key.like(f'{SETTINGS_PREFIX}%')).all()
        cfg = cls.from_rows(rows)
        g._pet_config = cfg
        return cfg

    @classmethod
    def from_rows(cls, rows):
        domyslne = cls()
        nazwy = {f.name for f in fields(cls)}
        nadpisania = {}
        for row in rows:
            nazwa = row.key[len(SETTINGS_PREFIX):]
            if nazwa not in nazwy:
                continue
            try:
                nadpisania[nazwa] = _przetworz(nazwa, row.value, getattr(domyslne, nazwa), cls._ZERO_OK)
            except (ValueError, TypeError) as exc:
                current_app.logger.warning('pets: ignoruję ustawienie %s=%r (%s)', row.key, row.value, exc)
        return cls(**nadpisania)


def _przetworz(nazwa, surowe, domyslna, zero_ok):
    """Konwersja + walidacja jednej wartości; ValueError = użyj domyślnej."""
    if isinstance(domyslna, bool):
        return str(surowe).strip().lower() in ('true', '1', 'yes')
    if isinstance(domyslna, int):
        liczba = int(str(surowe).strip())
        if liczba < 0 or (liczba == 0 and nazwa not in zero_ok):
            raise ValueError('liczba poza zakresem')
        if nazwa == 'rollout_pct' and liczba > 100:
            raise ValueError('procent > 100')
        return liczba
    if isinstance(domyslna, dict):
        try:
            parsed = json.loads(surowe)
        except json.JSONDecodeError as exc:
            raise ValueError(f'niepoprawny JSON: {exc}') from exc
        if not isinstance(parsed, dict):
            raise ValueError('oczekiwano obiektu JSON')
        scalone = {**domyslna, **parsed}
        for klucz, wartosc in scalone.items():
            if not isinstance(wartosc, (int, float)) or isinstance(wartosc, bool):
                raise ValueError(f'{klucz}: nie liczba')
            if not math.isfinite(wartosc):
                # json.loads przyjmuje NaN i Infinity; porównania z nimi nie łapią zakresów
                raise ValueError(f'{klucz}: liczba nieskończona lub NaN')
            if klucz == 'factor' and nazwa == 'night':
                if not 0 < wartosc <= 1:
                    raise ValueError('night.factor poza (0, 1]')
            elif klucz in ('start', 'end') and nazwa == 'night':
                if not 0 <= wartosc <= 23:
                    raise ValueError('godzina nocy poza 0–23')
            elif wartosc <= 0:
                raise ValueError(f'{klucz}: musi być dodatnia')
        return scalone
    raise TypeError(f'nieobsługiwany typ pola {nazwa}')


# ---------------------------------------------------------------------------
# Bramka funkcji: włącznik + rollout procentowy (cache w procesie, 10 s)
# ---------------------------------------------------------------------------

FEATURE_CACHE_SECONDS = 10
_feature_cache = {'enabled': False, 'pct': 0, 'checked_at': None}


def reset_feature_cache():
    _feature_cache.update(enabled=False, pct=0, checked_at=None)


def feature_flags():
    """(pets_enabled, pets_rollout_pct) z krótkim cache — jak app.maintenance_cache."""
    teraz = time.monotonic()
    ttl = current_app.config.get('PETS_FEATURE_CACHE_SECONDS', FEATURE_CACHE_SECONDS)
    sprawdzono = _feature_cache['checked_at']
    if sprawdzono is None or teraz - sprawdzono > ttl:
        from modules.auth.models import Settings
        surowe = Settings.get_value('pets_enabled', False)
        # Wiersz typu string z 'False' dałby bool('False') == True — kill-switch musi działać
        _feature_cache['enabled'] = surowe if isinstance(surowe, bool) else str(surowe).strip().lower() in ('true', '1', 'yes')
        try:
            pct = int(Settings.get_value('pets_rollout_pct', 0))
        except (TypeError, ValueError):
            pct = 0
        _feature_cache['pct'] = max(0, min(100, pct))
        _feature_cache['checked_at'] = teraz
    return _feature_cache['enabled'], _feature_cache['pct']


def pets_feature_for(user):
    """Czy ten użytkownik widzi pupile: flaga + rollout po user_id; admin/mod zawsze."""
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    enabled, pct = feature_flags()
    if not enabled:
        return False
    if getattr(user, 'role', None) in ('admin', 'mod'):
        return True
    return (user.id % 100) < pct


# ---------------------------------------------------------------------------
# Formularz panelu admina (etap 6, spec §5): pola płaskie 1:1, pola json rozbite na `pets_<klucz>_<pole>`
# ---------------------------------------------------------------------------

# (klucz Settings, typ Settings, pola json | None, etykieta)
ADMIN_FIELDS = (
    ('pets_enabled', 'boolean', None, 'Funkcja włączona'),
    ('pets_rollout_pct', 'integer', None, 'Rollout (% użytkowników po user_id)'),
    ('pets_decay_hours', 'json', ('hunger', 'fun', 'clean'), 'Pasek 100→0 w godzinach (sytość / radość / czystość)'),
    ('pets_night', 'json', ('start', 'end', 'factor'), 'Noc (od godz. / do godz. / mnożnik spadków)'),
    ('pets_health_drop_hours', 'integer', None, 'Zdrowie 100→0 przy pasku na zerze (h)'),
    ('pets_health_regen_hours', 'integer', None, 'Regeneracja zdrowia 0→100 (h)'),
    ('pets_egg_hours', 'integer', None, 'Inkubacja jajka (h)'),
    ('pets_start_egg_hours', 'integer', None, 'Inkubacja jajka startowego (h)'),
    ('pets_boost', 'json', ('hours', 'factor'), 'Ogrzewanie (godzin / mnożnik)'),
    ('pets_monthly_days', 'integer', None, 'Jajko miesięczne co (dni)'),
    ('pets_rescue_hours', 'integer', None, 'Ratunkowe po odejściu (h, 0 = od razu)'),
    ('pets_rescue_reminder_days', 'integer', None, 'Mail o nieodebranym ratunkowym po (dniach)'),
    ('pets_pity_after', 'integer', None, 'Gwarancja nowego gatunku po N duplikatach'),
    ('pets_max_stars', 'integer', None, 'Maks. gwiazdek'),
    ('pets_stage_days', 'json', ('child', 'adult'), 'Stadia: dziecko od / dorosły od (dni)'),
    ('pets_actions', 'json', ('feed', 'play', 'heal', 'heal_cooldown_h', 'allow_below', 'pat_gain',
                              'pat_per_hour', 'wake_penalty', 'awake_minutes'),
     'Akcje: karmienie / zabawa / leczenie / odstęp leczenia (h) / próg akcji / pat pat (+) / pat na godzinę / kara za obudzenie / okno po obudzeniu (min)'),
)

# Pola, które mogą być ułamkiem (reszta to liczby całkowite)
_FLOAT_FIELDS = frozenset({'pets_night_factor', 'pets_boost_factor', 'pets_actions_pat_gain'})


def admin_form_fields():
    """Lista nazw pól formularza w kolejności ADMIN_FIELDS (do szablonu i testów)."""
    nazwy = []
    for klucz, typ, pola, _ in ADMIN_FIELDS:
        if pola is None:
            nazwy.append(klucz)
        else:
            nazwy.extend(f'{klucz}_{pole}' for pole in pola)
    return nazwy


def admin_form_values(cfg):
    """Aktualna konfiguracja → słownik {pole formularza: wartość jako string}."""
    wartosci = {}
    for klucz, typ, pola, _ in ADMIN_FIELDS:
        atrybut = klucz[len(SETTINGS_PREFIX):]
        biezaca = getattr(cfg, atrybut)
        if pola is None:
            wartosci[klucz] = 'on' if (typ == 'boolean' and biezaca) else ('' if typ == 'boolean' else str(biezaca))
        else:
            for pole in pola:
                v = biezaca.get(pole)
                wartosci[f'{klucz}_{pole}'] = '' if v is None else (str(int(v)) if float(v).is_integer() else str(v))
    return wartosci


def _liczba(pole, surowe, errors):
    tekst = (surowe or '').strip().replace(',', '.')
    if tekst == '':
        errors[pole] = 'Pole wymagane.'
        return None
    try:
        if pole in _FLOAT_FIELDS:
            v = float(tekst)
            if not math.isfinite(v):
                raise ValueError
            return v
        if '.' in tekst:
            raise ValueError
        return int(tekst)
    except ValueError:
        errors[pole] = 'Podaj liczbę' + (' (może być ułamek).' if pole in _FLOAT_FIELDS else ' całkowitą.')
        return None


def validate_settings(form):
    """Formularz admina → ({klucz Settings: (wartość-string, typ)}, {pole formularza: komunikat}).

    Zakresy jak w `_przetworz` (liczby dodatnie poza _ZERO_OK, 0 ≤ pct ≤ 100) plus reguły specu §3.4:
    noc `0 ≤ start,end ≤ 23`, `0 < factor ≤ 1`; ogrzewanie `factor ≥ 1`; pat_gain > 0.
    Przy JAKIMKOLWIEK błędzie nic nie jest zapisywane — wołający sprawdza `errors`.
    """
    values, errors = {}, {}
    domyslne = PetConfig()
    for klucz, typ, pola, _ in ADMIN_FIELDS:
        atrybut = klucz[len(SETTINGS_PREFIX):]
        if typ == 'boolean':
            values[klucz] = ('true' if form.get(klucz) in ('on', 'true', '1') else 'false', typ)
            continue
        if pola is None:
            v = _liczba(klucz, form.get(klucz), errors)
            if v is None:
                continue
            if klucz == 'pets_rollout_pct' and not 0 <= v <= 100:
                errors[klucz] = 'Zakres 0–100.'
            elif v < 0 or (v == 0 and atrybut not in PetConfig._ZERO_OK):
                errors[klucz] = 'Liczba musi być dodatnia.'
            else:
                values[klucz] = (str(v), typ)
            continue
        slownik, blad_w_grupie = {}, False
        for pole in pola:
            nazwa = f'{klucz}_{pole}'
            v = _liczba(nazwa, form.get(nazwa), errors)
            if v is None:
                blad_w_grupie = True
                continue
            if klucz == 'pets_night' and pole in ('start', 'end') and not 0 <= v <= 23:
                errors[nazwa] = 'Godzina 0–23.'
            elif klucz == 'pets_night' and pole == 'factor' and not 0 < v <= 1:
                errors[nazwa] = 'Mnożnik w przedziale (0, 1].'
            elif klucz == 'pets_boost' and pole == 'factor' and v < 1:
                errors[nazwa] = 'Mnożnik ≥ 1.'
            elif v <= 0:
                errors[nazwa] = 'Liczba musi być dodatnia.'
            else:
                slownik[pole] = v
            if nazwa in errors:
                blad_w_grupie = True
        if blad_w_grupie:
            continue
        surowe = json.dumps(slownik)
        try:
            _przetworz(atrybut, surowe, getattr(domyslne, atrybut), PetConfig._ZERO_OK)
        except (ValueError, TypeError) as exc:
            errors[f'{klucz}_{pola[0]}'] = f'Nieprawidłowa wartość: {exc}'
            continue
        values[klucz] = (surowe, typ)
    return values, errors
