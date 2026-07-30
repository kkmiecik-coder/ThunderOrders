"""Cło/VAT: rozróżnienie NULL (nie ustalono) od 0 (ustalono bez podatku)

Revision ID: 90fb5ad1c7b6
Revises: 749897e046c0
Create Date: 2026-07-29 20:30:00.000000

Zdejmuje server_default='0.00' z poland_order_items i zamienia wszystkie
dzisiejsze zera na NULL. Jest to bezpieczne, bo przed tą zmianą kod nie
potrafił zapisać ustalonego zera — filtr `percentage > 0` w
modules/products/routes.py pomijał takie pozycje przy dystrybucji.
Weryfikacja na produkcji 2026-07-29: 6 paczek z zapisanym cłem miało
wyłącznie stawki > 0, a 7 paczek bez zapisanego cła wyłącznie zera.

Uwaga: brief zadania wskazywał revision id `a1b2c3d4e5f6`, ale ten identyfikator
jest już zajęty przez istniejącą migrację
`a1b2c3d4e5f6_add_payment_method_to_shipping_requests.py` (2026-01-11,
down_revision=8b9c0cbaf032, inna gałąź historii). Użyto losowego,
kolidującego identyfikatora `90fb5ad1c7b6`, żeby uniknąć duplikatu revision id
(który powodował CycleDetected w `flask db heads`).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '90fb5ad1c7b6'
down_revision = '749897e046c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.alter_column('customs_vat_percentage',
                              existing_type=sa.Numeric(5, 2),
                              existing_nullable=True,
                              server_default=None)
        batch_op.alter_column('customs_vat_amount',
                              existing_type=sa.Numeric(10, 2),
                              existing_nullable=True,
                              server_default=None)

    op.execute("UPDATE poland_order_items SET customs_vat_percentage = NULL, "
               "customs_vat_amount = NULL WHERE customs_vat_percentage = 0")
    op.execute("UPDATE orders SET customs_vat_sale_cost = NULL "
               "WHERE customs_vat_sale_cost = 0")


def downgrade():
    op.execute("UPDATE orders SET customs_vat_sale_cost = 0 "
               "WHERE customs_vat_sale_cost IS NULL")
    op.execute("UPDATE poland_order_items SET customs_vat_percentage = 0, "
               "customs_vat_amount = 0 WHERE customs_vat_percentage IS NULL")

    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.alter_column('customs_vat_percentage',
                              existing_type=sa.Numeric(5, 2),
                              existing_nullable=True,
                              server_default='0.00')
        batch_op.alter_column('customs_vat_amount',
                              existing_type=sa.Numeric(10, 2),
                              existing_nullable=True,
                              server_default='0.00')
