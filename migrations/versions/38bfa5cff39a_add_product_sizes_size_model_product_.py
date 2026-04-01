"""Add product sizes: Size model, product_sizes junction, selected_size on order items

Revision ID: 38bfa5cff39a
Revises: d3e4f5a6b7c8
Create Date: 2026-04-01 23:02:29.832172

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '38bfa5cff39a'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    # Create sizes table
    op.create_table('sizes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Create product_sizes junction table
    op.create_table('product_sizes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('size_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['size_id'], ['sizes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'size_id', name='unique_product_size')
    )

    # Add selected_size to order_items
    op.add_column('order_items', sa.Column('selected_size', sa.String(length=50), nullable=True))

    # Add selected_size to proxy_order_items
    op.add_column('proxy_order_items', sa.Column('selected_size', sa.String(length=50), nullable=True))

    # Add selected_size to poland_order_items
    op.add_column('poland_order_items', sa.Column('selected_size', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('poland_order_items', 'selected_size')
    op.drop_column('proxy_order_items', 'selected_size')
    op.drop_column('order_items', 'selected_size')
    op.drop_table('product_sizes')
    op.drop_table('sizes')
