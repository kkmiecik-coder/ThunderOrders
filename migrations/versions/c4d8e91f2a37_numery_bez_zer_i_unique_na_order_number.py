"""Numery zamowien bez zer wiodacych + UNIQUE na orders.order_number

Revision ID: c4d8e91f2a37
Revises: 85499b0cafe0
Create Date: 2026-08-19 12:45:00.000000

ClickUp 869ekw4p0. Dwie rzeczy naraz, bo jedna warunkuje drugą:

1. `orders.order_number` nie miał UNIQUE w bazie (model deklarował `unique=True`,
   ale żadna migracja indeksu nie zakładała). Stary generator czytał ostatni numer
   zwykłym SELECT-em i doklejał +1, więc przy sprzedaży LIVE równoległe zamówienia
   dostawały ten sam numer — w bazie narosło ponad 120 kolizji od kwietnia 2026.
   Duplikaty trzeba rozbić, zanim UNIQUE w ogóle da się założyć.

2. Numery tracą zera wiodące (EX/00001804 -> EX/1804) we wszystkich seriach:
   orders, proxy_orders, poland_orders, shipping_requests.

Rekord z najniższym ID zachowuje swój numer (to jego numer poszedł w mailach do
klienta jako pierwszy), duplikaty dostają kolejne numery za końcem swojej serii —
nie wciskamy ich w luki po skasowanych zamówieniach, bo lipcowe zamówienie
dostałoby wtedy numer wyglądający na kwietniowy.

Podmiana idzie dwufazowo (najpierw numery tymczasowe TMP/{ID}), żeby UPDATE
w tabelach z istniejącym UNIQUE nie zderzył się przejściowo z numerem, który
dopiero za chwilę zostanie zwolniony przez inny rekord.

Logika planu jest tu skopiowana celowo — lustro
`modules.orders.utils.plan_number_normalization` (pokryte testami w
tests/test_order_number_generation.py). Migracja musi zostać wykonywalna także
wtedy, gdy kod aplikacji pójdzie dalej.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c4d8e91f2a37'
down_revision = '85499b0cafe0'
branch_labels = None
depends_on = None


# Tabela, kolumna, szerokość paddingu używana przed tą migracją (dla downgrade)
SERIE = [
    ('orders', 'order_number', 8),
    ('proxy_orders', 'order_number', 5),
    ('poland_orders', 'order_number', 5),
    ('shipping_requests', 'request_number', 6),
]

UNIQUE_ORDERS = 'uq_orders_order_number'


def _normalizuj(numer):
    """'EX/00001804' -> 'EX/1804'; prefiks (także wieloczłonowy) bez zmian."""
    if not numer or '/' not in numer:
        return numer
    prefix, _, sekwencja = numer.rpartition('/')
    if not sekwencja.isdigit():
        return numer
    return f"{prefix}/{int(sekwencja)}"


def _zaplanuj(wiersze):
    """{id: nowy_numer} dla rekordów wymagających zmiany."""
    wiersze = sorted(wiersze, key=lambda r: r[0])
    zarezerwowane = {_normalizuj(numer) for _, numer in wiersze}

    # Koniec każdej serii, od którego dokładamy numery zastępcze
    nastepny_wolny = {}
    for numer in zarezerwowane:
        prefix, _, sekwencja = numer.rpartition('/')
        if sekwencja.isdigit():
            nastepny_wolny[prefix] = max(
                nastepny_wolny.get(prefix, 0), int(sekwencja) + 1
            )

    plan = {}
    zajete = set()

    for rekord_id, numer in wiersze:
        docelowy = _normalizuj(numer)

        if docelowy in zajete:
            prefix, _, _ = docelowy.rpartition('/')
            sekwencja = nastepny_wolny.get(prefix, 1)
            while (f"{prefix}/{sekwencja}" in zajete
                   or f"{prefix}/{sekwencja}" in zarezerwowane):
                sekwencja += 1
            docelowy = f"{prefix}/{sekwencja}"
            nastepny_wolny[prefix] = sekwencja + 1

        zajete.add(docelowy)
        if docelowy != numer:
            plan[rekord_id] = docelowy

    return plan


def _zastosuj(conn, tabela, kolumna, plan):
    """Dwufazowa podmiana numerów — omija przejściowe kolizje z UNIQUE."""
    if not plan:
        return

    tymczasowy = sa.text(
        f"UPDATE {tabela} SET {kolumna} = :numer WHERE id = :id"
    )
    for rekord_id in plan:
        conn.execute(tymczasowy, {'numer': f'TMP/{rekord_id}', 'id': rekord_id})

    for rekord_id, numer in plan.items():
        conn.execute(tymczasowy, {'numer': numer, 'id': rekord_id})


def _istnieje_tabela(conn, tabela):
    return sa.inspect(conn).has_table(tabela)


def _ma_unique_na_order_number(conn):
    for indeks in sa.inspect(conn).get_indexes('orders'):
        if indeks.get('unique') and indeks.get('column_names') == ['order_number']:
            return True
    for uq in sa.inspect(conn).get_unique_constraints('orders'):
        if uq.get('column_names') == ['order_number']:
            return True
    return False


def upgrade():
    conn = op.get_bind()

    for tabela, kolumna, _ in SERIE:
        if not _istnieje_tabela(conn, tabela):
            continue
        wiersze = [
            (r[0], r[1]) for r in
            conn.execute(sa.text(f"SELECT id, {kolumna} FROM {tabela}")).fetchall()
            if r[1]
        ]
        _zastosuj(conn, tabela, kolumna, _zaplanuj(wiersze))

    if not _ma_unique_na_order_number(conn):
        op.create_unique_constraint(UNIQUE_ORDERS, 'orders', ['order_number'])


def downgrade():
    """
    Przywraca zera wiodące i zdejmuje UNIQUE.

    Kolizji numerów rozbitych w upgrade() nie da się odtworzyć — i nie ma po co,
    bo to był efekt buga.
    """
    conn = op.get_bind()

    if _ma_unique_na_order_number(conn):
        op.drop_constraint(UNIQUE_ORDERS, 'orders', type_='unique')

    for tabela, kolumna, szerokosc in SERIE:
        if not _istnieje_tabela(conn, tabela):
            continue
        plan = {}
        for rekord_id, numer in conn.execute(
                sa.text(f"SELECT id, {kolumna} FROM {tabela}")).fetchall():
            if not numer or '/' not in numer:
                continue
            prefix, _, sekwencja = numer.rpartition('/')
            if not sekwencja.isdigit():
                continue
            stary = f"{prefix}/{int(sekwencja):0{szerokosc}d}"
            if stary != numer:
                plan[rekord_id] = stary
        _zastosuj(conn, tabela, kolumna, plan)
