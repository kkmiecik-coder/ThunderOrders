"""Reduce shipping request statuses to czeka_na_wycene and czeka_na_oplacenie

Revision ID: 35992f7dda93
Revises: a511c0a36dad
Create Date: 2026-01-17 20:32:26.093989

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '35992f7dda93'
down_revision = 'a511c0a36dad'
branch_labels = None
depends_on = None


def upgrade():
    """
    Deactivate unused shipping request statuses.
    Keep only: czeka_na_wycene, czeka_na_oplacenie
    Deactivate: nowe, do_wyslania, wyslane, dostarczone

    Note: We deactivate instead of delete to preserve data integrity
    for existing shipping requests that may use these statuses.
    """
    # Deactivate unused statuses
    op.execute("""
        UPDATE shipping_request_statuses
        SET is_active = 0
        WHERE slug IN ('nowe', 'do_wyslania', 'wyslane', 'dostarczone')
    """)

    # Update any existing shipping requests with 'nowe' status to 'czeka_na_wycene'
    op.execute("""
        UPDATE shipping_requests
        SET status = 'czeka_na_wycene'
        WHERE status = 'nowe'
    """)


def downgrade():
    """
    Reactivate all shipping request statuses.
    """
    op.execute("""
        UPDATE shipping_request_statuses
        SET is_active = 1
        WHERE slug IN ('nowe', 'do_wyslania', 'wyslane', 'dostarczone')
    """)
