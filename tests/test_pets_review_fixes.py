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
