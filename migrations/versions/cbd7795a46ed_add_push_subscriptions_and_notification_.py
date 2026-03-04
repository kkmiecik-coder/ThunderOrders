"""Add push_subscriptions and notification_preferences tables

Revision ID: cbd7795a46ed
Revises: fdd2484aac0f
Create Date: 2026-03-04 20:09:52.133142

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cbd7795a46ed'
down_revision = 'fdd2484aac0f'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_status_changes', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('payment_updates', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('shipping_updates', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('new_exclusive_pages', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('cost_added', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('admin_alerts', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.create_index('ix_notification_preferences_user_id', ['user_id'], unique=True)

    op.create_table('push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh_key', sa.String(length=255), nullable=False),
        sa.Column('auth_key', sa.String(length=255), nullable=False),
        sa.Column('device_name', sa.String(length=255), nullable=True, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.create_index('ix_push_subscriptions_user_id', ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_index('ix_push_subscriptions_user_id')
    op.drop_table('push_subscriptions')

    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_preferences_user_id')
    op.drop_table('notification_preferences')
