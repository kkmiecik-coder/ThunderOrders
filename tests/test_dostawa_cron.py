"""Komenda cron: przypomnienia o potwierdzeniu i automatyczne domykanie."""
from datetime import timedelta


def _wyslane(db, user, numer, dni_temu):
    from modules.orders.models import ShippingRequest, get_local_now
    sr = ShippingRequest(
        request_number=numer, user_id=user.id, status='wyslane',
        shipped_at=get_local_now() - timedelta(days=dni_temu))
    db.session.add(sr)
    db.session.commit()
    return sr


def test_przypomnienie_idzie_raz(app, db, make_user, monkeypatch):
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000500', dni_temu=5)

    pierwszy = _przetworz_dostawy()
    assert pierwszy['przypomnienia'] == 1
    assert sr.delivery_reminder_sent_at is not None

    drugi = _przetworz_dostawy()
    assert drugi['przypomnienia'] == 0


def test_nieudana_wysylka_nie_znaczy_zlecenia(app, db, make_user, monkeypatch):
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [False] * len(msgs))

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000501', dni_temu=5)

    _przetworz_dostawy()

    assert sr.delivery_reminder_sent_at is None


def test_przypomnienia_ida_porcjami(app, db, make_user, monkeypatch):
    """Recenzja całościowa (C2): faza 1 robiła `.all()` bez limitu, podczas gdy porcja
    (`autocomplete_batch`) chroniła wyłącznie fazę 2. Backfill uzupełnia shipped_at
    całej historii w TYM SAMYM przebiegu, więc pierwszy cron po wdrożeniu wysłałby
    przypomnienie do każdej paczki wysłanej od kwietnia: send_email_batch_sync śpi 2 s
    między mailami (2N sekund przebiegu), znacznik delivery_reminder_sent_at zapisuje
    się dopiero po całym batchu (kolejny cron zaczyna od nieoznaczonych i wysyła
    wszystko drugi raz), jedno połączenie SMTP trzymane kilkadziesiąt minut zerwie
    Hostinger, a w tej samej pętli leci N wątków pusha."""
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    Settings.set_value('delivery_autocomplete_enabled', False, type='boolean')
    db.session.commit()
    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    # Pięciu kandydatów, porcja 2 — najstarsze idą pierwsze.
    zlecenia = [_wyslane(db, user, f'WYS/00056{i}', dni_temu=10 - i) for i in range(5)]

    wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 2
    assert [z.delivery_reminder_sent_at is not None for z in zlecenia] == [
        True, True, False, False, False]


def test_faza1_pomija_zlecenia_ktore_zaraz_domknie_automat(app, db, make_user, monkeypatch):
    """Druga część C2: paczka starsza niż autocomplete_days kwalifikuje się już do
    fazy 2. Przypominanie o niej to szum — bez tego warunku pierwsi klienci dostawali
    „czy paczka dotarła?" i „zamykamy zlecenie" w odstępie minut."""
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    swieze = _wyslane(db, user, 'WYS/000570', dni_temu=5)
    stare = _wyslane(db, user, 'WYS/000571', dni_temu=40)

    with app.test_request_context():
        wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 1
    assert swieze.delivery_reminder_sent_at is not None
    assert stare.delivery_reminder_sent_at is None
    assert stare.status == 'dostarczone'


def test_faza1_nie_pomija_starych_gdy_automat_wylaczony(app, db, make_user, monkeypatch):
    """Odwrotna strona poprzedniego warunku: przy WYŁĄCZONYM automacie faza 2 nie
    ruszy, więc bezwarunkowe pomijanie starych paczek zostawiłoby je zupełnie bez
    przypomnienia — najstarsze zaległości zniknęłyby po cichu z obu faz."""
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_autocomplete_enabled', False, type='boolean')
    db.session.commit()
    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    stare = _wyslane(db, user, 'WYS/000575', dni_temu=40)

    wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 1
    assert stare.delivery_reminder_sent_at is not None


def test_wylaczony_przelacznik_wstrzymuje_faze(app, db, make_user, monkeypatch):
    from modules.auth.models import Settings
    from app import _przetworz_dostawy

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_enabled', False, type='boolean')
    db.session.commit()

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000502', dni_temu=40)

    wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 0
    assert wynik['domkniete'] == 0
    assert sr.status == 'wyslane'


def test_automat_domyka_najstarsze_w_ramach_porcji(app, db, make_user, monkeypatch):
    from modules.auth.models import Settings
    from app import _przetworz_dostawy

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    db.session.commit()
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    stare = [_wyslane(db, user, f'WYS/00051{i}', dni_temu=40 - i) for i in range(4)]

    # test_request_context: ta ścieżka nie mockuje build_delivery_autoclosed_message,
    # więc realny kod treści maila woła url_for(..., _external=True) — poza kontekstem
    # żądania to RuntimeError (brak SERVER_NAME), tak samo jak w innych testach maili
    # dostawy (patrz tests/test_dostawa_maile.py). W produkcji _przetworz_dostawy zawsze
    # działa wewnątrz request contextu, bo komenda CLI owija ją w _with_request_context.
    with app.test_request_context():
        wynik = _przetworz_dostawy()

    assert wynik['domkniete'] == 2
    assert stare[0].status == 'dostarczone'
    assert stare[1].status == 'dostarczone'
    assert stare[2].status == 'wyslane'
    assert stare[3].status == 'wyslane'


def test_zrodla_paczki_zbiorczej_pomijane(app, db, make_user, monkeypatch):
    from modules.auth.models import Settings
    from app import _przetworz_dostawy

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    db.session.commit()
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    lider = make_user()
    zbiorcze = _wyslane(db, lider, 'WYS/000520', dni_temu=40)
    zrodlo = _wyslane(db, lider, 'WYS/000521', dni_temu=40)
    zrodlo.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = zrodlo.id
    db.session.commit()

    with app.test_request_context():
        wynik = _przetworz_dostawy()

    # Domknięte zostaje tylko zlecenie zbiorcze; źródłowe dostaje status propagacją.
    assert wynik['domkniete'] == 1
    assert zbiorcze.status == 'dostarczone'
    assert zrodlo.status == 'dostarczone'


def test_domkniecie_automatem_nie_powiadamia_adminow(app, db, make_user, monkeypatch):
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    db.session.commit()

    do_adminow = []
    monkeypatch.setattr(
        EmailManager, 'notify_admin_delivery_confirmed',
        staticmethod(lambda sr: do_adminow.append('mail')))
    monkeypatch.setattr(
        PushManager, 'notify_admin_delivery_confirmed',
        staticmethod(lambda sr: do_adminow.append('push')))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    _wyslane(db, user, 'WYS/000530', dni_temu=40)

    with app.test_request_context():
        _przetworz_dostawy()

    assert do_adminow == []


def test_dry_run_nic_nie_zmienia(app, db, make_user, monkeypatch):
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))

    user = make_user()
    # Dwa zlecenia, bo od naprawy C2 fazy nie zachodzą już na siebie: paczka starsza
    # niż autocomplete_days idzie WYŁĄCZNIE do domknięcia, świeższa wyłącznie do
    # przypomnienia. Dry-run ma pokazać obie liczby i nie ruszyć żadnego rekordu.
    swieze = _wyslane(db, user, 'WYS/000540', dni_temu=5)
    stare = _wyslane(db, user, 'WYS/000541', dni_temu=40)

    wynik = _przetworz_dostawy(dry_run=True)

    assert wynik['przypomnienia'] == 1
    assert wynik['domkniete'] == 1
    assert swieze.status == 'wyslane'
    assert stare.status == 'wyslane'
    assert swieze.delivery_reminder_sent_at is None


def test_dry_run_widzi_zaleglosc_ktora_wymaga_backfillu(app, db, make_user, monkeypatch):
    """Zlecenie z shipped_at=NULL (jak cała historia sprzed wdrożenia) musi się
    pokazać w liczbach --dry-run, żeby dry-run miał w ogóle sens jako podgląd skali
    zaległości przed włączeniem crona. Backfill w trybie dry_run robi flush (widoczny
    w tej transakcji), nie commit — po przebiegu shipped_at ma zostać z powrotem
    puste, bo flush bez commit nigdy nie trafia trwale do bazy, a funkcja na końcu
    woła rollback().
    """
    from modules.admin.models import ActivityLog
    from modules.orders.models import ShippingRequest, get_local_now
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))

    user = make_user()
    # W przeciwieństwie do _wyslane() celowo BEZ shipped_at — to jest dokładnie
    # kształt danych historycznych, których dotyczy backfill. Dwa rekordy o różnym
    # wieku, bo od naprawy C2 przypomnienie i domknięcie dotyczą rozłącznych zakresów.
    zlecenia = []
    for numer, dni in (('WYS/000550', 40), ('WYS/000551', 5)):
        sr = ShippingRequest(request_number=numer, user_id=user.id, status='wyslane')
        db.session.add(sr)
        db.session.commit()
        db.session.add(ActivityLog(
            action='shipping_request_shipped', entity_type='shipping_request',
            entity_id=sr.id, created_at=get_local_now() - timedelta(days=dni)))
        db.session.commit()
        zlecenia.append(sr)

    # potwierdzenie stanu wyjściowego przed dry-run
    assert all(sr.shipped_at is None for sr in zlecenia)

    wynik = _przetworz_dostawy(dry_run=True)

    assert wynik['backfill']['z_logu'] == 2
    assert wynik['przypomnienia'] >= 1
    assert wynik['domkniete'] >= 1

    assert all(sr.shipped_at is None for sr in zlecenia)
    assert all(sr.status == 'wyslane' for sr in zlecenia)
