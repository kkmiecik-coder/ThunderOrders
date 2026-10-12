"""Panel /admin/pupile (spec §5): role, zapis ustawień z walidacją, statystyki, przyznanie jajka."""
from tests.pets_helpers import zaloz_profil, zaloz_pupila

PELNY_FORMULARZ = {
    'pets_enabled': 'on', 'pets_rollout_pct': '25', 'pets_jokes_enabled': 'on',
    'pets_decay_hours_hunger': '20', 'pets_decay_hours_fun': '30', 'pets_decay_hours_clean': '48',
    'pets_night_start': '22', 'pets_night_end': '7', 'pets_night_factor': '0.25',
    'pets_health_drop_hours': '72', 'pets_health_regen_hours': '24',
    'pets_egg_hours': '168', 'pets_start_egg_hours': '48',
    'pets_boost_hours': '8', 'pets_boost_factor': '2',
    'pets_monthly_days': '30', 'pets_rescue_hours': '0', 'pets_rescue_reminder_days': '7',
    'pets_pity_after': '2', 'pets_max_stars': '5',
    'pets_stage_days_child': '24', 'pets_stage_days_adult': '80',
    'pets_actions_feed': '50', 'pets_actions_play': '50',
    'pets_actions_allow_below': '80',
    'pets_actions_pat_gain': '0.25', 'pets_actions_pat_per_hour': '60',
    'pets_actions_wake_penalty': '10', 'pets_actions_awake_minutes': '20',
    'pets_hospital_hours': '8', 'pets_hospital_floor': '60', 'pets_hospital_wait_hours': '24',
}


def _admin(make_user, login, role='admin'):
    u = make_user(role=role, profile_completed=True)
    login(u)
    return u


def test_role_required(client, login, make_user):
    login(make_user(role='client', profile_completed=True))
    assert client.get('/admin/pupile').status_code == 403
    assert client.post('/admin/pupile/ustawienia', data={}).status_code == 403
    assert client.post('/admin/pupile/przyznaj', json={'user_id': 1}).status_code == 403


def test_mod_ma_dostep(client, login, make_user):
    _admin(make_user, login, role='mod')
    assert client.get('/admin/pupile').status_code == 200


def test_index_renderuje_formularz_i_statystyki(client, login, make_user, db):
    _admin(make_user, login)
    r = client.get('/admin/pupile')
    html = r.data.decode()
    assert r.status_code == 200
    for pole in PELNY_FORMULARZ:
        assert f'name="{pole}"' in html, pole
    assert 'Profile' in html and 'css/pages/admin/pets.css' in html and 'js/pages/admin/pets.js' in html


def test_zapis_ustawien_poprawny(client, login, make_user, db):
    from modules.admin.models import ActivityLog
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig, feature_flags, reset_feature_cache
    admin = _admin(make_user, login)
    r = client.post('/admin/pupile/ustawienia', data=PELNY_FORMULARZ, follow_redirects=False)
    assert r.status_code == 302
    reset_feature_cache()
    assert feature_flags() == (True, 25)
    cfg = PetConfig.load(force=True)
    assert cfg.decay_hours['hunger'] == 20 and cfg.night['start'] == 22 and cfg.actions['pat_gain'] == 0.25
    assert Settings.query.filter_by(key='pets_decay_hours').one().updated_by == admin.id
    assert ActivityLog.query.filter_by(action='pets_settings_updated').count() == 1


def test_wylaczenie_checkboxa_zapisuje_false(client, login, make_user, db):
    from modules.pets.config import feature_flags, reset_feature_cache
    _admin(make_user, login)
    dane = dict(PELNY_FORMULARZ)
    del dane['pets_enabled']          # niezaznaczony checkbox nie trafia do formularza
    assert client.post('/admin/pupile/ustawienia', data=dane).status_code == 302
    reset_feature_cache()
    assert feature_flags() == (False, 25)


def test_ustawienia_bledne_pole_nic_nie_zapisuje(client, login, make_user, db):
    """Review Focus 3: jedno złe pole = zero zapisów, komunikat przy polu."""
    from modules.auth.models import Settings
    _admin(make_user, login)
    dane = dict(PELNY_FORMULARZ, pets_rollout_pct='150', pets_night_factor='1.5')
    r = client.post('/admin/pupile/ustawienia', data=dane)
    html = r.data.decode()
    assert r.status_code == 400 and 'pets_rollout_pct' in html and 'pets_night_factor' in html
    assert Settings.query.filter(Settings.key.like('pets_%')).count() == 0


def test_szukaj_i_przyznaj_jajko(client, login, make_user, db):
    from modules.admin.models import ActivityLog
    from modules.pets.models import PetProfile
    _admin(make_user, login)
    gracz = make_user(email='gracz@example.com', first_name='Ola')
    zaloz_profil(gracz)
    zaloz_pupila(gracz, name='Mruczek')
    r = client.get('/admin/pupile/szukaj?q=gracz')
    wynik = r.get_json()
    assert r.status_code == 200 and wynik[0]['email'] == 'gracz@example.com' and wynik[0]['pets'][0]['name'] == 'Mruczek'
    assert wynik[0]['granted_pending'] == 0
    r = client.post('/admin/pupile/przyznaj', json={'user_id': gracz.id})
    assert r.status_code == 200 and r.get_json() == {'ok': True, 'granted_pending': 1}
    assert PetProfile.query.filter_by(user_id=gracz.id).one().granted_eggs_pending == 1
    assert ActivityLog.query.filter_by(action='pet_egg_granted', entity_id=gracz.id).count() == 1


def test_szukaj_za_krotkie_zapytanie_pusta_lista(client, login, make_user, db):
    _admin(make_user, login)
    r = client.get('/admin/pupile/szukaj?q=a')
    assert r.status_code == 200 and r.get_json() == []


def test_przyznaj_bez_profilu_czytelny_blad(client, login, make_user, db):
    """Review Focus 4: użytkownik bez startowego jajka → 409 z komunikatem, nie 500."""
    _admin(make_user, login)
    nowy = make_user()
    r = client.post('/admin/pupile/przyznaj', json={'user_id': nowy.id})
    assert r.status_code == 409 and 'startowego' in r.get_json()['message']
    r = client.post('/admin/pupile/przyznaj', json={'user_id': 999999})
    assert r.status_code == 404


def test_wylacznik_zartow_zapisuje_sie_z_formularza_wlacznika(client, login, make_user, db):
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    dane = {'scope': 'switch', 'pets_enabled': 'on', 'pets_rollout_pct': '25'}   # bez pets_jokes_enabled = odznaczony
    assert client.post('/admin/pupile/ustawienia', data=dane).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is False
    dane['pets_jokes_enabled'] = 'on'
    assert client.post('/admin/pupile/ustawienia', data=dane).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is True


def test_zapis_liczb_gry_nie_rusza_wylacznika_zartow(client, login, make_user, db):
    """Review Focus 2: formularz „Liczby gry” nie zawiera checkboxa żartów — nie może go wyzerować."""
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    Settings.set_value('pets_jokes_enabled', 'true', type='boolean')
    db.session.commit()
    liczby = {k: v for k, v in PELNY_FORMULARZ.items()
              if k not in ('pets_enabled', 'pets_rollout_pct', 'pets_jokes_enabled')}
    assert client.post('/admin/pupile/ustawienia', data=liczby).status_code == 302
    assert PetConfig.load(force=True).jokes_enabled is True
