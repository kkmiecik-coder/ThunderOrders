"""Remove stock order aggregation settings from DB

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-01 10:30:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    # Remove aggregation settings (now hardcoded in get_products_to_order)
    op.execute("DELETE FROM settings WHERE `key` IN ('stock_order_aggregation_types', 'stock_order_aggregation_statuses')")


def downgrade():
    # Restore default settings
    op.execute("INSERT INTO settings (`key`, value, type) VALUES ('stock_order_aggregation_types', '[\"pre_order\", \"exclusive\"]', 'json') ON DUPLICATE KEY UPDATE value=value")
    op.execute("INSERT INTO settings (`key`, value, type) VALUES ('stock_order_aggregation_statuses', '[\"nowe\"]', 'json') ON DUPLICATE KEY UPDATE value=value")
