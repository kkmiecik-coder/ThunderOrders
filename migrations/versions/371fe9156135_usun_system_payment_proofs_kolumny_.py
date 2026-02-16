"""Usun system payment proofs - kolumny Order i ShippingRequest

Revision ID: 371fe9156135
Revises: 9b5d4a3f76bd
Create Date: 2026-02-16 19:59:32.273238

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '371fe9156135'
down_revision = '9b5d4a3f76bd'
branch_labels = None
depends_on = None


def upgrade():
    # Usunięcie kolumn payment proof z tabeli orders
    with op.batch_alter_table('orders', schema=None) as batch_op:
        # Legacy (stary system - pojedynczy proof)
        batch_op.drop_column('payment_proof_file')
        batch_op.drop_column('payment_proof_uploaded_at')
        batch_op.drop_column('payment_proof_status')
        batch_op.drop_column('payment_proof_rejection_reason')
        # Dual system - proof za zamówienie
        batch_op.drop_column('payment_proof_order_file')
        batch_op.drop_column('payment_proof_order_uploaded_at')
        batch_op.drop_column('payment_proof_order_status')
        batch_op.drop_column('payment_proof_order_rejection_reason')
        # Dual system - proof za wysyłkę
        batch_op.drop_column('payment_proof_shipping_file')
        batch_op.drop_column('payment_proof_shipping_uploaded_at')
        batch_op.drop_column('payment_proof_shipping_status')
        batch_op.drop_column('payment_proof_shipping_rejection_reason')

    # Usunięcie kolumn payment proof z tabeli shipping_requests
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.drop_column('payment_method')
        batch_op.drop_column('payment_proof_file')
        batch_op.drop_column('payment_proof_uploaded_at')
        batch_op.drop_column('payment_proof_status')
        batch_op.drop_column('payment_proof_rejection_reason')


def downgrade():
    # Przywrócenie kolumn payment proof w tabeli shipping_requests
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_proof_rejection_reason', mysql.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_status', mysql.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_uploaded_at', mysql.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_file', mysql.VARCHAR(length=255), nullable=True))
        batch_op.add_column(sa.Column('payment_method', mysql.VARCHAR(length=100), nullable=True))

    # Przywrócenie kolumn payment proof w tabeli orders
    with op.batch_alter_table('orders', schema=None) as batch_op:
        # Dual system - proof za wysyłkę
        batch_op.add_column(sa.Column('payment_proof_shipping_rejection_reason', mysql.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_status', mysql.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_uploaded_at', mysql.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_file', mysql.VARCHAR(length=255), nullable=True))
        # Dual system - proof za zamówienie
        batch_op.add_column(sa.Column('payment_proof_order_rejection_reason', mysql.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_status', mysql.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_uploaded_at', mysql.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_file', mysql.VARCHAR(length=255), nullable=True))
        # Legacy (stary system - pojedynczy proof)
        batch_op.add_column(sa.Column('payment_proof_rejection_reason', mysql.TEXT(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_status', mysql.VARCHAR(length=20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_uploaded_at', mysql.DATETIME(), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_file', mysql.VARCHAR(length=255), nullable=True))
