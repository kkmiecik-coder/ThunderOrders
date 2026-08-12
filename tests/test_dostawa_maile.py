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


def test_przypomnienie_paczki_zbiorczej_idzie_tylko_do_lidera(app, db, make_user, make_order):
    """Dwie wady naraz — wyciek (C1) i prośba o czynność niewykonalną.

    `_kopiuj_adres` ustawia `zbiorcze.user_id = lead.user_id`, więc `_adresat_zlecenia`
    kończyło na pierwszej gałęzi (jest user, jest e-mail) i strażnik `is_consolidation`
    poniżej był nieosiągalny. Mail szedł WYŁĄCZNIE do lidera i wymieniał w treści
    numery zamówień wszystkich uczestników — to naprawiła poprzednia fala.

    Rozesłanie go wtedy do wszystkich wprowadziło jednak wadę drugą: nie-lider
    dostawał prośbę „potwierdź odbiór" z CTA prowadzącym na stronę, która odpowiada
    mu, że tej paczki stąd nie potwierdzi (`zlecenie_do_potwierdzenia` oddaje mu
    `do_domkniecia=None`). Ten mail nie informuje, tylko prosi — więc dostaje go
    wyłącznie osoba zdolna prośbę spełnić.
    """
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000205', 'WYS/000206', 'WYS/000207'))
    (lider, zrodlo_a, order_a), (drugi, zrodlo_b, order_b) = zrodla

    with app.test_request_context():
        msgs = EmailManager.build_delivery_confirmation_message(zbiorcze)

    assert len(msgs) == 1, 'o potwierdzenie prosimy wyłącznie lidera'
    mail_lidera = msgs[0]
    assert mail_lidera.recipients == ['lider@example.com']
    assert 'Potwierdzam odbiór' in mail_lidera.html

    # Wyciek z poprzedniej fali nadal pilnowany: lider widzi swoje zamówienie
    # i numer SWOJEGO zlecenia źródłowego, nie paczki zbiorczej ani cudzych danych.
    assert order_a.order_number in mail_lidera.html
    assert order_b.order_number not in mail_lidera.html, 'wyciek cudzego zamówienia'
    assert zrodlo_a.request_number in mail_lidera.html
    assert zrodlo_b.request_number not in mail_lidera.html
    assert zbiorcze.request_number not in mail_lidera.html


def test_domkniecie_paczki_zbiorczej_idzie_do_kazdego_ale_nie_tak_samo(
        app, db, make_user, make_order):
    """Domknięcie automatem to informacja, nie prośba — idzie więc do WSZYSTKICH.

    Ta sama wada wycieku co w przypomnieniu: delivery_autoclosed.html nie renderuje
    listy zamówień, ale niesie numer zlecenia i link — jedno i drugie prowadziło na
    paczkę zbiorczą z cudzymi danymi.

    Nie-lider musi dodatkowo wiedzieć, że karton pojechał na cudzy adres: bez tego
    zdania „od wysyłki paczki WYS/… minęło N dni" brzmi jak o przesyłce nadanej do
    niego. Nazwisko skrócone (`short_addressee_name`), pełnego nigdzie nie ma.
    """
    from utils.email_manager import EmailManager

    lider = make_user(email='lider@example.com', first_name='Ola', last_name='Kowalska')
    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000215', 'WYS/000216', 'WYS/000217'),
        user_lidera=lider)
    (_, zrodlo_a, _), (drugi, zrodlo_b, _) = zrodla

    with app.test_request_context():
        msgs = EmailManager.build_delivery_autoclosed_message(zbiorcze)

    assert len(msgs) == 2, 'informację o domknięciu dostają wszyscy uczestnicy'
    po_adresie = {m.recipients[0]: m for m in msgs}
    mail_lidera = po_adresie['lider@example.com']
    mail_drugiego = po_adresie['drugi@example.com']

    assert zrodlo_a.request_number in mail_lidera.html
    assert zrodlo_b.request_number not in mail_lidera.html
    assert zbiorcze.request_number not in mail_lidera.html
    assert zrodlo_b.request_number in mail_drugiego.html
    assert zrodlo_a.request_number not in mail_drugiego.html

    # Adresat kartonu nie dostaje zdania o „paczce zbiorczej na cudzy adres" —
    # to jego adres.
    assert 'paczce zbiorczej' not in mail_lidera.html
    assert ('Twoje zamówienia jechały w paczce zbiorczej wysłanej na adres: Ola K.'
            in mail_drugiego.html)
    # Nazwisko już kończy zdanie kropką skrótu — druga byłaby „Ola K...".
    assert 'Ola K..' not in mail_drugiego.html
    assert 'Kowalska' not in mail_drugiego.html, 'pełne nazwisko obcej osoby'
    # Automat nie jest niczyim potwierdzeniem — o potwierdzeniu ani słowa.
    assert 'potwierdziła' not in mail_drugiego.html


def test_domkniecie_bez_nazwy_adresata_nie_zostawia_dziury_w_zdaniu(
        app, db, make_user, make_order):
    """Konto lidera bez imienia i nazwiska, paczkomat bez shipping_name:
    `short_addressee_name` oddaje None. Zdanie ma wtedy zostać zdaniem, a nie
    urwać się na dwukropku ani wypisać „None"."""
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000235', 'WYS/000236', 'WYS/000237'))

    with app.test_request_context():
        msgs = EmailManager.build_delivery_autoclosed_message(zbiorcze)

    mail_drugiego = {m.recipients[0]: m for m in msgs}['drugi@example.com']
    assert 'wysłanej na adres innego uczestnika' in mail_drugiego.html
    assert 'None' not in mail_drugiego.html


def test_uczestnik_bez_konta_jest_pomijany_a_reszta_dostaje_mail(app, db, make_user, make_order):
    """Wariant brzegowy z poprzedniej rundy zostaje domknięty: uczestnik bez konta
    (albo bez adresu) jest POMIJANY, bez fallbacku na adres z zamówienia — dla paczki
    zbiorczej taki adres może należeć do zupełnie innej osoby. Reszta uczestników
    dostaje swoje maile normalnie, zamiast tracić powiadomienie przez cudzy brak.

    Na mailu o domknięciu, nie na przypomnieniu: przypomnienie idzie dziś wyłącznie
    do lidera, więc usunięcie jego konta zostawiałoby zero wiadomości i test nie
    mówiłby już nic o pomijaniu jednego uczestnika przy zachowaniu pozostałych.
    """
    from utils.email_manager import EmailManager

    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000225', 'WYS/000226', 'WYS/000227'))
    (lider, zrodlo_a, _), (drugi, zrodlo_b, _) = zrodla

    zrodlo_a.user_id = None  # konto lidera usunięte po konsolidacji
    db.session.commit()

    with app.test_request_context():
        msgs = EmailManager.build_delivery_autoclosed_message(zbiorcze)

    assert len(msgs) == 1
    assert msgs[0].recipients == ['drugi@example.com']


def test_paczka_zbiorcza_bez_lidera_nie_prosi_nikogo_o_potwierdzenie(
        app, db, make_user, make_order):
    """Stan awaryjny danych: paczka zbiorcza bez `lead_source_request_id`.

    Odbioru nie potwierdzi wtedy NIKT (`zlecenie_do_potwierdzenia` porównuje się
    właśnie z tym polem), więc przypomnienie nie ma adresata — zamiast rozesłać je
    do wszystkich „na wszelki wypadek" nie wysyłamy nic. Informacja o domknięciu
    działa dalej, bo ona o nic nie prosi.
    """
    from utils.email_manager import EmailManager

    zbiorcze, _ = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000245', 'WYS/000246', 'WYS/000247'))
    zbiorcze.lead_source_request_id = None
    db.session.commit()

    with app.test_request_context():
        assert EmailManager.build_delivery_confirmation_message(zbiorcze) == []
        assert len(EmailManager.build_delivery_autoclosed_message(zbiorcze)) == 2


def test_podziekowanie_za_odbior_rozroznia_lidera_od_uczestnika(
        app, db, make_user, make_order, maile_synchronicznie):
    """Sedno ustalenia 1a: „Dziękujemy za potwierdzenie" tylko temu, kto potwierdził.

    Realny render przez Jinję (mail.record_messages()), bo wada siedzi w treści
    szablonu, nie w doborze adresatów — poprzednia fala rozesłała nie-liderowi temat
    „Dziękujemy za potwierdzenie odbioru", nagłówek „Dziękujemy, X!" i zdanie
    „Odbiór paczki … został potwierdzony", czyli podziękowanie za cudze kliknięcie.
    """
    from extensions import mail
    from modules.orders.review_models import DeliveryReview
    from utils.email_manager import EmailManager

    lider = make_user(email='lider@example.com', first_name='Ola', last_name='Kowalska')
    zbiorcze, zrodla = _paczka_zbiorcza(
        db, make_user, make_order, ('WYS/000255', 'WYS/000256', 'WYS/000257'),
        user_lidera=lider)
    (_, zrodlo_a, order_a), (drugi, zrodlo_b, order_b) = zrodla

    # Ocenę wystawia lider na SWOIM zleceniu źródłowym — tak robi zapisz_ocene.
    db.session.add(DeliveryReview(
        shipping_request_id=zrodlo_a.id, user_id=lider.id, rating=5, comment='Ekspresowo'))
    db.session.commit()

    with app.test_request_context(), mail.record_messages() as outbox:
        EmailManager.notify_delivery_confirmed(zbiorcze)

    assert len(outbox) == 2, 'o odbiorze dowiadują się obaj uczestnicy'
    po_adresie = {m.recipients[0]: m for m in outbox}
    mail_lidera = po_adresie['lider@example.com']
    mail_drugiego = po_adresie['drugi@example.com']

    # Lider: podziękowanie i jego własna ocena.
    assert mail_lidera.subject == f'Dziękujemy za potwierdzenie odbioru — {zrodlo_a.request_number}'
    assert 'Dziękujemy, Ola!' in mail_lidera.html
    assert 'Twoja ocena dostawy: 5/5' in mail_lidera.html

    # Nie-lider: żadnego podziękowania za potwierdzenie i wprost powiedziane, kto
    # potwierdził. Numer zlecenia w temacie jest JEGO, nie lidera.
    assert mail_drugiego.subject == (
        f'Paczka z Twoimi zamówieniami została odebrana — {zrodlo_b.request_number}')
    assert 'Dziękujemy za potwierdzenie' not in mail_drugiego.subject
    assert 'Dziękujemy za potwierdzenie' not in mail_drugiego.html
    assert 'Dziękujemy,' not in mail_drugiego.html
    assert 'został potwierdzony' not in mail_drugiego.html
    assert 'Odbiór potwierdziła osoba, do której paczka została nadana.' in mail_drugiego.html
    assert 'Ola K.' in mail_drugiego.html
    assert 'Kowalska' not in mail_drugiego.html

    # I nadal żadnego wycieku między uczestnikami (regres po poprzedniej fali).
    assert zrodlo_b.request_number not in mail_lidera.html
    assert order_b.order_number not in mail_lidera.html
    assert 'Ekspresowo' not in mail_drugiego.html, 'cudza opinia'
    assert zrodlo_a.request_number not in mail_drugiego.html
    assert order_a.order_number not in mail_drugiego.html
    assert zbiorcze.request_number not in mail_lidera.html
    assert zbiorcze.request_number not in mail_drugiego.html


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
