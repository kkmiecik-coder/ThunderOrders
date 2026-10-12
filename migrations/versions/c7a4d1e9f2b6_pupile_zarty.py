"""Pupile: żarty towarzysza: obrazki wychylania i przełącznik w profilu (spec v3.2 §6)

Revision ID: c7a4d1e9f2b6
Revises: b5d8e2f4a917
"""
from alembic import op
import sqlalchemy as sa

revision = 'c7a4d1e9f2b6'
down_revision = 'b5d8e2f4a917'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pet_peek_images',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=80), nullable=False),
        sa.Column('label', sa.String(length=60), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('filename'),
    )
    with op.batch_alter_table('pet_profiles') as batch:
        batch.add_column(sa.Column('jokes_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade():
    with op.batch_alter_table('pet_profiles') as batch:
        batch.drop_column('jokes_enabled')
    op.drop_table('pet_peek_images')
