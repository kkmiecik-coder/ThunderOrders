"""Set is_initial=true for czeka_na_wycene status

Revision ID: 9b5d4a3f76bd
Revises: 35992f7dda93
Create Date: 2026-01-18 01:14:36.341526

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9b5d4a3f76bd'
down_revision = '35992f7dda93'
branch_labels = None
depends_on = None


def upgrade():
    # Set is_initial = 1 for 'czeka_na_wycene' status
    # This allows shipping requests with this status to be cancelled
    op.execute("""
        UPDATE shipping_request_statuses
        SET is_initial = 1
        WHERE slug = 'czeka_na_wycene'
    """)


def downgrade():
    # Revert is_initial = 0 for 'czeka_na_wycene' status
    op.execute("""
        UPDATE shipping_request_statuses
        SET is_initial = 0
        WHERE slug = 'czeka_na_wycene'
    """)
