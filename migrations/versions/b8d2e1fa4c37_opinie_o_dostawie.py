"""Tabela opinii o dostawie (task 869efhwph)

Revision ID: b8d2e1fa4c37
Revises: a7c1d0e93b21
"""
from alembic import op
import sqlalchemy as sa

revision = 'b8d2e1fa4c37'
down_revision = 'a7c1d0e93b21'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'delivery_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('shipping_request_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.SmallInteger(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['shipping_request_id'], ['shipping_requests.id'],
                                name='fk_delivery_reviews_shipping_request',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name='fk_delivery_reviews_user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('shipping_request_id', name='uq_delivery_reviews_request'),
    )
    op.create_index('ix_delivery_reviews_user_id', 'delivery_reviews', ['user_id'])


def downgrade():
    # Bez osobnego drop_index: ix_delivery_reviews_user_id podtrzymuje klucz obcy
    # fk_delivery_reviews_user, a MariaDB odmawia usunięcia takiego indeksu
    # („Cannot drop index … needed in a foreign key constraint"). drop_table usuwa
    # indeksy i klucze obce razem z tabelą. Znana pułapka tego repozytorium.
    op.drop_table('delivery_reviews')
