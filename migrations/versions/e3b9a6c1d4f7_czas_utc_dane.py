"""Czas w UTC: przeliczenie zapisanych dat z czasu polskiego na UTC (tylko dane)

Revision ID: e3b9a6c1d4f7
Revises: c7a4d1e9f2b6
Create Date: 2026-10-23

Odwrócenie `timezone_fix_001` (2025-12-27). Kod od tej wersji czyta naiwne wartości
z bazy jako UTC, a dotąd `get_local_now()` zapisywał naiwny czas polski. Migracja
przelicza kolumny z `utils.czas_migracja.KOLUMNY` (lista jawna i zamrożona, z powodami
wykluczeń w `WYKLUCZONE`). Schemat bez zmian.

- wsadami po `WSAD` wierszy według `id` (każdy wiersz dokładnie raz — konwersja nie jest
  idempotentna), jeden UPDATE na wiersz ze wszystkimi kolumnami tabeli naraz,
- NULL zostaje NULL; wartość, która nie jest datetime (np. zerowa data MariaDB), przerywa
  migrację z nazwą tabeli, kolumny i id,
- MariaDB: kolumny z `ON UPDATE CURRENT_TIMESTAMP` spoza listy są przypinane (`kol = kol`),
  żeby UPDATE nie nadpisał ich bieżącym czasem,
- zmiany czasu przez `zoneinfo` (nie stały offset): podwójna jesienna godzina to pierwsze
  wystąpienie (`fold=0`), nieistniejąca wiosenna 2:30 -> 1:30 UTC,
- `downgrade()` to konwersja odwrotna. upgrade + downgrade odtwarza każdą wartość poza
  nieistniejącą wiosenną godziną (2:xx wraca jako 3:xx); downgrade + upgrade — poza drugim
  wystąpieniem jesiennej godziny (wraca 1 h wcześniej). Obie straty są z natury rzeczy.
"""
from datetime import datetime

import sqlalchemy as sa
from alembic import op

from utils.czas_migracja import KOLUMNY, pl_naive_to_utc_naive, utc_naive_to_pl_naive

# revision identifiers, used by Alembic.
revision = 'e3b9a6c1d4f7'
down_revision = 'c7a4d1e9f2b6'
branch_labels = None
depends_on = None

WSAD = 1000


def upgrade():
    _przelicz(pl_naive_to_utc_naive, 'czas polski -> UTC')


def downgrade():
    _przelicz(utc_naive_to_pl_naive, 'UTC -> czas polski')


def _przelicz(konwersja, opis):
    polaczenie = op.get_bind()
    inspektor = sa.inspect(polaczenie)
    print(f'Migracja czasu ({opis}) — przeliczone wartości per kolumna:')
    for tabela, kolumny in KOLUMNY.items():
        klucz = inspektor.get_pk_constraint(tabela)['constrained_columns']
        if klucz != ['id']:
            raise RuntimeError(f'{tabela}: klucz główny {klucz}, migracja obsługuje tylko `id`')
        przypiete = _kolumny_on_update(polaczenie, tabela, kolumny)
        liczniki = _przelicz_tabele(polaczenie, tabela, kolumny, przypiete, konwersja)
        for kolumna in kolumny:
            print(f'  {tabela}.{kolumna}: {liczniki[kolumna]}')
        if przypiete:
            print(f'  ({tabela}: bez zmian ON UPDATE {", ".join(przypiete)})')


def _kolumny_on_update(polaczenie, tabela, kolumny):
    """Kolumny MariaDB z `ON UPDATE CURRENT_TIMESTAMP`, których migracja sama nie ustawia."""
    if polaczenie.dialect.name not in ('mysql', 'mariadb'):
        return []
    wynik = polaczenie.execute(sa.text(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :tabela AND LOWER(EXTRA) LIKE '%on update%'"
    ), {'tabela': tabela})
    return [nazwa for (nazwa,) in wynik if nazwa not in kolumny]


def _przelicz_tabele(polaczenie, tabela, kolumny, przypiete, konwersja):
    t = sa.table(tabela, sa.column('id', sa.Integer),
                 *(sa.column(k, sa.DateTime) for k in [*kolumny, *przypiete]))
    zapytanie = (sa.select(t.c.id, *(t.c[k] for k in kolumny))
                 .where(sa.or_(*(t.c[k].isnot(None) for k in kolumny)))
                 .order_by(t.c.id)
                 .limit(WSAD))
    aktualizacja = (sa.update(t)
                    .where(t.c.id == sa.bindparam('_id'))
                    .values({**{t.c[k]: sa.bindparam(f'_n_{k}') for k in kolumny},
                             **{t.c[k]: t.c[k] for k in przypiete}}))

    liczniki = dict.fromkeys(kolumny, 0)
    ostatnie_id = None
    while True:
        wsad = zapytanie if ostatnie_id is None else zapytanie.where(t.c.id > ostatnie_id)
        wiersze = polaczenie.execute(wsad).all()
        if not wiersze:
            return liczniki
        parametry = []
        for wiersz in wiersze:
            nowe = {'_id': wiersz[0]}
            for kolumna, wartosc in zip(kolumny, wiersz[1:]):
                if wartosc is not None:
                    if not isinstance(wartosc, datetime):
                        raise RuntimeError(f'{tabela}.{kolumna} id={wiersz[0]}: {wartosc!r} to nie datetime')
                    wartosc = konwersja(wartosc)
                    liczniki[kolumna] += 1
                nowe[f'_n_{kolumna}'] = wartosc
            parametry.append(nowe)
        polaczenie.execute(aktualizacja, parametry)
        ostatnie_id = wiersze[-1][0]
