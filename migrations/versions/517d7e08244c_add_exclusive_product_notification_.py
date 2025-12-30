"""Add exclusive product notification subscriptions

Revision ID: 517d7e08244c
Revises: 26764a10e8c2
Create Date: 2025-12-30 10:22:55.429134

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '517d7e08244c'
down_revision = '26764a10e8c2'
branch_labels = None
depends_on = None


def upgrade():
    # Create exclusive_product_notifications table
    op.create_table('exclusive_product_notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exclusive_page_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('guest_email', sa.String(length=255), nullable=True),
        sa.Column('notified', sa.Boolean(), nullable=False, default=False),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['exclusive_page_id'], ['exclusive_pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for efficient querying
    op.create_index('ix_notification_page_product', 'exclusive_product_notifications', ['exclusive_page_id', 'product_id'], unique=False)
    op.create_index('ix_notification_not_notified', 'exclusive_product_notifications', ['exclusive_page_id', 'product_id', 'notified'], unique=False)


def downgrade():
    op.drop_index('ix_notification_not_notified', table_name='exclusive_product_notifications')
    op.drop_index('ix_notification_page_product', table_name='exclusive_product_notifications')
    op.drop_table('exclusive_product_notifications')
