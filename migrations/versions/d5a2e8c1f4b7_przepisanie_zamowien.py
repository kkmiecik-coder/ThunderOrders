"""Przepisywanie zamówień: kotwica kolejki FIFO i ukrywanie dowodu przelewu

Revision ID: d5a2e8c1f4b7
Revises: c4f1a9e7b2d5
Create Date: 2026-11-24
"""
from alembic import op
import sqlalchemy as sa


revision = 'd5a2e8c1f4b7'
down_revision = 'c4f1a9e7b2d5'
branch_labels = None
depends_on = None


def upgrade():
    # NULL dla wszystkich istniejących zamówień = kolejność FIFO bez zmian.
    op.add_column('orders', sa.Column('fifo_anchor_order_id', sa.Integer(), nullable=True))
    op.create_index('ix_orders_fifo_anchor_order_id', 'orders', ['fifo_anchor_order_id'])
    op.create_foreign_key(
        'fk_orders_fifo_anchor_order_id', 'orders', 'orders',
        ['fifo_anchor_order_id'], ['id'], ondelete='SET NULL')

    op.add_column('payment_confirmations', sa.Column(
        'proof_hidden_for_client', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    op.drop_column('payment_confirmations', 'proof_hidden_for_client')
    op.drop_constraint('fk_orders_fifo_anchor_order_id', 'orders', type_='foreignkey')
    op.drop_index('ix_orders_fifo_anchor_order_id', table_name='orders')
    op.drop_column('orders', 'fifo_anchor_order_id')
