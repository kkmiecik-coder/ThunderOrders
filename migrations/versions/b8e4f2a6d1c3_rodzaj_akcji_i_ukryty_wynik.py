"""Rodzaj akcji (gratis/zakup) i ukryty wynik rozdziału kart

Revision ID: b8e4f2a6d1c3
Revises: a7d3e9f1c2b4
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa


revision = 'b8e4f2a6d1c3'
down_revision = 'a7d3e9f1c2b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gift_campaigns', sa.Column('kind', sa.String(length=10), nullable=False,
                                              server_default='gratis'))
    op.add_column('gift_campaigns', sa.Column('results_hidden', sa.Boolean(), nullable=False,
                                              server_default='0'))


def downgrade():
    # Status „zakończona (rozdział ręczny)” nie istnieje w starszej wersji — wraca do „zamknięta”.
    op.execute("UPDATE gift_campaigns SET status='zamknieta' WHERE status='zakonczona'")
    op.drop_column('gift_campaigns', 'results_hidden')
    op.drop_column('gift_campaigns', 'kind')
