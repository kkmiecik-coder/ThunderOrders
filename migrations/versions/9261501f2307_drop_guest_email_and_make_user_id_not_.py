"""drop guest_email and make user_id not null on offer_product_notifications

Revision ID: 9261501f2307
Revises: 373e67e06b3d
Create Date: 2026-04-24 23:13:12.920478

Powody:
- Zrezygnowano z subskrypcji powiadomień dla niezalogowanych użytkowników —
  endpoint subscribe_notification ma teraz @login_required, więc kolumna
  guest_email nie jest już zapisywana.
- user_id staje się wymagane, bo każda subskrypcja ma zalogowanego użytkownika.

Safety:
- Przed upgrade: `SELECT COUNT(*) FROM offer_product_notifications WHERE user_id IS NULL;`
  musi zwrócić 0. Jeśli są rekordy z NULL user_id (tylko guest_email), migracja
  padnie przy ALTER COLUMN SET NOT NULL. Takie rekordy należy wcześniej usunąć
  lub zbackfillować ręcznie.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '9261501f2307'
down_revision = '373e67e06b3d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('offer_product_notifications', schema=None) as batch_op:
        batch_op.drop_column('guest_email')
        batch_op.alter_column(
            'user_id',
            existing_type=mysql.INTEGER(display_width=11),
            nullable=False,
        )


def downgrade():
    with op.batch_alter_table('offer_product_notifications', schema=None) as batch_op:
        batch_op.alter_column(
            'user_id',
            existing_type=mysql.INTEGER(display_width=11),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column('guest_email', mysql.VARCHAR(length=255), nullable=True)
        )
