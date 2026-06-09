"""Add contests tables

Revision ID: d9e0f1a2b3c4
Revises: 4b86ef34e7b5
Create Date: 2026-06-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd9e0f1a2b3c4'
down_revision = '4b86ef34e7b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('contests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('prize_product_id', sa.Integer(), nullable=True),
        sa.Column('num_winners', sa.Integer(), nullable=False),
        sa.Column('ticket_min', sa.Integer(), nullable=False),
        sa.Column('ticket_max', sa.Integer(), nullable=False),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False),
        sa.Column('eligibility_min_orders', sa.Integer(), nullable=True),
        sa.Column('eligibility_min_total_value', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('eligibility_active_within_days', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_admin_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['prize_product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['created_by_admin_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('contest_spins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('tickets_won', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_contest_spins_contest_user', 'contest_spins', ['contest_id', 'user_id'], unique=False)
    op.create_table('contest_winners',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contest_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('place', sa.Integer(), nullable=False),
        sa.Column('tickets_at_draw', sa.Integer(), nullable=False),
        sa.Column('chance_pct', sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column('prize_product_id', sa.Integer(), nullable=True),
        sa.Column('drawn_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['contest_id'], ['contests.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['prize_product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('contest_id', 'user_id', name='uq_contest_winner_user'),
        sa.UniqueConstraint('contest_id', 'place', name='uq_contest_winner_place'),
    )


def downgrade():
    # DROP TABLE usuwa indeksy i FK atomowo — nie dropujemy ręcznie indeksu
    # podtrzymującego FK (MariaDB: "Cannot drop index needed in a foreign key constraint").
    op.drop_table('contest_winners')
    op.drop_table('contest_spins')
    op.drop_table('contests')
