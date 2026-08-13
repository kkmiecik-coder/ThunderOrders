"""send_email_batch: pod TESTING wysyła synchronicznie, bez wątku i bez odstępów.

Wątek uruchamiany bez daemon=True w send_email_batch() (utils/email_sender.py) jest
świadomym wyborem dla produkcji (patrz komentarz przy funkcji) — ale pod TESTING
zostawiał wątek nie-daemon dobijający się do (suppressed) SMTP, na którego
zakończenie pytest czekał przy wyjściu procesu. Ten plik pokrywa obie połowy
naprawy: pod TESTING funkcja NIE odpala Thread w ogóle (wysyła w wątku wołającego)
i NIE śpi 2 s między wiadomościami — inaczej przeniesienie wysyłki do wątku testu
zamieniłoby zawieszony proces na wolniejszy zestaw.
"""


def test_send_email_batch_pod_testing_nie_odpala_watku(app, monkeypatch):
    from extensions import mail
    from utils.email_sender import prepare_email, send_email_batch
    import utils.email_sender as es

    def _wybuchnij(*a, **kw):
        raise AssertionError(
            'send_email_batch nie powinien konstruować Thread pod TESTING')
    monkeypatch.setattr(es, 'Thread', _wybuchnij)
    # Bez podmiany time.sleep: pojedyncza wiadomość i tak nie ma po czym robić
    # odstępu, a brak odstępu w ogóle pokrywa osobny test niżej.
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


def test_send_email_batch_pod_testing_nie_spi_miedzy_mailami(app, monkeypatch):
    """Pod TESTING batch pomija też ODSTĘP między wiadomościami.

    Odstęp (SMTP_ODSTEP_MIEDZY_MAILAMI = 2 s) broni przed limitem dostawcy, ale
    TESTING włącza MAIL_SUPPRESS_SEND — sieci nie ma, więc nie ma czego limitować,
    a po przeniesieniu wysyłki do wątku wołającego te sekundy szły wprost w czas
    testu (paczka zbiorcza z N uczestnikami = (N-1) × 2 s na każdy taki test).

    Przy okazji (asercja poboczna, nie o niej jest ten test) lista dostaje None-y:
    tak wracają wiadomości z nieudanego renderu w prepare_email() i batch ma je
    odsiać zamiast wywalić się na `None.recipients`.
    """
    from extensions import mail
    from utils.email_sender import prepare_email, send_email_batch
    import utils.email_sender as es

    drzemki = []
    monkeypatch.setattr(es.time, 'sleep', lambda s: drzemki.append(s))
    monkeypatch.setitem(app.config, 'MAIL_DEFAULT_SENDER', 'noreply@thunderorders.cloud')

    def _wiadomosc(numer, adres):
        return prepare_email(
            to=adres, subject=f'Temat {numer}', template='delivery_confirmed',
            user_name='Bartek', rating=5, comment='Super', okno_edycji_dni=3,
            consolidation_note=None, request_number=f'WYS/00090{numer}',
            confirm_url=f'https://thunderorders.cloud/zlecenia/{numer}/potwierdz',
        )

    with app.test_request_context():
        wiadomosci = [_wiadomosc(1, 'pierwsza@example.com'),
                      _wiadomosc(2, 'druga@example.com'),
                      _wiadomosc(3, 'trzecia@example.com')]
        assert all(m is not None for m in wiadomosci)

        with mail.record_messages() as outbox:
            send_email_batch([None] + wiadomosci + [None])

    # Trzy maile wyszły — pominięcie odstępu nie gubi wiadomości, a None-y
    # zostały odsiane (bez filtra pętla wywala się na pierwszym z nich)...
    assert len(outbox) == 3
    assert [m.recipients[0] for m in outbox] == [
        'pierwsza@example.com', 'druga@example.com', 'trzecia@example.com']
    # ...i żadna sekunda nie została przespana (bez naprawy: [2, 2]).
    assert drzemki == []
