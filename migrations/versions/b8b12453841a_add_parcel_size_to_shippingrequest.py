"""Add parcel_size to ShippingRequest

Revision ID: b8b12453841a
Revises: a1b2c3d4e5f6
Create Date: 2026-01-11 05:45:45.067728

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b8b12453841a'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parcel_size', sa.String(length=1), nullable=True))


def downgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.drop_column('parcel_size')
