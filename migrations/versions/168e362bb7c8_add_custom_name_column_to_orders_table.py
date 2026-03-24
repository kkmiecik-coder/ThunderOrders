"""Add custom_name column to orders table

Revision ID: 168e362bb7c8
Revises: cd2811dfb179
Create Date: 2026-03-24 22:30:59.837310

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '168e362bb7c8'
down_revision = 'cd2811dfb179'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('custom_name', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('orders', 'custom_name')
