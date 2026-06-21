"""
Testy batch'owej wysyłki przypomnień o płatności.

Regresja dla błędów SMTP 'too many AUTH commands' (450) / 'too many connections' (421)
z Hostingera: przypomnienia muszą iść JEDNYM połączeniem SMTP (jeden AUTH), a nie
osobnym połączeniem per email.
"""
import smtplib
from unittest.mock import MagicMock

from flask_mail import Message

import utils.email_sender as es


class FakeConn:
    """Atrapa połączenia SMTP (kontekst-manager) zliczająca wysłane wiadomości."""

    def __init__(self):
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, msg):
        self.sent.append(msg)


def _make_msg(to):
    return Message(subject='Test', recipients=[to],
                   sender='noreply@thunderorders.cloud', body='body')


def test_batch_sync_uses_single_connection(app, monkeypatch):
    """N maili = JEDNO połączenie SMTP (jeden AUTH), wszystkie wysłane."""
    with app.app_context():
        conn = FakeConn()
        connect_mock = MagicMock(return_value=conn)
        monkeypatch.setattr(es.mail, 'connect', connect_mock)
        monkeypatch.setattr(es.time, 'sleep', lambda *_: None)  # pomiń opóźnienia 2s

        msgs = [_make_msg(f'u{i}@example.com') for i in range(5)]
        results = es.send_email_batch_sync(msgs)

        assert connect_mock.call_count == 1  # jeden AUTH, nie pięć
        assert len(conn.sent) == 5
        assert results == [True] * 5


def test_batch_sync_returns_per_message_results(app, monkeypatch):
    """Wynik jest zgodny kolejnościowo z messages; porażka jednego nie blokuje reszty."""
    with app.app_context():
        class Conn(FakeConn):
            def send(self, msg):
                if msg.recipients == ['bad@example.com']:
                    raise smtplib.SMTPRecipientsRefused({'bad@example.com': (550, b'no')})
                self.sent.append(msg)

        monkeypatch.setattr(es.mail, 'connect', MagicMock(return_value=Conn()))
        monkeypatch.setattr(es.time, 'sleep', lambda *_: None)

        msgs = [_make_msg('ok1@example.com'),
                _make_msg('bad@example.com'),
                _make_msg('ok2@example.com')]
        results = es.send_email_batch_sync(msgs)

        assert results == [True, False, True]


def test_batch_sync_retries_transient_error(app, monkeypatch):
    """Błąd przejściowy jest ponawiany do SMTP_MAX_RETRIES razy, potem porażka."""
    with app.app_context():
        class Conn(FakeConn):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def send(self, msg):
                self.calls += 1
                raise smtplib.SMTPServerDisconnected('boom')

        conn = Conn()
        monkeypatch.setattr(es.mail, 'connect', MagicMock(return_value=conn))
        monkeypatch.setattr(es.time, 'sleep', lambda *_: None)

        results = es.send_email_batch_sync([_make_msg('a@example.com')])

        assert results == [False]
        assert conn.calls == es.SMTP_MAX_RETRIES


def test_batch_sync_empty_list(app):
    """Pusta lista nie tworzy połączenia i zwraca pustą listę wyników."""
    with app.app_context():
        assert es.send_email_batch_sync([]) == []
