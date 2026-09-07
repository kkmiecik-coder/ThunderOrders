"""Indeks zlozony offer_reservations (offer_page_id, expires_at) - deadlocki przy cleanup

Lazy cleanup rezerwacji kasuje po WHERE offer_page_id = ? AND expires_at < ?.
Tabela miala tylko osobny indeks na expires_at i indeks FK na offer_page_id, wiec
InnoDB blokowal wygasle rezerwacje ze WSZYSTKICH stron ofertowych naraz. Przy starcie
oferty kilkanascie rownoleglych zadan robilo ten sam DELETE i wpadalo w deadlocki
(8 sztuk 2026-09-07 o 10:00 UTC). Indeks zlozony zawezi blokady do jednej strony.

Migracja napisana recznie — autogenerate wykryl kilkanascie niepowiazanych roznic
(dryf modeli wzgledem bazy), ktorych ta zmiana swiadomie NIE dotyka.

Revision ID: dde1a45a7d87
Revises: c9d1e2f3a4b5
Create Date: 2026-09-07 12:49:14.734974

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'dde1a45a7d87'
down_revision = 'c9d1e2f3a4b5'
branch_labels = None
depends_on = None

INDEX_NAME = 'ix_offer_reservations_page_expires'
TABLE_NAME = 'offer_reservations'


def upgrade():
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ['offer_page_id', 'expires_at'],
        unique=False,
    )


def downgrade():
    # Indeks FK na offer_page_id zostaje nietkniety, wiec usuniecie tego
    # indeksu nie odbiera MariaDB podparcia dla klucza obcego.
    op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
