"""Add proxy_shipping_cost and customs_vat_sale_cost to orders

Revision ID: 683a7daa4d8c
Revises: d4e5f6a7b8c9
Create Date: 2026-02-21 01:22:31.154400

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '683a7daa4d8c'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('proxy_shipping_cost', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('customs_vat_sale_cost', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('customs_vat_sale_cost')
        batch_op.drop_column('proxy_shipping_cost')
