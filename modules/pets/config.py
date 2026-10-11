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
