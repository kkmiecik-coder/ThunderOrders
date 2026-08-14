"""EmailLog: ślad po każdym mailu — od zakolejkowania po wynik SMTP.

Powód powstania: klienci dostali PODWÓJNE maile o zmianie statusu zamówienia
z ~3 h opóźnienia (PO/00000355, EX/00001800), a system nie miał jak tego pokazać.
`send_email()` zwraca True zaraz po wystartowaniu wątku, więc „wysłane" znaczyło
tylko „zakolejkowane" — ani druga próba po zerwanym połączeniu, ani czas oczekiwania
na SMTP nie zostawiały śladu nigdzie poza logiem tekstowym serwera.

Wpis powstaje więc DWUFAZOWO: `queued` przy kolejkowaniu i `sent`/`failed` po
faktycznym wyniku SMTP, razem z licznikiem prób i czasem trwania.
"""
import smtplib

import pytest


def _log_dla(db, recipient):
    from modules.admin.models import EmailLog
    return EmailLog.query.filter_by(recipient=recipient).one()


def test_udana_wysylka_zostawia_wpis_sent(app, db, maile_synchronicznie):
    """Najprostszy przypadek: mail poszedł → jeden wpis ze statusem 'sent'."""
    from utils.email_sender import send_email

    with app.test_request_context():
        send_email(to='klient@example.com', subject='Zmiana statusu ST/1',
                   template='order_status_change', user_name='Ala',
                   order_number='ST/1', old_status='Nowe', new_status='Wysłane')

    wpis = _log_dla(db, 'klient@example.com')
    assert wpis.status == 'sent'
    assert wpis.template == 'order_status_change'
    assert wpis.subject == 'Zmiana statusu ST/1'
    assert wpis.attempts == 1
    assert wpis.sent_at is not None
    assert wpis.error is None


def test_nieudana_wysylka_zostawia_wpis_failed_z_bledem(app, db, maile_synchronicznie,
                                                        monkeypatch):
    """Trwały błąd SMTP musi zostawić 'failed' z treścią błędu, a nie ciszę."""
    from extensions import mail
    from utils.email_sender import send_email

    def _odmowa(_msg):
        raise smtplib.SMTPRecipientsRefused({'zly@example.com': (550, b'No such user')})
    monkeypatch.setattr(mail, 'send', _odmowa)

    with app.test_request_context():
        send_email(to='zly@example.com', subject='Cokolwiek',
                   template='order_status_change', user_name='Ala',
                   order_number='ST/1', old_status='Nowe', new_status='Wysłane')

    wpis = _log_dla(db, 'zly@example.com')
    assert wpis.status == 'failed'
    assert wpis.sent_at is None
    assert 'SMTPRecipientsRefused' in wpis.error


def test_ponowiona_wysylka_liczy_proby(app, db, maile_synchronicznie, monkeypatch):
    """Sedno sprawy: druga próba po zerwanym połączeniu MUSI być widoczna.

    Hostinger potrafi przyjąć wiadomość i zerwać połączenie przed odpowiedzią —
    kod uznaje to za błąd przejściowy i wysyła PONOWNIE, czyli klient dostaje
    duplikat. Bez licznika prób w bazie ta ścieżka jest nie do odróżnienia od
    dwóch niezależnych wysyłek.
    """
    from extensions import mail
    from utils.email_sender import send_email

    proby = {'n': 0}

    def _zerwij_raz(_msg):
        proby['n'] += 1
        if proby['n'] == 1:
            raise smtplib.SMTPServerDisconnected('Connection unexpectedly closed')

    monkeypatch.setattr(mail, 'send', _zerwij_raz)

    with app.test_request_context():
        send_email(to='klient@example.com', subject='Zmiana statusu ST/2',
                   template='order_status_change', user_name='Ala',
                   order_number='ST/2', old_status='Nowe', new_status='Wysłane')

    wpis = _log_dla(db, 'klient@example.com')
    assert wpis.status == 'sent'
    assert wpis.attempts == 2


def test_wpis_wiaze_sie_z_zamowieniem(app, db, make_user, make_order, maile_synchronicznie):
    """Mail o zmianie statusu musi dać się przypiąć do zamówienia (historia zmian)."""
    from utils.email_manager import EmailManager

    user = make_user(role='client', email='klient@example.com')
    order = make_order(user, status='wyslane')

    with app.test_request_context():
        EmailManager.notify_status_change(order, 'Nowe', 'Wysłane')

    wpis = _log_dla(db, 'klient@example.com')
    assert wpis.entity_type == 'order'
    assert wpis.entity_id == order.id


def test_blad_logowania_nie_wywraca_wysylki(app, db, maile_synchronicznie, monkeypatch):
    """Log jest dodatkiem — jego awaria nie może zabrać klientowi maila."""
    from extensions import mail
    import utils.email_sender as es

    monkeypatch.setattr(es, '_zaloguj_kolejkowanie',
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('baza padła')))

    with app.test_request_context():
        with mail.record_messages() as outbox:
            wynik = es.send_email(to='klient@example.com', subject='Mimo wszystko',
                                  template='order_status_change', user_name='Ala',
                                  order_number='ST/3', old_status='Nowe', new_status='Wysłane')

    assert wynik is True
    assert len(outbox) == 1


def test_batch_loguje_kazdego_odbiorce(app, db, maile_synchronicznie):
    """Paczka zbiorcza idzie jednym połączeniem — każdy uczestnik ma własny wpis."""
    from modules.admin.models import EmailLog
    from utils.email_sender import prepare_email, send_email_batch

    with app.test_request_context():
        wiadomosci = [
            prepare_email(to=adres, subject=f'Temat {i}', template='order_status_change',
                          user_name='Ala', order_number=f'ST/{i}',
                          old_status='Nowe', new_status='Wysłane',
                          log_context={'entity_type': 'order', 'entity_id': i})
            for i, adres in enumerate(['a@example.com', 'b@example.com'], start=1)
        ]
        send_email_batch(wiadomosci)

    wpisy = EmailLog.query.order_by(EmailLog.recipient).all()
    assert [w.recipient for w in wpisy] == ['a@example.com', 'b@example.com']
    assert {w.status for w in wpisy} == {'sent'}
    assert [w.entity_id for w in wpisy] == [1, 2]


def test_historia_admina_pokazuje_wyslany_mail(app, db, client, make_user, make_order,
                                               login, maile_synchronicznie):
    """Po to całe przedsięwzięcie: admin widzi w historii zamówienia, że mail poszedł.

    Przepływ jest tu prawdziwy — zmiana statusu idzie tym samym endpointem, co
    z panelu, więc test pokrywa też przekazanie kontekstu zamówienia z routingu
    aż do wpisu w bazie.
    """
    klient = make_user(role='client', email='klient@example.com')
    order = make_order(klient, status='nowe')
    login(make_user(role='admin', profile_completed=True))

    odp = client.post(f'/admin/orders/{order.id}/status', data={'status': 'wyslane'})
    assert odp.status_code == 200

    tresc = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)

    assert 'klient@example.com' in tresc
    assert 'zmiana statusu' in tresc      # type_label szablonu order_status_change
    assert 'wysłany' in tresc             # status_label


def test_historia_admina_pokazuje_nieudana_wysylke(app, db, client, make_user, make_order,
                                                   login, maile_synchronicznie, monkeypatch):
    """Nieudany mail ma być w historii widoczny JAKO nieudany, nie ukryty."""
    from extensions import mail

    def _odmowa(_msg):
        raise smtplib.SMTPRecipientsRefused({'klient@example.com': (550, b'No such user')})
    monkeypatch.setattr(mail, 'send', _odmowa)

    klient = make_user(role='client', email='klient@example.com')
    order = make_order(klient, status='nowe')
    login(make_user(role='admin', profile_completed=True))

    client.post(f'/admin/orders/{order.id}/status', data={'status': 'wyslane'})
    tresc = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)

    assert 'błąd wysyłki' in tresc


def test_historia_zamowienia_pokazuje_maile_ze_zlecenia_wysylki(app, db, client, make_user,
                                                                make_order, login):
    """Mail o paczce wisi przy zleceniu wysyłki, ale admin szuka go przy zamówieniu.

    Maile wysyłkowe („paczka wysłana", „zmiana statusu zlecenia") logują się z
    kontekstem zlecenia — bez dociągnięcia ich po powiązaniu historia zamówienia
    milczałaby akurat o tych wiadomościach, o które pyta klient.
    """
    from modules.admin.models import EmailLog
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    klient = make_user(role='client', email='klient@example.com')
    order = make_order(klient, status='wyslane')
    sr = ShippingRequest(user_id=klient.id, request_number='WYS/000999', status='wyslane')
    db.session.add(sr)
    db.session.flush()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.add(EmailLog(recipient='klient@example.com', subject='Paczka wysłana',
                            template='shipment_sent', entity_type='shipping_request',
                            entity_id=sr.id, status='sent', attempts=1))
    db.session.commit()

    login(make_user(role='admin', profile_completed=True))
    tresc = client.get(f'/admin/orders/{order.id}').get_data(as_text=True)

    assert 'paczka wysłana' in tresc


def test_historia_klienta_pomija_wpisy_techniczne(app, db, client, make_user, make_order,
                                                  login):
    """Klient nie ogląda logów technicznych w historii swojego zamówienia.

    `client_detail` renderuje KAŻDY ActivityLog danego zamówienia, a nieznanej akcji
    daje surową nazwę i ikonę 📝. Bez białej listy pierwsza nowa akcja techniczna
    wycieka klientowi na stronę.
    """
    from utils.activity_logger import log_activity

    user = make_user(role='client', email='klient@example.com')
    order = make_order(user)
    log_activity(user=None, action='email_dostarczony_wewnetrzny', entity_type='order',
                 entity_id=order.id, new_value={'recipient': 'klient@example.com'})

    login(user)
    resp = client.get(f'/client/orders/{order.id}')

    assert resp.status_code == 200
    assert b'email_dostarczony_wewnetrzny' not in resp.data
