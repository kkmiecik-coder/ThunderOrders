"""Add set_product_id to exclusive_sections

Revision ID: d822f4f81388
Revises: timezone_fix_001
Create Date: 2025-12-27 21:47:46.001161

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd822f4f81388'
down_revision = 'timezone_fix_001'
branch_labels = None
depends_on = None


def upgrade():
    # Add set_product_id column to exclusive_sections
    with op.batch_alter_table('exclusive_sections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('set_product_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_exclusive_sections_set_product',
            'products',
            ['set_product_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    # Remove set_product_id column from exclusive_sections
    with op.batch_alter_table('exclusive_sections', schema=None) as batch_op:
        batch_op.drop_constraint('fk_exclusive_sections_set_product', type_='foreignkey')
        batch_op.drop_column('set_product_id')
