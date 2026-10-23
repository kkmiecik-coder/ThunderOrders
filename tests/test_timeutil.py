"""Testy modułu utils/timeutil: pomocniki UTC/PL i typ kolumny UTCDateTime."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
from sqlalchemy.exc import StatementError

from utils.timeutil import (
    PL_TZ,
    UTCDateTime,
    iso_utc,
    parse_pl_input,
    pl_date,
    pl_day_bounds_utc,
    pl_input_to_utc,
    pl_today,
    to_pl,
    utcnow,
)

UTC = timezone.utc


def test_utcnow_aware():
    assert utcnow().tzinfo == UTC


def test_pl_input_to_utc_lato_i_zima():
    assert pl_input_to_utc(datetime(2026, 7, 1, 20, 0)) == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
    assert pl_input_to_utc(datetime(2026, 12, 1, 20, 0)) == datetime(2026, 12, 1, 19, 0, tzinfo=UTC)
    assert pl_input_to_utc(None) is None


def test_pl_input_to_utc_aware_rzuca():
    with pytest.raises(ValueError):
        pl_input_to_utc(datetime(2026, 7, 1, 20, 0, tzinfo=UTC))


def test_podwojna_godzina():
    # 25.10.2026 o 2:30 zdarza się dwa razy; wybieramy pierwsze wystąpienie (fold=0, CEST)
    assert pl_input_to_utc(datetime(2026, 10, 25, 2, 30)) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert to_pl(datetime(2026, 10, 25, 1, 30, tzinfo=UTC)).hour == 2


def test_to_pl_konwertuje_aware_utc():
    wynik = to_pl(datetime(2026, 7, 1, 18, 0, tzinfo=UTC))
    assert wynik.tzinfo == PL_TZ
    assert (wynik.hour, wynik.day) == (20, 1)
    assert to_pl(None) is None


def test_to_pl_naiwny_rzuca():
    with pytest.raises(ValueError):
        to_pl(datetime(2026, 7, 1, 18, 0))


def test_parse_pl_input():
    assert parse_pl_input('2026-07-01T20:00') == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
    assert parse_pl_input('01.07.2026 20:00', '%d.%m.%Y %H:%M') == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
    assert parse_pl_input('') is None
    assert parse_pl_input(None) is None


def test_pl_today_to_data_polska():
    assert pl_today() == datetime.now(PL_TZ).date()


def test_pl_day_bounds_utc():
    assert pl_day_bounds_utc(date(2026, 7, 1)) == (
        datetime(2026, 6, 30, 22, 0, tzinfo=UTC),
        datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )
    # doba, w której cofamy zegary, ma 25 h; doba, w której je przesuwamy, 23 h
    start, koniec = pl_day_bounds_utc(date(2026, 10, 25))
    assert koniec - start == timedelta(hours=25)
    start, koniec = pl_day_bounds_utc(date(2026, 3, 29))
    assert koniec - start == timedelta(hours=23)


def test_pl_date_po_polnocy():
    assert pl_date(datetime(2026, 7, 1, 22, 30, tzinfo=UTC)) == date(2026, 7, 2)
    assert pl_date(datetime(2026, 7, 1, 21, 30, tzinfo=UTC)) == date(2026, 7, 1)


def test_iso_utc():
    assert iso_utc(datetime(2026, 10, 30, 19, 0, tzinfo=UTC)) == '2026-10-30T19:00:00Z'
    assert iso_utc(datetime(2026, 7, 1, 20, 0, tzinfo=PL_TZ)) == '2026-07-01T18:00:00Z'
    assert iso_utc(None) is None


def _tabela_testowa():
    """Własny silnik SQLite i tabela — niezależnie od modeli aplikacji."""
    silnik = create_engine('sqlite://')
    metadane = MetaData()
    tabela = Table(
        'czas_test', metadane,
        Column('id', Integer, primary_key=True),
        Column('kiedy', UTCDateTime, nullable=True),
    )
    metadane.create_all(silnik)
    return silnik, tabela


def test_utcdatetime_roundtrip():
    silnik, tabela = _tabela_testowa()
    zapis = datetime(2026, 7, 1, 20, 0, tzinfo=PL_TZ)  # lato: UTC+2
    with silnik.begin() as polaczenie:
        polaczenie.execute(tabela.insert().values(id=1, kiedy=zapis))
        odczyt = polaczenie.execute(select(tabela.c.kiedy)).scalar_one()
        # w bazie leży naiwny UTC
        surowy = polaczenie.exec_driver_sql('SELECT kiedy FROM czas_test').scalar_one()
    assert odczyt == datetime(2026, 7, 1, 18, 0, tzinfo=UTC)
    assert odczyt.tzinfo == UTC
    assert surowy.startswith('2026-07-01 18:00:00')


def test_utcdatetime_none():
    silnik, tabela = _tabela_testowa()
    with silnik.begin() as polaczenie:
        polaczenie.execute(tabela.insert().values(id=1, kiedy=None))
        assert polaczenie.execute(select(tabela.c.kiedy)).scalar_one() is None


def test_utcdatetime_naiwny_rzuca():
    silnik, tabela = _tabela_testowa()
    with pytest.raises(StatementError) as blad:
        with silnik.begin() as polaczenie:
            polaczenie.execute(tabela.insert().values(id=1, kiedy=datetime(2026, 7, 1, 20, 0)))
    assert isinstance(blad.value.orig, ValueError)
    assert 'naiwny datetime' in str(blad.value.orig)


def test_polaczenie_mariadb_dostaje_strefe_utc():
    from unittest import mock

    import pymysql
    from extensions import _ustaw_strefe_utc_w_mariadb

    polaczenie = mock.MagicMock(spec=pymysql.connections.Connection)
    _ustaw_strefe_utc_w_mariadb(polaczenie, None)
    polaczenie.cursor.return_value.execute.assert_called_once_with("SET time_zone = '+00:00'")


def test_polaczenie_sqlite_bez_ustawiania_strefy():
    import sqlite3

    from extensions import _ustaw_strefe_utc_w_mariadb

    # SQLite nie zna SET time_zone - listener ma go pominąć bez błędu
    _ustaw_strefe_utc_w_mariadb(sqlite3.connect(':memory:'), None)


@pytest.mark.parametrize('wartosc', ['2026-07-01 20:00:00', date(2026, 7, 1)])
def test_utcdatetime_tekst_i_data_rzucaja_valueerror(wartosc):
    # Surowy tekst (np. argument CLI) albo `date` nie mają strefy - ValueError z nazwą typu,
    # a nie AttributeError z `.tzinfo`
    silnik, tabela = _tabela_testowa()
    with pytest.raises(StatementError) as blad:
        with silnik.begin() as polaczenie:
            polaczenie.execute(select(tabela.c.id).where(tabela.c.kiedy >= wartosc))
    assert isinstance(blad.value.orig, ValueError)
    assert type(wartosc).__name__ in str(blad.value.orig)
