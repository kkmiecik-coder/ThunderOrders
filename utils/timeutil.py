"""
Czas w ThunderOrders: w bazie i w kodzie zawsze UTC, w Polsce tylko na brzegach.
===============================================================================

Zasady:
    - w bazie leży naiwny UTC (kolumny `UTCDateTime`), w kodzie aware UTC (`utcnow()`),
    - czas polski (`Europe/Warsaw`) pojawia się wyłącznie przy wyświetlaniu, wczytaniu
      formularza i liczeniu granic polskiej doby (statystyki: filtr w SQL zakresem z
      `pl_day_bounds_utc`, kubełki dni w Pythonie przez `bucket_by_pl_day`),
    - stała strefa nigdy nie jest stałym offsetem (zmiana czasu: 23 h / 25 h doby).

Naiwny datetime w miejscu, gdzie oczekujemy czasu, to błąd — rzucamy `ValueError`,
zamiast zgadywać strefę.
"""
import logging
from collections.abc import Iterable
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.types import DateTime, TypeDecorator

PL_TZ = ZoneInfo('Europe/Warsaw')


def utcnow() -> datetime:
    """Bieżąca chwila jako aware UTC."""
    return datetime.now(timezone.utc)


def to_pl(dt: datetime | None) -> datetime | None:
    """Aware datetime -> aware czas polski. Naiwny datetime to błąd (`ValueError`)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError(f'to_pl: naiwny datetime {dt!r} - oczekiwano aware (UTC)')
    return dt.astimezone(PL_TZ)


def pl_input_to_utc(naive_pl: datetime | None) -> datetime | None:
    """Naiwny czas polski (np. z formularza) -> aware UTC.

    Przy podwójnej godzinie (jesienna zmiana czasu) wybiera pierwsze wystąpienie (`fold=0`).
    """
    if naive_pl is None:
        return None
    if naive_pl.tzinfo is not None:
        raise ValueError(f'pl_input_to_utc: oczekiwano naiwnego czasu polskiego, jest {naive_pl!r}')
    return naive_pl.replace(tzinfo=PL_TZ, fold=0).astimezone(timezone.utc)


def parse_pl_input(s: str | None, fmt: str = '%Y-%m-%dT%H:%M') -> datetime | None:
    """Tekst z formularza (czas polski) -> aware UTC. Pusty tekst daje `None`."""
    if not s:
        return None
    return pl_input_to_utc(datetime.strptime(s, fmt))


def format_pl_input(dt: datetime | None, fmt: str = '%Y-%m-%dT%H:%M') -> str:
    """Aware chwila -> tekst do pola formularza w czasie polskim (odwrotność `parse_pl_input`).

    Pusty tekst dla `None`; naiwny datetime to błąd (`ValueError`, jak w `to_pl`).
    """
    if dt is None:
        return ''
    return to_pl(dt).strftime(fmt)


def pl_today() -> date:
    """Dzisiejsza data w Polsce."""
    return datetime.now(PL_TZ).date()


def pl_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """Półotwarty przedział `[start, koniec)` w aware UTC dla polskiej doby `d`.

    Liczony z lokalnych północy, a nie przez +24 h — w dniach zmiany czasu doba ma 23 h lub 25 h.
    """
    start = datetime.combine(d, time.min, tzinfo=PL_TZ)
    koniec = datetime.combine(d + timedelta(days=1), time.min, tzinfo=PL_TZ)
    return start.astimezone(timezone.utc), koniec.astimezone(timezone.utc)


def pl_date(dt: datetime) -> date:
    """Data polska dla aware chwili (np. do kubełkowania po dniach)."""
    return to_pl(dt).date()


def bucket_by_pl_day(rows: Iterable[tuple[datetime | None, Any]]) -> dict[date, list]:
    """Pary `(chwila, wartość)` -> `{polska data: [wartości]}` w kolejności wejścia.

    Zamiast `func.date(kolumna)` w SQL: baza zna tylko dobę UTC, a dzień w statystykach
    to doba polska. Wiersze bez chwili są pomijane, naiwna chwila to błąd (jak w `to_pl`).
    """
    kubelki = {}
    for chwila, wartosc in rows:
        if chwila is None:
            continue
        kubelki.setdefault(pl_date(chwila), []).append(wartosc)
    return kubelki


def iso_utc(dt: datetime | None) -> str | None:
    """Aware datetime -> ISO w UTC z sufiksem `Z`, np. `2026-10-30T19:00:00Z`."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError(f'iso_utc: naiwny datetime {dt!r} - oczekiwano aware')
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


DISPLAY_TIMEZONES_KEY = 'display_timezones'
DEFAULT_DISPLAY_TIMEZONES = ({'label': 'Seul', 'tz': 'Asia/Seoul'},)


def get_display_timezones() -> list[dict]:
    """Miasta z podpowiedzi przy godzinach: `[{"label": "Seul", "tz": "Asia/Seoul"}, ...]`.

    Lista z ustawień (`Settings`, typ json) edytowana przez admina; bez wiersza — Seul.
    Zapisana pusta lista to świadome wyłączenie podpowiedzi, nie powrót do domyślnej.
    Zepsuty wiersz (nie-JSON albo nie lista) daje listę domyślną, a wpisy bez tekstowych
    `label` i `tz` są pomijane — lista idzie na `<body>` każdej strony, więc podpowiedź nie
    może wywrócić całego panelu.
    """
    from modules.auth.models import Settings   # import leniwy: modele importują ten moduł

    try:
        strefy = Settings.get_value(DISPLAY_TIMEZONES_KEY)
    except (ValueError, TypeError):     # nie-JSON albo NULL w kolumnie value
        logging.getLogger(__name__).warning('display_timezones: wartość nie jest JSON-em, używam domyślnej')
        strefy = None
    if strefy is not None and not isinstance(strefy, list):
        logging.getLogger(__name__).warning('display_timezones: wartość nie jest listą, używam domyślnej')
        strefy = None
    if strefy is None:
        return [dict(s) for s in DEFAULT_DISPLAY_TIMEZONES]
    return [
        {'label': s['label'], 'tz': s['tz']} for s in strefy
        if isinstance(s, dict) and isinstance(s.get('label'), str) and isinstance(s.get('tz'), str)
    ]


class UTCDateTime(TypeDecorator):
    """Kolumna czasu: do bazy idzie naiwny UTC, z bazy wraca aware UTC.

    Zapis naiwnego datetime to błąd (`ValueError`, w SQLAlchemy opakowany w `StatementError`) —
    nie zgadujemy, czy to był czas polski, czy UTC. Tak samo tekst czy `date` (np. surowy
    argument z CLI w porównaniu) — najpierw `parse_pl_input()` albo `pl_day_bounds_utc()`.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValueError(
                f'UTCDateTime: oczekiwano aware datetime, jest {type(value).__name__} {value!r} '
                f'- tekst zamień przez parse_pl_input(), datę przez pl_day_bounds_utc()'
            )
        if value.tzinfo is None:
            raise ValueError(f'UTCDateTime: naiwny datetime {value!r} - użyj aware (utcnow(), pl_input_to_utc())')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
