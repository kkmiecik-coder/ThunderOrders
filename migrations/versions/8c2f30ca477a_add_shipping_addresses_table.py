"""Add shipping_addresses table

Revision ID: 8c2f30ca477a
Revises: 517d7e08244c
Create Date: 2026-01-10 15:24:10.655820

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c2f30ca477a'
down_revision = '517d7e08244c'
branch_labels = None
depends_on = None


def upgrade():
    # Tworzenie tabeli shipping_addresses
    op.create_table('shipping_addresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('address_type', sa.String(length=20), nullable=False),
        sa.Column('pickup_courier', sa.String(length=50), nullable=True),
        sa.Column('pickup_point_id', sa.String(length=50), nullable=True),
        sa.Column('pickup_address', sa.String(length=500), nullable=True),
        sa.Column('pickup_postal_code', sa.String(length=10), nullable=True),
        sa.Column('pickup_city', sa.String(length=100), nullable=True),
        sa.Column('shipping_name', sa.String(length=200), nullable=True),
        sa.Column('shipping_address', sa.String(length=500), nullable=True),
        sa.Column('shipping_postal_code', sa.String(length=10), nullable=True),
        sa.Column('shipping_city', sa.String(length=100), nullable=True),
        sa.Column('shipping_voivodeship', sa.String(length=50), nullable=True),
        sa.Column('shipping_country', sa.String(length=100), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Tworzenie indeksów
    with op.batch_alter_table('shipping_addresses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_shipping_addresses_is_active'), ['is_active'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipping_addresses_is_default'), ['is_default'], unique=False)
        batch_op.create_index(batch_op.f('ix_shipping_addresses_user_id'), ['user_id'], unique=False)


def downgrade():
    # Usunięcie indeksów i tabeli
    with op.batch_alter_table('shipping_addresses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_shipping_addresses_user_id'))
        batch_op.drop_index(batch_op.f('ix_shipping_addresses_is_default'))
        batch_op.drop_index(batch_op.f('ix_shipping_addresses_is_active'))

    op.drop_table('shipping_addresses')
