"""Remove guest order columns from orders table

Revision ID: 40e7b60d7360
Revises: ba7ae52feb68
Create Date: 2026-03-02 19:30:56.973064

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '40e7b60d7360'
down_revision = 'ba7ae52feb68'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_orders_guest_view_token'))
        batch_op.drop_column('guest_view_token')
        batch_op.drop_column('guest_name')
        batch_op.drop_column('guest_phone')
        batch_op.drop_column('guest_email')
        batch_op.drop_column('is_guest_order')


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_guest_order', mysql.TINYINT(display_width=1), server_default=sa.text('0'), nullable=True))
        batch_op.add_column(sa.Column('guest_email', mysql.VARCHAR(length=120), nullable=True))
        batch_op.add_column(sa.Column('guest_phone', mysql.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('guest_name', mysql.VARCHAR(length=100), nullable=True))
        batch_op.add_column(sa.Column('guest_view_token', mysql.VARCHAR(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_orders_guest_view_token'), ['guest_view_token'], unique=True)
