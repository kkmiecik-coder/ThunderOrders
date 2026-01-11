"""Add payment_method to shipping_requests

Revision ID: a1b2c3d4e5f6
Revises: 8b9c0cbaf032
Create Date: 2026-01-11 04:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '8b9c0cbaf032'
branch_labels = None
depends_on = None


def upgrade():
    # Add payment_method column to shipping_requests table
    op.add_column('shipping_requests', sa.Column('payment_method', sa.String(length=100), nullable=True))


def downgrade():
    # Remove payment_method column from shipping_requests table
    op.drop_column('shipping_requests', 'payment_method')
