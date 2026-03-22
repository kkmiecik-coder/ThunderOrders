"""Add repeatable field to exclusive_set_bonuses

Revision ID: d5fbc91d1c10
Revises: ed001c28669a
Create Date: 2026-03-22 22:38:26.772649

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd5fbc91d1c10'
down_revision = 'ed001c28669a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('exclusive_set_bonuses', sa.Column('repeatable', sa.Boolean(), nullable=True, server_default='0'))


def downgrade():
    op.drop_column('exclusive_set_bonuses', 'repeatable')
