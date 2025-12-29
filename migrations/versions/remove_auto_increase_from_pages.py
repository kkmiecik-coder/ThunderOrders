"""Remove per-page auto-increase columns from exclusive_pages

Revision ID: remove_auto_increase
Revises: cc1c0a80e4af
Create Date: 2025-12-29 22:30:00

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_auto_increase'
down_revision = 'cc1c0a80e4af'
branch_labels = None
depends_on = None


def upgrade():
    # Remove auto-increase columns from exclusive_pages
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.drop_column('auto_increase_product_threshold')
        batch_op.drop_column('auto_increase_amount')
        batch_op.drop_column('auto_increase_enabled')
        batch_op.drop_column('auto_increase_set_threshold')


def downgrade():
    # Add back auto-increase columns (if needed to rollback)
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_increase_enabled', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('auto_increase_product_threshold', sa.DECIMAL(5, 2), default=100.00))
        batch_op.add_column(sa.Column('auto_increase_set_threshold', sa.DECIMAL(5, 2), default=50.00))
        batch_op.add_column(sa.Column('auto_increase_amount', sa.Integer(), default=1))
