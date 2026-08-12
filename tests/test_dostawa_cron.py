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
        staticmethod(lambda sr: object()))
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
        staticmethod(lambda sr: object()))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [False] * len(msgs))

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000501', dni_temu=5)

    _przetworz_dostawy()

    assert sr.delivery_reminder_sent_at is None


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
        staticmethod(lambda sr: object()))

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000540', dni_temu=40)

    wynik = _przetworz_dostawy(dry_run=True)

    assert wynik['przypomnienia'] >= 1
    assert sr.status == 'wyslane'
    assert sr.delivery_reminder_sent_at is None


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
        staticmethod(lambda sr: object()))

    user = make_user()
    # W przeciwieństwie do _wyslane() celowo BEZ shipped_at — to jest dokładnie
    # kształt danych historycznych, których dotyczy backfill.
    sr = ShippingRequest(request_number='WYS/000550', user_id=user.id, status='wyslane')
    db.session.add(sr)
    db.session.commit()
    db.session.add(ActivityLog(
        action='shipping_request_shipped', entity_type='shipping_request',
        entity_id=sr.id, created_at=get_local_now() - timedelta(days=40)))
    db.session.commit()

    assert sr.shipped_at is None  # potwierdzenie stanu wyjściowego przed dry-run

    wynik = _przetworz_dostawy(dry_run=True)

    assert wynik['backfill']['z_logu'] == 1
    assert wynik['przypomnienia'] >= 1
    assert wynik['domkniete'] >= 1

    assert sr.shipped_at is None
    assert sr.status == 'wyslane'
