"""Dodaj tabelę contest_excluded_users (wykluczeni z losowania)

Revision ID: 830b9d3167ad
Revises: 261f567bb320
Create Date: 2026-07-14 00:00:00.000000

Migracja zawęża się WYŁĄCZNIE do nowej tabeli contest_excluded_users
(wykluczanie osób z losowania zwycięzców konkursu).
"""
from alembic import op
import sqlalchemy as sa

revision = '830b9d3167ad'
down_revision = '261f567bb320'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'contest_excluded_users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contest_id', 'user_id', name='uq_contest_excluded_user'),
    )


def downgrade():
    op.drop_table('contest_excluded_users')
