"""Add google_id, facebook_id, nullable password_hash for OAuth

Revision ID: fdd2484aac0f
Revises: 1e3a635cca49
Create Date: 2026-03-03 22:20:33.297458

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fdd2484aac0f'
down_revision = '1e3a635cca49'
branch_labels = None
depends_on = None


def upgrade():
    # Add OAuth provider ID columns
    op.add_column('users', sa.Column('google_id', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('facebook_id', sa.String(255), nullable=True))

    # Create unique indexes for OAuth IDs
    op.create_index('ix_users_google_id', 'users', ['google_id'], unique=True)
    op.create_index('ix_users_facebook_id', 'users', ['facebook_id'], unique=True)

    # Make password_hash nullable (OAuth users don't have passwords)
    op.alter_column('users', 'password_hash',
                     existing_type=sa.String(255),
                     nullable=True)


def downgrade():
    # Make password_hash non-nullable again
    op.alter_column('users', 'password_hash',
                     existing_type=sa.String(255),
                     nullable=False)

    # Drop indexes and columns
    op.drop_index('ix_users_facebook_id', table_name='users')
    op.drop_index('ix_users_google_id', table_name='users')
    op.drop_column('users', 'facebook_id')
    op.drop_column('users', 'google_id')
