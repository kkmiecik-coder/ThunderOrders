"""Add custom product fields to order_items

Revision ID: ef96d9758ddd
Revises: a6f97fad2422
Create Date: 2025-12-19 14:17:17.309604

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ef96d9758ddd'
down_revision = 'a6f97fad2422'
branch_labels = None
depends_on = None


def upgrade():
    # Add custom product fields to order_items
    op.add_column('order_items', sa.Column('custom_name', sa.String(length=255), nullable=True))
    op.add_column('order_items', sa.Column('custom_sku', sa.String(length=100), nullable=True))
    op.add_column('order_items', sa.Column('is_custom', sa.Boolean(), nullable=True, server_default='0'))
    op.add_column('order_items', sa.Column('is_full_set', sa.Boolean(), nullable=True, server_default='0'))

    # Make product_id nullable (to allow custom products without product)
    op.alter_column('order_items', 'product_id',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade():
    # Make product_id NOT NULL again
    op.alter_column('order_items', 'product_id',
                    existing_type=sa.Integer(),
                    nullable=False)

    # Remove custom product fields
    op.drop_column('order_items', 'is_full_set')
    op.drop_column('order_items', 'is_custom')
    op.drop_column('order_items', 'custom_sku')
    op.drop_column('order_items', 'custom_name')
