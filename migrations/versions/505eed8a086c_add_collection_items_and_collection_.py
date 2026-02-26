"""Add collection_items and collection_item_images tables

Revision ID: 505eed8a086c
Revises: 5108c4bac441
Create Date: 2026-02-26 23:45:16.483973

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '505eed8a086c'
down_revision = '5108c4bac441'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('collection_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('market_price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=True),
        sa.Column('order_item_id', sa.Integer(), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('collection_items', schema=None) as batch_op:
        batch_op.create_index('ix_collection_items_user_id', ['user_id'], unique=False)

    op.create_table('collection_item_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('collection_item_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('path_original', sa.String(length=500), nullable=False),
        sa.Column('path_compressed', sa.String(length=500), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['collection_item_id'], ['collection_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('collection_item_images')
    op.drop_table('collection_items')
