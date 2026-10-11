"""Globalny wyłącznik maila o pupilach w ustawieniach maili admina."""


def test_notify_pet_alert_zapisuje_sie_i_wylacza(client, login, make_user):
    from utils.email_manager import EmailManager
    admin = make_user(role='admin')
    login(admin)
    r = client.post('/admin/orders/settings/email-notifications', json={'toggles': {'notify_pet_alert': False}})
    assert r.status_code == 200, r.data
    EmailManager.clear_email_config_cache()
    assert EmailManager.is_email_enabled('notify_pet_alert') is False
    assert EmailManager.is_email_enabled('notify_pickup_reminder') is True   # reszta domyślnie True


def test_strona_ustawien_ma_przelacznik_pupili(client, login, make_user):
    admin = make_user(role='admin')
    login(admin)
    r = client.get('/admin/orders/settings')
    assert r.status_code == 200 and b'notify_pet_alert' in r.data
