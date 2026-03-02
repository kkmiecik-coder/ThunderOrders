"""Add set_number to order_items

Revision ID: 6e68897ebcd7
Revises: 40e7b60d7360
Create Date: 2026-03-02 23:55:47.224156

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6e68897ebcd7'
down_revision = '40e7b60d7360'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('set_number', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.drop_column('set_number')
