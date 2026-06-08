"""Add preview_enabled to offer_pages

Revision ID: 4b86ef34e7b5
Revises: a5458721cd81
Create Date: 2026-06-08 20:39:56.964229

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4b86ef34e7b5'
down_revision = 'a5458721cd81'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('offer_pages', sa.Column('preview_enabled', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    op.drop_column('offer_pages', 'preview_enabled')
