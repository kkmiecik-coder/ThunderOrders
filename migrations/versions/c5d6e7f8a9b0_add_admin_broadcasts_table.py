"""Add admin_broadcasts table

Revision ID: c5d6e7f8a9b0
Revises: a1f8b2c3d4e5
Create Date: 2026-03-04 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c5d6e7f8a9b0'
down_revision = 'a1f8b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_broadcasts',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('url', sa.String(length=512), nullable=True),
        sa.Column('target_type', sa.String(length=20), nullable=False),
        sa.Column('target_data', sa.Text(), nullable=True),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['sent_by'], ['users.id'], name='fk_admin_broadcasts_sent_by'),
    )
    op.create_index('ix_admin_broadcasts_created_at', 'admin_broadcasts', ['created_at'])


def downgrade():
    op.drop_index('ix_admin_broadcasts_created_at', table_name='admin_broadcasts')
    op.drop_table('admin_broadcasts')
