"""Dodaj customs_vat_percentage i customs_vat_amount do poland_order_items

Revision ID: b2c3d4e5f6a7
Revises: 605e21170ba9
Create Date: 2026-02-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('customs_vat_percentage', sa.Numeric(5, 2), nullable=True, server_default='0.00'))
        batch_op.add_column(sa.Column('customs_vat_amount', sa.Numeric(10, 2), nullable=True, server_default='0.00'))


def downgrade():
    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.drop_column('customs_vat_amount')
        batch_op.drop_column('customs_vat_percentage')
