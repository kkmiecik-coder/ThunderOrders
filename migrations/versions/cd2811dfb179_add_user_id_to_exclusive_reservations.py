"""Add user_id to exclusive_reservations

Revision ID: cd2811dfb179
Revises: d5fbc91d1c10
Create Date: 2026-03-22 22:50:39.923945

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cd2811dfb179'
down_revision = 'd5fbc91d1c10'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('exclusive_reservations', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_exclusive_reservations_user_id', 'exclusive_reservations', 'users', ['user_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_exclusive_reservations_user_id', 'exclusive_reservations', type_='foreignkey')
    op.drop_column('exclusive_reservations', 'user_id')
