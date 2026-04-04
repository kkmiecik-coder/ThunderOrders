"""Add registration_reminder_sent_at to users

Revision ID: 7f6f9463ebc2
Revises: 5b4341510c00
Create Date: 2026-04-04 22:50:17.676081

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7f6f9463ebc2'
down_revision = '5b4341510c00'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('registration_reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'registration_reminder_sent_at')
