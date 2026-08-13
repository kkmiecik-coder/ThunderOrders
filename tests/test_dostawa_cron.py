"""Komenda cron: przypomnienia o potwierdzeniu i automatyczne domykanie."""
from datetime import timedelta

import pytest


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


def test_faza1_nie_wymaga_user_id_na_zleceniu(app, db, make_user, monkeypatch):
    """Dług #2 (G4-cron): faza przypomnień wymagała ShippingRequest.user_id IS NOT
    NULL, faza domykania nie — rozjazd, mimo że to warstwa mailowa
    (_adresat_zlecenia / _odbiorcy_dostawy), nie SQL, decyduje kto faktycznie
    dostanie maila. Kierunek naprawy: usuwamy filtr z fazy 1, bo dla zwykłego
    zlecenia z usuniętym kontem ta warstwa i tak schodzi na e-mail z zamówienia —
    SQL wykluczał więc kandydatów, którym mail i tak by poszedł."""
    from app import _przetworz_dostawy
    from modules.orders.models import ShippingRequest, get_local_now
    from utils.email_manager import EmailManager

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: [object()]))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    # user_id=None: dokładnie stan po ON DELETE SET NULL, gdy konto właściciela
    # zlecenia (albo lidera paczki zbiorczej) zostaje skasowane.
    sr = ShippingRequest(
        request_number='WYS/000580', user_id=None, status='wyslane',
        shipped_at=get_local_now() - timedelta(days=5))
    db.session.add(sr)
    db.session.commit()

    wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 1
    assert sr.delivery_reminder_sent_at is not None


def test_kandydat_bez_odbiorcy_nie_wraca_bezterminowo(app, db, make_user, monkeypatch):
    """Dług #5: gdy dla kandydata NIE MA odbiorcy, delivery_reminder_sent_at musi
    mimo to zostać ustawiony — inaczej wraca w KAŻDYM kolejnym przebiegu, logując to
    samo ostrzeżenie i zajmując miejsce w porcji bezterminowo (szczególnie przy
    wyłączonym automacie, bo faza 2 nigdy go nie domknie).

    Zlecenie bez konta (ON DELETE SET NULL) i bez zamówienia, z którego dałoby się
    wziąć adres — `_adresat_zlecenia` oddaje wtedy (None, None). To prawdziwy brak
    odbiorcy, nie zaślepka: build_delivery_confirmation_message idzie tu realną
    ścieżką i sam stwierdza, że nie ma do kogo pisać. Dla przyczyn ODWRACALNYCH
    (wyłączony przełącznik, błąd renderu) znacznika stawiać nie wolno — patrz dwa
    testy niżej."""
    from app import _przetworz_dostawy
    from modules.orders.models import ShippingRequest, get_local_now
    from utils.email_manager import EmailManager

    sr = ShippingRequest(
        request_number='WYS/000581', user_id=None, status='wyslane',
        shipped_at=get_local_now() - timedelta(days=5))
    db.session.add(sr)
    db.session.commit()

    pierwszy = _przetworz_dostawy()
    assert pierwszy['przypomnienia'] == 0
    assert sr.delivery_reminder_sent_at is not None

    # Drugi przebieg: kandydat nie wraca, bo delivery_reminder_sent_at IS NOT NULL
    # go już wyklucza z zapytania fazy 1 — build_* w ogóle nie jest wywoływane.
    wywolania = []
    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message',
        staticmethod(lambda sr: wywolania.append(sr) or []))
    _przetworz_dostawy()
    assert wywolania == []


def test_kandydat_bez_odbiorcy_nie_znaczony_gdy_maile_wylaczone_globalnie(
        app, db, make_user, monkeypatch):
    """Wyłączony globalnie mail o potwierdzeniu nie może zostawić po sobie trwałego
    znacznika: to stan ODWRACALNY, a `delivery_reminder_sent_at` okradłby zlecenie
    z przypomnienia na zawsze, także po ponownym włączeniu powiadomienia.

    Test pilnuje SKUTKU (brak znacznika), nie mechanizmu, którym się go osiąga —
    dziś dają go dwa niezależne mechanizmy naraz: warunek wejścia do fazy w app.py
    i rozstrzyganie po `_jest_komu_przypomniec` w środku. Sam warunek wejścia
    (i to, czym płacimy za jego brak) pokrywa
    test_wylaczony_globalnie_mail_nie_wchodzi_w_faze_przypomnien niżej — dawna wersja
    tego docstringa przypisywała tę rolę temu testowi, choć przy włączonym strażniku
    gałąź „trzech przyczyn pustej listy" w ogóle się tu nie wykonuje."""
    import json
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    Settings.set_value(
        'email_notifications_config',
        json.dumps({'notify_delivery_confirmation': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000582', dni_temu=5)

    wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 0
    assert sr.delivery_reminder_sent_at is None


def test_wylaczony_globalnie_mail_nie_wchodzi_w_faze_przypomnien(
        app, db, make_user, monkeypatch, caplog):
    """Globalny przełącznik `notify_delivery_confirmation` jest warunkiem WEJŚCIA do
    fazy 1, a nie tylko filtrem w środku — i tego nie pilnował żaden test (zdjęcie
    warunku zostawiało 21 z 21 testów crona zielonych).

    Bez strażnika faza mieli całą zaległość: dla każdego kandydata woła build_*, ten
    oddaje pustą listę (powiadomienie wyłączone), a że odbiorca ISTNIEJE, kod schodzi
    w gałąź „prepare_email nie oddał wiadomości" i loguje ERROR wskazujący na błąd
    renderu szablonu — fałszywą diagnozę, po jednej linii na każde zlecenie, dla kogoś
    kto czyta log produkcyjny. Stąd dwie asercje: faza nie ma prawa tknąć build_*
    ani zostawić po sobie takiego ERROR-a."""
    import json
    import logging
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    Settings.set_value(
        'email_notifications_config',
        json.dumps({'notify_delivery_confirmation': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()

    prawdziwy_build = EmailManager.build_delivery_confirmation_message
    wywolania = []

    def szpieg(sr):
        wywolania.append(sr.request_number)
        return prawdziwy_build(sr)

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message', staticmethod(szpieg))

    user = make_user()
    _wyslane(db, user, 'WYS/000583', dni_temu=5)

    with caplog.at_level(logging.ERROR):
        _przetworz_dostawy()

    assert wywolania == [], (
        'przy wyłączonym mailu faza 1 nie ma prawa w ogóle wołać build_* — '
        f'zawołała dla: {wywolania}')
    falszywe = [r for r in caplog.records
                if 'prepare_email nie oddał wiadomości' in r.getMessage()]
    assert falszywe == [], (
        'wyłączony przez admina przełącznik nie jest awarią renderu — ERROR o '
        f'prepare_email to fałszywa diagnoza: {[r.getMessage() for r in falszywe]}')


def test_dry_run_rollback_gwarantowany_mimo_wyjatku_w_fazie(app, db, make_user, monkeypatch):
    """Dług #3: rollback w --dry-run stał POZA try/finally — bezpieczny wyłącznie
    dzięki teardownowi kontekstu Flaska w _with_request_context. Ten test woła
    _przetworz_dostawy() bez takiego kontekstu i wymusza wyjątek W TRAKCIE fazy 1,
    więc jedyne, co może cofnąć flush z backfillu, to gwarancja w samej funkcji."""
    from app import _przetworz_dostawy
    from modules.orders.models import ShippingRequest, get_local_now
    from utils.email_manager import EmailManager

    user = make_user()
    # Bez shipped_at, ale z updated_at cofniętym o 5 dni: dokładnie to, co backfill
    # (flush, nie commit, w dry-run) uzupełnia z ostatniej deski ratunku kaskady —
    # i wystarczająco stare, żeby zlecenie trafiło do kandydatów fazy 1.
    sr = ShippingRequest(request_number='WYS/000590', user_id=user.id, status='wyslane')
    db.session.add(sr)
    db.session.commit()
    sr.updated_at = get_local_now() - timedelta(days=5)
    db.session.commit()
    assert sr.shipped_at is None

    def wybuchnij(_sr):
        raise RuntimeError('symulowana awaria budowania wiadomości')

    monkeypatch.setattr(
        EmailManager, 'build_delivery_confirmation_message', staticmethod(wybuchnij))

    with pytest.raises(RuntimeError):
        _przetworz_dostawy(dry_run=True)

    # Gdyby rollback nie zadziałał, flush z backfillu (shipped_at ustawione w tej
    # samej transakcji) przeżyłby wyjątek — w tym teście nic nie sprząta po sobie
    # kontekstu Flaska, więc jedyna gwarancja to try/finally w samej funkcji.
    assert sr.shipped_at is None


def test_blad_renderu_nie_znaczy_przypomnienia_jako_wyslanego(app, db, make_user, monkeypatch):
    """O5: `prepare_email()` oddaje None TAKŻE przy błędzie renderu szablonu, a
    build_* odfiltrowuje None-y — pusta lista, mimo że odbiorca istnieje i przełącznik
    jest włączony. Rozstrzyganie po samej pustej liście stawiało wtedy znacznik
    „przypomnienie wysłane" i kasowało zlecenie z kolejki NA ZAWSZE, choć przyczyna
    jest odwracalna. To dokładne przeciwieństwo polityki przy nieudanej WYSYŁCE, gdzie
    świadomie wybieramy duplikat zamiast cichej utraty (patrz
    test_nieudana_wysylka_nie_znaczy_zlecenia)."""
    from app import _przetworz_dostawy
    from utils import email_sender

    prawdziwy_prepare = email_sender.prepare_email
    render_pada = {'tak': True}
    monkeypatch.setattr(
        'utils.email_sender.prepare_email',
        lambda **kw: None if render_pada['tak'] else prawdziwy_prepare(**kw))
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    sr = _wyslane(db, user, 'WYS/000620', dni_temu=5)

    # test_request_context: idziemy realną ścieżką budowania maila, a ta woła
    # url_for(..., _external=True) — tak samo jak w produkcji pod _with_request_context.
    with app.test_request_context():
        pierwszy = _przetworz_dostawy()

    assert pierwszy['przypomnienia'] == 0
    assert sr.delivery_reminder_sent_at is None, (
        'błąd renderu to stan przejściowy — znacznik oznaczałby cichą, trwałą utratę')

    # Po ustaniu przyczyny kandydat MUSI wrócić — to jest cały sens braku znacznika.
    render_pada['tak'] = False
    with app.test_request_context():
        drugi = _przetworz_dostawy()

    assert drugi['przypomnienia'] == 1
    assert sr.delivery_reminder_sent_at is not None


def _paczka_zbiorcza_wyslana(db, make_user, numer_paczki, numery_zrodel, dni_temu):
    """Paczka zbiorcza N klientów, każdy z własnym kontem i adresem.

    Bez zamówień: `consolidation_participants` bierze uczestników z
    `consolidated_sources`, a lista zamówień nie wpływa na liczbę wiadomości —
    `_odbiorcy_dostawy` oddaje po jednej pozycji na uczestnika z kontem i e-mailem.
    Zwraca (zbiorcze, [zrodla]); pierwsze źródło jest wiodące, tak jak ustawia to
    konsolidacja w WMS.
    """
    from modules.orders.models import ShippingRequest, get_local_now

    zbiorcze = ShippingRequest(
        request_number=numer_paczki, status='wyslane',
        shipped_at=get_local_now() - timedelta(days=dni_temu))
    db.session.add(zbiorcze)
    db.session.commit()

    zrodla = []
    for i, numer in enumerate(numery_zrodel):
        user = make_user(email=f'uczestnik{i}-{numer[-6:]}@example.com')
        zrodlo = ShippingRequest(
            request_number=numer, user_id=user.id, status='wyslane',
            shipped_at=get_local_now() - timedelta(days=dni_temu),
            consolidated_into_id=zbiorcze.id)
        db.session.add(zrodlo)
        db.session.commit()
        zrodla.append(zrodlo)

    # _kopiuj_adres przy konsolidacji ustawia zbiorcze.user_id = user_id lidera.
    zbiorcze.user_id = zrodla[0].user_id
    zbiorcze.lead_source_request_id = zrodla[0].id
    db.session.commit()
    assert zbiorcze.is_consolidation
    return zbiorcze, zrodla


def test_rozstrzyganie_odbiorcy_nie_dubluje_ostrzezen(app, db, make_user, monkeypatch, caplog):
    """Ścieżka „odbiorca jest, ale wiadomość się nie złożyła" wołała
    EmailManager._odbiorcy_dostawy DRUGI raz w tym samym przebiegu — pierwszy raz
    zrobiło to build_delivery_confirmation_message linię wyżej. Ta funkcja nie jest
    ani darmowa, ani cicha: buduje od nowa kontekst każdego adresata (url_for
    _external=True) i loguje WARNING o każdym uczestniku paczki bez adresu e-mail.
    Efekt: te same ostrzeżenia dwa razy pod rząd, czyli fałszywy trop dla kogoś, kto
    diagnozuje produkcję po logu."""
    import logging
    from app import _przetworz_dostawy

    monkeypatch.setattr('utils.email_sender.prepare_email', lambda **kw: None)
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    zbiorcze, zrodla = _paczka_zbiorcza_wyslana(
        db, make_user, 'WYS/000650', ('WYS/000651', 'WYS/000652'), dni_temu=5)
    # Drugi uczestnik traci konto (ON DELETE SET NULL na user_id) — to o nim
    # _odbiorcy_dostawy loguje ostrzeżenie. Lider (pierwsze źródło) konto zachowuje,
    # więc odbiorca ISTNIEJE i wchodzimy dokładnie w tę gałąź.
    zrodla[1].user_id = None
    db.session.commit()

    with app.test_request_context(), caplog.at_level(logging.WARNING):
        wynik = _przetworz_dostawy()

    assert wynik['przypomnienia'] == 0
    assert zbiorcze.delivery_reminder_sent_at is None, (
        'nieudane złożenie wiadomości jest odwracalne — znacznik byłby cichą utratą')
    ostrzezenia = [r for r in caplog.records
                   if 'bez adresu e-mail' in r.getMessage()]
    assert len(ostrzezenia) == 1, (
        f'uczestnik bez adresu ma dać JEDNO ostrzeżenie na przebieg, dostaliśmy '
        f'{len(ostrzezenia)}: {[r.getMessage() for r in ostrzezenia]}')


def test_porcja_fazy2_liczy_wiadomosci_paczki_zbiorczej(app, db, make_user, monkeypatch):
    """O6: porcja fazy 2 to limit PODWÓJNY, a jedyny test, jaki miała, używał czterech
    zwykłych zleceń po jednej wiadomości — nie odróżniał limitu na zlecenia od limitu
    na wiadomości, więc cofnięcie całej zmiany zostawiało zestaw zielony.

    Paczka zbiorcza z trzema uczestnikami to trzy maile w jednym batchu SMTP (2 s
    odstępu między wiadomościami), więc przy porcji 2 wyczerpuje ją sama, a zlecenie
    stojące za nią w kolejce ma poczekać na następny przebieg. Limit liczący wyłącznie
    zlecenia domknąłby oba."""
    from modules.auth.models import Settings
    from app import _przetworz_dostawy

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    db.session.commit()
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    zbiorcze, zrodla = _paczka_zbiorcza_wyslana(
        db, make_user, 'WYS/000600',
        ('WYS/000601', 'WYS/000602', 'WYS/000603'), dni_temu=40)
    # Młodsze o dzień, więc w kolejce (shipped_at rosnąco) stoi ZA paczką zbiorczą.
    kolejne = _wyslane(db, make_user(), 'WYS/000604', dni_temu=39)

    with app.test_request_context():
        wynik = _przetworz_dostawy()

    assert wynik['domkniete'] == 1
    assert zbiorcze.status == 'dostarczone'
    assert all(z.status == 'dostarczone' for z in zrodla), 'propagacja na źródła'
    assert kolejne.status == 'wyslane', (
        'trzy maile paczki zbiorczej wyczerpały porcję 2 — to zlecenie idzie '
        'w następnym przebiegu')


def test_porcja_fazy2_obowiazuje_gdy_nie_powstaje_zadna_wiadomosc(
        app, db, make_user, monkeypatch):
    """O1 (krytyczne): naprawa z pierwszej fali zamieniła twardy `.limit()` w SQL na
    licznik WYSŁANYCH wiadomości. Gdy zlecenia nie produkują wiadomości — bo admin
    wyłączył notify_delivery_autoclosed albo nie ma odbiorcy z adresem — licznik
    zostaje na zerze, `break` nigdy nie strzela i jeden przebieg przerabia CAŁĄ
    zaległość. Każda iteracja to dostarcz_zlecenie() (status, propagacja, kaskada na
    zamówienia, kolekcja, commit) plus push, a pierwszy przebieg po wdrożeniu widzi
    ~1800 zaległych zleceń."""
    import json
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    Settings.set_value(
        'email_notifications_config',
        json.dumps({'notify_delivery_autoclosed': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()

    pushe = []
    monkeypatch.setattr(
        PushManager, 'notify_delivery_autoclosed',
        staticmethod(lambda sr: pushe.append(sr.request_number)))

    user = make_user()
    zlecenia = [_wyslane(db, user, f'WYS/00061{i}', dni_temu=40 - i) for i in range(6)]

    with app.test_request_context():
        wynik = _przetworz_dostawy()

    assert wynik['domkniete'] == 2
    assert [z.status for z in zlecenia] == [
        'dostarczone', 'dostarczone', 'wyslane', 'wyslane', 'wyslane', 'wyslane']
    assert len(pushe) == 2, 'burza pushy do klientów jest częścią tej samej regresji'


def test_porcja_fazy2_nie_zakleszcza_sie_na_zleceniach_z_delivered_at(
        app, db, make_user, monkeypatch):
    """Regresja po przywróceniu `.limit()` (druga fala): zapytanie fazy 2 brało N
    najstarszych zleceń o statusie `wyslane`, ale NIE pytało o delivered_at — a
    strażnik w dostarcz_zlecenie() odrzuca każde zlecenie z ustawionym delivered_at
    niezależnie od statusu. Takie zlecenie zjadało miejsce w porcji i wracało
    w KAŻDYM przebiegu, bo delivered_at nie jest w całym repo nigdzie zerowane.
    Kolejka idzie shipped_at ASC, więc blokery osiadają na czele: przy ich liczbie
    równej porcji automat domykał zero i nie ruszał się już nigdy, zostawiając
    w logu wyłącznie INFO „Pominięto…".

    Stan „wyslane + delivered_at" nie jest wymysłem testu: ship_shipping_request()
    odrzuca tylko status `wyslane` i statusy nieopłacone, więc paczka zwrócona
    i nadana ponownie przechodzi przez nią ze statusu `dostarczone`, dostaje świeży
    shipped_at i ZACHOWUJE stary delivered_at. Druga droga to admin cofający status
    zleceniu przez PUT."""
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from modules.orders.models import get_local_now

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    db.session.commit()
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    user = make_user()
    # Dwa blokery na CZELE kolejki (najstarsze) — dokładnie tyle, ile wynosi porcja.
    blokery = [_wyslane(db, user, f'WYS/00064{i}', dni_temu=40 - i) for i in range(2)]
    for bloker in blokery:
        bloker.delivered_at = get_local_now() - timedelta(days=30)
    db.session.commit()
    # Prawdziwy kandydat stoi ZA nimi (młodszy o dwa dni).
    kandydat = _wyslane(db, user, 'WYS/000642', dni_temu=38)

    with app.test_request_context():
        wynik = _przetworz_dostawy()

    assert wynik['domkniete'] == 1
    assert kandydat.status == 'dostarczone', (
        'blokery z ustawionym delivered_at zjadły całą porcję — automat stanął '
        'i nie ruszy się już nigdy, bo one wracają w każdym przebiegu')
    assert [b.status for b in blokery] == ['wyslane', 'wyslane'], (
        'blokerów nie ruszamy — filtr ma je omijać, a nie naprawiać ich stan')


def test_dry_run_pokazuje_tyle_ile_domknie_realny_przebieg(app, db, make_user, monkeypatch):
    """Podgląd jest krokiem bezpieczeństwa z instrukcji wdrożenia, więc musi zgadzać
    się z przebiegiem realnym. Liczył jednak wiadomości tak, jakby mail był zawsze
    włączony i jakby pisał do KAŻDEGO uczestnika paczki — przy wyłączonym przełączniku
    pokazywał mniej zleceń, niż automat by domknął.

    Scenariusz jest dobrany tak, żeby ROZRÓŻNIAĆ stary licznik od nowego, a nie tylko
    padać z jakiegokolwiek powodu: paczka zbiorcza z trzema uczestnikami na czele
    kolejki, wyłączony notify_delivery_autoclosed, porcja 2. Stary licznik dopisywał
    3 wiadomości niezależnie od przełącznika, wyczerpywał budżet już na pierwszym
    zleceniu i pokazywał 1 — a realny przebieg nie wysyła nic, więc domyka 2.
    Pierwsza wersja tego testu używała sześciu zwykłych zleceń, gdzie stary licznik
    (1 na zlecenie) i nowy (0, bo mail wyłączony) przy porcji 2 dają tę samą liczbę,
    więc przywrócenie starego bloku podglądu zostawiało ją zieloną."""
    import json
    from modules.auth.models import Settings
    from app import _przetworz_dostawy
    from utils.email_manager import EmailManager

    Settings.set_value('delivery_reminder_enabled', False, type='boolean')
    Settings.set_value('delivery_autocomplete_batch', 2, type='integer')
    Settings.set_value(
        'email_notifications_config',
        json.dumps({'notify_delivery_autoclosed': False}), type='json')
    db.session.commit()
    EmailManager.clear_email_config_cache()
    monkeypatch.setattr(
        'utils.email_sender.send_email_batch_sync', lambda msgs: [True] * len(msgs))

    zbiorcze, zrodla = _paczka_zbiorcza_wyslana(
        db, make_user, 'WYS/000630',
        ('WYS/000631', 'WYS/000632', 'WYS/000633'), dni_temu=40)
    # Młodsze o dzień, więc w kolejce (shipped_at rosnąco) stoi ZA paczką zbiorczą.
    kolejne = _wyslane(db, make_user(), 'WYS/000634', dni_temu=39)

    podglad = _przetworz_dostawy(dry_run=True)
    assert zbiorcze.status == 'wyslane' and kolejne.status == 'wyslane', (
        'dry-run niczego nie zmienia')

    with app.test_request_context():
        realny = _przetworz_dostawy()

    assert podglad['domkniete'] == realny['domkniete'] == 2
    assert kolejne.status == 'dostarczone', (
        'przy wyłączonym mailu nic nie zjada budżetu wiadomości, więc porcja 2 '
        'obejmuje oba zlecenia — i podgląd musi mówić to samo')
    assert all(z.status == 'dostarczone' for z in zrodla), 'propagacja na źródła'
