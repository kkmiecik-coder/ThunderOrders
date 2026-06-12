"""Mobile idempotency keys

Revision ID: c72aad290158
Revises: c0ee01fee8b5
Create Date: 2026-06-12 15:37:44.900338

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c72aad290158'
down_revision = 'c0ee01fee8b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mobile_idempotency_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=False),
    sa.Column('endpoint', sa.String(length=64), nullable=False),
    sa.Column('status_code', sa.Integer(), nullable=True),
    sa.Column('response_body', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_idem_user_key')
    )
    with op.batch_alter_table('mobile_idempotency_keys', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mobile_idempotency_keys_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_mobile_idempotency_keys_user_id'), ['user_id'], unique=False)


def downgrade():
    # drop_table samo zdejmuje indeksy; NIE dropujemy indeksu podtrzymującego
    # FK (user_id) przed DROP TABLE, bo MariaDB by to odrzuciła.
    op.drop_table('mobile_idempotency_keys')
