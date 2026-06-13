"""Add mobile_device (FCM push tokens)

Revision ID: e896e0208289
Revises: c72aad290158
Create Date: 2026-06-13 18:35:01.609205

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e896e0208289'
down_revision = 'c72aad290158'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('mobile_device',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('fcm_token', sa.String(length=512), nullable=False),
    sa.Column('platform', sa.String(length=16), nullable=False),
    sa.Column('last_used_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('fcm_token')
    )
    with op.batch_alter_table('mobile_device', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_mobile_device_user_id'), ['user_id'], unique=False)


def downgrade():
    # drop_table samo zdejmuje indeksy; NIE dropujemy indeksu podtrzymującego
    # FK (user_id) przed DROP TABLE, bo MariaDB by to odrzuciła.
    op.drop_table('mobile_device')
