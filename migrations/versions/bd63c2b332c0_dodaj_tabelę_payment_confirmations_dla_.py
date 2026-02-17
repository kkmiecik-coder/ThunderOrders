"""Dodaj tabelę payment_confirmations dla systemu potwierdzeń płatności

Revision ID: bd63c2b332c0
Revises: 371fe9156135
Create Date: 2026-02-16 21:21:34.882070

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'bd63c2b332c0'
down_revision = '371fe9156135'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_confirmations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('payment_stage', sa.String(length=50), nullable=False, comment="Etap: 'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'"),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False, comment='Kwota do zapłaty w PLN'),
        sa.Column('proof_file', sa.String(length=255), nullable=True, comment='Nazwa pliku potwierdzenia'),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True, comment='Data uploadu przez klienta'),
        sa.Column('status', sa.String(length=20), nullable=False, comment="Status: 'pending', 'approved', 'rejected'"),
        sa.Column('rejection_reason', sa.Text(), nullable=True, comment='Powód odrzucenia (admin)'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('payment_confirmations')
