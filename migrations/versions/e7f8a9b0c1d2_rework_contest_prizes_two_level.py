"""Rework contest_prizes to two-level structure (prize + items)

Revision ID: e7f8a9b0c1d2
Revises: f7a8b9c0d1e2
Create Date: 2026-06-09 16:00:00.000000

Drops the old flat contest_prizes table (product_id + quantity) and creates
the new two-level structure:
  contest_prizes  (id, contest_id, name nullable, quantity)
  contest_prize_items  (id, prize_id, product_id, quantity)
"""
from alembic import op
import sqlalchemy as sa

revision = 'e7f8a9b0c1d2'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    # Drop old flat table (was never in production; added only in local migration f7a8b9c0d1e2).
    # MariaDB: must drop FK constraint before dropping its backing index.
    # Auto-generated FK name follows the _ibfk_N pattern.
    op.drop_constraint('contest_prizes_ibfk_1', 'contest_prizes', type_='foreignkey')
    op.drop_index('ix_contest_prizes_contest', table_name='contest_prizes')
    op.drop_table('contest_prizes')

    # New two-level structure
    op.create_table(
        'contest_prizes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_prizes_contest', 'contest_prizes', ['contest_id'], unique=False)

    op.create_table(
        'contest_prize_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('prize_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['prize_id'], ['contest_prizes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_prize_items_prize', 'contest_prize_items', ['prize_id'], unique=False)


def downgrade():
    op.drop_index('ix_contest_prize_items_prize', table_name='contest_prize_items')
    op.drop_table('contest_prize_items')
    op.drop_index('ix_contest_prizes_contest', table_name='contest_prizes')
    op.drop_table('contest_prizes')

    # Restore old flat contest_prizes
    op.create_table(
        'contest_prizes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_prizes_contest', 'contest_prizes', ['contest_id'], unique=False)
