"""Add created_by_admin_id to orders for admin-placed extra orders

Revision ID: a5458721cd81
Revises: 58b97392cedb
Create Date: 2026-05-01 17:58:49.399570

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5458721cd81'
down_revision = '58b97392cedb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('created_by_admin_id', sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_orders_created_by_admin_id'),
            ['created_by_admin_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_orders_created_by_admin_id',
            'users',
            ['created_by_admin_id'],
            ['id'],
        )


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_orders_created_by_admin_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_orders_created_by_admin_id'))
        batch_op.drop_column('created_by_admin_id')
