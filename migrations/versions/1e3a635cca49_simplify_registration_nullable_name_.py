"""Simplify registration: nullable name/phone, add profile_completed

Revision ID: 1e3a635cca49
Revises: 6e68897ebcd7
Create Date: 2026-03-03 21:27:48.188159

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1e3a635cca49'
down_revision = '6e68897ebcd7'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Zmień first_name na nullable
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('first_name',
               existing_type=sa.String(length=100),
               nullable=True)

    # 2. Zmień last_name na nullable
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('last_name',
               existing_type=sa.String(length=100),
               nullable=True)

    # 3. Zmień phone na nullable
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('phone',
               existing_type=sa.String(length=20),
               nullable=True)

    # 4. Dodaj kolumnę profile_completed
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('profile_completed', sa.Boolean(),
                                       nullable=False, server_default=sa.text('0')))

    # 5. Ustaw profile_completed=TRUE dla istniejących użytkowników z uzupełnionymi danymi
    op.execute(
        "UPDATE users SET profile_completed = 1 "
        "WHERE first_name IS NOT NULL AND first_name != '' AND email_verified = 1"
    )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('profile_completed')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('phone',
               existing_type=sa.String(length=20),
               nullable=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('last_name',
               existing_type=sa.String(length=100),
               nullable=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('first_name',
               existing_type=sa.String(length=100),
               nullable=False)
