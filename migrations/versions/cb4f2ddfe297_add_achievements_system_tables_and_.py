"""Add achievements system tables and login streak

Revision ID: cb4f2ddfe297
Revises: e6ca372c32c3
Create Date: 2026-03-13 00:24:18.464646

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cb4f2ddfe297'
down_revision = 'e6ca372c32c3'
branch_labels = None
depends_on = None


def upgrade():
    # Achievement table
    op.create_table('achievement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('category', sa.Enum('orders', 'collection', 'loyalty', 'speed', 'exclusive', 'social', 'financial', 'profile', name='achievement_category'), nullable=False),
        sa.Column('rarity', sa.Enum('common', 'rare', 'epic', 'legendary', name='achievement_rarity'), nullable=False),
        sa.Column('icon_filename', sa.String(length=120), nullable=True),
        sa.Column('tier', sa.Integer(), nullable=True),
        sa.Column('tier_group', sa.String(length=60), nullable=True),
        sa.Column('trigger_type', sa.Enum('event', 'cron', name='achievement_trigger_type'), nullable=False),
        sa.Column('trigger_config', sa.JSON(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )
    with op.batch_alter_table('achievement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_achievement_slug'), ['slug'], unique=True)
        batch_op.create_index(batch_op.f('ix_achievement_tier_group'), ['tier_group'], unique=False)

    # UserAchievement table
    op.create_table('user_achievement',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('achievement_id', sa.Integer(), nullable=False),
        sa.Column('unlocked_at', sa.DateTime(), nullable=True),
        sa.Column('seen', sa.Boolean(), nullable=True),
        sa.Column('shared', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievement.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement')
    )
    with op.batch_alter_table('user_achievement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_achievement_achievement_id'), ['achievement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_achievement_user_id'), ['user_id'], unique=False)

    # AchievementStat table
    op.create_table('achievement_stat',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('achievement_id', sa.Integer(), nullable=False),
        sa.Column('total_unlocked', sa.Integer(), nullable=True),
        sa.Column('percentage', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['achievement_id'], ['achievement.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('achievement_id')
    )

    # Add login streak columns to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('login_streak', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('last_login_date', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('last_login_date')
        batch_op.drop_column('login_streak')

    op.drop_table('achievement_stat')

    with op.batch_alter_table('user_achievement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_achievement_user_id'))
        batch_op.drop_index(batch_op.f('ix_user_achievement_achievement_id'))

    op.drop_table('user_achievement')

    with op.batch_alter_table('achievement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_achievement_tier_group'))
        batch_op.drop_index(batch_op.f('ix_achievement_slug'))

    op.drop_table('achievement')
