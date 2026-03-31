"""Add bonus section type for preorder pages

Revision ID: c2d3e4f5a6b7
Revises: b1a2c3d4e5f6
Create Date: 2026-04-01 00:30:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c2d3e4f5a6b7'
down_revision = 'b1a2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Add 'bonus' to section_type enum
    op.execute("ALTER TABLE offer_sections MODIFY COLUMN section_type ENUM('heading','paragraph','product','set','variant_group','bonus') NOT NULL")


def downgrade():
    # Remove 'bonus' from enum (only if no rows use it)
    op.execute("ALTER TABLE offer_sections MODIFY COLUMN section_type ENUM('heading','paragraph','product','set','variant_group') NOT NULL")
