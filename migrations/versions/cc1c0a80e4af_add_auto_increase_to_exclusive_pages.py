"""Add auto-increase to exclusive pages

Revision ID: cc1c0a80e4af
Revises: d822f4f81388
Create Date: 2025-12-29 21:47:15.118083

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'cc1c0a80e4af'
down_revision = 'd822f4f81388'
branch_labels = None
depends_on = None


def upgrade():
    # Add auto-increase columns to exclusive_pages
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_increase_enabled', sa.Boolean(), nullable=True, server_default='0'))
        batch_op.add_column(sa.Column('auto_increase_product_threshold', sa.DECIMAL(precision=5, scale=2), nullable=True, server_default='100.00', comment='Próg wyprzedania produktu (%)'))
        batch_op.add_column(sa.Column('auto_increase_set_threshold', sa.DECIMAL(precision=5, scale=2), nullable=True, server_default='50.00', comment='Próg wyprzedanych produktów w secie (%)'))
        batch_op.add_column(sa.Column('auto_increase_amount', sa.Integer(), nullable=True, server_default='1', comment='Zwiększenie max o (szt.)'))

    # Create exclusive_auto_increase_log table
    op.create_table('exclusive_auto_increase_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exclusive_page_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('old_max_quantity', sa.Integer(), nullable=False),
        sa.Column('new_max_quantity', sa.Integer(), nullable=False),
        sa.Column('products_at_threshold', sa.JSON(), nullable=True, comment='Lista product_id które osiągnęły próg'),
        sa.Column('total_products_in_set', sa.Integer(), nullable=False),
        sa.Column('products_sold_count', sa.JSON(), nullable=True, comment='Mapa {product_id: sold_count}'),
        sa.Column('trigger_product_threshold', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('trigger_set_threshold', sa.DECIMAL(precision=5, scale=2), nullable=False),
        sa.Column('trigger_increase_amount', sa.Integer(), nullable=False),
        sa.Column('triggered_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['exclusive_page_id'], ['exclusive_pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['exclusive_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        mysql_engine='InnoDB'
    )

    # Create indexes for exclusive_auto_increase_log
    with op.batch_alter_table('exclusive_auto_increase_log', schema=None) as batch_op:
        batch_op.create_index('idx_page_section', ['exclusive_page_id', 'section_id'])
        batch_op.create_index('idx_triggered_at', ['triggered_at'])


def downgrade():
    # Drop exclusive_auto_increase_log table
    op.drop_table('exclusive_auto_increase_log')

    # Remove auto-increase columns from exclusive_pages
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.drop_column('auto_increase_amount')
        batch_op.drop_column('auto_increase_set_threshold')
        batch_op.drop_column('auto_increase_product_threshold')
        batch_op.drop_column('auto_increase_enabled')
