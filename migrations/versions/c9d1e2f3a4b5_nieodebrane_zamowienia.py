"""Kolumny pod listę nieodebranych zamówień.

`orders.status_changed_at` — moment wejścia w obecny status; źródło kolumny
„leży X dni". Nullable i BEZ backfillu: dla zamówień sprzed wdrożenia wiek liczy
się z `activity_log`, a wpisanie im tu daty migracji byłoby cichym kłamstwem
(wszystkie zaległości wyglądałyby na świeże).

`orders.pickup_reminder_sent_at` — kiedy ostatnio poszło przypomnienie o odbiorze.
Nullable, bo przed wdrożeniem żadne nie poszło.

Podpięte pod 6b335dbff596: historia migracji ma trzy głowy, z czego dwie pochodzą
z grudnia 2025. Żywa jest ta gałąź.

Revision ID: c9d1e2f3a4b5
Revises: 6b335dbff596
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1e2f3a4b5'
down_revision = '6b335dbff596'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('status_changed_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('pickup_reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('orders', 'pickup_reminder_sent_at')
    op.drop_column('orders', 'status_changed_at')
