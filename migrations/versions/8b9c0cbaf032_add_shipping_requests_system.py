"""Add shipping requests system

Revision ID: 8b9c0cbaf032
Revises: afe4f8d18c48
Create Date: 2026-01-11 02:23:57.087242

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8b9c0cbaf032'
down_revision = 'afe4f8d18c48'
branch_labels = None
depends_on = None


def upgrade():
    # Create shipping_request_statuses table
    op.create_table('shipping_request_statuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('badge_color', sa.String(length=7), nullable=True, default='#6B7280'),
        sa.Column('sort_order', sa.Integer(), nullable=True, default=0),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('is_initial', sa.Boolean(), nullable=True, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Create shipping_requests table
    op.create_table('shipping_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_number', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('address_type', sa.String(length=20), nullable=True),
        sa.Column('shipping_name', sa.String(length=200), nullable=True),
        sa.Column('shipping_address', sa.String(length=500), nullable=True),
        sa.Column('shipping_postal_code', sa.String(length=10), nullable=True),
        sa.Column('shipping_city', sa.String(length=100), nullable=True),
        sa.Column('shipping_voivodeship', sa.String(length=50), nullable=True),
        sa.Column('shipping_country', sa.String(length=100), nullable=True),
        sa.Column('pickup_courier', sa.String(length=100), nullable=True),
        sa.Column('pickup_point_id', sa.String(length=50), nullable=True),
        sa.Column('pickup_address', sa.String(length=500), nullable=True),
        sa.Column('pickup_postal_code', sa.String(length=10), nullable=True),
        sa.Column('pickup_city', sa.String(length=100), nullable=True),
        sa.Column('total_shipping_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('payment_proof_file', sa.String(length=255), nullable=True),
        sa.Column('payment_proof_uploaded_at', sa.DateTime(), nullable=True),
        sa.Column('payment_proof_status', sa.String(length=20), nullable=True),
        sa.Column('payment_proof_rejection_reason', sa.Text(), nullable=True),
        sa.Column('tracking_number', sa.String(length=100), nullable=True),
        sa.Column('courier', sa.String(length=50), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['status'], ['shipping_request_statuses.slug'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_number')
    )

    # Create shipping_request_orders junction table
    op.create_table('shipping_request_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shipping_request_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('shipping_cost', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['shipping_request_id'], ['shipping_requests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Insert default statuses
    op.execute("""
        INSERT INTO shipping_request_statuses (slug, name, badge_color, sort_order, is_active, is_initial, created_at, updated_at)
        VALUES
            ('nowe', 'Nowe', '#3B82F6', 1, 1, 1, NOW(), NOW()),
            ('czeka_na_wycene', 'Czeka na wycenę', '#F59E0B', 2, 1, 0, NOW(), NOW()),
            ('czeka_na_oplacenie', 'Czeka na opłacenie', '#EF4444', 3, 1, 0, NOW(), NOW()),
            ('do_wyslania', 'Do wysłania', '#8B5CF6', 4, 1, 0, NOW(), NOW()),
            ('wyslane', 'Wysłane', '#10B981', 5, 1, 0, NOW(), NOW()),
            ('dostarczone', 'Dostarczone', '#059669', 6, 1, 0, NOW(), NOW())
    """)


def downgrade():
    op.drop_table('shipping_request_orders')
    op.drop_table('shipping_requests')
    op.drop_table('shipping_request_statuses')
