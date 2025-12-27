"""Merge migration heads

Revision ID: 9556407dc0e2
Revises: b1c2d3e4f5a6, f5fe71f921ef
Create Date: 2025-12-27 01:02:37.211823

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9556407dc0e2'
down_revision = ('b1c2d3e4f5a6', 'f5fe71f921ef')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
