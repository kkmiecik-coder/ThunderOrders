"""Make ShippingRequest.user_id nullable for user deletion

Revision ID: e8dd8d002da3
Revises: 29c3d5a11696
Create Date: 2026-02-23 21:07:18.070328

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'e8dd8d002da3'
down_revision = '29c3d5a11696'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.alter_column('user_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=True)


def downgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.alter_column('user_id',
               existing_type=mysql.INTEGER(display_width=11),
               nullable=False)
