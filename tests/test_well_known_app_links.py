"""
Testy plików Digital Asset Links / Associated Domains dla apki mobilnej
(autofill haseł: iCloud Keychain + Google Password Manager).

Platformy mają twarde wymagania, które łatwo zepsuć refaktorem:
- serwowane po HTTPS, status 200, BEZ przekierowań (30x),
- Content-Type: application/json,
- AASA celowo BEZ rozszerzenia .json w nazwie,
- katalog /.well-known/ musi działać też w trybie maintenance.
"""
import time


def test_aasa_contract(client):
    r = client.get('/.well-known/apple-app-site-association')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/json'
    assert 'Location' not in r.headers  # brak przekierowania
    assert r.get_json() == {
        "webcredentials": {"apps": ["7LYBV3242V.cloud.thunderorders.mobile"]}
    }


def test_assetlinks_contract(client):
    r = client.get('/.well-known/assetlinks.json')
    assert r.status_code == 200
    assert r.headers['Content-Type'] == 'application/json'
    assert 'Location' not in r.headers
    data = r.get_json()
    assert isinstance(data, list) and len(data) == 1
    target = data[0]['target']
    assert data[0]['relation'] == ['delegate_permission/common.get_login_creds']
    assert target['namespace'] == 'android_app'
    assert target['package_name'] == 'cloud.thunderorders.mobile'
    # Co najmniej odcisk debug keystore (release dojdzie przy publikacji).
    assert (
        "42:4E:0A:0A:CA:2A:D2:DC:D0:01:6E:FB:8B:28:03:B6:4E:EE:07:82:77:40:18:73:8A:D5:D9:06:FE:A7:72:F1"
        in target['sha256_cert_fingerprints']
    )


def test_well_known_bypasses_maintenance(app, client):
    """W trybie konserwacji walidatory Apple/Google muszą dostać 200, nie 503."""
    app.maintenance_cache = {'enabled': True, 'checked_at': time.time()}
    try:
        for url in ('/.well-known/apple-app-site-association',
                    '/.well-known/assetlinks.json'):
            r = client.get(url)
            assert r.status_code == 200, f'{url} -> {r.status_code}'
    finally:
        app.maintenance_cache = {'enabled': False, 'checked_at': 0}
