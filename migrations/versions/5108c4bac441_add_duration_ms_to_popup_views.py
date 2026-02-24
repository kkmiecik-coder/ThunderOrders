"""Add duration_ms to popup_views

Revision ID: 5108c4bac441
Revises: 9652bf010d9f
Create Date: 2026-02-24 23:28:33.061306

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5108c4bac441'
down_revision = '9652bf010d9f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('popup_views', schema=None) as batch_op:
        batch_op.add_column(sa.Column('duration_ms', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('popup_views', schema=None) as batch_op:
        batch_op.drop_column('duration_ms')
