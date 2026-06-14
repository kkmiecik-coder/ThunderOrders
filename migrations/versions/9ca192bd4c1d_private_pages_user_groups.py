"""private pages + user groups

Revision ID: 9ca192bd4c1d
Revises: e896e0208289
Create Date: 2026-06-14 22:24:24.825610

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9ca192bd4c1d'
down_revision = 'e896e0208289'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('user_group_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_group_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('added_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_group_id'], ['user_groups.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_group_id', 'user_id', name='unique_user_group_member')
    )
    op.create_table('offer_page_groups',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('offer_page_id', sa.Integer(), nullable=False),
    sa.Column('user_group_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['offer_page_id'], ['offer_pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_group_id'], ['user_groups.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_page_id', 'user_group_id', name='unique_offer_page_group')
    )
    op.create_table('offer_page_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('offer_page_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['offer_page_id'], ['offer_pages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_page_id', 'user_id', name='unique_offer_page_user')
    )
    with op.batch_alter_table('offer_pages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_private', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('offer_pages', schema=None) as batch_op:
        batch_op.drop_column('is_private')

    op.drop_table('offer_page_users')
    op.drop_table('offer_page_groups')
    op.drop_table('user_group_members')
    op.drop_table('user_groups')
