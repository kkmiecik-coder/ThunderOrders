"""Dodaj kolumny logo_light i logo_dark do PaymentMethod

Revision ID: 69ff99fe4e3c
Revises: 3ad9fb792ebb
Create Date: 2026-02-17 00:24:41.815177

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '69ff99fe4e3c'
down_revision = '3ad9fb792ebb'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo_light', sa.String(length=300), nullable=True, comment='Ścieżka do logo dla light mode'))
        batch_op.add_column(sa.Column('logo_dark', sa.String(length=300), nullable=True, comment='Ścieżka do logo dla dark mode'))


def downgrade():
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.drop_column('logo_dark')
        batch_op.drop_column('logo_light')
