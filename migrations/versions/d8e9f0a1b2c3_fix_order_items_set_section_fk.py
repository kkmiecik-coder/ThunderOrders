"""Fix order_items set_section_id FK to ON DELETE SET NULL

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-01-12 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    # Check if FK exists and get its name and delete rule
    result = connection.execute(text("""
        SELECT CONSTRAINT_NAME, DELETE_RULE
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'order_items'
        AND REFERENCED_TABLE_NAME = 'exclusive_sections'
    """))
    fk_row = result.fetchone()

    if fk_row:
        fk_name = fk_row[0]
        delete_rule = fk_row[1]

        # Only update if not already SET NULL
        if delete_rule != 'SET NULL':
            with op.batch_alter_table('order_items', schema=None) as batch_op:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
                batch_op.create_foreign_key(
                    'fk_order_items_set_section',
                    'exclusive_sections',
                    ['set_section_id'],
                    ['id'],
                    ondelete='SET NULL'
                )


def downgrade():
    connection = op.get_bind()

    # Check if FK exists
    result = connection.execute(text("""
        SELECT CONSTRAINT_NAME
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'order_items'
        AND REFERENCED_TABLE_NAME = 'exclusive_sections'
    """))
    fk_row = result.fetchone()

    if fk_row:
        fk_name = fk_row[0]
        with op.batch_alter_table('order_items', schema=None) as batch_op:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.create_foreign_key(
                'fk_order_items_set_section',
                'exclusive_sections',
                ['set_section_id'],
                ['id']
            )
