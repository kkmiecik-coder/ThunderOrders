"""Add notify_clients_on_publish to ExclusivePage

Revision ID: d7eb037b264b
Revises: 683a7daa4d8c
Create Date: 2026-02-21 23:43:34.813043

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd7eb037b264b'
down_revision = '683a7daa4d8c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notify_clients_on_publish', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.drop_column('notify_clients_on_publish')
