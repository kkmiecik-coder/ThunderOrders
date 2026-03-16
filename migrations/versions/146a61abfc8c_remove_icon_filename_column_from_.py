"""Remove icon_filename column from achievement table

Revision ID: 146a61abfc8c
Revises: 409f3b11895d
Create Date: 2026-03-16 20:29:22.442772

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '146a61abfc8c'
down_revision = '409f3b11895d'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('achievement', 'icon_filename')


def downgrade():
    op.add_column('achievement', sa.Column('icon_filename', sa.String(length=120), nullable=True))
