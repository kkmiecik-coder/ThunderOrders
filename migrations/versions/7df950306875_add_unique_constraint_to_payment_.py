"""Add unique constraint to payment_reminder_logs

Revision ID: 7df950306875
Revises: 6a2c80d1f048
Create Date: 2026-04-07 22:45:59.859657

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '7df950306875'
down_revision = '6a2c80d1f048'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        'uq_reminder_log_order_config',
        'payment_reminder_logs',
        ['order_id', 'config_id']
    )


def downgrade():
    op.drop_constraint('uq_reminder_log_order_config', 'payment_reminder_logs', type_='unique')
