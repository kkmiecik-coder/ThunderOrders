"""Add payment_deadline to OfferPage and payment reminder tables

Revision ID: 6a2c80d1f048
Revises: 61a9a180890c
Create Date: 2026-04-07 22:42:19.805791

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '6a2c80d1f048'
down_revision = '61a9a180890c'
branch_labels = None
depends_on = None


def _table_exists(table_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(table_name, column_name):
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not _table_exists('payment_reminder_configs'):
        op.create_table('payment_reminder_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reminder_type', sa.String(length=30), nullable=False),
        sa.Column('hours', sa.Integer(), nullable=False),
        sa.Column('payment_stage', sa.String(length=30), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )

    if not _table_exists('payment_reminder_logs'):
        op.create_table('payment_reminder_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=True),
        sa.Column('reminder_type', sa.String(length=30), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['config_id'], ['payment_reminder_configs.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
        )

    if not _column_exists('offer_pages', 'payment_deadline'):
        with op.batch_alter_table('offer_pages', schema=None) as batch_op:
            batch_op.add_column(sa.Column('payment_deadline', sa.DateTime(), nullable=True))


def downgrade():
    if _column_exists('offer_pages', 'payment_deadline'):
        with op.batch_alter_table('offer_pages', schema=None) as batch_op:
            batch_op.drop_column('payment_deadline')

    if _table_exists('payment_reminder_logs'):
        op.drop_table('payment_reminder_logs')

    if _table_exists('payment_reminder_configs'):
        op.drop_table('payment_reminder_configs')
