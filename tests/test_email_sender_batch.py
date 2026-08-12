"""send_email_batch: pod TESTING wysyła synchronicznie, bez wątku w tle.

Wątek uruchamiany bez daemon=True w send_email_batch() (utils/email_sender.py) jest
świadomym wyborem dla produkcji (patrz komentarz przy funkcji) — ale pod TESTING
zostawiał wątek nie-daemon dobijający się do (suppressed) SMTP, na którego
zakończenie pytest czekał przy wyjściu procesu. Ten plik pokrywa naprawę: pod
TESTING funkcja NIE odpala Thread w ogóle, tylko wysyła w wątku wołającego.
"""


def test_send_email_batch_pod_testing_nie_odpala_watku(app, monkeypatch):
    from extensions import mail
    from utils.email_sender import prepare_email, send_email_batch
    import utils.email_sender as es

    def _wybuchnij(*a, **kw):
        raise AssertionError(
            'send_email_batch nie powinien konstruować Thread pod TESTING')
    monkeypatch.setattr(es, 'Thread', _wybuchnij)
    # Batch śpi 2s między mailami (limit dostawcy) — w teście synchronicznym to
    # czysty przestój, więc neutralizujemy tak samo jak fixture maile_synchronicznie.
    monkeypatch.setattr(es.time, 'sleep', lambda _s: None)
    # .env w worktree ma MAIL_DEFAULT_SENDER jako pusty string ustawiony — Flask-Mail
    # odrzuca Message bez nadawcy asercją przy send() (patrz fixture maile_synchronicznie).
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

    with app.test_request_context():
        msg = prepare_email(
            to='ktos@example.com', subject='Testowy temat', template='delivery_confirmed',
            user_name='Anna', rating=None, comment=None, okno_edycji_dni=3,
            consolidation_note=None, request_number='WYS/000900',
            confirm_url='https://thunderorders.cloud/zlecenia/1/potwierdz',
        )
        assert msg is not None

        with mail.record_messages() as outbox:
            # Gdyby TESTING nie było honorowane, powyższy monkeypatch na Thread
            # rzuciłby AssertionError w tym miejscu.
            send_email_batch([msg])

    # Wysyłka faktycznie zaszła (synchronicznie) — nie zniknęła po drodze.
    assert len(outbox) == 1
    assert outbox[0].subject == 'Testowy temat'
    assert outbox[0].recipients == ['ktos@example.com']


def test_send_email_batch_pod_testing_pomija_puste_i_none(app, monkeypatch):
    """messages=None wpadają z prepare_email() po nieudanym renderze — batch ma
    je odsiać zamiast wywalić się na None.recipients."""
    from extensions import mail
    from utils.email_sender import prepare_email, send_email_batch
    import utils.email_sender as es

    monkeypatch.setattr(es.time, 'sleep', lambda _s: None)
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

    with app.test_request_context():
        msg = prepare_email(
            to='druga@example.com', subject='Drugi temat', template='delivery_confirmed',
            user_name='Bartek', rating=5, comment='Super', okno_edycji_dni=3,
            consolidation_note=None, request_number='WYS/000901',
            confirm_url='https://thunderorders.cloud/zlecenia/2/potwierdz',
        )

        with mail.record_messages() as outbox:
            send_email_batch([None, msg, None])

    assert len(outbox) == 1
    assert outbox[0].recipients == ['druga@example.com']
