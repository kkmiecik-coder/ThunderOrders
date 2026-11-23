"""Import CSV: serwer nie przyjmuje ścieżki pliku od klienta.

Wcześniej /admin/imports/csv/start brał `temp_file_path` z JSON-a (sprawdzał
tylko os.path.exists), potem czytał ten plik, a sprzątanie starych importów
wołało na nim os.remove. Teraz klient przesyła tylko `temp_file_id` (UUID
z uploadu), ścieżkę buduje serwer, a wszystko spoza katalogu tymczasowego
jest odrzucane — także przy kasowaniu.
"""
import io
import os

import pytest


CSV_BODY = 'name,sku\nKubek,K-1\n'


@pytest.fixture
def temp_dir(app, tmp_path):
    d = tmp_path / 'csv_temp'
    d.mkdir()
    old = app.config.get('CSV_IMPORT_TEMP_DIR')
    app.config['CSV_IMPORT_TEMP_DIR'] = str(d)
    yield d
    app.config['CSV_IMPORT_TEMP_DIR'] = old


@pytest.fixture
def no_executor(monkeypatch):
    from extensions import executor
    submitted = []
    monkeypatch.setattr(executor, 'submit', lambda fn, *a, **kw: submitted.append(a))
    return submitted


@pytest.fixture
def outside_file(tmp_path):
    f = tmp_path / 'secret.txt'
    f.write_text('nie ruszać')
    return f


def _admin(db, make_user, login):
    u = make_user(role='admin')
    login(u)
    return u


def _upload(client):
    return client.post('/admin/imports/csv/upload',
                       data={'file': (io.BytesIO(CSV_BODY.encode()), 'produkty.csv')},
                       content_type='multipart/form-data')


def _start(client, **extra):
    body = {'column_mapping': {'name': 'name', 'sku': 'sku'}, 'total_rows': 1,
            'filename': 'produkty.csv'}
    body.update(extra)
    return client.post('/admin/imports/csv/start', json=body)


def test_upload_saves_outside_static_and_returns_only_id(
        client, db, make_user, login, temp_dir):
    _admin(db, make_user, login)
    r = _upload(client)
    data = r.get_json()
    assert r.status_code == 200 and data['success'] is True
    assert 'temp_path' not in data
    files = os.listdir(temp_dir)
    assert len(files) == 1
    assert data['temp_file_id'] in files[0]


def test_default_temp_dir_is_not_public_static(app):
    from modules.imports import temp_files
    with app.app_context():
        app.config.pop('CSV_IMPORT_TEMP_DIR', None)
        d = temp_files.get_temp_dir()
    static_dir = os.path.realpath(os.path.join(app.root_path, 'static'))
    assert not d.startswith(static_dir + os.sep)


def test_start_ignores_client_supplied_path(
        client, db, make_user, login, temp_dir, no_executor, outside_file):
    from modules.imports.models import CsvImport
    _admin(db, make_user, login)
    r = _start(client, temp_file_path=str(outside_file))
    assert r.status_code == 400
    assert CsvImport.query.count() == 0
    assert no_executor == []


@pytest.mark.parametrize('bad_id', ['../../etc/passwd', '/etc/passwd', 'abc',
                                    '12345678-1234-1234-1234-1234567890ab/../x', None, 5])
def test_start_rejects_bad_temp_file_id(
        client, db, make_user, login, temp_dir, no_executor, bad_id):
    from modules.imports.models import CsvImport
    _admin(db, make_user, login)
    r = _start(client, temp_file_id=bad_id)
    assert r.status_code == 400
    assert CsvImport.query.count() == 0


def test_start_rejects_other_users_file(
        client, db, make_user, login, temp_dir, no_executor):
    from modules.imports.models import CsvImport
    _admin(db, make_user, login)
    temp_id = _upload(client).get_json()['temp_file_id']
    other = make_user(role='admin')
    login(other)
    r = _start(client, temp_file_id=temp_id)
    assert r.status_code == 400
    assert CsvImport.query.count() == 0


def test_start_with_server_issued_id_works(
        client, db, make_user, login, temp_dir, no_executor):
    from modules.imports.models import CsvImport
    _admin(db, make_user, login)
    temp_id = _upload(client).get_json()['temp_file_id']
    r = _start(client, temp_file_id=temp_id)
    assert r.status_code == 200, r.get_json()
    imp = CsvImport.query.one()
    assert os.path.dirname(os.path.realpath(imp.temp_file_path)) == os.path.realpath(temp_dir)
    assert os.path.exists(imp.temp_file_path)
    assert len(no_executor) == 1


def test_old_import_cleanup_never_deletes_outside_temp_dir(
        client, db, make_user, login, temp_dir, no_executor, outside_file):
    from modules.imports.models import CsvImport
    u = _admin(db, make_user, login)
    # 16 starych importów; najstarszy (offset 15) wskazuje plik poza katalogiem tymczasowym
    from datetime import timedelta
    from utils.timeutil import utcnow
    now = utcnow()
    for i in range(16):
        db.session.add(CsvImport(filename=f'{i}.csv', user_id=u.id, total_rows=1,
                                 status='completed', column_mapping={},
                                 temp_file_path=str(outside_file) if i == 15 else None,
                                 created_at=now - timedelta(minutes=i + 1)))
    db.session.commit()
    temp_id = _upload(client).get_json()['temp_file_id']
    r = _start(client, temp_file_id=temp_id)
    assert r.status_code == 200
    assert outside_file.exists()


def test_processor_refuses_path_outside_temp_dir(app, db, make_user, temp_dir, outside_file):
    from modules.imports.models import CsvImport
    from modules.imports.csv_processor import _process_csv_import_internal
    u = make_user(role='admin')
    imp = CsvImport(filename='x.csv', user_id=u.id, total_rows=1, status='pending',
                    column_mapping={'name': 'name'}, error_log=[],
                    temp_file_path=str(outside_file))
    db.session.add(imp)
    db.session.commit()

    _process_csv_import_internal(imp.id)

    db.session.refresh(imp)
    assert imp.status == 'failed'
    assert imp.successful_rows in (0, None)
    assert outside_file.exists()


def test_safe_remove_only_inside_temp_dir(app, temp_dir, outside_file):
    from modules.imports import temp_files
    inside = temp_dir / '1_x.csv'
    inside.write_text('a')
    with app.app_context():
        assert temp_files.safe_remove(str(outside_file)) is False
        assert temp_files.safe_remove(str(temp_dir / '..' / 'secret.txt')) is False
        assert temp_files.safe_remove(str(inside)) is True
    assert outside_file.exists()
    assert not inside.exists()
