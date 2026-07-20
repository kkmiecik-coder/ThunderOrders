"""shipping packaging pricing

Revision ID: 749897e046c0
Revises: 830b9d3167ad
Create Date: 2026-07-20 20:06:15.879497

Migracja zawęża się WYŁĄCZNIE do kolumn cennika materiału opakowaniowego
(packaging_materials.sale_price, packaging_materials.size_category) oraz
nowych pól zlecenia wysyłki (shipping_requests.packaging_material_id + FK,
client_package_preference, client_notes, poszerzenie parcel_size do
String(10)). Alembic autogen wykrył też dużo niepowiązanego dryfu (indeksy,
komentarze kolumn, stare tabele exclusive_*) — celowo pominięty tutaj.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '749897e046c0'
down_revision = '830b9d3167ad'
branch_labels = None
depends_on = None


def upgrade():
    # packaging_materials: cennik + gabaryt
    op.add_column('packaging_materials', sa.Column('sale_price', sa.Numeric(precision=8, scale=2), nullable=True))
    op.add_column('packaging_materials', sa.Column('size_category', sa.String(length=10), nullable=True))

    # shipping_requests: wybrany materiał opakowaniowy, preferencja klienta, uwagi klienta
    op.add_column('shipping_requests', sa.Column('packaging_material_id', sa.Integer(), nullable=True))
    op.add_column('shipping_requests', sa.Column('client_package_preference', sa.String(length=30), nullable=True))
    op.add_column('shipping_requests', sa.Column('client_notes', sa.Text(), nullable=True))

    op.alter_column('shipping_requests', 'parcel_size',
                     existing_type=mysql.VARCHAR(length=1),
                     type_=sa.String(length=10),
                     existing_nullable=True)

    op.create_foreign_key(
        'fk_shipping_requests_packaging_material_id',
        'shipping_requests', 'packaging_materials',
        ['packaging_material_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_shipping_requests_packaging_material_id', 'shipping_requests', type_='foreignkey')

    op.alter_column('shipping_requests', 'parcel_size',
                     existing_type=sa.String(length=10),
                     type_=mysql.VARCHAR(length=1),
                     existing_nullable=True)

    op.drop_column('shipping_requests', 'client_notes')
    op.drop_column('shipping_requests', 'client_package_preference')
    op.drop_column('shipping_requests', 'packaging_material_id')

    op.drop_column('packaging_materials', 'size_category')
    op.drop_column('packaging_materials', 'sale_price')
