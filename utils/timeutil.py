"""
Czas w ThunderOrders: w bazie i w kodzie zawsze UTC, w Polsce tylko na brzegach.
===============================================================================

Zasady:
    - w bazie leży naiwny UTC (kolumny `UTCDateTime`), w kodzie aware UTC (`utcnow()`),
    - czas polski (`Europe/Warsaw`) pojawia się wyłącznie przy wyświetlaniu, wczytaniu
      formularza i liczeniu granic polskiej doby,
    - stała strefa nigdy nie jest stałym offsetem (zmiana czasu: 23 h / 25 h doby).

Naiwny datetime w miejscu, gdzie oczekujemy czasu, to błąd — rzucamy `ValueError`,
zamiast zgadywać strefę.
"""
from datetime import date, datetime, time, timedelta, timezone
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


def iso_utc(dt: datetime | None) -> str | None:
    """Aware datetime -> ISO w UTC z sufiksem `Z`, np. `2026-10-30T19:00:00Z`."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        raise ValueError(f'iso_utc: naiwny datetime {dt!r} - oczekiwano aware')
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class UTCDateTime(TypeDecorator):
    """Kolumna czasu: do bazy idzie naiwny UTC, z bazy wraca aware UTC.

    Zapis naiwnego datetime to błąd (`ValueError`, w SQLAlchemy opakowany w `StatementError`) —
    nie zgadujemy, czy to był czas polski, czy UTC.
    """
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f'UTCDateTime: naiwny datetime {value!r} - użyj aware (utcnow(), pl_input_to_utc())')
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
