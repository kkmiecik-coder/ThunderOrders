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
        msg = EmailManager.build_delivery_confirmation_message(sr)

    assert msg is not None
    assert msg.recipients == ['klient@example.com']
    assert sr.request_number in msg.html


def test_przypomnienie_respektuje_przelacznik(app, db, make_user):
    from utils.email_manager import EmailManager

    _wlacz(db, 'notify_delivery_confirmation', False)
    user = make_user()
    sr = _zlecenie(db, user, 'WYS/000201')

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) is None


def test_przypomnienie_bez_adresata_zwraca_none(app, db):
    from modules.orders.models import ShippingRequest
    from utils.email_manager import EmailManager
    from extensions import db as _db

    sr = ShippingRequest(request_number='WYS/000202', user_id=None, status='wyslane')
    _db.session.add(sr)
    _db.session.commit()

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(sr) is None


def test_mail_o_automatycznym_domknieciu_podaje_liczbe_dni(app, db, make_user):
    from modules.auth.models import Settings
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_autocomplete_days', 14, type='integer')
    db.session.commit()

    user = make_user(email='auto@example.com')
    sr = _zlecenie(db, user, 'WYS/000203', status='dostarczone')

    with app.test_request_context():
        msg = EmailManager.build_delivery_autoclosed_message(sr)

    assert msg is not None
    assert '14' in msg.html


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


def test_przypomnienie_paczka_zbiorcza_bez_wlasciciela_zwraca_none(app, db, make_user, make_order):
    """Regres z code review rundy 1 (Important 1): konto lidera paczki zbiorczej
    usunięte (user_id=None na zleceniu zbiorczym) nie może schodzić na adres z
    pierwszego zamówienia. sr.orders dla paczki zbiorczej idzie po surowym
    request_orders i zwraca zamówienia WSZYSTKICH uczestników razem — orders[0]
    mógłby być zamówieniem osoby zupełnie niezwiązanej z liderem. Wysłany do niej
    mail ujawniłby cudzy numer zlecenia i listę zamówień. Zero adresata -> zero
    maila, bez fallbacku na zgadywanie."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from utils.email_manager import EmailManager
    from extensions import db as _db

    lider = make_user(email='lider@example.com')
    drugi = make_user(email='drugi@example.com')

    # Zlecenie zbiorcze bez właściciela (konto lidera usunięte po konsolidacji).
    zbiorcze = ShippingRequest(request_number='WYS/000205', user_id=None, status='wyslane')
    _db.session.add(zbiorcze)
    _db.session.commit()

    zrodlo_a = ShippingRequest(
        request_number='WYS/000206', user_id=lider.id, status='wyslane',
        consolidated_into_id=zbiorcze.id)
    zrodlo_b = ShippingRequest(
        request_number='WYS/000207', user_id=drugi.id, status='wyslane',
        consolidated_into_id=zbiorcze.id)
    _db.session.add_all([zrodlo_a, zrodlo_b])
    _db.session.commit()
    zbiorcze.lead_source_request_id = zrodlo_a.id

    order_a = make_order(lider, status='wyslane')
    order_b = make_order(drugi, status='wyslane')
    _db.session.add(ShippingRequestOrder(
        shipping_request_id=zbiorcze.id, order_id=order_a.id, source_request_id=zrodlo_a.id))
    _db.session.add(ShippingRequestOrder(
        shipping_request_id=zbiorcze.id, order_id=order_b.id, source_request_id=zrodlo_b.id))
    _db.session.commit()

    assert zbiorcze.is_consolidation

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(zbiorcze) is None


class _WatekNatychmiastowy:
    """Zamiennik threading.Thread na potrzeby testów renderujących maile naprawdę.

    send_email() renderuje szablon Jinja SYNCHRONICZNIE (msg.html = render_template(...)),
    ale samą wysyłkę (mail.send) odpala w wątku tła — bez tej podmiany asercja na
    treść wysłanej wiadomości ścigałaby się z tamtym wątkiem (albo trafiałaby na
    listener mail.record_messages() już odłączony po wyjściu z bloku `with`).
    Podmieniamy WYŁĄCZNIE start wątku na wywołanie synchroniczne w tym samym wątku —
    renderowanie Jinja i mail.send() (przechwycony przez mail.record_messages())
    zachodzą naprawdę, nic tu nie jest zaślepką.
    """

    def __init__(self, target=None, args=(), kwargs=None, name=None, **_ignorowane):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        pass


def test_notify_delivery_confirmed_renderuje_z_ocena(app, db, make_user, monkeypatch):
    """Regres z code review rundy 1 (Important 2): notify_delivery_confirmed() był
    jedyną z pięciu metod kontraktu bez żadnego pokrycia, więc delivery_confirmed.html
    nigdy nie był realnie renderowany przez Jinję w testach — literówka w {{ comment }}
    albo błąd w {% if rating %} przeszłaby niezauważona.

    Podmieniamy TYLKO threading.Thread (patrz _WatekNatychmiastowy) — send_email()
    woła prawdziwy render_template(), a wysyłkę przechwytuje wbudowany w Flask-Mail
    mail.record_messages(). Żaden SMTP nie jest wołany: pod TESTING=True
    mail.suppress jest True (Flask-Mail: config.get('MAIL_SUPPRESS_SEND', testing)),
    więc Connection.send() i tak pomija realne wysłanie, tylko emituje sygnał
    email_dispatched, na którym łapie record_messages()."""
    from extensions import mail
    from modules.orders.review_models import DeliveryReview
    from utils.email_manager import EmailManager

    monkeypatch.setattr('utils.email_sender.Thread', _WatekNatychmiastowy)
    # .env w tym worktree ma MAIL_DEFAULT_SENDER='' (pusty, ale USTAWIONY string) —
    # os.getenv(..., 'noreply@thunderorders.cloud') w config.py zwraca wtedy '',
    # bo domyślna wartość działa tylko przy BRAKU zmiennej, nie przy pustej. Message
    # z pustym sender=... Flask-Mail odrzuca asercją przy realnym send() (nawet
    # tłumionym przez mail.suppress). To wyłącznie kwestia konfiguracji tego
    # środowiska testowego, nie kodu produkcyjnego — nadpisujemy na czas testu.
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

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


def test_notify_delivery_confirmed_renderuje_bez_oceny(app, db, make_user, monkeypatch):
    """Druga gałąź {% if rating %} w delivery_confirmed.html: bez wystawionej
    jeszcze oceny (sr.review is None) mail pokazuje przycisk „Oceń dostawę",
    nie sekcję z gwiazdkami/komentarzem. Patrz docstring testu powyżej —
    ta sama technika (mail.record_messages() + synchroniczny Thread)."""
    from extensions import mail
    from utils.email_manager import EmailManager

    monkeypatch.setattr('utils.email_sender.Thread', _WatekNatychmiastowy)
    # Patrz komentarz w teście powyżej — MAIL_DEFAULT_SENDER='' w .env tego worktree.
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

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
