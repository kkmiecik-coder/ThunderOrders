"""Zmiana statusów poland_orders: w_drodze/w_urzedzie_celnym -> zamowione

Revision ID: c3d4e5f6a7b8
Revises: a8b9c0d1e2f3
Create Date: 2026-02-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'a8b9c0d1e2f3'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Expand ENUM to include new value alongside old ones
    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('w_drodze', 'w_urzedzie_celnym', 'dostarczone_gom', 'anulowane', 'zamowione') "
        "NOT NULL DEFAULT 'w_drodze'"
    )

    # 2. Map old values to new
    op.execute("UPDATE poland_orders SET status = 'zamowione' WHERE status IN ('w_drodze', 'w_urzedzie_celnym')")

    # 3. Shrink ENUM to final values only
    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('zamowione', 'dostarczone_gom', 'anulowane') "
        "NOT NULL DEFAULT 'zamowione'"
    )


def downgrade():
    # 1. Expand ENUM to include old values
    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('zamowione', 'dostarczone_gom', 'anulowane', 'w_drodze', 'w_urzedzie_celnym') "
        "NOT NULL DEFAULT 'zamowione'"
    )

    # 2. Map back
    op.execute("UPDATE poland_orders SET status = 'w_drodze' WHERE status = 'zamowione'")

    # 3. Shrink to original ENUM
    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('w_drodze', 'w_urzedzie_celnym', 'dostarczone_gom', 'anulowane') "
        "NOT NULL DEFAULT 'w_drodze'"
    )
