"""Make bonus FK nullable with SET NULL ondelete

Revision ID: b15560d41eae
Revises: 19e2e3d860a0
Create Date: 2026-03-07 02:05:49.402472

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b15560d41eae'
down_revision = '19e2e3d860a0'
branch_labels = None
depends_on = None


def upgrade():
    # ExclusiveSetBonus.bonus_product_id: NOT NULL -> nullable, ondelete SET NULL
    with op.batch_alter_table('exclusive_set_bonuses', schema=None) as batch_op:
        batch_op.alter_column('bonus_product_id',
                              existing_type=sa.Integer(),
                              nullable=True)
        batch_op.drop_constraint('exclusive_set_bonuses_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(
            'exclusive_set_bonuses_ibfk_1',
            'products', ['bonus_product_id'], ['id'],
            ondelete='SET NULL'
        )

    # ExclusiveSetBonusRequiredProduct.product_id: NOT NULL -> nullable, ondelete SET NULL
    with op.batch_alter_table('exclusive_set_bonus_required_products', schema=None) as batch_op:
        batch_op.alter_column('product_id',
                              existing_type=sa.Integer(),
                              nullable=True)
        batch_op.drop_constraint('exclusive_set_bonus_required_products_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(
            'exclusive_set_bonus_required_products_ibfk_2',
            'products', ['product_id'], ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    # Revert ExclusiveSetBonusRequiredProduct.product_id
    with op.batch_alter_table('exclusive_set_bonus_required_products', schema=None) as batch_op:
        batch_op.drop_constraint('exclusive_set_bonus_required_products_ibfk_2', type_='foreignkey')
        batch_op.create_foreign_key(
            'exclusive_set_bonus_required_products_ibfk_2',
            'products', ['product_id'], ['id']
        )
        batch_op.alter_column('product_id',
                              existing_type=sa.Integer(),
                              nullable=False)

    # Revert ExclusiveSetBonus.bonus_product_id
    with op.batch_alter_table('exclusive_set_bonuses', schema=None) as batch_op:
        batch_op.drop_constraint('exclusive_set_bonuses_ibfk_1', type_='foreignkey')
        batch_op.create_foreign_key(
            'exclusive_set_bonuses_ibfk_1',
            'products', ['bonus_product_id'], ['id']
        )
        batch_op.alter_column('bonus_product_id',
                              existing_type=sa.Integer(),
                              nullable=False)
