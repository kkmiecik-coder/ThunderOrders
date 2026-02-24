"""Add popups, popup_views tables and user login_count

Revision ID: 1f85b2c9e3f2
Revises: e8dd8d002da3
Create Date: 2026-02-24 22:03:28.693012

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1f85b2c9e3f2'
down_revision = 'e8dd8d002da3'
branch_labels = None
depends_on = None


def upgrade():
    # Tabela popups
    op.create_table('popups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('draft', 'active', 'archived', name='popup_status'), nullable=False),
        sa.Column('target_roles', sa.Text(), nullable=True),
        sa.Column('display_mode', sa.Enum('once', 'every_login', 'first_login', name='popup_display_mode'), nullable=False),
        sa.Column('cta_text', sa.String(length=100), nullable=True),
        sa.Column('cta_url', sa.String(length=500), nullable=True),
        sa.Column('cta_color', sa.String(length=20), nullable=True),
        sa.Column('bg_color', sa.String(length=20), nullable=True),
        sa.Column('modal_size', sa.Enum('sm', 'md', 'lg', name='popup_modal_size'), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('popups', schema=None) as batch_op:
        batch_op.create_index('ix_popups_status', ['status'], unique=False)

    # Tabela popup_views (statystyki wyświetleń)
    op.create_table('popup_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('popup_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.Enum('viewed', 'dismissed', 'cta_clicked', name='popup_view_action'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['popup_id'], ['popups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('popup_views', schema=None) as batch_op:
        batch_op.create_index('ix_popup_views_popup_id', ['popup_id'], unique=False)
        batch_op.create_index('ix_popup_views_user_id', ['user_id'], unique=False)

    # Dodanie login_count do users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('login_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    # Usunięcie login_count z users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('login_count')

    # Usunięcie tabel
    with op.batch_alter_table('popup_views', schema=None) as batch_op:
        batch_op.drop_index('ix_popup_views_user_id')
        batch_op.drop_index('ix_popup_views_popup_id')
    op.drop_table('popup_views')

    with op.batch_alter_table('popups', schema=None) as batch_op:
        batch_op.drop_index('ix_popups_status')
    op.drop_table('popups')
