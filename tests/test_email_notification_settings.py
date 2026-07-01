"""
Testy zapisu ustawień powiadomień email (/admin/orders/settings/email-notifications).

Regresja: whitelista ALLOWED_KEYS w endpoincie musi obejmować wszystkie klucze
toggle'i renderowane w szablonie settings.html. W przeciwnym razie toggle, którego
klucza brakuje na whiteliście, nie zostanie zapisany i "wraca" po odświeżeniu strony.
"""
import json

import pytest


def _admin(make_user):
    return make_user(role='admin')


def _get_config(db):
    from modules.auth.models import Settings
    return Settings.get_value('email_notifications_config', {})


def test_supplier_toggles_are_persisted(client, db, make_user, login):
    """Wyłączenie toggle'i dostawcy musi zapisać się w configu (bug: wracały po odświeżeniu)."""
    login(_admin(make_user))

    resp = client.post('/admin/orders/settings/email-notifications', json={
        'toggles': {
            'notify_supplier_ordered': False,
            'notify_supplier_cancelled': False,
        },
        'disabled_admin_ids': [],
        'extra_emails': '',
    })

    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    config = _get_config(db)
    assert config.get('notify_supplier_ordered') is False
    assert config.get('notify_supplier_cancelled') is False


def test_all_template_toggle_keys_are_whitelisted(client, db, make_user, login):
    """
    Każdy klucz toggle'a z szablonu musi trafiać do zapisanego configu.
    Chroni przed rozjechaniem się szablonu i whitelisty backendu w przyszłości.
    """
    login(_admin(make_user))

    # Klucze toggle'i tak jak renderuje je templates/admin/orders/settings.html
    template_keys = [
        'notify_order_confirmation', 'notify_status_change', 'notify_order_completed',
        'notify_tracking_added', 'notify_packing_photo', 'notify_order_cancelled',
        'notify_supplier_ordered', 'notify_supplier_cancelled',
        'notify_cost_added', 'notify_payment_approved', 'notify_payment_rejected',
        'notify_payment_reminder', 'notify_shipping_request_created',
        'notify_shipping_status_change', 'notify_offer_closure',
        'notify_new_offer_page', 'notify_back_in_stock',
        'notify_admin_new_order', 'notify_admin_payment_uploaded',
    ]

    # Wyślij wszystkie jako wyłączone
    resp = client.post('/admin/orders/settings/email-notifications', json={
        'toggles': {k: False for k in template_keys},
        'disabled_admin_ids': [],
        'extra_emails': '',
    })
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    config = _get_config(db)
    missing = [k for k in template_keys if k not in config]
    assert not missing, f'Klucze pominięte przez backend (brak w ALLOWED_KEYS): {missing}'
    for k in template_keys:
        assert config[k] is False, f'{k} powinno być zapisane jako False'
