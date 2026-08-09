"""Konsolidacja zleceń wysyłki

Revision ID: c3d1b24441be
Revises: 5d55aefadf79
Create Date: 2026-08-09 22:18:22.694416

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3d1b24441be'
down_revision = '5d55aefadf79'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('consolidated_into_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('lead_source_request_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_shipping_requests_consolidated_into', 'shipping_requests',
            ['consolidated_into_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(
            'fk_shipping_requests_lead_source', 'shipping_requests',
            ['lead_source_request_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('shipping_request_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_request_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_shipping_request_orders_source_request', 'shipping_requests',
            ['source_request_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('shipping_request_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shipping_request_orders_source_request', type_='foreignkey')
        batch_op.drop_column('source_request_id')

    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shipping_requests_lead_source', type_='foreignkey')
        batch_op.drop_constraint('fk_shipping_requests_consolidated_into', type_='foreignkey')
        batch_op.drop_column('lead_source_request_id')
        batch_op.drop_column('consolidated_into_id')
