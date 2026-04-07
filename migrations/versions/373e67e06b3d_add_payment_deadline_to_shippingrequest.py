"""Add payment_deadline to ShippingRequest

Revision ID: 373e67e06b3d
Revises: 604f4ef9810f
Create Date: 2026-04-07 23:56:58.493396

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '373e67e06b3d'
down_revision = '604f4ef9810f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('shipping_requests', sa.Column('payment_deadline', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('shipping_requests', 'payment_deadline')
