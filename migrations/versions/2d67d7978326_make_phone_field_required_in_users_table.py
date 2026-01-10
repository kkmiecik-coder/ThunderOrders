"""Make phone field required in users table

Revision ID: 2d67d7978326
Revises: 8c2f30ca477a
Create Date: 2026-01-10 17:04:16.159737

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '2d67d7978326'
down_revision = '8c2f30ca477a'
branch_labels = None
depends_on = None


def upgrade():
    # First, update existing NULL phone values to empty string to avoid constraint violation
    op.execute("UPDATE users SET phone = '' WHERE phone IS NULL")

    # Then alter column to NOT NULL
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('phone',
               existing_type=mysql.VARCHAR(length=20),
               nullable=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('phone',
               existing_type=mysql.VARCHAR(length=20),
               nullable=True)
