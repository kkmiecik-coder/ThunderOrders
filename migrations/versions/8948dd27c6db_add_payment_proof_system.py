"""Add payment proof system

Revision ID: 8948dd27c6db
Revises: 9556407dc0e2
Create Date: 2025-12-27 01:04:46.132829

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8948dd27c6db'
down_revision = '9556407dc0e2'
branch_labels = None
depends_on = None


def upgrade():
    # Create payment_methods table (with error handling for existing table)
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)

    if 'payment_methods' not in inspector.get_table_names():
        op.create_table('payment_methods',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=200), nullable=False),
            sa.Column('details', sa.Text(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )

    # Add payment proof columns to orders table (with error handling for existing columns)
    orders_columns = [col['name'] for col in inspector.get_columns('orders')]

    with op.batch_alter_table('orders', schema=None) as batch_op:
        if 'payment_proof_file' not in orders_columns:
            batch_op.add_column(sa.Column('payment_proof_file', sa.String(length=255), nullable=True))
        if 'payment_proof_uploaded_at' not in orders_columns:
            batch_op.add_column(sa.Column('payment_proof_uploaded_at', sa.DateTime(), nullable=True))
        if 'payment_proof_status' not in orders_columns:
            batch_op.add_column(sa.Column('payment_proof_status', sa.String(length=20), nullable=True))
        if 'payment_proof_rejection_reason' not in orders_columns:
            batch_op.add_column(sa.Column('payment_proof_rejection_reason', sa.Text(), nullable=True))


def downgrade():
    # Remove payment proof columns from orders table
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('payment_proof_rejection_reason')
        batch_op.drop_column('payment_proof_status')
        batch_op.drop_column('payment_proof_uploaded_at')
        batch_op.drop_column('payment_proof_file')

    # Drop payment_methods table
    op.drop_table('payment_methods')
