"""Add exclusive set bonuses and order item bonus fields

Revision ID: a6635d3f4d56
Revises: 3e03d1983083
Create Date: 2026-03-06 15:09:51.025779

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a6635d3f4d56'
down_revision = '3e03d1983083'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create exclusive_set_bonuses table
    op.create_table('exclusive_set_bonuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('trigger_type', sa.Enum('buy_products', 'price_threshold', 'quantity_threshold', name='bonus_trigger_type'), nullable=False),
        sa.Column('threshold_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('bonus_product_id', sa.Integer(), nullable=False),
        sa.Column('bonus_quantity', sa.Integer(), nullable=False),
        sa.Column('bonus_label', sa.String(length=200), nullable=True),
        sa.Column('max_available', sa.Integer(), nullable=True),
        sa.Column('when_exhausted', sa.Enum('hide', 'show_exhausted', name='bonus_when_exhausted'), nullable=False),
        sa.Column('count_full_set', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bonus_product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['section_id'], ['exclusive_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_exclusive_set_bonuses_section_id', 'exclusive_set_bonuses', ['section_id'])

    # 2. Create exclusive_set_bonus_required_products table
    op.create_table('exclusive_set_bonus_required_products',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bonus_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('min_quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['bonus_id'], ['exclusive_set_bonuses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_exclusive_set_bonus_required_products_bonus_id', 'exclusive_set_bonus_required_products', ['bonus_id'])

    # 3. Add bonus fields to order_items
    op.add_column('order_items', sa.Column('is_bonus', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('order_items', sa.Column('bonus_source_section_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_order_items_bonus_source_section',
        'order_items', 'exclusive_sections',
        ['bonus_source_section_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    op.drop_constraint('fk_order_items_bonus_source_section', 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'bonus_source_section_id')
    op.drop_column('order_items', 'is_bonus')
    op.drop_index('ix_exclusive_set_bonus_required_products_bonus_id', 'exclusive_set_bonus_required_products')
    op.drop_table('exclusive_set_bonus_required_products')
    op.drop_index('ix_exclusive_set_bonuses_section_id', 'exclusive_set_bonuses')
    op.drop_table('exclusive_set_bonuses')
