"""Add marketing_consent column to users

Revision ID: 5f939c7f0507
Revises: a97a2b74a2a0
Create Date: 2026-03-16 21:50:49.931520

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5f939c7f0507'
down_revision = 'a97a2b74a2a0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('marketing_consent', sa.Boolean(), nullable=False,
                                       server_default='0',
                                       comment='Zgoda na komunikację marketingową (nowe dropy, back-in-stock, broadcasty). Wymagana przez RODO.'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('marketing_consent')
