"""admin grantable badges: extend enums, add is_hidden_until_unlocked, granted_by_id

Revision ID: 405efca8e619
Revises: add_sale_date_changes_pref
Create Date: 2026-04-26 21:03:27.442352

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '405efca8e619'
down_revision = 'add_sale_date_changes_pref'
branch_labels = None
depends_on = None


def upgrade():
    # Extend ENUMs on `achievement` (MariaDB requires explicit ALTER for enum changes)
    op.execute(
        "ALTER TABLE achievement MODIFY category "
        "ENUM('orders', 'collection', 'loyalty', 'speed', 'exclusive', "
        "'social', 'financial', 'profile', 'special') NOT NULL"
    )
    op.execute(
        "ALTER TABLE achievement MODIFY rarity "
        "ENUM('common', 'rare', 'epic', 'legendary', 'cosmic') NOT NULL"
    )
    op.execute(
        "ALTER TABLE achievement MODIFY trigger_type "
        "ENUM('event', 'cron', 'manual') NOT NULL"
    )

    # Add `is_hidden_until_unlocked` to `achievement`
    with op.batch_alter_table('achievement', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_hidden_until_unlocked',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('0'),
            )
        )

    # Add `granted_by_id` (nullable FK to users) to `user_achievement`
    with op.batch_alter_table('user_achievement', schema=None) as batch_op:
        batch_op.add_column(sa.Column('granted_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_user_achievement_granted_by_id',
            'users',
            ['granted_by_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    # Drop FK and `granted_by_id` from `user_achievement`
    with op.batch_alter_table('user_achievement', schema=None) as batch_op:
        batch_op.drop_constraint('fk_user_achievement_granted_by_id', type_='foreignkey')
        batch_op.drop_column('granted_by_id')

    # Drop `is_hidden_until_unlocked` from `achievement`
    with op.batch_alter_table('achievement', schema=None) as batch_op:
        batch_op.drop_column('is_hidden_until_unlocked')

    # Restore original ENUMs on `achievement`
    op.execute(
        "ALTER TABLE achievement MODIFY trigger_type "
        "ENUM('event', 'cron') NOT NULL"
    )
    op.execute(
        "ALTER TABLE achievement MODIFY rarity "
        "ENUM('common', 'rare', 'epic', 'legendary') NOT NULL"
    )
    op.execute(
        "ALTER TABLE achievement MODIFY category "
        "ENUM('orders', 'collection', 'loyalty', 'speed', 'exclusive', "
        "'social', 'financial', 'profile') NOT NULL"
    )
