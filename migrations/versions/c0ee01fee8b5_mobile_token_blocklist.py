"""mobile_token_blocklist

Revision ID: c0ee01fee8b5
Revises: e7f8a9b0c1d2
Create Date: 2026-06-11 22:21:47.941906

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c0ee01fee8b5'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mobile_token_blocklist',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('jti', sa.String(length=36), nullable=False),
    sa.Column('token_type', sa.String(length=16), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('mobile_token_blocklist', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mobile_token_blocklist_jti'), ['jti'], unique=True)
        batch_op.create_index(batch_op.f('ix_mobile_token_blocklist_user_id'), ['user_id'], unique=False)


def downgrade():
    # drop_table samo zdejmuje indeksy; NIE dropujemy indeksu podtrzymującego
    # FK (user_id) przed DROP TABLE, bo MariaDB by to odrzuciła.
    op.drop_table('mobile_token_blocklist')
