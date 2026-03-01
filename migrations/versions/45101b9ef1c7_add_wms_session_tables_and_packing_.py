"""Add WMS session tables and packing fields to Order

Revision ID: 45101b9ef1c7
Revises: b28d164340ee
Create Date: 2026-02-28 15:53:49.558564

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '45101b9ef1c7'
down_revision = 'b28d164340ee'
branch_labels = None
depends_on = None


def upgrade():
    # --- New tables ---
    op.create_table('wms_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('phone_connected', sa.Boolean(), nullable=True),
        sa.Column('phone_connected_at', sa.DateTime(), nullable=True),
        sa.Column('desktop_connected_at', sa.DateTime(), nullable=True),
        sa.Column('current_order_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('wms_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wms_sessions_session_token'), ['session_token'], unique=True)

    op.create_table('wms_session_orders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('picking_started_at', sa.DateTime(), nullable=True),
        sa.Column('picking_completed_at', sa.DateTime(), nullable=True),
        sa.Column('packing_completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['wms_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('wms_session_shipping_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('shipping_request_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['wms_sessions.id'], ),
        sa.ForeignKeyConstraint(['shipping_request_id'], ['shipping_requests.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # --- New columns on orders ---
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('wms_locked_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('wms_session_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('packed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('packed_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('packing_photo', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('total_package_weight', sa.Numeric(precision=8, scale=2), nullable=True))
        batch_op.create_foreign_key('fk_orders_wms_session_id', 'wms_sessions', ['wms_session_id'], ['id'])
        batch_op.create_foreign_key('fk_orders_packed_by', 'users', ['packed_by'], ['id'])


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_orders_packed_by', type_='foreignkey')
        batch_op.drop_constraint('fk_orders_wms_session_id', type_='foreignkey')
        batch_op.drop_column('total_package_weight')
        batch_op.drop_column('packing_photo')
        batch_op.drop_column('packed_by')
        batch_op.drop_column('packed_at')
        batch_op.drop_column('wms_session_id')
        batch_op.drop_column('wms_locked_at')

    op.drop_table('wms_session_shipping_requests')
    op.drop_table('wms_session_orders')
    with op.batch_alter_table('wms_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wms_sessions_session_token'))
    op.drop_table('wms_sessions')
