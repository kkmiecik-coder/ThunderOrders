"""Pupile: pobyt w szpitalu i skórki jajek (spec v3 §4.3)

Revision ID: b5d8e2f4a917
Revises: f3e9a1c7b2d4
"""
from alembic import op
import sqlalchemy as sa

revision = 'b5d8e2f4a917'
down_revision = 'f3e9a1c7b2d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pets') as batch:
        batch.add_column(sa.Column('hospital_since', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('hospital_healed_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('hospital_ready_notified_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('egg_skin', sa.SmallInteger(), nullable=False, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('pets') as batch:
        batch.drop_column('egg_skin')
        batch.drop_column('hospital_ready_notified_at')
        batch.drop_column('hospital_healed_at')
        batch.drop_column('hospital_since')
