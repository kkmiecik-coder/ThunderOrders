"""Obrazki wychylania w panelu /admin/pupile (spec v3.2 §6.4–6.5): upload z przezroczystością, przełącz, usuń."""
import io
import os

import pytest
from PIL import Image


@pytest.fixture(autouse=True)
def _katalog_obrazkow(app, tmp_path):
    app.config['PETS_PEEK_UPLOAD_DIR'] = str(tmp_path)
    yield
    app.config.pop('PETS_PEEK_UPLOAD_DIR', None)


def _admin(make_user, login, role='admin'):
    u = make_user(role=role, profile_completed=True)
    login(u)
    return u


def _png(w=300, h=200, srodek=True):
    """Przezroczyste tło + nieprzezroczysty czerwony kwadrat pośrodku."""
    obraz = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if srodek:
        obraz.paste((255, 0, 0, 255), (w // 3, h // 3, 2 * w // 3, 2 * h // 3))
    buf = io.BytesIO()
    obraz.save(buf, 'PNG')
    buf.seek(0)
    return buf


def _wgraj(client, plik, nazwa='gwiazdka.png', **form):
    return client.post('/admin/pupile/obrazki', data={'image': (plik, nazwa), **form},
                       content_type='multipart/form-data')


def _flashe(client):
    with client.session_transaction() as sess:
        return [tresc for _kat, tresc in sess.get('_flashes', [])]


def test_upload_zapisuje_webp_z_przezroczystoscia(client, login, make_user, db, tmp_path):
    from modules.admin.models import ActivityLog
    from modules.pets.models import PetPeekImage
    admin = _admin(make_user, login)
    r = _wgraj(client, _png(), label='  Gwiazdka  ')
    assert r.status_code == 302
    obrazek = PetPeekImage.query.one()
    assert obrazek.filename.endswith('.webp') and obrazek.label == 'Gwiazdka'
    assert obrazek.is_active is True and obrazek.created_by == admin.id
    sciezka = tmp_path / obrazek.filename
    assert sciezka.exists()
    wynik = Image.open(sciezka).convert('RGBA')
    assert max(wynik.size) == 240
    assert wynik.getpixel((2, 2))[3] == 0            # tło zostało przezroczyste
    assert wynik.getpixel((wynik.width // 2, wynik.height // 2))[3] == 255
    assert ActivityLog.query.filter_by(action='pet_peek_image_added', entity_id=obrazek.id).count() == 1


def test_upload_malego_obrazka_nie_powieksza(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png(100, 80))
    wynik = Image.open(tmp_path / PetPeekImage.query.one().filename)
    assert wynik.size == (100, 80)


def test_upload_animowanego_gifa_bierze_pierwsza_klatke(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    klatki = [Image.new('RGB', (60, 60), kolor) for kolor in ('red', 'blue')]
    buf = io.BytesIO()
    klatki[0].save(buf, 'GIF', save_all=True, append_images=klatki[1:], duration=100, loop=0)
    buf.seek(0)
    assert _wgraj(client, buf, 'ruch.gif').status_code == 302
    wynik = Image.open(tmp_path / PetPeekImage.query.one().filename)
    assert getattr(wynik, 'n_frames', 1) == 1


@pytest.mark.parametrize('plik,nazwa,fragment', [
    (lambda: io.BytesIO(b'to nie jest obrazek'), 'a.png', 'uszkodzony'),
    (lambda: io.BytesIO(b'MZ'), 'wirus.exe', 'Dozwolone formaty'),
    (lambda: io.BytesIO(b'x' * (2 * 1024 * 1024 + 1)), 'duzy.png', 'za duży'),
    (lambda: io.BytesIO(b''), 'pusty.png', 'pusty'),
])
def test_upload_odrzuca_zle_pliki(client, login, make_user, db, tmp_path, plik, nazwa, fragment):
    """Review Focus 3: zły typ / uszkodzony / za duży / pusty — flash, brak rekordu, brak pliku."""
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    r = _wgraj(client, plik(), nazwa)
    assert r.status_code == 302
    assert PetPeekImage.query.count() == 0 and os.listdir(tmp_path) == []
    assert any(fragment in tresc for tresc in _flashe(client))


def test_upload_odrzuca_bombe_pikseli(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    buf = io.BytesIO()
    Image.new('RGB', (2001, 2001), 'white').save(buf, 'PNG')   # mały plik, ponad 4 mln pikseli
    buf.seek(0)
    _wgraj(client, buf, 'bomba.png')
    assert PetPeekImage.query.count() == 0 and os.listdir(tmp_path) == []
    assert any('pikseli' in tresc for tresc in _flashe(client))


def test_upload_bez_pliku(client, login, make_user, db):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    assert client.post('/admin/pupile/obrazki', data={}, content_type='multipart/form-data').status_code == 302
    assert PetPeekImage.query.count() == 0
    assert any('Wybierz plik' in tresc for tresc in _flashe(client))


def test_upload_limit_30(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    db.session.add_all([PetPeekImage(filename=f'{i}.webp') for i in range(30)])
    db.session.commit()
    _wgraj(client, _png())
    assert PetPeekImage.query.count() == 30 and os.listdir(tmp_path) == []
    assert any('limit' in tresc for tresc in _flashe(client))


def test_przelacz_i_usun_kasuje_plik(client, login, make_user, db, tmp_path):
    from modules.admin.models import ActivityLog
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png())
    obrazek = PetPeekImage.query.one()
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/przelacz').status_code == 302
    db.session.refresh(obrazek)
    assert obrazek.is_active is False
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/przelacz').status_code == 302
    db.session.refresh(obrazek)
    assert obrazek.is_active is True
    plik = tmp_path / obrazek.filename
    assert plik.exists()
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/usun').status_code == 302
    assert PetPeekImage.query.count() == 0 and not plik.exists()
    assert ActivityLog.query.filter_by(action='pet_peek_image_deleted').count() == 1


def test_usun_gdy_pliku_juz_nie_ma(client, login, make_user, db, tmp_path):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login)
    _wgraj(client, _png())
    obrazek = PetPeekImage.query.one()
    os.remove(tmp_path / obrazek.filename)
    assert client.post(f'/admin/pupile/obrazki/{obrazek.id}/usun').status_code == 302
    assert PetPeekImage.query.count() == 0


def test_nieznany_obrazek_404(client, login, make_user, db):
    _admin(make_user, login)
    assert client.post('/admin/pupile/obrazki/999/przelacz').status_code == 404
    assert client.post('/admin/pupile/obrazki/999/usun').status_code == 404


def test_klient_nie_ma_dostepu(client, login, make_user, db):
    login(make_user(role='client', profile_completed=True))
    assert client.post('/admin/pupile/obrazki', data={}).status_code == 403
    assert client.post('/admin/pupile/obrazki/1/przelacz').status_code == 403
    assert client.post('/admin/pupile/obrazki/1/usun').status_code == 403


def test_mod_moze_dodawac(client, login, make_user, db):
    from modules.pets.models import PetPeekImage
    _admin(make_user, login, role='mod')
    _wgraj(client, _png())
    assert PetPeekImage.query.count() == 1


def test_index_pokazuje_karte_i_miniature(client, login, make_user, db):
    _admin(make_user, login)
    _wgraj(client, _png(), label='Gwiazdka')
    html = client.get('/admin/pupile').data.decode()
    assert 'id="paPeekTitle"' in html and 'name="image"' in html and 'data-confirm' in html
    assert '/static/uploads/pet_peeks/' in html and 'Gwiazdka' in html
