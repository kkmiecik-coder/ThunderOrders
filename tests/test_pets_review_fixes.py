"""Fix pass po recenzji końcowej (backend): widoczność odznak, walidacja panelu, limity, checkpoint konfiguracji."""
from datetime import timedelta

from tests.pets_helpers import zaloz_profil, zaloz_pupila
from tests.test_pets_admin import PELNY_FORMULARZ, _admin
from tests.test_pets_routes import _wlacz


def test_odznaki_pupili_niewidoczne_bez_funkcji(db, make_user):
    """Important 2: przed włączeniem flagi (i poza rolloutem) galeria nie pokazuje odznak kategorii pets."""
    from modules.achievements.seed import seed_achievements
    from modules.achievements.services import AchievementService
    seed_achievements()
    db.session.commit()
    user = make_user()
    kategorie = {a['category'] for a in AchievementService().get_user_achievements(user)}
    assert 'pets' not in kategorie
    _wlacz(db)
    lista = AchievementService().get_user_achievements(user)
    assert sum(1 for a in lista if a['category'] == 'pets') == 9


def test_walidacja_przyjmuje_godzine_0_w_nocy():
    """Important 3: spec §3.4 — 0 ≤ start,end ≤ 23; 0 nie jest „liczbą niedodatnią”."""
    from modules.pets.config import validate_settings
    dane = dict(PELNY_FORMULARZ, pets_night_start='0', pets_night_end='6')
    values, errors = validate_settings(dane)
    assert 'pets_night_start' not in errors and 'pets_night_end' not in errors and not errors
    dane = dict(PELNY_FORMULARZ, pets_night_start='22', pets_night_end='0')
    assert not validate_settings(dane)[1]


def test_wlacznik_zapisuje_sie_osobno_bez_liczb(client, login, make_user, db):
    """Important 3: awaryjne wyłączenie nie może zależeć od poprawności 28 pól liczbowych."""
    from modules.auth.models import Settings
    from modules.pets.config import feature_flags, reset_feature_cache
    _admin(make_user, login)
    Settings.set_value('pets_monthly_days', '0', type='integer')     # „zepsuta” wartość w bazie
    db.session.commit()
    r = client.post('/admin/pupile/ustawienia', data={'scope': 'switch', 'pets_rollout_pct': '0'})
    assert r.status_code == 302
    reset_feature_cache()
    assert feature_flags() == (False, 0)
    assert Settings.query.filter_by(key='pets_monthly_days').one().value == '0'   # reszta nietknięta


def test_limity_gorne_w_formularzu_i_w_konfiguracji(client, login, make_user, db):
    """Important 4: literówka admina nie może wysypać dashboardu (OverflowError z timedelta)."""
    from modules.auth.models import Settings
    from modules.pets.config import PetConfig
    _admin(make_user, login)
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_monthly_days='9999999999'))
    assert r.status_code == 400 and 'pets_monthly_days' in r.data.decode()
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_stage_days_child='90', pets_stage_days_adult='80'))
    assert r.status_code == 400 and 'pets_stage_days_child' in r.data.decode()
    # wiersz w bazie poza zakresem (np. wpisany ręcznie) → wartość domyślna, nie awaria
    Settings.set_value('pets_monthly_days', '9999999999', type='integer')
    Settings.set_value('pets_egg_hours', '99999', type='integer')
    db.session.commit()
    cfg = PetConfig.load(force=True)
    assert cfg.monthly_days == 30 and cfg.egg_hours == 168


def test_dashboard_nie_pada_gdy_widget_pupila_rzuca(client, login, make_user, db, monkeypatch):
    """Important 4: błąd w module pupili nie może zabrać klientowi dashboardu."""
    from modules.pets import service
    user = make_user(profile_completed=True)
    login(user)
    _wlacz(db)
    monkeypatch.setattr(service, 'state_for_user', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('awaria')))
    r = client.get('/client/dashboard')
    assert r.status_code == 200 and b'id="petsWidget"' not in r.data


def test_zapis_konfiguracji_przelicza_pupile_stara_konfiguracja(client, login, make_user, db):
    """Important 5: obniżenie tempa nie działa wstecz — stan każdego żywego pupila jest domykany
    starą konfiguracją w chwili zapisu (checkpoint), nowa liczy się od teraz."""
    from modules.auth.models import get_local_now
    from modules.pets.models import Pet
    from modules.pets.service import state_for_user
    _admin(make_user, login)
    gracz = make_user()
    zaloz_profil(gracz)
    teraz = get_local_now()
    pet = zaloz_pupila(gracz, fun=0.0, health=100.0, now=teraz - timedelta(hours=40))   # 40 h z paskiem na zerze
    r = client.post('/admin/pupile/ustawienia', data=dict(PELNY_FORMULARZ, pets_health_drop_hours='24', pets_night_start='0', pets_night_end='0'))
    assert r.status_code == 302
    db.session.expire_all()
    pet = db.session.get(Pet, pet.id)
    assert pet.status == 'alive' and pet.state_at >= teraz - timedelta(seconds=5)   # checkpoint zapisał stan „teraz”
    assert 0 < pet.health < 100                                                     # 40 h starym tempem (72 h) ≈ 44
    stan = state_for_user(gracz)
    assert stan['pets'] and stan['pets'][0]['id'] == pet.id and stan['pets'][0]['mood'] != 'krytyczny' or stan['pets'][0]['bars']['health'] > 0


# --- minory z recenzji A: walidacja wejścia, CSRF, koszt odznak, pet_adult_alive ---

def test_przyznaj_odrzuca_bool_jako_user_id(client, login, make_user, db):
    _admin(make_user, login)
    assert client.post('/admin/pupile/przyznaj', json={'user_id': True}).status_code == 400
    assert client.post('/admin/pupile/przyznaj', json={'user_id': '1; drop'}).status_code == 400


def test_towarzysz_enabled_i_imie_musza_miec_wlasciwy_typ(client, login, make_user, db):
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    r = client.post('/client/pupile/api/towarzysz', json={'pet_id': pet.id, 'enabled': 'false'})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'
    r = client.post(f'/client/pupile/api/{pet.id}/imie', json={'name': ['Mruczek']})
    assert r.status_code == 400


def test_csrf_chroni_api_i_panel(app, client, login, make_user, db, monkeypatch):
    """Spec §8: testy CSRF. Przy włączonej ochronie POST bez tokenu = 400 JSON (front pokazuje „odśwież stronę”)."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)
    user = make_user()
    login(user)
    _wlacz(db)
    zaloz_profil(user)
    pet = zaloz_pupila(user)
    r = client.post(f'/client/pupile/api/{pet.id}/akcja', json={'action': 'feed'})
    assert r.status_code == 400 and r.get_json()['error'] == 'bad_request'
    admin = make_user(role='admin', profile_completed=True)
    login(admin)
    r = client.post('/admin/pupile/przyznaj', json={'user_id': user.id})
    assert r.status_code == 400 and r.get_json()['ok'] is False
    r = client.post('/admin/pupile/ustawienia', data={'scope': 'switch', 'pets_rollout_pct': '5'})
    assert r.status_code == 400


def test_odznaki_sprawdzane_tylko_przy_pierwszej_opiece_dnia(db, make_user, monkeypatch):
    """Minor A: każda paczka pat robiła ~10 zapytań odznak; w perform_action zmienia się tylko care_days."""
    from datetime import timedelta
    from tests.pets_helpers import T0
    from modules.achievements.services import AchievementService
    from modules.pets.actions import perform_action
    wywolania = []
    monkeypatch.setattr(AchievementService, 'check_event', lambda self, user, ev, context=None: wywolania.append(ev) or [])
    user = make_user()
    zaloz_profil(user)
    pet = zaloz_pupila(user, hunger=20.0, fun=20.0)
    _wlacz(db)
    perform_action(user, pet.id, 'feed', now=T0 + timedelta(hours=1))
    perform_action(user, pet.id, 'play', now=T0 + timedelta(hours=2))
    assert wywolania == ['pet_event']


def test_adult_alive_pomija_odejscie_wyliczone(db, make_user):
    """Minor A: pupil 'alive' w bazie, ale martwy w symulacji (między przebiegami crona) nie liczy się jako dorosły."""
    from datetime import timedelta
    from tests.pets_helpers import T0
    from modules.achievements.checkers import get_metric_value
    from modules.pets.species import SPECIES_SLUGS
    user = make_user()
    zaloz_profil(user)
    dawno = T0 - timedelta(days=200)
    for slug in SPECIES_SLUGS[:7]:
        zaloz_pupila(user, species=slug, hatched_at=dawno, now=T0)
    # ósmy: dorosły, ale z paskiem na zerze od 10 dni → w symulacji odszedł
    zaloz_pupila(user, species=SPECIES_SLUGS[7], hatched_at=dawno, now=T0 - timedelta(days=10), hunger=0.0)
    assert get_metric_value(user, 'pet_adult_alive', {'threshold': 8}, {'now': T0}) == (7, False)


def test_formularz_liczb_bez_pol_wlacznika_zapisuje_sie(client, login, make_user, db):
    """Po rozdzieleniu formularzy „Liczby gry” nie zawierają pets_enabled/pets_rollout_pct — nie mogą być wymagane."""
    from modules.pets.config import PetConfig, feature_flags, reset_feature_cache
    _admin(make_user, login)
    _wlacz(db)                                       # flaga on, pct 100 — ma zostać nietknięta
    dane = {k: v for k, v in PELNY_FORMULARZ.items() if k not in ('pets_enabled', 'pets_rollout_pct')}
    dane['pets_decay_hours_hunger'] = '22'
    r = client.post('/admin/pupile/ustawienia', data=dane)
    assert r.status_code == 302
    reset_feature_cache()
    assert feature_flags() == (True, 100)
    assert PetConfig.load(force=True).decay_hours['hunger'] == 22
