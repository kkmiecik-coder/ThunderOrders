"""Add exclusive_page_name to orders and change FK to ON DELETE SET NULL

Revision ID: c7d8e9f0a1b2
Revises: b8b12453841a
Create Date: 2026-01-12 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = 'b8b12453841a'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()

    # 1. Check if exclusive_page_name column already exists
    result = connection.execute(text("""
        SELECT COUNT(*) as cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'orders'
        AND COLUMN_NAME = 'exclusive_page_name'
    """))
    column_exists = result.fetchone()[0] > 0

    if not column_exists:
        # Add exclusive_page_name column to orders
        with op.batch_alter_table('orders', schema=None) as batch_op:
            batch_op.add_column(sa.Column('exclusive_page_name', sa.String(length=200), nullable=True))

        # Populate exclusive_page_name from existing exclusive_pages
        connection.execute(text("""
            UPDATE orders o
            JOIN exclusive_pages ep ON o.exclusive_page_id = ep.id
            SET o.exclusive_page_name = ep.name
            WHERE o.is_exclusive = 1
        """))

    # 2. Check if FK needs to be updated to ON DELETE SET NULL
    # Get current FK definition
    result = connection.execute(text("""
        SELECT CONSTRAINT_NAME, DELETE_RULE
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'orders'
        AND REFERENCED_TABLE_NAME = 'exclusive_pages'
    """))
    fk_row = result.fetchone()

    if fk_row:
        fk_name = fk_row[0]
        delete_rule = fk_row[1]

        # Only update if not already SET NULL
        if delete_rule != 'SET NULL':
            with op.batch_alter_table('orders', schema=None) as batch_op:
                batch_op.drop_constraint(fk_name, type_='foreignkey')
                batch_op.create_foreign_key(
                    'orders_ibfk_2',
                    'exclusive_pages',
                    ['exclusive_page_id'],
                    ['id'],
                    ondelete='SET NULL'
                )


def downgrade():
    connection = op.get_bind()

    # Check if FK exists and get its name
    result = connection.execute(text("""
        SELECT CONSTRAINT_NAME
        FROM information_schema.REFERENTIAL_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'orders'
        AND REFERENCED_TABLE_NAME = 'exclusive_pages'
    """))
    fk_row = result.fetchone()

    if fk_row:
        fk_name = fk_row[0]
        with op.batch_alter_table('orders', schema=None) as batch_op:
            batch_op.drop_constraint(fk_name, type_='foreignkey')
            batch_op.create_foreign_key(
                'orders_ibfk_2',
                'exclusive_pages',
                ['exclusive_page_id'],
                ['id']
            )

    # Remove exclusive_page_name column if it exists
    result = connection.execute(text("""
        SELECT COUNT(*) as cnt FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'orders'
        AND COLUMN_NAME = 'exclusive_page_name'
    """))
    if result.fetchone()[0] > 0:
        with op.batch_alter_table('orders', schema=None) as batch_op:
            batch_op.drop_column('exclusive_page_name')
