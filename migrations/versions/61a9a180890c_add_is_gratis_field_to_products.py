"""Add is_gratis field to products

Revision ID: 61a9a180890c
Revises: 7f6f9463ebc2
Create Date: 2026-04-07 20:41:21.631559

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '61a9a180890c'
down_revision = '7f6f9463ebc2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('is_gratis', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    op.drop_column('products', 'is_gratis')
