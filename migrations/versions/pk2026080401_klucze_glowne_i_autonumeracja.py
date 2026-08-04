"""klucze glowne i autonumeracja dla 6 tabel

Sześć tabel na produkcji powstało bez PRIMARY KEY i bez AUTO_INCREMENT na
kolumnie `id`. MariaDB odrzuca wtedy każdy INSERT, który nie podaje `id`
jawnie, błędem 1364 ("Field 'id' doesn't have a default value") — czyli
zapis do tych tabel z poziomu aplikacji był niemożliwy.

Wyszło to przy masowym anulowaniu zamówień, które zapisuje powód jako
komentarz do zamówienia (`order_comments`). Tabela miała zero wierszy —
komentarza do zamówienia nigdy na produkcji nie udało się dodać. Tak samo
`order_refunds`, więc wystawienie zwrotu też by się wysypało.

Modele w kodzie zawsze deklarowały `id` jako klucz główny, więc baza
testowa (budowana z modeli) była poprawna i żaden test tego nie wykrywał.
Rozjechała się wyłącznie baza produkcyjna.

Migracja jest bezpieczna do wielokrotnego uruchomienia: pomija tabele,
które klucz główny już mają.

Revision ID: pk2026080401
Revises: 18128f2dca91
Create Date: 2026-08-04 13:34:43.874864

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'pk2026080401'
down_revision = '18128f2dca91'
branch_labels = None
depends_on = None


# Tabele bez klucza głównego (stan produkcji na 2026-08-04).
# Wszystkie mają kolumnę `id` typu int(11) NOT NULL.
TABELE = (
    'order_comments',
    'order_refunds',
    'order_templates',
    'order_template_items',
    'exclusive_products',
    'email_templates',
)


def _istnieje(polaczenie, tabela):
    return polaczenie.execute(sa.text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = :t
    """), {'t': tabela}).scalar() > 0


def _ma_klucz_glowny(polaczenie, tabela):
    return polaczenie.execute(sa.text("""
        SELECT COUNT(*) FROM information_schema.table_constraints
        WHERE table_schema = DATABASE()
          AND table_name = :t
          AND constraint_type = 'PRIMARY KEY'
    """), {'t': tabela}).scalar() > 0


def upgrade():
    polaczenie = op.get_bind()

    # SQLite (baza testowa) nie zna information_schema ani MODIFY COLUMN,
    # a tam schemat i tak jest poprawny, bo powstaje z modeli.
    if polaczenie.dialect.name != 'mysql':
        return

    for tabela in TABELE:
        if not _istnieje(polaczenie, tabela):
            continue
        if _ma_klucz_glowny(polaczenie, tabela):
            continue

        # ADD PRIMARY KEY musi zadziałać przed MODIFY ... AUTO_INCREMENT —
        # MariaDB nie pozwala na kolumnę AUTO_INCREMENT, która nie jest kluczem.
        # W jednym ALTER-ze silnik wykonuje to we właściwej kolejności.
        # AUTO_INCREMENT wystartuje od MAX(id)+1, więc istniejące wiersze
        # (email_templates ma id 1-6) zachowują swoje numery.
        op.execute(
            f'ALTER TABLE `{tabela}` '
            f'ADD PRIMARY KEY (`id`), '
            f'MODIFY `id` INT(11) NOT NULL AUTO_INCREMENT'
        )


def downgrade():
    polaczenie = op.get_bind()

    if polaczenie.dialect.name != 'mysql':
        return

    for tabela in TABELE:
        if not _istnieje(polaczenie, tabela):
            continue
        if not _ma_klucz_glowny(polaczenie, tabela):
            continue

        op.execute(
            f'ALTER TABLE `{tabela}` '
            f'MODIFY `id` INT(11) NOT NULL, '
            f'DROP PRIMARY KEY'
        )
