"""Sekcja zdjeciowa: typ image + tabela offer_section_images

Revision ID: e7a1c4b92d55
Revises: b8d2e1fa4c37
Create Date: 2026-08-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e7a1c4b92d55'
down_revision = 'b8d2e1fa4c37'
branch_labels = None
depends_on = None


def upgrade():
    # Enum w MariaDB rozszerzamy ręcznie — autogenerate tego nie wykrywa
    op.execute(
        "ALTER TABLE offer_sections MODIFY COLUMN section_type "
        "ENUM('heading','paragraph','product','set','variant_group','bonus','image') NOT NULL"
    )

    op.create_table(
        'offer_section_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=500), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['section_id'], ['offer_sections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_offer_section_images_section_id', 'offer_section_images',
                    ['section_id'], unique=False)


def downgrade():
    # Sam drop_table zdejmuje też indeks podtrzymujący FK — nie dropuj go osobno,
    # bo MariaDB odmówi usunięcia indeksu potrzebnego kluczowi obcemu.
    op.drop_table('offer_section_images')
    op.execute(
        "DELETE FROM offer_sections WHERE section_type = 'image'"
    )
    op.execute(
        "ALTER TABLE offer_sections MODIFY COLUMN section_type "
        "ENUM('heading','paragraph','product','set','variant_group','bonus') NOT NULL"
    )
