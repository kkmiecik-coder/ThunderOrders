"""Remove payment_reminder_sent_at from orders

Revision ID: 95e587caeddd
Revises: 7df950306875
Create Date: 2026-04-07 22:58:07.673995

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '95e587caeddd'
down_revision = '7df950306875'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('payment_reminder_sent_at')


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_reminder_sent_at', sa.DateTime(), nullable=True))
