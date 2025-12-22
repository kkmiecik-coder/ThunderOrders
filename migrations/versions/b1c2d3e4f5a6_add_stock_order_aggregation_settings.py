"""Add stock order aggregation settings

Revision ID: b1c2d3e4f5a6
Revises: a6f97fad2422
Create Date: 2025-12-21

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a6f97fad2422'
branch_labels = None
depends_on = None


def upgrade():
    # Insert default settings for stock order aggregation
    settings_table = sa.table(
        'settings',
        sa.column('key', sa.String),
        sa.column('value', sa.Text),
        sa.column('type', sa.String),
        sa.column('description', sa.String),
        sa.column('updated_at', sa.DateTime)
    )

    op.bulk_insert(settings_table, [
        {
            'key': 'stock_order_aggregation_types',
            'value': '["pre_order", "exclusive"]',
            'type': 'json',
            'description': 'Typy zamówień klientów uwzględniane w zakładce Do zamówienia',
            'updated_at': datetime.now()
        },
        {
            'key': 'stock_order_aggregation_statuses',
            'value': '["nowe"]',
            'type': 'json',
            'description': 'Statusy zamówień klientów uwzględniane w zakładce Do zamówienia',
            'updated_at': datetime.now()
        }
    ])


def downgrade():
    # Remove the settings
    op.execute("DELETE FROM settings WHERE `key` = 'stock_order_aggregation_types'")
    op.execute("DELETE FROM settings WHERE `key` = 'stock_order_aggregation_statuses'")
