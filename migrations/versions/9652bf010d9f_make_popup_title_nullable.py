"""Make popup title nullable

Revision ID: 9652bf010d9f
Revises: 1f85b2c9e3f2
Create Date: 2026-02-24 23:16:57.484733

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '9652bf010d9f'
down_revision = '1f85b2c9e3f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('popups', schema=None) as batch_op:
        batch_op.alter_column('title',
               existing_type=mysql.VARCHAR(length=200),
               nullable=True)


def downgrade():
    with op.batch_alter_table('popups', schema=None) as batch_op:
        batch_op.alter_column('title',
               existing_type=mysql.VARCHAR(length=200),
               nullable=False)
