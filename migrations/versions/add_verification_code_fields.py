"""Add verification code fields to users table

Revision ID: add_verification_code
Revises:
Create Date: 2025-12-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_verification_code'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add new columns for 6-digit verification code system."""
    # Add new columns for email verification code system
    op.add_column('users', sa.Column('email_verification_code', sa.String(6), nullable=True))
    op.add_column('users', sa.Column('email_verification_code_expires', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('email_verification_code_sent_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('email_verification_attempts', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('users', sa.Column('email_verification_locked_until', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('verification_session_token', sa.String(64), nullable=True))

    # Add index for verification session token
    op.create_index('ix_users_verification_session_token', 'users', ['verification_session_token'], unique=False)


def downgrade():
    """Remove verification code columns."""
    op.drop_index('ix_users_verification_session_token', table_name='users')
    op.drop_column('users', 'verification_session_token')
    op.drop_column('users', 'email_verification_locked_until')
    op.drop_column('users', 'email_verification_attempts')
    op.drop_column('users', 'email_verification_code_sent_at')
    op.drop_column('users', 'email_verification_code_expires')
    op.drop_column('users', 'email_verification_code')
