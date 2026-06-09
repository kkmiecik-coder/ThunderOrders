"""Add contest_prizes table

Revision ID: f7a8b9c0d1e2
Revises: d9e0f1a2b3c4
Create Date: 2026-06-09 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f7a8b9c0d1e2'
down_revision = 'd9e0f1a2b3c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('contest_prizes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_prizes_contest', 'contest_prizes', ['contest_id'], unique=False)


def downgrade():
    op.drop_index('ix_contest_prizes_contest', table_name='contest_prizes')
    op.drop_table('contest_prizes')
