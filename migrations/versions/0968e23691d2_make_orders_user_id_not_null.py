"""make orders user_id not null

Revision ID: 0968e23691d2
Revises: 9261501f2307
Create Date: 2026-04-24 23:13:33.404300

Powód:
- Zrezygnowano z zamówień gości. place_order wymaga @login_required, więc
  user_id jest zawsze ustawiany przy tworzeniu zamówienia.
- FK orders_ibfk_1 miał ON DELETE SET NULL (dla usuniętych gości). To jest
  niepotrzebne — użytkownicy nigdy nie są fizycznie usuwani, tylko
  anonimizowani przez User.anonymize() (zachowywany jest rekord z emailem
  deleted_user_{id}@thunderorders.local).
- Zmieniamy FK na ON DELETE RESTRICT, spójnie z innymi FK w orders
  (fk_orders_packaging_material_id, fk_orders_packed_by, fk_orders_wms_session_id).

Safety:
- Przed upgrade: `SELECT COUNT(*) FROM orders WHERE user_id IS NULL;` musi
  zwrócić 0 (zweryfikowano 2026-04-24).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '0968e23691d2'
down_revision = '9261501f2307'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop stary FK z ON DELETE SET NULL
    op.drop_constraint('orders_ibfk_1', 'orders', type_='foreignkey')

    # 2. ALTER COLUMN na NOT NULL
    op.alter_column(
        'orders',
        'user_id',
        existing_type=mysql.INTEGER(display_width=11),
        nullable=False,
    )

    # 3. Dodaj FK na nowo z ON DELETE RESTRICT
    op.create_foreign_key(
        'orders_ibfk_1',
        'orders',
        'users',
        ['user_id'],
        ['id'],
        ondelete='RESTRICT',
        onupdate='RESTRICT',
    )


def downgrade():
    op.drop_constraint('orders_ibfk_1', 'orders', type_='foreignkey')

    op.alter_column(
        'orders',
        'user_id',
        existing_type=mysql.INTEGER(display_width=11),
        nullable=True,
    )

    op.create_foreign_key(
        'orders_ibfk_1',
        'orders',
        'users',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
        onupdate='RESTRICT',
    )
