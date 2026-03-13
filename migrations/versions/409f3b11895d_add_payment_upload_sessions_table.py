"""Add payment_upload_sessions table

Revision ID: 409f3b11895d
Revises: cb4f2ddfe297
Create Date: 2026-03-13 20:22:08.983171

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '409f3b11895d'
down_revision = 'cb4f2ddfe297'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_upload_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('uploaded_filename', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('payment_upload_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_payment_upload_sessions_session_token'), ['session_token'], unique=True)


def downgrade():
    with op.batch_alter_table('payment_upload_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_payment_upload_sessions_session_token'))

    op.drop_table('payment_upload_sessions')
