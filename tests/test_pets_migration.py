"""Migracja pupili uruchamiana na świeżym SQLite — parytet z modelami i odwracalność.

Nie da się tu odpalić całego łańcucha migracji (15 starszych plików ma surowy SQL dla
MariaDB bez guardu), więc budujemy tylko tabele-zależności z modeli i uruchamiamy
wyłącznie upgrade()/downgrade() tej jednej rewizji przez Operations.context.
"""
import importlib.util
import pathlib

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

REWIZJA = 'f3e9a1c7b2d4'
PLIK = pathlib.Path('migrations/versions') / f'{REWIZJA}_pupile_fundament.py'


def _zaladuj_migracje():
    spec = importlib.util.spec_from_file_location('migracja_pupile', PLIK)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def silnik(app):
    """Osobny SQLite w stanie „sprzed migracji" dla tabel, których migracja dotyka (FK / ALTER).

    Celowo NIE z modeli:
    - model NotificationPreference ma już `pet_updates` (Task 2), a migracja ma tę kolumnę dodać;
    - na SQLite `batch_alter_table` z `server_default=sa.text(...)` przebudowuje tabelę przez
      refleksję, która idzie po FK (notification_preferences -> users -> avatars -> ...),
      więc tabele z modeli wymagałyby całego schematu aplikacji.
    Nowych tabel pupili też nie tworzymy: zrobi to migracja.
    """
    engine = sa.create_engine('sqlite://')
    meta = sa.MetaData()
    sa.Table('users', meta, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('achievement', meta,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('category', sa.String(20), nullable=False))
    sa.Table('notification_preferences', meta,
             sa.Column('id', sa.Integer, primary_key=True),
             sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'),
                       nullable=False, unique=True),
             sa.Column('order_status_changes', sa.Boolean, nullable=False))
    meta.create_all(bind=engine)
    yield engine
    engine.dispose()


def _kolumny(insp, tabela):
    return {c['name']: c['nullable'] for c in insp.get_columns(tabela)}


def test_migracja_jest_jedyna_glowa():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config('migrations/alembic.ini')
    cfg.set_main_option('script_location', 'migrations')
    sd = ScriptDirectory.from_config(cfg)
    assert sd.get_heads() == [REWIZJA]
    assert sd.get_revision(REWIZJA).down_revision == 'dde1a45a7d87'


def test_upgrade_tworzy_tabele_zgodne_z_modelami(silnik):
    from modules.pets.models import Pet, PetProfile, PetEvent
    migracja = _zaladuj_migracje()
    with silnik.begin() as conn:
        assert 'pet_updates' not in _kolumny(sa.inspect(conn), 'notification_preferences')
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migracja.upgrade()
        insp = sa.inspect(conn)
        tabele = set(insp.get_table_names())
        assert {'pets', 'pet_profiles', 'pet_events'} <= tabele

        for model in (Pet, PetProfile, PetEvent):
            z_modelu = {c.name: c.nullable for c in model.__table__.columns}
            assert _kolumny(insp, model.__tablename__) == z_modelu, model.__tablename__

        indeksy = {i['name'] for i in insp.get_indexes('pets')}
        assert 'ix_pets_user_status' in indeksy
        indeksy_zdarzen = {i['name'] for i in insp.get_indexes('pet_events')}
        assert {'ix_pet_events_pet_type_created', 'ix_pet_events_user_created'} <= indeksy_zdarzen

        assert 'pet_updates' in _kolumny(insp, 'notification_preferences')


def test_downgrade_odwraca_upgrade(silnik):
    migracja = _zaladuj_migracje()
    with silnik.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migracja.upgrade()
        with Operations.context(ctx):
            migracja.downgrade()
        insp = sa.inspect(conn)
        tabele = set(insp.get_table_names())
        assert not ({'pets', 'pet_profiles', 'pet_events'} & tabele)
        assert 'pet_updates' not in _kolumny(insp, 'notification_preferences')
