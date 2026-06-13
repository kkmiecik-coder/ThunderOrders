"""Task 5 (E10): push "produkt wrócił" OBOK e-maila back-in-stock.

Dotyczy ŻYWEGO kodu rezerwacji LIVE (`modules/offers/socket_events.py`).
Decyzja Konrada: wariant „obok" — gdy subskrybent back-in-stock jest OFFLINE
(gałąź e-mail-fallback), leci e-mail JAK DZIŚ + dodatkowo Web Push + FCM przez
nowy `PushManager.notify_back_in_stock`. Push jest CZYSTO ADDYTYWNY: e-mail i
flaga `notified` bez zmian; błąd push nie może wywrócić e-maila/rezerwacji/WS.
"""
import pytest


def _setup_subscription(db, make_user, make_product):
    """User + produkt + aktywna strona oferty + subskrypcja back-in-stock (notified=False)."""
    from modules.offers.models import OfferPage, OfferProductNotificationSubscription

    user = make_user()
    product = make_product()
    page = OfferPage(name='Drop', token=OfferPage.generate_token(), status='active',
                     page_type='exclusive', created_by=user.id)
    db.session.add(page)
    db.session.commit()

    sub = OfferProductNotificationSubscription(
        offer_page_id=page.id, product_id=product.id, user_id=user.id, notified=False)
    db.session.add(sub)
    db.session.commit()
    return user, product, page, sub


def _seed_old_unavailable(page_id, product_id):
    """Produkt był niedostępny (available=0) w poprzednim snapshocie."""
    from modules.offers.redis_state import get_state
    get_state().set_last_availability(page_id, {str(product_id): {'available': 0}})


def test_back_in_stock_offline_fires_push_alongside_email(
        app, db, make_user, make_product, monkeypatch):
    """User offline (brak aktywnego sid) + produkt wraca na stan → notify_back_in_stock
    wołane (Web Push + FCM) ORAZ e-mail nadal wysłany (parytet). Flaga notified=True."""
    from modules.offers.socket_events import _check_notification_subscriptions
    from utils.push_manager import PushManager

    user, product, page, sub = _setup_subscription(db, make_user, make_product)
    _seed_old_unavailable(page.id, product.id)

    calls = {'email': [], 'push': []}

    def fake_email(**kwargs):
        calls['email'].append(kwargs)
        return True

    def fake_push(**kwargs):
        calls['push'].append(kwargs)

    # E-mail importowany wewnątrz funkcji (from utils.email_sender import ...) → patch modułu.
    monkeypatch.setattr('utils.email_sender.send_back_in_stock_email', fake_email)
    monkeypatch.setattr(PushManager, 'notify_back_in_stock', fake_push)

    with app.test_request_context():
        _check_notification_subscriptions(page.id, {str(product.id): {'available': 5}})

    # E-mail nadal wołany (parytet — push jest OBOK, nie zamiast)
    assert len(calls['email']) == 1
    # Push wołany dokładnie raz, dla właściwego usera/produktu
    assert len(calls['push']) == 1
    assert calls['push'][0]['user_id'] == user.id
    assert calls['push'][0]['product_name'] == product.name

    db.session.refresh(sub)
    assert sub.notified is True


def test_back_in_stock_push_error_does_not_break_email(
        app, db, make_user, make_product, monkeypatch):
    """Wyjątek z notify_back_in_stock NIE może wywrócić przepływu: e-mail wysłany,
    flaga notified ustawiona, brak propagacji wyjątku z _check_notification_subscriptions."""
    from modules.offers.socket_events import _check_notification_subscriptions
    from utils.push_manager import PushManager

    user, product, page, sub = _setup_subscription(db, make_user, make_product)
    _seed_old_unavailable(page.id, product.id)

    calls = {'email': []}

    def fake_email(**kwargs):
        calls['email'].append(kwargs)
        return True

    def boom_push(**kwargs):
        raise RuntimeError('push down')

    monkeypatch.setattr('utils.email_sender.send_back_in_stock_email', fake_email)
    monkeypatch.setattr(PushManager, 'notify_back_in_stock', boom_push)

    with app.test_request_context():
        # Nie może podnieść wyjątku — push owinięty w try/except
        _check_notification_subscriptions(page.id, {str(product.id): {'available': 5}})

    assert len(calls['email']) == 1
    db.session.refresh(sub)
    assert sub.notified is True
