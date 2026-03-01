"""Add picked_quantity to order_items

Revision ID: 22e992c94ec5
Revises: 45101b9ef1c7
Create Date: 2026-02-28 16:54:04.294643

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '22e992c94ec5'
down_revision = '45101b9ef1c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('picked_quantity', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.drop_column('picked_quantity')
