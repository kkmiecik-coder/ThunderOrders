"""/api/exchange-rate (formularz produktu): wiek kursu z cache liczy przeglądarka z `cached_at_iso`."""
from datetime import timedelta

from utils.timeutil import PL_TZ, iso_utc, utcnow


def test_kurs_z_cache_podaje_chwile_iso_utc(app, db, client, make_user, login, monkeypatch):
    from modules.auth.models import Settings

    def _bez_sieci(*a, **kw):
        raise AssertionError('kurs ma przyjść z cache, nie z NBP')
    monkeypatch.setattr('utils.currency.fetch_nbp_rate', _bez_sieci)

    chwila = (utcnow() - timedelta(hours=2)).replace(microsecond=0)
    Settings.set_value('warehouse_currency_krw_rate', '0.0029')
    # Znacznik w ustawieniach to tekst czasu polskiego bez strefy (tak zapisuje cache_rate)
    Settings.set_value('warehouse_currency_last_update', chwila.astimezone(PL_TZ).strftime('%Y-%m-%d %H:%M:%S'))
    db.session.commit()

    login(make_user(role='admin'))
    dane = client.get('/api/exchange-rate?currency=KRW').get_json()

    assert dane['success'] and dane['cached']
    assert dane['cached_at_iso'] == iso_utc(chwila)
    assert dane['cached_at_iso'].endswith('Z')
