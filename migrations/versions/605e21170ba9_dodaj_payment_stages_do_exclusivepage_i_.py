"""Dodaj payment_stages do ExclusivePage i Order

Revision ID: 605e21170ba9
Revises: 69ff99fe4e3c
Create Date: 2026-02-17 20:07:34.581043

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '605e21170ba9'
down_revision = '69ff99fe4e3c'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj kolumnę payment_stages do exclusive_pages (default=3, NOT NULL)
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_stages', sa.Integer(), nullable=False, server_default='4'))

    # Dodaj kolumnę payment_stages do orders (nullable)
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_stages', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('payment_stages')

    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.drop_column('payment_stages')
