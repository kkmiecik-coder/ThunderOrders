"""rozdzial gratisow

Revision ID: f4c8d2a7b9e1
Revises: e3b9a6c1d4f7
Create Date: 2026-11-16

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4c8d2a7b9e1'
down_revision = 'e3b9a6c1d4f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'gift_campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('bonus_product_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('race_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_admin_id', sa.Integer(), nullable=True),
        sa.Column('entitlements_snapshot', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['bonus_product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_admin_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'gift_campaign_pages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('offer_page_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['offer_page_id'], ['offer_pages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'offer_page_id', name='uq_gift_campaign_page'),
    )
    op.create_table(
        'gift_card_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'gift_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ranking_json', sa.Text(), nullable=True),
        sa.Column('ranking_updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'user_id', name='uq_gift_participant'),
    )
    op.create_table(
        'gift_race_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'user_id', name='uq_gift_race_entry'),
    )
    op.create_table(
        'gift_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_item_id', sa.Integer(), nullable=False),
        sa.Column('card_type_id', sa.Integer(), nullable=False),
        sa.Column('round_no', sa.Integer(), nullable=False),
        sa.Column('rank_position', sa.Integer(), nullable=True),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['card_type_id'], ['gift_card_types.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('gift_assignments')
    op.drop_table('gift_race_entries')
    op.drop_table('gift_participants')
    op.drop_table('gift_card_types')
    op.drop_table('gift_campaign_pages')
    op.drop_table('gift_campaigns')
