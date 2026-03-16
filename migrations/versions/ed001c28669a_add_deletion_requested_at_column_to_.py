"""Add deletion_requested_at column to users

Revision ID: ed001c28669a
Revises: 5f939c7f0507
Create Date: 2026-03-16 22:30:59.452472

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ed001c28669a'
down_revision = '5f939c7f0507'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deletion_requested_at', sa.DateTime(), nullable=True,
                                       comment='Data żądania usunięcia konta (RODO art. 17). Po 30 dniach dane zostaną zanonimizowane.'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('deletion_requested_at')
