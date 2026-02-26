"""Add public collection config, upload sessions, temp uploads, is_public on collection_items

Revision ID: b28d164340ee
Revises: 505eed8a086c
Create Date: 2026-02-27 00:34:51.811602

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b28d164340ee'
down_revision = '505eed8a086c'
branch_labels = None
depends_on = None


def upgrade():
    # Tabela konfiguracji publicznej strony kolekcji
    op.create_table('public_collection_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=12), nullable=False),
        sa.Column('show_prices', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    with op.batch_alter_table('public_collection_configs', schema=None) as batch_op:
        batch_op.create_index('ix_public_collection_configs_token', ['token'], unique=True)

    # Tabela sesji uploadu QR
    op.create_table('collection_upload_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('collection_item_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['collection_item_id'], ['collection_items.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('collection_upload_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_collection_upload_sessions_session_token', ['session_token'], unique=True)

    # Tabela tymczasowych uploadow z QR
    op.create_table('collection_temp_uploads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('path_original', sa.String(length=500), nullable=False),
        sa.Column('path_compressed', sa.String(length=500), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['collection_upload_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Dodanie kolumny is_public do collection_items
    with op.batch_alter_table('collection_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade():
    with op.batch_alter_table('collection_items', schema=None) as batch_op:
        batch_op.drop_column('is_public')

    op.drop_table('collection_temp_uploads')

    with op.batch_alter_table('collection_upload_sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_collection_upload_sessions_session_token')
    op.drop_table('collection_upload_sessions')

    with op.batch_alter_table('public_collection_configs', schema=None) as batch_op:
        batch_op.drop_index('ix_public_collection_configs_token')
    op.drop_table('public_collection_configs')
