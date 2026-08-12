"""Push i dzwonek dla zdarzeń dostawy."""


def _zlecenie(db, user, numer='WYS/000300', status='wyslane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def test_przypomnienie_trafia_do_wlasciciela(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    user = make_user()
    sr = _zlecenie(db, user)

    PushManager.notify_delivery_confirmation(sr)

    assert len(wyslane) == 1
    assert wyslane[0]['user_id'] == user.id
    assert wyslane[0]['notification_type'] == 'shipping_updates'
    assert sr.request_number in wyslane[0]['body']


def test_zlecenie_bez_wlasciciela_nie_wysyla(app, db, monkeypatch):
    from extensions import db as _db
    from modules.orders.models import ShippingRequest
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    sr = ShippingRequest(request_number='WYS/000301', user_id=None, status='wyslane')
    _db.session.add(sr)
    _db.session.commit()

    PushManager.notify_delivery_confirmation(sr)

    assert wyslane == []


def test_powiadomienie_dla_adminow_idzie_do_kazdego(app, db, make_user, monkeypatch):
    from utils.push_manager import PushManager

    wyslane = []
    monkeypatch.setattr(
        PushManager, '_fire_and_forget',
        staticmethod(lambda **kw: wyslane.append(kw)))

    make_user(role='admin', email='a1@example.com')
    make_user(role='admin', email='a2@example.com')
    klient = make_user()
    sr = _zlecenie(db, klient, 'WYS/000302', status='dostarczone')

    PushManager.notify_admin_delivery_confirmed(sr)

    assert len(wyslane) == 2
    assert all(w['notification_type'] == 'admin_alerts' for w in wyslane)
