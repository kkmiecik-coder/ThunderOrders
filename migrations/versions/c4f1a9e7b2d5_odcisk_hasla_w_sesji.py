"""Kolumny do unieważniania sesji po zmianie hasła i cooldownu linku resetu

Revision ID: c4f1a9e7b2d5
Revises: b8e4f2a6d1c3
Create Date: 2026-11-22
"""
from alembic import op
import sqlalchemy as sa


revision = 'c4f1a9e7b2d5'
down_revision = 'b8e4f2a6d1c3'
branch_labels = None
depends_on = None


def upgrade():
    # Obie kolumny NULL dla istniejących kont: NULL w password_changed_at oznacza
    # „hasło nie zmieniane od wdrożenia" — stare sesje działają dalej (nikt nie zostaje wylogowany).
    op.add_column('users', sa.Column('password_reset_sent_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'password_reset_sent_at')
