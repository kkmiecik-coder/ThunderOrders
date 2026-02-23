"""Add payment_reminder_sent_at to orders

Revision ID: 29c3d5a11696
Revises: 7ddafcc51794
Create Date: 2026-02-22 04:25:51.051525

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '29c3d5a11696'
down_revision = '7ddafcc51794'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('payment_reminder_sent_at')
