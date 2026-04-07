"""Add customs_payment_deadline to PolandOrder

Revision ID: 604f4ef9810f
Revises: ac678e0c84f8
Create Date: 2026-04-07 23:45:55.245944

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '604f4ef9810f'
down_revision = 'ac678e0c84f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('poland_orders', sa.Column('customs_payment_deadline', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('poland_orders', 'customs_payment_deadline')
