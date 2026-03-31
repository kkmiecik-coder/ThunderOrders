"""Rename exclusive tables to offers, add page_type

Revision ID: b1a2c3d4e5f6
Revises: c501f414652a
Create Date: 2026-03-31 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1a2c3d4e5f6'
down_revision = 'c501f414652a'
branch_labels = None
depends_on = None


def upgrade():
    # ===========================================
    # 1. Rename exclusive tables to offer tables
    # ===========================================
    op.rename_table('exclusive_pages', 'offer_pages')
    op.rename_table('exclusive_sections', 'offer_sections')
    op.rename_table('exclusive_set_items', 'offer_set_items')
    op.rename_table('exclusive_reservations', 'offer_reservations')
    op.rename_table('exclusive_auto_increase_log', 'offer_auto_increase_log')
    op.rename_table('exclusive_product_notifications', 'offer_product_notifications')
    op.rename_table('exclusive_set_bonuses', 'offer_set_bonuses')
    op.rename_table('exclusive_set_bonus_required_products', 'offer_bonus_required_products')

    # ===========================================
    # 2. Add page_type column to offer_pages
    # ===========================================
    op.add_column('offer_pages', sa.Column(
        'page_type',
        sa.Enum('exclusive', 'preorder', name='offer_page_type'),
        nullable=False,
        server_default='exclusive'
    ))
    op.create_index('ix_offer_pages_page_type', 'offer_pages', ['page_type'])

    # ===========================================
    # 3. Rename columns in orders table
    # ===========================================
    # Rename exclusive_page_id -> offer_page_id
    op.alter_column('orders', 'exclusive_page_id',
                    new_column_name='offer_page_id',
                    existing_type=sa.Integer(),
                    existing_nullable=True)

    # Rename exclusive_page_name -> offer_page_name
    op.alter_column('orders', 'exclusive_page_name',
                    new_column_name='offer_page_name',
                    existing_type=sa.String(200),
                    existing_nullable=True)

    # Drop is_exclusive column
    op.drop_column('orders', 'is_exclusive')

    # ===========================================
    # 4. Update FK references in order_items
    # ===========================================
    # MariaDB: drop old FK, create new FK pointing to renamed tables
    # set_section_id FK: exclusive_sections -> offer_sections
    try:
        op.drop_constraint('order_items_ibfk_4', 'order_items', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'order_items_set_section_fk', 'order_items',
        'offer_sections', ['set_section_id'], ['id'],
        ondelete='SET NULL'
    )

    # bonus_source_section_id FK: exclusive_sections -> offer_sections
    try:
        op.drop_constraint('order_items_ibfk_5', 'order_items', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'order_items_bonus_section_fk', 'order_items',
        'offer_sections', ['bonus_source_section_id'], ['id'],
        ondelete='SET NULL'
    )

    # orders.offer_page_id FK: exclusive_pages -> offer_pages
    try:
        op.drop_constraint('orders_ibfk_2', 'orders', type_='foreignkey')
    except Exception:
        pass
    op.create_foreign_key(
        'orders_offer_page_fk', 'orders',
        'offer_pages', ['offer_page_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade():
    # Drop new FKs
    try:
        op.drop_constraint('orders_offer_page_fk', 'orders', type_='foreignkey')
        op.drop_constraint('order_items_bonus_section_fk', 'order_items', type_='foreignkey')
        op.drop_constraint('order_items_set_section_fk', 'order_items', type_='foreignkey')
    except Exception:
        pass

    # Restore is_exclusive column
    op.add_column('orders', sa.Column('is_exclusive', sa.Boolean(), server_default='0', nullable=True))

    # Rename columns back
    op.alter_column('orders', 'offer_page_name',
                    new_column_name='exclusive_page_name',
                    existing_type=sa.String(200),
                    existing_nullable=True)
    op.alter_column('orders', 'offer_page_id',
                    new_column_name='exclusive_page_id',
                    existing_type=sa.Integer(),
                    existing_nullable=True)

    # Drop page_type
    op.drop_index('ix_offer_pages_page_type', 'offer_pages')
    op.drop_column('offer_pages', 'page_type')

    # Rename tables back
    op.rename_table('offer_bonus_required_products', 'exclusive_set_bonus_required_products')
    op.rename_table('offer_set_bonuses', 'exclusive_set_bonuses')
    op.rename_table('offer_product_notifications', 'exclusive_product_notifications')
    op.rename_table('offer_auto_increase_log', 'exclusive_auto_increase_log')
    op.rename_table('offer_reservations', 'exclusive_reservations')
    op.rename_table('offer_set_items', 'exclusive_set_items')
    op.rename_table('offer_sections', 'exclusive_sections')
    op.rename_table('offer_pages', 'exclusive_pages')

    # Restore old FKs
    op.create_foreign_key(
        'orders_ibfk_2', 'orders',
        'exclusive_pages', ['exclusive_page_id'], ['id'],
        ondelete='SET NULL'
    )
