"""Remove bonus_label column from exclusive_set_bonuses

Revision ID: 19e2e3d860a0
Revises: a6635d3f4d56
Create Date: 2026-03-07 00:30:34.915321

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '19e2e3d860a0'
down_revision = 'a6635d3f4d56'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('exclusive_set_bonuses', schema=None) as batch_op:
        batch_op.drop_column('bonus_label')


def downgrade():
    with op.batch_alter_table('exclusive_set_bonuses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bonus_label', sa.String(length=200), nullable=True))
