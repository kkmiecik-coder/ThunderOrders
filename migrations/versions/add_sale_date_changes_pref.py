"""Add sale_date_changes preference to notification_preferences

Revision ID: add_sale_date_changes_pref
Revises: 0968e23691d2
Create Date: 2026-04-26 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_sale_date_changes_pref'
down_revision = '0968e23691d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sale_date_changes', sa.Boolean(), nullable=False, server_default=sa.text('1')))

    # Backfill: TRUE only when all other categories are TRUE
    op.execute("""
        UPDATE notification_preferences
        SET sale_date_changes = CASE
            WHEN order_status_changes = 1
             AND payment_updates = 1
             AND shipping_updates = 1
             AND new_exclusive_pages = 1
             AND cost_added = 1
             AND admin_alerts = 1
            THEN 1
            ELSE 0
        END
    """)


def downgrade():
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('sale_date_changes')
