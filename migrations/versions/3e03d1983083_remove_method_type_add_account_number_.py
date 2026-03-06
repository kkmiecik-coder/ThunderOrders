"""Remove method_type, add account_number_label and code_label to PaymentMethod

Revision ID: 3e03d1983083
Revises: c5d6e7f8a9b0
Create Date: 2026-03-05 21:13:08.689037

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '3e03d1983083'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_number_label', sa.String(length=100), nullable=True,
                                       comment='Etykieta pola account_number (np. Numer konta, Numer telefonu, Email)'))
        batch_op.add_column(sa.Column('code_label', sa.String(length=100), nullable=True,
                                       comment='Etykieta pola code (np. Kod SWIFT, RevTag)'))
        batch_op.drop_column('method_type')


def downgrade():
    with op.batch_alter_table('payment_methods', schema=None) as batch_op:
        batch_op.add_column(sa.Column('method_type', mysql.VARCHAR(length=20), nullable=False,
                                       server_default='other',
                                       comment="Typ: 'transfer' (przelew), 'instant' (BLIK), 'online' (PayPal/Revolut), 'other'"))
        batch_op.drop_column('code_label')
        batch_op.drop_column('account_number_label')
