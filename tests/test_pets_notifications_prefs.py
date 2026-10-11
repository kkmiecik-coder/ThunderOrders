"""Preferencja „Pupile" (pet_updates): API preferencji + karta w profilu widoczna bez pusha."""
from flask import url_for


def _wlacz_funkcje(db):
    from modules.auth.models import Settings
    from modules.pets.config import reset_feature_cache
    Settings.set_value('pets_enabled', 'true', type='boolean')
    Settings.set_value('pets_rollout_pct', 100, type='integer')
    db.session.commit()
    reset_feature_cache()


def test_get_preferences_domyslnie_ma_pet_updates(client, login, make_user):
    user = make_user()
    login(user)
    r = client.get('/notifications/preferences')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['pet_updates'] is True
    assert dane['sale_date_changes'] is True and dane['order_supplier_ordered'] is True


def test_post_preferences_zapisuje_pet_updates(client, login, make_user, db):
    from modules.notifications.models import NotificationPreference
    user = make_user()
    login(user)
    r = client.post('/notifications/preferences', json={'pet_updates': False})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert NotificationPreference.query.filter_by(user_id=user.id).one().pet_updates is False
    assert client.get('/notifications/preferences').get_json()['pet_updates'] is False


def test_karta_pupili_w_profilu_tylko_gdy_funkcja_dostepna(app, client, login, make_user, db):
    user = make_user(profile_completed=True)
    login(user)
    with app.test_request_context():
        url = url_for('profile.index')
    r = client.get(url)
    assert r.status_code == 200 and b'petUpdatesToggle' not in r.data
    _wlacz_funkcje(db)
    r = client.get(url)
    assert r.status_code == 200 and b'petUpdatesToggle' in r.data
    assert b'pet-updates-toggle.js' in r.data
