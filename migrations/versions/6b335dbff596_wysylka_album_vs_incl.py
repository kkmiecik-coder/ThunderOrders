"""wysylka album vs incl

Podział kosztu Wysyłki KR na cały album i samo incl — same kolumny, bez
logiki liczenia (ta dojdzie w kolejnym kroku).

`order_items.incl_only_quantity` mówi, ile sztuk z pozycji klient bierze
jako samo incl (reszta to całe albumy). Kolumna jest NOT NULL, a tabela
`order_items` ma na produkcji dane — bez `server_default='0'` MariaDB
odrzuci ALTER TABLE, bo istniejące wiersze nie miałyby czym wypełnić nowej
kolumny. `server_default` załatwia to na poziomie bazy, niezależnie od
tego, co robi ORM.

`poland_order_items.shipping_cost_album_per_unit` i `...incl_per_unit` to
stawki wysyłki KR za sztukę, osobno dla albumu i dla incl. Nullable, bez
domyślnej wartości i bez backfillu — NULL w obu oznacza partię sprzed
rozdzielenia stawek, dla której koszt nadal dzieli się po równo
(shipping_cost / quantity), dokładnie jak wcześniej.

Revision ID: 6b335dbff596
Revises: a7f4c2b91e08
Create Date: 2026-08-31 13:29:59.675957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6b335dbff596'
down_revision = 'a7f4c2b91e08'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('order_items', sa.Column(
        'incl_only_quantity', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('poland_order_items', sa.Column(
        'shipping_cost_album_per_unit', sa.Numeric(10, 2), nullable=True))
    op.add_column('poland_order_items', sa.Column(
        'shipping_cost_incl_per_unit', sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column('poland_order_items', 'shipping_cost_incl_per_unit')
    op.drop_column('poland_order_items', 'shipping_cost_album_per_unit')
    op.drop_column('order_items', 'incl_only_quantity')
