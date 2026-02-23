"""Add is_archived to poland_orders

Revision ID: 7ddafcc51794
Revises: d7eb037b264b
Create Date: 2026-02-22 01:19:30.779473

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7ddafcc51794'
down_revision = 'd7eb037b264b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('poland_orders', sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    op.drop_column('poland_orders', 'is_archived')
