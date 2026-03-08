"""Add OCR verification fields to PaymentConfirmation

Revision ID: 4c4f453545b5
Revises: b15560d41eae
Create Date: 2026-03-08 04:01:17.772654

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '4c4f453545b5'
down_revision = 'b15560d41eae'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_confirmations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_method_id', sa.Integer(), nullable=True, comment='Metoda płatności wybrana przez klienta przy uploadzie'))
        batch_op.add_column(sa.Column('ocr_score', sa.Integer(), nullable=True, comment='OCR confidence score 0-100'))
        batch_op.add_column(sa.Column('ocr_details', sa.Text(), nullable=True, comment='JSON z detalami OCR: wykryte kwoty, tytuły, dane odbiorcy'))
        batch_op.add_column(sa.Column('auto_approved', sa.Boolean(), nullable=False, server_default=sa.text('0'), comment='Czy auto-zatwierdzone przez OCR (score >= próg)'))
        batch_op.create_foreign_key('fk_pc_payment_method_id', 'payment_methods', ['payment_method_id'], ['id'])


def downgrade():
    with op.batch_alter_table('payment_confirmations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pc_payment_method_id', type_='foreignkey')
        batch_op.drop_column('auto_approved')
        batch_op.drop_column('ocr_details')
        batch_op.drop_column('ocr_score')
        batch_op.drop_column('payment_method_id')
