"""Add payment_deadline to PolandOrder

Revision ID: ac678e0c84f8
Revises: 95e587caeddd
Create Date: 2026-04-07 23:31:35.169690

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ac678e0c84f8'
down_revision = '95e587caeddd'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('poland_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_deadline', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('poland_orders', schema=None) as batch_op:
        batch_op.drop_column('payment_deadline')
