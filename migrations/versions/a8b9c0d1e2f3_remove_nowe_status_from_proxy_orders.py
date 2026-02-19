"""Remove nowe status from proxy_orders

Revision ID: a8b9c0d1e2f3
Revises: f7e3a9c2b1d4
Create Date: 2026-02-17 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a8b9c0d1e2f3'
down_revision = 'f7e3a9c2b1d4'
branch_labels = None
depends_on = None


def upgrade():
    # Move any existing 'nowe' rows to 'zamowiono'
    op.execute("""
        UPDATE proxy_orders SET status = 'zamowiono'
        WHERE status = 'nowe'
    """)

    # Alter enum to remove 'nowe'
    op.alter_column('proxy_orders', 'status',
                     type_=sa.Enum('zamowiono', 'dostarczone_do_proxy', 'anulowane',
                                   name='proxy_order_status'),
                     existing_nullable=False,
                     server_default='zamowiono')


def downgrade():
    # Re-add 'nowe' to enum
    op.alter_column('proxy_orders', 'status',
                     type_=sa.Enum('nowe', 'zamowiono', 'dostarczone_do_proxy', 'anulowane',
                                   name='proxy_order_status'),
                     existing_nullable=False,
                     server_default='nowe')
