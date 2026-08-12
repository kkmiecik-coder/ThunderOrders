"""Maile dostawy — przełączniki, adresaci, treść."""


def _zlecenie(db, user, numer='WYS/000200', status='wyslane'):
    from modules.orders.models import ShippingRequest
    sr = ShippingRequest(request_number=numer, user_id=user.id, status=status)
    db.session.add(sr)
    db.session.commit()
    return sr


def _wlacz(db, klucz, wartosc=True):
    import json
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager
    config = Settings.get_value('email_notifications_config', {}) or {}
    config[klucz] = wartosc
    # Settings.set_value() robi str(value), nie json.dumps(value) — z gołym
    # dict-em zapisałby reprezentację Pythona ({'a': False}, pojedyncze cudzysłowy,
    # wielka litera False), której get_value(type='json') nie odczyta z powrotem
    # (json.loads rzuci wyjątkiem, is_email_enabled po cichu wróci do True).
    # Produkcyjny kod (modules/orders/routes.py:update_email_notification_settings)
    # zawsze serializuje ręcznie przed zapisem — ten helper musi robić to samo.
    Settings.set_value('email_notifications_config', json.dumps(config), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()


def test_przypomnienie_buduje_wiadomosc(app, db, make_user, make_order):
    from modules.orders.models import ShippingRequestOrder
    from utils.email_manager import EmailManager

    user = make_user(email='klient@example.com')
    sr = _zlecenie(db, user)
    order = make_order(user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()

    with app.test_request_context():
        msgs = EmailManager.build_delivery_confirmation_message(sr)

    # build_* zwraca LISTĘ Message (jednoelementową dla zwykłego zlecenia) — paczka
    # zbiorcza z definicji rodzi po jednej wiadomości na uczestnika.
    assert len(msgs) == 1
    assert msgs[0].recipients == ['klient@example.com']
    assert sr.request_number in msgs[0].html


def test_przypomnienie_respektuje_przelacznik(app, db, make_user):
    from utils.email_manager import EmailManager

    _wlacz(db, 'notify_delivery_confirmation', False)
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000201')

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) == []


def test_przypomnienie_bez_adresata_zwraca_pusto(app, db):
    from modules.orders.models import ShippingRequest
    from utils.email_manager import EmailManager
    from extensions import db as _db

    sr = ShippingRequest(request_number='WYS/000202', user_id=None, status='wyslane')
    _db.session.add(sr)
    _db.session.commit()

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) == []


def test_mail_o_automatycznym_domknieciu_podaje_liczbe_dni(app, db, make_user):
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_autocomplete_days', 14, type='integer')
    db.session.commit()

    user = make_user(email='auto@example.com')
    sr = _zlecenie(db, user, 'WYS/000203', status='dostarczone')

    with app.test_request_context():
        msgs = EmailManager.build_delivery_autoclosed_message(sr)

    assert len(msgs) == 1
    assert '14' in msgs[0].html


def test_mail_do_adminow_zawiera_ocene(app, db, make_user, monkeypatch):
    from modules.orders.review_models import DeliveryReview
    from utils.email_manager import EmailManager

    wyslane = []
    monkeypatch.setattr(
        EmailManager, 'get_admin_notification_emails',
        classmethod(lambda cls: ['admin@example.com']))
    monkeypatch.setattr(
        'utils.email_sender.send_email',
        lambda to, subject, template, **kw: wyslane.append((to, kw)) or True)

    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000204', status='dostarczone')
    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=user.id, rating=5, comment='Super'))
    db.session.commit()

    with app.test_request_context():
        EmailManager.notify_admin_delivery_confirmed(sr)

    assert wyslane, 'mail do adminów nie poszedł'
    assert wyslane[0][1]['rating'] == 5
    assert wyslane[0][1]['comment'] == 'Super'


def _paczka_zbiorcza(db, make_user, make_order, numery, user_lidera=None):
    """Paczka zbiorcza dwóch klientów, każdy z własnym zamówieniem.

    Zwraca (zbiorcze, [(user, zrodlo, order), ...]) — pierwszy element listy jest
    liderem. `numery` to trzy numery zleceń: zbiorcze, źródło lidera, źródło drugiego.
    """
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from extensions import db as _db

    lider = user_lidera if user_lidera is not None else make_user(email='lider@example.com')
    drugi = make_user(email='drugi@example.com')

    # _kopiuj_adres przy konsolidacji ustawia zbiorcze.user_id = user_id lidera —
    # odtwarzamy dokładnie ten stan, bo to on jest źródłem wycieku.
    zbiorcze = ShippingRequest(
        request_number=numery[0], user_id=lider.id, status='wyslane')
    _db.session.add(zbiorcze)
    _db.session.commit()

    zrodla = []
    for numer, user in ((numery[1], lider), (numery[2], drugi)):
        zrodlo = ShippingRequest(
            request_number=numer, user_id=user.id, status='wyslane',
            consolidated_into_id=zbiorcze.id)
        _db.session.add(zrodlo)
        _db.session.commit()
        order = make_order(user, status='wyslane')
        _db.session.add(ShippingRequestOrder(
            shipping_request_id=zbiorcze.id, order_id=order.id,
            source_request_id=zrodlo.id))
        _db.session.commit()
        zrodla.append((user, zrodlo, order))

    zbiorcze.lead_source_request_id = zrodla[0][1].id
    _db.session.commit()
    assert zbiorcze.is_consolidation
    return zbiorcze, zrodla


def test_przypomnienie_paczka_zbiorcza_idzie_osobno_do_kazdego(app, db, make_user, make_order):
    """Recenzja całościowa (C1): ścieżka główna wycieku — lider Z AKTYWNYM kontem.

    `_kopiuj_adres` ustawia `zbiorcze.user_id = lead.user_id`, więc `_adresat_zlecenia`
    kończyło na pierwszej gałęzi (jest user, jest e-mail) i strażnik `is_consolidation`
    poniżej był nieosiągalny. Mail szedł WYŁĄCZNIE do lidera i wymieniał w treści
    numery zamówień wszystkich uczestników, a pozostali nie dostawali nic.
    """
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000205', 'WYS/000206', 'WYS/000207'))
    (lider, zrodlo_a, order_a), (drugi, zrodlo_b, order_b) = zrodla

    with app.test_request_context():
        msgs = EmailManager.build_delivery_confirmation_message(zbiorcze)

    assert len(msgs) == 2, 'każdy uczestnik ma dostać własną wiadomość'
    po_adresie = {m.recipients[0]: m for m in msgs}
    assert set(po_adresie) == {'lider@example.com', 'drugi@example.com'}

    mail_lidera = po_adresie['lider@example.com']
    assert order_a.order_number in mail_lidera.html
    assert order_b.order_number not in mail_lidera.html, 'wyciek cudzego zamówienia'
    assert zrodlo_a.request_number in mail_lidera.html
    assert zbiorcze.request_number not in mail_lidera.html

    mail_drugiego = po_adresie['drugi@example.com']
    assert order_b.order_number in mail_drugiego.html
    assert order_a.order_number not in mail_drugiego.html, 'wyciek cudzego zamówienia'
    assert zrodlo_b.request_number in mail_drugiego.html


def test_domkniecie_paczki_zbiorczej_idzie_osobno_do_kazdego(app, db, make_user, make_order):
    """Ta sama wada w drugim mailu: automatyczne domknięcie. delivery_autoclosed.html
    nie renderuje listy zamówień, ale niesie numer zlecenia i link — jedno i drugie
    prowadziło na paczkę zbiorczą z cudzymi danymi."""
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000215', 'WYS/000216', 'WYS/000217'))
    (lider, zrodlo_a, _), (drugi, zrodlo_b, _) = zrodla

    with app.test_request_context():
        msgs = EmailManager.build_delivery_autoclosed_message(zbiorcze)

    assert len(msgs) == 2
    po_adresie = {m.recipients[0]: m for m in msgs}
    assert zrodlo_a.request_number in po_adresie['lider@example.com'].html
    assert zrodlo_b.request_number not in po_adresie['lider@example.com'].html
    assert zbiorcze.request_number not in po_adresie['lider@example.com'].html
    assert zrodlo_b.request_number in po_adresie['drugi@example.com'].html
    assert zrodlo_a.request_number not in po_adresie['drugi@example.com'].html


def test_uczestnik_bez_konta_jest_pomijany_a_reszta_dostaje_mail(app, db, make_user, make_order):
    """Wariant brzegowy z poprzedniej rundy zostaje domknięty: uczestnik bez konta
    (albo bez adresu) jest POMIJANY, bez fallbacku na adres z zamówienia — dla paczki
    zbiorczej taki adres może należeć do zupełnie innej osoby. Reszta uczestników
    dostaje swoje maile normalnie, zamiast tracić powiadomienie przez cudzy brak."""
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000225', 'WYS/000226', 'WYS/000227'))
    (lider, zrodlo_a, _), (drugi, zrodlo_b, _) = zrodla

    zrodlo_a.user_id = None  # konto lidera usunięte po konsolidacji
    db.session.commit()

    with app.test_request_context():
        msgs = EmailManager.build_delivery_confirmation_message(zbiorcze)

    assert len(msgs) == 1
    assert msgs[0].recipients == ['drugi@example.com']


def test_notify_delivery_confirmed_renderuje_z_ocena(app, db, make_user, maile_synchronicznie):
    """Regres z code review rundy 1 (Important 2): notify_delivery_confirmed() był
    jedyną z pięciu metod kontraktu bez żadnego pokrycia, więc delivery_confirmed.html
    nigdy nie był realnie renderowany przez Jinję w testach — literówka w {{ comment }}
    albo błąd w {% if rating %} przeszłaby niezauważona.

    Fixture `maile_synchronicznie` podmienia TYLKO wątek wysyłki (patrz conftest) —
    send_email() woła prawdziwy render_template(), a wysyłkę przechwytuje wbudowany
    w Flask-Mail mail.record_messages(). Żaden SMTP nie jest wołany: pod TESTING=True
    mail.suppress jest True (Flask-Mail: config.get('MAIL_SUPPRESS_SEND', testing)),
    więc Connection.send() i tak pomija realne wysłanie, tylko emituje sygnał
    email_dispatched, na którym łapie record_messages()."""
    from extensions import mail
    from modules.orders.review_models import DeliveryReview
    from utils.email_manager import EmailManager

    user = make_user(email='klient@example.com', first_name='Zosia')
    sr = _zlecenie(db, user, 'WYS/000210', status='dostarczone')
    db.session.add(DeliveryReview(
        shipping_request_id=sr.id, user_id=user.id, rating=4, comment='Szybka wysyłka'))
    db.session.commit()

    with app.test_request_context(), mail.record_messages() as outbox:
        EmailManager.notify_delivery_confirmed(sr)

    assert len(outbox) == 1, 'mail o potwierdzeniu nie poszedł'
    html = outbox[0].html
    assert 'Zosia' in html
    assert 'WYS/000210' in html
    assert 'Twoja ocena dostawy: 4/5' in html
    assert 'Szybka wysyłka' in html


def test_notify_delivery_confirmed_renderuje_bez_oceny(app, db, make_user, maile_synchronicznie):
    """Druga gałąź {% if rating %} w delivery_confirmed.html: bez wystawionej
    jeszcze oceny (sr.review is None) mail pokazuje przycisk „Oceń dostawę",
    nie sekcję z gwiazdkami/komentarzem. Patrz docstring testu powyżej —
    ta sama technika (mail.record_messages() + synchroniczny Thread)."""
    from extensions import mail
    from utils.email_manager import EmailManager

    user = make_user(email='klient2@example.com', first_name='Adam')
    sr = _zlecenie(db, user, 'WYS/000211', status='dostarczone')

    with app.test_request_context(), mail.record_messages() as outbox:
        EmailManager.notify_delivery_confirmed(sr)

    assert len(outbox) == 1, 'mail o potwierdzeniu nie poszedł'
    html = outbox[0].html
    assert 'Adam' in html
    assert 'WYS/000211' in html
    assert 'Oceń dostawę' in html
    assert 'Twoja ocena dostawy' not in html
