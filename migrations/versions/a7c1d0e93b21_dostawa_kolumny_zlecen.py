"""Kolumny dostawy na zleceniach wysyłki (task 869efhwph)

Uzupełnienie shipped_at dla historii NIE jest tutaj — robi to
modules/orders/delivery_backfill.odtworz_shipped_at() wołane przez komendę
check-delivery-confirmations. Dzięki temu logika jest przetestowana i sama się
naprawia, a migracja nie zależy od kodu aplikacji.

Revision ID: a7c1d0e93b21
Revises: c3d1b24441be
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c1d0e93b21'
down_revision = 'c3d1b24441be'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shipped_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('delivered_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('delivered_source', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('delivery_reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.drop_column('delivery_reminder_sent_at')
        batch_op.drop_column('delivered_source')
        batch_op.drop_column('delivered_at')
        batch_op.drop_column('shipped_at')
