"""Add selected_size to offer_reservations

Revision ID: e4d65c8baacc
Revises: 38bfa5cff39a
Create Date: 2026-04-02 23:05:13.383966

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e4d65c8baacc'
down_revision = '38bfa5cff39a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('offer_reservations', sa.Column('selected_size', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('offer_reservations', 'selected_size')
