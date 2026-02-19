"""Dodaj status urzad_celny do poland_orders

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-02-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('zamowione', 'urzad_celny', 'dostarczone_gom', 'anulowane') "
        "NOT NULL DEFAULT 'zamowione'"
    )


def downgrade():
    # Map urzad_celny back to zamowione before shrinking enum
    op.execute("UPDATE poland_orders SET status = 'zamowione' WHERE status = 'urzad_celny'")

    op.execute(
        "ALTER TABLE poland_orders MODIFY COLUMN status "
        "ENUM('zamowione', 'dostarczone_gom', 'anulowane') "
        "NOT NULL DEFAULT 'zamowione'"
    )
