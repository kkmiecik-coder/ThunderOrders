"""Dodaj 6-cyfrowy kod resetu hasla (mobile API)

Revision ID: 261f567bb320
Revises: 9ca192bd4c1d
Create Date: 2026-06-15 20:32:34.853626

Uwaga: autogenerate wykrył dużo szumu (drift modeli vs baza na orders/offers/wms
itd.) niezwiązanego z tą zmianą. Migracja celowo zawęża się WYŁĄCZNIE do 5 nowych
kolumn password_reset_* na users (6-cyfrowy kod resetu hasła dla mobile API).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '261f567bb320'
down_revision = '9ca192bd4c1d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_reset_code', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('password_reset_code_expires', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('password_reset_code_sent_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('password_reset_attempts', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('password_reset_locked_until', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_reset_locked_until')
        batch_op.drop_column('password_reset_attempts')
        batch_op.drop_column('password_reset_code_sent_at')
        batch_op.drop_column('password_reset_code_expires')
        batch_op.drop_column('password_reset_code')
