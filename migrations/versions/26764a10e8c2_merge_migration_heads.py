"""Merge migration heads

Revision ID: 26764a10e8c2
Revises: remove_auto_increase
Create Date: 2025-12-29 23:09:04.346140

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '26764a10e8c2'
down_revision = 'remove_auto_increase'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
