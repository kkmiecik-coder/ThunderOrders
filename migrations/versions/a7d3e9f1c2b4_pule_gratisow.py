"""pule gratisow: kilka produktow-gratisow w jednej akcji + uwagi klientek

Revision ID: a7d3e9f1c2b4
Revises: f4c8d2a7b9e1
Create Date: 2026-11-17

Każda istniejąca akcja dostaje jedną pulę z dotychczasowym produktem-gratisem; ilości
z gift_card_types.quantity przechodzą do gift_pool_stock, a przydziały dostają pool_id.
Downgrade przenosi dane z PIERWSZEJ puli akcji z powrotem (pozostałe pule giną).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7d3e9f1c2b4'
down_revision = 'f4c8d2a7b9e1'
branch_labels = None
depends_on = None


def _fk_name(table, column):
    """Nazwa klucza obcego na kolumnie (MariaDB nadaje je sama, np. gift_campaigns_ibfk_1)."""
    row = op.get_bind().execute(sa.text(
        "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c "
        "AND REFERENCED_TABLE_NAME IS NOT NULL"
    ), {'t': table, 'c': column}).first()
    return row[0] if row else None


def upgrade():
    op.create_table(
        'gift_campaign_pools',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('bonus_product_id', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['campaign_id'], ['gift_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bonus_product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'bonus_product_id', name='uq_gift_campaign_pool'),
    )
    op.create_table(
        'gift_pool_stock',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pool_id', sa.Integer(), nullable=False),
        sa.Column('card_type_id', sa.Integer(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['pool_id'], ['gift_campaign_pools.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['card_type_id'], ['gift_card_types.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pool_id', 'card_type_id', name='uq_gift_pool_stock'),
    )
    op.add_column('gift_participants', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('gift_assignments', sa.Column('pool_id', sa.Integer(), nullable=True))

    # --- dane: jedna pula na istniejącą akcję ---
    op.execute(
        "INSERT INTO gift_campaign_pools (campaign_id, bonus_product_id, sort_order) "
        "SELECT id, bonus_product_id, 0 FROM gift_campaigns"
    )
    op.execute(
        "INSERT INTO gift_pool_stock (pool_id, card_type_id, quantity) "
        "SELECT p.id, t.id, t.quantity FROM gift_card_types t "
        "JOIN gift_campaign_pools p ON p.campaign_id = t.campaign_id"
    )
    op.execute(
        "UPDATE gift_assignments a JOIN gift_campaign_pools p ON p.campaign_id = a.campaign_id "
        "SET a.pool_id = p.id"
    )

    op.alter_column('gift_assignments', 'pool_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key('fk_gift_assignments_pool', 'gift_assignments', 'gift_campaign_pools',
                          ['pool_id'], ['id'], ondelete='CASCADE')

    fk = _fk_name('gift_campaigns', 'bonus_product_id')
    if fk:
        op.drop_constraint(fk, 'gift_campaigns', type_='foreignkey')
    op.drop_column('gift_campaigns', 'bonus_product_id')
    op.drop_column('gift_card_types', 'quantity')


def downgrade():
    op.add_column('gift_card_types', sa.Column('quantity', sa.Integer(), nullable=True))
    op.add_column('gift_campaigns', sa.Column('bonus_product_id', sa.Integer(), nullable=True))

    # Pierwsza pula akcji (najmniejszy sort_order, potem id) wraca jako jedyny gratis.
    first_pool = (
        "SELECT p.id FROM gift_campaign_pools p WHERE p.campaign_id = {cid} "
        "ORDER BY p.sort_order, p.id LIMIT 1"
    )
    op.execute(
        "UPDATE gift_campaigns c SET c.bonus_product_id = ("
        "SELECT p.bonus_product_id FROM gift_campaign_pools p WHERE p.campaign_id = c.id "
        "ORDER BY p.sort_order, p.id LIMIT 1)"
    )
    op.execute(
        "UPDATE gift_card_types t SET t.quantity = ("
        "SELECT s.quantity FROM gift_pool_stock s WHERE s.card_type_id = t.id AND s.pool_id = ("
        + first_pool.format(cid='t.campaign_id') + "))"
    )
    # Przydziały z pozostałych pul nie mają już gdzie wrócić.
    op.execute(
        "DELETE a FROM gift_assignments a WHERE a.pool_id <> ("
        + first_pool.format(cid='a.campaign_id') + ")"
    )
    op.create_foreign_key(None, 'gift_campaigns', 'products', ['bonus_product_id'], ['id'], ondelete='SET NULL')

    op.drop_constraint('fk_gift_assignments_pool', 'gift_assignments', type_='foreignkey')
    op.drop_column('gift_assignments', 'pool_id')
    op.drop_column('gift_participants', 'notes')
    op.drop_table('gift_pool_stock')
    op.drop_table('gift_campaign_pools')
