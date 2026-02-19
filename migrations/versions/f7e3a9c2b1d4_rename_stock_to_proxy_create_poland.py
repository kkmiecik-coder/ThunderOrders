"""Rename stock_orders to proxy_orders and create poland_orders

Revision ID: f7e3a9c2b1d4
Revises: 605e21170ba9
Create Date: 2026-02-17 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'f7e3a9c2b1d4'
down_revision = '605e21170ba9'
branch_labels = None
depends_on = None


def _table_exists(connection, table_name):
    """Check if a table exists in the current database."""
    result = connection.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :tbl"
    ), {'tbl': table_name})
    return result.scalar() > 0


def _column_exists(connection, table_name, column_name):
    """Check if a column exists in a table."""
    result = connection.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :tbl AND column_name = :col"
    ), {'tbl': table_name, 'col': column_name})
    return result.scalar() > 0


def _fk_exists(connection, table_name, constraint_name):
    """Check if a FK constraint exists."""
    result = connection.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.table_constraints "
        "WHERE table_schema = DATABASE() AND table_name = :tbl "
        "AND constraint_name = :cname AND constraint_type = 'FOREIGN KEY'"
    ), {'tbl': table_name, 'cname': constraint_name})
    return result.scalar() > 0


def upgrade():
    conn = op.get_bind()

    # === STEP 1-2: Rename tables (skip if already done) ===
    if _table_exists(conn, 'stock_order_items') and not _table_exists(conn, 'proxy_order_items'):
        op.rename_table('stock_order_items', 'proxy_order_items')

    if _table_exists(conn, 'stock_orders') and not _table_exists(conn, 'proxy_orders'):
        op.rename_table('stock_orders', 'proxy_orders')

    # === STEP 3: Rename column stock_order_id → proxy_order_id ===
    # MariaDB auto-renames FK constraints when table is renamed.
    # After renaming stock_order_items → proxy_order_items:
    #   stock_order_items_ibfk_1 (product_id) → proxy_order_items_ibfk_1
    #   stock_order_items_ibfk_2 (stock_order_id) → proxy_order_items_ibfk_2
    # On fresh DB (no rename yet): constraint is stock_order_items_ibfk_2
    if _column_exists(conn, 'proxy_order_items', 'stock_order_id'):
        # Drop whichever FK constraint exists on stock_order_id
        if _fk_exists(conn, 'proxy_order_items', 'proxy_order_items_ibfk_2'):
            op.drop_constraint('proxy_order_items_ibfk_2', 'proxy_order_items', type_='foreignkey')
        elif _fk_exists(conn, 'proxy_order_items', 'stock_order_items_ibfk_2'):
            op.drop_constraint('stock_order_items_ibfk_2', 'proxy_order_items', type_='foreignkey')

        op.alter_column('proxy_order_items', 'stock_order_id',
                         new_column_name='proxy_order_id',
                         existing_type=sa.Integer(),
                         existing_nullable=False)

        op.create_foreign_key(
            'proxy_order_items_proxy_order_id_fkey',
            'proxy_order_items', 'proxy_orders',
            ['proxy_order_id'], ['id'],
            ondelete='CASCADE'
        )

    # === STEP 4: Update status enum ===
    # Map old statuses to new ones (safe even if rows don't match)
    op.execute("""
        UPDATE proxy_orders SET status = 'zamowiono'
        WHERE status IN ('oczekujace', 'w_drodze_polska')
    """)
    op.execute("""
        UPDATE proxy_orders SET status = 'dostarczone_do_proxy'
        WHERE status IN ('dostarczone_proxy', 'urzad_celny', 'dostarczone_gom')
    """)

    # Modify the enum column
    op.alter_column('proxy_orders', 'status',
                     type_=sa.Enum('nowe', 'zamowiono', 'dostarczone_do_proxy', 'anulowane',
                                   name='proxy_order_status'),
                     existing_nullable=False,
                     server_default='nowe')

    # === STEP 5: Update order_number format ===
    op.execute("""
        UPDATE proxy_orders
        SET order_number = CONCAT('PRX/', LPAD(
            CAST(SUBSTRING_INDEX(order_number, '/', -1) AS UNSIGNED), 5, '0'
        ))
        WHERE order_number LIKE 'SO/PROXY/%'
    """)
    op.execute("""
        UPDATE proxy_orders
        SET order_number = CONCAT('PL/', LPAD(
            CAST(SUBSTRING_INDEX(order_number, '/', -1) AS UNSIGNED), 5, '0'
        ))
        WHERE order_number LIKE 'SO/PL/%'
    """)

    # === STEP 6: Add new columns to proxy_orders ===
    if not _column_exists(conn, 'proxy_orders', 'shipping_cost_total'):
        op.add_column('proxy_orders', sa.Column('shipping_cost_total', sa.Numeric(10, 2), server_default='0.00'))
    if not _column_exists(conn, 'proxy_orders', 'shipping_cost_declared'):
        op.add_column('proxy_orders', sa.Column('shipping_cost_declared', sa.Numeric(10, 2), server_default='0.00'))
    if not _column_exists(conn, 'proxy_orders', 'shipping_cost_difference'):
        op.add_column('proxy_orders', sa.Column('shipping_cost_difference', sa.Numeric(10, 2), server_default='0.00'))

    # === STEP 7: Add new columns to proxy_order_items ===
    if not _column_exists(conn, 'proxy_order_items', 'shipping_cost_per_item'):
        op.add_column('proxy_order_items', sa.Column('shipping_cost_per_item', sa.Numeric(10, 2), server_default='0.00'))
    if not _column_exists(conn, 'proxy_order_items', 'shipping_cost_total'):
        op.add_column('proxy_order_items', sa.Column('shipping_cost_total', sa.Numeric(10, 2), server_default='0.00'))
    if not _column_exists(conn, 'proxy_order_items', 'order_id'):
        op.add_column('proxy_order_items', sa.Column('order_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'proxy_order_items_order_id_fkey',
            'proxy_order_items', 'orders',
            ['order_id'], ['id']
        )

    # === STEP 8: Create poland_orders table ===
    if not _table_exists(conn, 'poland_orders'):
        op.create_table('poland_orders',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('order_number', sa.String(50), nullable=False),
            sa.Column('proxy_order_id', sa.Integer(), nullable=False),
            sa.Column('status', sa.Enum('w_drodze', 'w_urzedzie_celnym', 'dostarczone_gom', 'anulowane',
                                         name='poland_order_status'), nullable=False, server_default='w_drodze'),
            sa.Column('total_amount', sa.Numeric(10, 2), server_default='0.00'),
            sa.Column('shipping_cost', sa.Numeric(10, 2), server_default='0.00'),
            sa.Column('customs_cost', sa.Numeric(10, 2), server_default='0.00'),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('admin_notes', sa.Text(), nullable=True),
            sa.Column('tracking_number', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('shipped_at', sa.DateTime(), nullable=True),
            sa.Column('delivered_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('order_number'),
            sa.ForeignKeyConstraint(['proxy_order_id'], ['proxy_orders.id'], ondelete='CASCADE')
        )

    # === STEP 9: Create poland_order_items table ===
    if not _table_exists(conn, 'poland_order_items'):
        op.create_table('poland_order_items',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('poland_order_id', sa.Integer(), nullable=False),
            sa.Column('proxy_order_item_id', sa.Integer(), nullable=False),
            sa.Column('product_id', sa.Integer(), nullable=False),
            sa.Column('order_id', sa.Integer(), nullable=True),
            sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('shipping_cost', sa.Numeric(10, 2), server_default='0.00'),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['poland_order_id'], ['poland_orders.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['proxy_order_item_id'], ['proxy_order_items.id']),
            sa.ForeignKeyConstraint(['product_id'], ['products.id']),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'])
        )


def downgrade():
    conn = op.get_bind()

    # Drop new tables
    if _table_exists(conn, 'poland_order_items'):
        op.drop_table('poland_order_items')
    if _table_exists(conn, 'poland_orders'):
        op.drop_table('poland_orders')

    # Remove new columns from proxy_order_items
    if _column_exists(conn, 'proxy_order_items', 'order_id'):
        if _fk_exists(conn, 'proxy_order_items', 'proxy_order_items_order_id_fkey'):
            op.drop_constraint('proxy_order_items_order_id_fkey', 'proxy_order_items', type_='foreignkey')
        op.drop_column('proxy_order_items', 'order_id')
    if _column_exists(conn, 'proxy_order_items', 'shipping_cost_total'):
        op.drop_column('proxy_order_items', 'shipping_cost_total')
    if _column_exists(conn, 'proxy_order_items', 'shipping_cost_per_item'):
        op.drop_column('proxy_order_items', 'shipping_cost_per_item')

    # Remove new columns from proxy_orders
    if _column_exists(conn, 'proxy_orders', 'shipping_cost_difference'):
        op.drop_column('proxy_orders', 'shipping_cost_difference')
    if _column_exists(conn, 'proxy_orders', 'shipping_cost_declared'):
        op.drop_column('proxy_orders', 'shipping_cost_declared')
    if _column_exists(conn, 'proxy_orders', 'shipping_cost_total'):
        op.drop_column('proxy_orders', 'shipping_cost_total')

    # Revert order_number format
    op.execute("""
        UPDATE proxy_orders
        SET order_number = CONCAT('SO/PROXY/', LPAD(
            CAST(SUBSTRING_INDEX(order_number, '/', -1) AS UNSIGNED), 5, '0'
        ))
        WHERE order_number LIKE 'PRX/%' AND order_number NOT LIKE 'PRX/PL/%'
    """)
    op.execute("""
        UPDATE proxy_orders
        SET order_number = CONCAT('SO/PL/', LPAD(
            CAST(SUBSTRING_INDEX(order_number, '/', -1) AS UNSIGNED), 5, '0'
        ))
        WHERE order_number LIKE 'PL/%' AND order_number NOT LIKE 'PRX/PL/%'
    """)

    # Revert status enum
    op.execute("""
        UPDATE proxy_orders SET status = 'nowe'
        WHERE status = 'zamowiono'
    """)
    op.execute("""
        UPDATE proxy_orders SET status = 'dostarczone_proxy'
        WHERE status = 'dostarczone_do_proxy'
    """)
    op.alter_column('proxy_orders', 'status',
                     type_=sa.Enum('nowe', 'oczekujace', 'dostarczone_proxy', 'w_drodze_polska',
                                   'urzad_celny', 'dostarczone_gom', 'anulowane',
                                   name='stock_order_status'),
                     existing_nullable=False,
                     server_default='nowe')

    # Rename column back
    if _column_exists(conn, 'proxy_order_items', 'proxy_order_id'):
        if _fk_exists(conn, 'proxy_order_items', 'proxy_order_items_proxy_order_id_fkey'):
            op.drop_constraint('proxy_order_items_proxy_order_id_fkey', 'proxy_order_items', type_='foreignkey')
        op.alter_column('proxy_order_items', 'proxy_order_id',
                         new_column_name='stock_order_id',
                         existing_type=sa.Integer(),
                         existing_nullable=False)
        op.create_foreign_key(
            'stock_order_items_ibfk_2',
            'proxy_order_items', 'proxy_orders',
            ['stock_order_id'], ['id'],
            ondelete='CASCADE'
        )

    # Rename tables back
    if _table_exists(conn, 'proxy_orders') and not _table_exists(conn, 'stock_orders'):
        op.rename_table('proxy_orders', 'stock_orders')
    if _table_exists(conn, 'proxy_order_items') and not _table_exists(conn, 'stock_order_items'):
        op.rename_table('proxy_order_items', 'stock_order_items')
