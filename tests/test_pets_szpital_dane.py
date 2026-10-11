"""Spec v3 §4.2–4.3: kolumny szpitala i skórki, konfiguracja pets_hospital, formularz admina."""
import json

from tests.test_pets_admin import PELNY_FORMULARZ, _admin


def test_model_ma_kolumny_szpitala_i_skorki():
    from modules.pets.models import EGG_SKINS, EVENT_TYPES, PRUNABLE_EVENT_TYPES, Pet
    kol = {c.name: c for c in Pet.__table__.columns}
    for nazwa in ('hospital_since', 'hospital_healed_at', 'hospital_ready_notified_at'):
        assert kol[nazwa].nullable is True
    assert kol['egg_skin'].nullable is False
    assert EGG_SKINS == ('kropki', 'niebo', 'laczka', 'paski', 'laty')
    assert {'admit', 'discharge'} <= set(EVENT_TYPES)
    assert not ({'admit', 'discharge'} & set(PRUNABLE_EVENT_TYPES))


def test_konfiguracja_szpitala_domyslna_i_z_settings(db):
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    assert PetConfig().hospital == {'hours': 8, 'floor': 60, 'wait_hours': 24}
    Settings.set_value('pets_hospital', json.dumps({'hours': 12, 'wait_hours': 0}), type='json')
    db.session.commit()
    cfg = PetConfig.load(force=True)
    assert cfg.hospital == {'hours': 12, 'floor': 60, 'wait_hours': 0}      # wait_hours 0 legalne
    Settings.set_value('pets_hospital', json.dumps({'hours': 999}), type='json')
    db.session.commit()
    assert PetConfig.load(force=True).hospital['hours'] == 8                  # > 168 → domyślne


def test_formularz_admina_ma_pola_szpitala_bez_leczenia(client, login, make_user, db):
    _admin(make_user, login)
    html = client.get('/admin/pupile').data.decode()
    for pole in ('pets_hospital_hours', 'pets_hospital_floor', 'pets_hospital_wait_hours'):
        assert f'name="{pole}"' in html
    assert 'name="pets_actions_heal"' not in html and 'name="pets_actions_heal_cooldown_h"' not in html


def test_zapis_szpitala_z_formularza_i_limity(client, login, make_user, db):
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_hours='6',
                                                         pets_hospital_floor='70', pets_hospital_wait_hours='0'))
    assert r.status_code == 302
    assert PetConfig.load(force=True).hospital == {'hours': 6, 'floor': 70, 'wait_hours': 0}
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_hours='200'))
    assert r.status_code == 400 and 'pets_hospital_hours' in r.data.decode()
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_hospital_floor='0'))
    assert r.status_code == 400 and 'pets_hospital_floor' in r.data.decode()
