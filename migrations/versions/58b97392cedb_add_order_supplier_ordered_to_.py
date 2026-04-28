"""add order_supplier_ordered to notification_preferences

Revision ID: 58b97392cedb
Revises: 405efca8e619
Create Date: 2026-04-28 09:45:39.540564

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '58b97392cedb'
down_revision = '405efca8e619'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'order_supplier_ordered',
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('order_supplier_ordered')
