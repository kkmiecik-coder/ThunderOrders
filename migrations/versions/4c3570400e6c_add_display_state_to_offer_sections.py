"""Add display_state to offer_sections

Stan wyświetlania sekcji na stronie sprzedaży pre-order:
- active   — sekcja widoczna i zamawialna (domyślny, zgodny z zachowaniem sprzed zmiany)
- sold_out — sekcja widoczna, wyszarzona, z nakładką "Sold-out", NIE zamawialna
- hidden   — sekcja nie renderuje się wcale

Revision ID: 4c3570400e6c
Revises: c4d8e91f2a37
Create Date: 2026-08-21 10:07:41.774939

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4c3570400e6c'
down_revision = 'c4d8e91f2a37'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'offer_sections',
        sa.Column(
            'display_state',
            sa.Enum('active', 'sold_out', 'hidden', name='offer_section_display_state'),
            nullable=False,
            server_default='active',
        )
    )


def downgrade():
    op.drop_column('offer_sections', 'display_state')
