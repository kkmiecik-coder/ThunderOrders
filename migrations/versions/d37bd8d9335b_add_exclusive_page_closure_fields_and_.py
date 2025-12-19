"""Add exclusive page closure fields and order item set fulfillment

Revision ID: d37bd8d9335b
Revises: add_verification_code
Create Date: 2025-12-18 23:19:43.721333

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd37bd8d9335b'
down_revision = 'add_verification_code'
branch_labels = None
depends_on = None


def upgrade():
    # Dodaj pola do exclusive_pages dla funkcjonalności całkowitego zamknięcia
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_fully_closed', sa.Boolean(), nullable=True, default=False))
        batch_op.add_column(sa.Column('closed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('closed_by_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_exclusive_pages_closed_by', 'users', ['closed_by_id'], ['id'])

    # Dodaj pola do order_items dla alokacji setów
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_set_fulfilled', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('set_section_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_order_items_set_section', 'exclusive_sections', ['set_section_id'], ['id'])


def downgrade():
    # Usuń pola z order_items
    with op.batch_alter_table('order_items', schema=None) as batch_op:
        batch_op.drop_constraint('fk_order_items_set_section', type_='foreignkey')
        batch_op.drop_column('set_section_id')
        batch_op.drop_column('is_set_fulfilled')

    # Usuń pola z exclusive_pages
    with op.batch_alter_table('exclusive_pages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_exclusive_pages_closed_by', type_='foreignkey')
        batch_op.drop_column('closed_by_id')
        batch_op.drop_column('closed_at')
        batch_op.drop_column('is_fully_closed')
