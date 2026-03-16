"""Add analytics_consent_date column to users

Revision ID: a97a2b74a2a0
Revises: 146a61abfc8c
Create Date: 2026-03-16 21:34:12.324591

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a97a2b74a2a0'
down_revision = '146a61abfc8c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('analytics_consent_date', sa.DateTime(), nullable=True,
                                       comment='Data ostatniej zmiany zgody analitycznej (do ponownego pytania po 14 dniach od odmowy)'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('analytics_consent_date')
