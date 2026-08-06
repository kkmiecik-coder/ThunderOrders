from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def _seed_poland_order_with_deadline(db, order, deadline):
    """Tworzy minimalny łańcuch ProxyOrder -> PolandOrder -> PolandOrderItem
    powiązany z `order`, z `customs_payment_deadline = deadline`.

    Order.get_customs_vat_deadline() czyta terminy przez PolandOrderItemOrder
    (rozdział partii FIFO), więc trzeba przejść przez cały łańcuch FK
    (ProxyOrder -> PolandOrder, ProxyOrderItem -> PolandOrderItem) i dodatkowo
    utworzyć jawny link PolandOrderItemOrder — to on jest źródłem prawdy.
    """
    from modules.products.models import (
        ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem, Product,
    )

    product = Product(name='Testowy produkt', sale_price=Decimal('10.00'), quantity=5)
    db.session.add(product)
    db.session.commit()

    proxy_order = ProxyOrder(order_number='PRX/00001', order_type='polska')
    db.session.add(proxy_order)
    db.session.commit()

    proxy_order_item = ProxyOrderItem(
        proxy_order_id=proxy_order.id,
        product_id=product.id,
        order_id=order.id,
        quantity=1,
        unit_price=Decimal('10.00'),
        total_price=Decimal('10.00'),
    )
    db.session.add(proxy_order_item)
    db.session.commit()

    poland_order = PolandOrder(
        order_number='PRX/PL/00001',
        proxy_order_id=proxy_order.id,
        customs_payment_deadline=deadline,
    )
    db.session.add(poland_order)
    db.session.commit()

    poland_order_item = PolandOrderItem(
        poland_order_id=poland_order.id,
        proxy_order_item_id=proxy_order_item.id,
        product_id=product.id,
        order_id=order.id,
        quantity=1,
    )
    db.session.add(poland_order_item)
    db.session.commit()

    from modules.products.models import PolandOrderItemOrder
    db.session.add(PolandOrderItemOrder(poland_order_item_id=poland_order_item.id, order_id=order.id, quantity=1))
    db.session.commit()


def _seed_poland_order_with_shipping_kr_deadline(db, order, deadline):
    """Wariant `_seed_poland_order_with_deadline` ustawiający `payment_deadline`
    (E2: wysyłka KR) zamiast `customs_payment_deadline` (E3), przez ten sam
    łańcuch ProxyOrder -> PolandOrder -> PolandOrderItem, bo Order.get_shipping_kr_deadline()
    czyta go dokładnie tak samo jak get_customs_vat_deadline().
    """
    from modules.products.models import (
        ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem, Product,
    )

    product = Product(name='Testowy produkt', sale_price=Decimal('10.00'), quantity=5)
    db.session.add(product)
    db.session.commit()

    proxy_order = ProxyOrder(order_number='PRX/00002', order_type='polska')
    db.session.add(proxy_order)
    db.session.commit()

    proxy_order_item = ProxyOrderItem(
        proxy_order_id=proxy_order.id,
        product_id=product.id,
        order_id=order.id,
        quantity=1,
        unit_price=Decimal('10.00'),
        total_price=Decimal('10.00'),
    )
    db.session.add(proxy_order_item)
    db.session.commit()

    poland_order = PolandOrder(
        order_number='PRX/PL/00002',
        proxy_order_id=proxy_order.id,
        payment_deadline=deadline,
    )
    db.session.add(poland_order)
    db.session.commit()

    poland_order_item = PolandOrderItem(
        poland_order_id=poland_order.id,
        proxy_order_item_id=proxy_order_item.id,
        product_id=product.id,
        order_id=order.id,
        quantity=1,
    )
    db.session.add(poland_order_item)
    db.session.commit()

    from modules.products.models import PolandOrderItemOrder
    db.session.add(PolandOrderItemOrder(poland_order_item_id=poland_order_item.id, order_id=order.id, quantity=1))
    db.session.commit()


def test_cron_skips_shipping_kr_stage_with_zero_amount(app, db, make_user, make_order, monkeypatch):
    """Regresja: cron nie może wysłać przypomnienia o etapie E2 (wysyłka KR),
    gdy termin już minął ale koszt wysyłki (proxy_shipping_cost) wynosi 0/None —
    np. admin ustawił termin zanim wycenił przesyłkę. Bez tego zabezpieczenia
    klient dostałby maila z prośbą o zapłatę 0 zł.
    """
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient5@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        payment_stages=4,
        proxy_shipping_cost=None,
    )

    _seed_poland_order_with_shipping_kr_deadline(db, order, now - timedelta(hours=5))

    config = PaymentReminderConfig(reminder_type='before_deadline', hours=1, payment_stage='shipping_kr', enabled=True)
    db.session.add(config)
    db.session.commit()

    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', lambda messages: [True] * len(messages))
    monkeypatch.setattr('utils.push_manager.PushManager.notify_payment_reminder', lambda *a, **kw: None)

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders'])

    assert result.exit_code == 0, result.output + str(result.exception)
    log = PaymentReminderLog.query.filter_by(order_id=order.id, stage='shipping_kr').first()
    assert log is None


def test_cron_sends_reminder_for_customs_vat_stage(app, db, make_user, make_order, monkeypatch):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient3@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )

    _seed_poland_order_with_deadline(db, order, now - timedelta(hours=5))

    config = PaymentReminderConfig(reminder_type='before_deadline', hours=1, payment_stage='product', enabled=True)
    db.session.add(config)
    db.session.commit()

    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', lambda messages: [True] * len(messages))
    # Push notifications go out on a real background thread (PushManager._fire_and_forget)
    # that outlives the test's in-memory sqlite session, causing flaky FlushErrors when
    # the next test's db teardown races it. Push delivery isn't under test here — only
    # the reminder log/stage bookkeeping is — so stub it out.
    monkeypatch.setattr('utils.push_manager.PushManager.notify_payment_reminder', lambda *a, **kw: None)

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders'])

    assert result.exit_code == 0, result.output + str(result.exception)
    log = PaymentReminderLog.query.filter_by(order_id=order.id, stage='customs_vat').first()
    assert log is not None


def test_cron_dry_run_does_not_write_log(app, db, make_user, make_order):
    """`after_order_placed` used deliberately: it triggers off `order.created_at`,
    a real DB column — unlike `before_deadline` for the 'product' stage, which reads
    `get_product_deadline()` -> `offer_page.payment_deadline`, an in-process
    monkeypatch of which the CLI-invoked cron (fresh DB query) would never see.
    This keeps the dry-run assertion meaningful (a reminder really is due) instead
    of trivially passing because nothing ever fires.
    """
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient4@example.com'),
        total_amount=Decimal('100.00'),
        created_at=now - timedelta(hours=100),
    )

    config = PaymentReminderConfig(reminder_type='after_order_placed', hours=1, payment_stage='product', enabled=True)
    db.session.add(config)
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders', '--dry-run'])

    assert result.exit_code == 0
    assert PaymentReminderLog.query.filter_by(order_id=order.id).count() == 0


def test_cron_after_order_placed_skips_exclusive_order_with_open_sale(app, db, make_user, make_order, monkeypatch):
    """Regresja: after_order_placed musi dotyczyć WYŁĄCZNIE on_hand/preorder,
    tak jak dotyczyło przed rozszerzeniem crona na wszystkie etapy. Zamówienie
    typu 'exclusive' (strona sprzedaży) bez ustalonego terminu i bez zamkniętej
    sprzedaży nie ma jak być opłacone (can_upload_product_payment blokuje) —
    reguła after_order_placed nie powinna wysyłać dla niego przypomnienia,
    niezależnie od tego, ile godzin minęło od złożenia zamówienia.
    """
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient5@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        created_at=now - timedelta(hours=100),
    )

    config = PaymentReminderConfig(reminder_type='after_order_placed', hours=1, payment_stage='product', enabled=True)
    db.session.add(config)
    db.session.commit()

    monkeypatch.setattr('utils.push_manager.PushManager.notify_payment_reminder', lambda *a, **k: None)
    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', lambda messages: [True] * len(messages))

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders'])

    assert result.exit_code == 0
    assert PaymentReminderLog.query.filter_by(order_id=order.id).count() == 0


import pytest


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_cron_pomija_zamowienia_zamkniete(app, db, make_user, make_order, monkeypatch, status):
    """Zamówienie anulowane albo czekające na zwrot nie może dostawać ponagleń o zapłatę.

    Klient dostałby maila 'zapłać' za coś, czego już nie ma — a przy zwrocie to my
    jesteśmy mu winni pieniądze, nie odwrotnie.
    """
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email=f'klient-{status}@example.com'),
        total_amount=Decimal('100.00'),
        order_type='on_hand',
        status=status,
        created_at=now - timedelta(hours=100),
    )

    config = PaymentReminderConfig(
        reminder_type='after_order_placed', hours=1, payment_stage='product', enabled=True
    )
    db.session.add(config)
    db.session.commit()

    monkeypatch.setattr('utils.push_manager.PushManager.notify_payment_reminder', lambda *a, **k: None)
    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', lambda messages: [True] * len(messages))

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders'])

    assert result.exit_code == 0
    assert PaymentReminderLog.query.filter_by(order_id=order.id).count() == 0
