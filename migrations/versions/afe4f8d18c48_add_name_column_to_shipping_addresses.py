"""Add name column to shipping_addresses

Revision ID: afe4f8d18c48
Revises: 6da5b6edca1e
Create Date: 2026-01-11 01:49:29.847663

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'afe4f8d18c48'
down_revision = '6da5b6edca1e'
branch_labels = None
depends_on = None


def upgrade():
    # Dodanie kolumny 'name' do tabeli shipping_addresses
    op.add_column('shipping_addresses', sa.Column('name', sa.String(length=100), nullable=True))


def downgrade():
    # Usunięcie kolumny 'name' z tabeli shipping_addresses
    op.drop_column('shipping_addresses', 'name')
