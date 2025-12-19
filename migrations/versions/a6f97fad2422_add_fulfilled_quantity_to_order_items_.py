"""Add fulfilled_quantity to order_items for partial set fulfillment

Revision ID: a6f97fad2422
Revises: d37bd8d9335b
Create Date: 2025-12-19 13:13:43.708441

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a6f97fad2422'
down_revision = 'd37bd8d9335b'
branch_labels = None
depends_on = None


def upgrade():
    # Add fulfilled_quantity column to order_items
    op.add_column('order_items', sa.Column('fulfilled_quantity', sa.Integer(), nullable=True))


def downgrade():
    # Remove fulfilled_quantity column from order_items
    op.drop_column('order_items', 'fulfilled_quantity')
