"""Pupile (tamagotchi): tabele pet_profiles/pets/pet_events, preferencja pet_updates,
kategoria odznak 'pets'

Revision ID: f3e9a1c7b2d4
Revises: dde1a45a7d87
Create Date: 2026-10-11 12:00:00.000000

Spec: docs/superpowers/specs/2026-10-10-pupile-tamagotchi-design.md §3.3
"""
from alembic import op
import sqlalchemy as sa

revision = 'f3e9a1c7b2d4'
down_revision = 'dde1a45a7d87'
branch_labels = None
depends_on = None

KATEGORIE_STARE = ('orders', 'collection', 'loyalty', 'speed', 'exclusive',
                   'social', 'financial', 'profile', 'special')
KATEGORIE_NOWE = KATEGORIE_STARE + ('pets',)


def _enum_sql(wartosci):
    return 'ENUM(' + ', '.join(f"'{w}'" for w in wartosci) + ')'


def upgrade():
    # Kolejność: pets -> pet_profiles (FK companion_pet_id -> pets) -> pet_events
    op.create_table(
        'pets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('egg', 'alive', 'dead', 'merged', name='pet_status'), nullable=False),
        sa.Column('species', sa.String(length=32), nullable=True),
        sa.Column('name', sa.String(length=20), nullable=True),
        sa.Column('egg_source', sa.Enum('start', 'monthly', 'rescue', 'granted', name='pet_egg_source'), nullable=False),
        sa.Column('egg_hours', sa.SmallInteger(), nullable=False),
        sa.Column('egg_progress_sec', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('egg_progress_at', sa.DateTime(), nullable=False),
        sa.Column('boost_until', sa.DateTime(), nullable=True),
        sa.Column('egg_ready_notified_at', sa.DateTime(), nullable=True),
        sa.Column('hatched_at', sa.DateTime(), nullable=True),
        sa.Column('merged_into_pet_id', sa.Integer(), nullable=True),
        sa.Column('hunger', sa.Float(), nullable=False),
        sa.Column('fun', sa.Float(), nullable=False),
        sa.Column('clean', sa.Float(), nullable=False),
        sa.Column('health', sa.Float(), nullable=False),
        sa.Column('state_at', sa.DateTime(), nullable=False),
        sa.Column('awake_until', sa.DateTime(), nullable=True),
        sa.Column('stars', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('care_days', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_care_date', sa.Date(), nullable=True),
        sa.Column('last_heal_at', sa.DateTime(), nullable=True),
        sa.Column('notify_level', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('died_at', sa.DateTime(), nullable=True),
        sa.Column('death_notified_at', sa.DateTime(), nullable=True),
        sa.Column('rescue_egg_claimed_at', sa.DateTime(), nullable=True),
        sa.Column('rescue_reminder_sent_at', sa.DateTime(), nullable=True),
        sa.Column('lights_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_light_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['merged_into_pet_id'], ['pets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pets_user_status', 'pets', ['user_id', 'status'], unique=False)

    op.create_table(
        'pet_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('companion_pet_id', sa.Integer(), nullable=True),
        sa.Column('companion_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('dupes_in_row', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('start_egg_claimed_at', sa.DateTime(), nullable=False),
        sa.Column('last_monthly_egg_at', sa.DateTime(), nullable=False),
        sa.Column('monthly_notified_at', sa.DateTime(), nullable=True),
        sa.Column('granted_eggs_pending', sa.SmallInteger(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['companion_pet_id'], ['pets.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_pet_profiles_user_id'),
    )

    op.create_table(
        'pet_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pet_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pet_id'], ['pets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pet_events_pet_type_created', 'pet_events', ['pet_id', 'type', 'created_at'], unique=False)
    op.create_index('ix_pet_events_user_created', 'pet_events', ['user_id', 'created_at'], unique=False)

    # Preferencja powiadomień o pupilach (domyślnie włączona dla wszystkich)
    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pet_updates', sa.Boolean(), nullable=False,
                                      server_default=sa.text('1')))

    # Enum kategorii odznak: MariaDB wymaga jawnego ALTER (jak w 405efca8e619);
    # SQLite (testy, lokalny podgląd) nie zna MODIFY, a tam schemat powstaje z modeli.
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute('ALTER TABLE achievement MODIFY category ' + _enum_sql(KATEGORIE_NOWE) + ' NOT NULL')


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        # Odznaki z nowej kategorii nie mogą zostać w enumie bez tej wartości
        op.execute("UPDATE achievement SET category = 'special' WHERE category = 'pets'")
        op.execute('ALTER TABLE achievement MODIFY category ' + _enum_sql(KATEGORIE_STARE) + ' NOT NULL')

    with op.batch_alter_table('notification_preferences', schema=None) as batch_op:
        batch_op.drop_column('pet_updates')

    # Bez osobnego drop_index: MariaDB nie pozwala zdjąć indeksu podtrzymującego FK,
    # a drop_table usuwa indeksy razem z tabelą. Kolejność odwrotna do FK.
    op.drop_table('pet_events')
    op.drop_table('pet_profiles')
    op.drop_table('pets')
