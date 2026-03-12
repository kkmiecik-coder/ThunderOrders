"""Add QR tracking tables (qr_campaigns, qr_visits)

Revision ID: e6ca372c32c3
Revises: 4c4f453545b5
Create Date: 2026-03-12 21:37:39.457830

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6ca372c32c3'
down_revision = '4c4f453545b5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('qr_campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('target_url', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('qr_campaigns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_qr_campaigns_slug'), ['slug'], unique=True)

    op.create_table('qr_visits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('visitor_id', sa.String(length=64), nullable=False),
        sa.Column('is_unique', sa.Boolean(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('device_type', sa.String(length=20), nullable=True),
        sa.Column('browser', sa.String(length=50), nullable=True),
        sa.Column('os', sa.String(length=50), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('referer', sa.String(length=500), nullable=True),
        sa.Column('visited_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['qr_campaigns.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('qr_visits', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_qr_visits_campaign_id'), ['campaign_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_qr_visits_visited_at'), ['visited_at'], unique=False)
        batch_op.create_index('ix_qr_visits_visitor_campaign', ['visitor_id', 'campaign_id'], unique=False)


def downgrade():
    with op.batch_alter_table('qr_visits', schema=None) as batch_op:
        batch_op.drop_index('ix_qr_visits_visitor_campaign')
        batch_op.drop_index(batch_op.f('ix_qr_visits_visited_at'))
        batch_op.drop_index(batch_op.f('ix_qr_visits_campaign_id'))

    op.drop_table('qr_visits')

    with op.batch_alter_table('qr_campaigns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_qr_campaigns_slug'))

    op.drop_table('qr_campaigns')
