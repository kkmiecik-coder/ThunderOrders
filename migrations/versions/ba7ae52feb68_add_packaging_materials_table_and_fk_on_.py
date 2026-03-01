"""Add packaging_materials table and FK on orders

Revision ID: ba7ae52feb68
Revises: 22e992c94ec5
Create Date: 2026-03-01 17:58:27.842588

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ba7ae52feb68'
down_revision = '22e992c94ec5'
branch_labels = None
depends_on = None


def upgrade():
    # Create packaging_materials table
    op.create_table('packaging_materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('inner_length', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('inner_width', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('inner_height', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('max_weight', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('own_weight', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('quantity_in_stock', sa.Integer(), nullable=True),
        sa.Column('low_stock_threshold', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Add packaging_material_id FK column to orders
    op.add_column('orders', sa.Column('packaging_material_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_orders_packaging_material_id',
        'orders', 'packaging_materials',
        ['packaging_material_id'], ['id']
    )


def downgrade():
    # Remove FK and column from orders
    op.drop_constraint('fk_orders_packaging_material_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'packaging_material_id')

    # Drop packaging_materials table
    op.drop_table('packaging_materials')
