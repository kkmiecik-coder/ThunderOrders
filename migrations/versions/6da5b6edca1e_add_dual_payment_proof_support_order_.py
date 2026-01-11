"""Add dual payment proof support (order + shipping)

Revision ID: 6da5b6edca1e
Revises: 2d67d7978326
Create Date: 2026-01-10 19:58:58.261741

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6da5b6edca1e'
down_revision = '2d67d7978326'
branch_labels = None
depends_on = None


def upgrade():
    # Add 8 new columns for dual payment proof system
    with op.batch_alter_table('orders', schema=None) as batch_op:
        # Payment proof for ORDER (products)
        batch_op.add_column(sa.Column('payment_proof_order_file', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_uploaded_at', sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_order_rejection_reason', sa.Text, nullable=True))

        # Payment proof for SHIPPING (delivery cost)
        batch_op.add_column(sa.Column('payment_proof_shipping_file', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_uploaded_at', sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_status', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('payment_proof_shipping_rejection_reason', sa.Text, nullable=True))

    # Migrate existing payment proof data to ORDER columns
    connection = op.get_bind()
    connection.execute(
        sa.text("""
            UPDATE orders
            SET payment_proof_order_file = payment_proof_file,
                payment_proof_order_uploaded_at = payment_proof_uploaded_at,
                payment_proof_order_status = payment_proof_status,
                payment_proof_order_rejection_reason = payment_proof_rejection_reason
            WHERE payment_proof_file IS NOT NULL
        """)
    )


def downgrade():
    # Remove 8 columns (in reverse order)
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('payment_proof_shipping_rejection_reason')
        batch_op.drop_column('payment_proof_shipping_status')
        batch_op.drop_column('payment_proof_shipping_uploaded_at')
        batch_op.drop_column('payment_proof_shipping_file')
        batch_op.drop_column('payment_proof_order_rejection_reason')
        batch_op.drop_column('payment_proof_order_status')
        batch_op.drop_column('payment_proof_order_uploaded_at')
        batch_op.drop_column('payment_proof_order_file')
