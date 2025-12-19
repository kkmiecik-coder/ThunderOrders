"""Add guest_view_token to orders

Revision ID: f5fe71f921ef
Revises: ef96d9758ddd
Create Date: 2025-12-19 15:56:48.650150

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f5fe71f921ef'
down_revision = 'ef96d9758ddd'
branch_labels = None
depends_on = None


def upgrade():
    # Add guest_view_token column to orders table
    op.add_column('orders', sa.Column('guest_view_token', sa.String(length=64), nullable=True))

    # Create unique index on guest_view_token
    op.create_index('ix_orders_guest_view_token', 'orders', ['guest_view_token'], unique=True)


def downgrade():
    # Drop index first
    op.drop_index('ix_orders_guest_view_token', table_name='orders')

    # Drop column
    op.drop_column('orders', 'guest_view_token')
