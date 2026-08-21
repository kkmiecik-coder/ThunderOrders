"""Powiadomienia o paczce zbiorczej — każdy uczestnik dostaje swoje, bez cudzych danych."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


@pytest.fixture
def przechwycone(monkeypatch):
    from utils.push_manager import PushManager
    import utils.email_sender as es
    # batch_calls zbiera DŁUGOŚĆ każdej listy przekazanej do send_email_batch —
    # jedno wywołanie z listą N wiadomości ma wyglądać inaczej niż N wywołań z listą 1
    # (dokładnie ten błąd — pętla po send_email() zamiast batcha — ma tu być widoczny).
    dane = {'email': [], 'status_email': [], 'push': [], 'batch_calls': []}
    monkeypatch.setattr(es, 'prepare_shipment_sent_email',
                        lambda **kw: dane['email'].append(kw) or None)
    monkeypatch.setattr(es, 'prepare_shipping_status_change_email',
                        lambda **kw: dane['status_email'].append(kw) or None)
    # Zlecenie POJEDYNCZE (także źródłowe wyjęte z paczki) idzie drugą drogą —
    # send_..., nie prepare_... + batch. Zbieramy do tego samego klucza, bo to
    # ten sam mail; ścieżki odróżnia batch_calls.
    monkeypatch.setattr(es, 'send_shipping_status_change_email',
                        lambda **kw: dane['status_email'].append(kw) or None)
    monkeypatch.setattr(es, 'send_email_batch',
                        lambda messages: dane['batch_calls'].append(len(messages)))
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: dane['push'].append(kw)))
    return dane


def test_kazdy_uczestnik_dostaje_wlasna_liste_zamowien(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zbiorcze.tracking_number = '622333444'
    zbiorcze.courier = 'inpost'
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    assert len(przechwycone['email']) == 2
    # Batch, nie pętla po send_email()/send_shipment_sent_email() per uczestnik.
    assert przechwycone['batch_calls'] == [2]

    po_adresie = {m['user_email']: m for m in przechwycone['email']}
    mail_a = po_adresie[sr_a.user.email]
    mail_b = po_adresie[sr_b.user.email]
    moje = {o.order_number for o in sr_b.display_orders}
    cudze = {o.order_number for o in sr_a.display_orders}
    assert set(mail_b['order_numbers']) == moje
    assert not (set(mail_b['order_numbers']) & cudze)

    # sr_a jest wiodące (lead_request_id=zrodla[0].id w _konsolidacja) — paczka
    # jedzie na JEGO adres, więc lider nie dostaje notatki „jedzie gdzie indziej",
    # a nie-lider dostaje ją z formą short_addressee_name (nie pełnym nazwiskiem).
    assert mail_a['consolidation_note'] is None
    assert mail_b['consolidation_note'] is not None
    assert zbiorcze.short_addressee_name in mail_b['consolidation_note']


def test_uczestnik_niewiodacy_dostaje_push(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    db.session.commit()

    from utils.push_manager import PushManager
    PushManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    odbiorcy = {p['user_id'] for p in przechwycone['push']}
    assert odbiorcy == {sr_a.user_id, sr_b.user_id}


def test_paczka_bez_wlasciciela_nie_wysyla_nic(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.user_id = None
    sr_a.user_id = None
    sr_b.user_id = None
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    # Fallback na adres z pierwszego zamówienia wysłałby obcej osobie listę
    # zamówień wszystkich uczestników — dla paczki zbiorczej jest wyłączony.
    assert przechwycone['email'] == []


# ---------- Ta sama klasa błędu przy zwykłej zmianie statusu (nie tylko nadaniu) ----------
#
# EmailManager._status_change_consolidated i gałąź is_consolidation w
# PushManager.notify_shipping_status_change nie były pokryte przy pierwszym
# przejściu — a to dokładnie ta sama para błędów (wyciek cudzych zamówień do
# lidera / cisza dla pozostałych uczestników), tylko przy trigerze innym niż
# nadanie paczki (np. admin ręcznie zmienia zbiorcze na „spakowane" bez
# dotykania trackingu — modules/orders/routes.py woła wtedy
# notify_shipping_status_change, nie notify_shipment_sent).

def test_status_change_kazdy_uczestnik_dostaje_wlasna_liste_zamowien(db, przechwycone, make_user, make_order):
    """Zmiana statusu paczki zbiorczej: każdy uczestnik dostaje mail z WŁASNĄ
    listą zamówień (bez cudzych numerów), jednym wywołaniem batcha."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipping_status_change(zbiorcze, 'oplacone')

    assert len(przechwycone['status_email']) == 2
    # Batch, nie pętla po send_shipping_status_change_email() per uczestnik.
    assert przechwycone['batch_calls'] == [2]

    po_adresie = {m['user_email']: m for m in przechwycone['status_email']}
    mail_b = po_adresie[sr_b.user.email]
    moje = {o.order_number for o in sr_b.display_orders}
    cudze = {o.order_number for o in sr_a.display_orders}
    assert {o.order_number for o in mail_b['orders']} == moje
    assert not ({o.order_number for o in mail_b['orders']} & cudze)


def test_status_change_wszyscy_uczestnicy_dostaja_push(db, przechwycone, make_user, make_order):
    """Zmiana statusu paczki zbiorczej wysyła push do KAŻDEGO uczestnika, nie
    tylko do usera zlecenia zbiorczego (lidera)."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from utils.push_manager import PushManager
    PushManager.notify_shipping_status_change(zbiorcze, 'Spakowane')

    odbiorcy = {p['user_id'] for p in przechwycone['push']}
    assert odbiorcy == {sr_a.user_id, sr_b.user_id}


# ---------- Powiadomienie o samym scaleniu (Task 12) ----------
#
# Task 11 pokrył wysyłkę i zmianę statusu, ale nie samo utworzenie paczki
# zbiorczej. Bez tego klient dowiaduje się o zmianie dopiero z maila o
# wysyłce, w którym nagle pojawia się cudzy adres.

def test_powiadomienie_o_scaleniu_idzie_do_wszystkich(db, przechwycone, monkeypatch,
                                                      make_user, make_order):
    import utils.email_sender as es
    maile = []
    monkeypatch.setattr(es, 'prepare_shipment_consolidated_email',
                        lambda **kw: maile.append(kw) or None)
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    # Nazwisko w rubryce adresowej pod kontrolą testu — chodzi o asercję „pełne
    # nazwisko nie wyciekło", więc musi to być nazwisko inne niż to z konta
    # uczestnika, żeby dało się je jednoznacznie wypatrzeć w treści maila.
    zbiorcze.shipping_name = 'Karolina Testowska'
    db.session.commit()

    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    EmailManager.notify_shipment_consolidated(zbiorcze)
    PushManager.notify_shipment_consolidated(zbiorcze)

    assert {m['user_email'] for m in maile} == {sr_a.user.email, sr_b.user.email}
    # Adresat wie, że to jego adres; pozostali widzą, do kogo jedzie paczka.
    assert any(m['is_recipient'] for m in maile)
    assert any(not m['is_recipient'] for m in maile)
    assert {p['user_id'] for p in przechwycone['push']} == {sr_a.user_id, sr_b.user_id}

    # sr_a jest wiodące (lead_request_id=zrodla[0].id w _konsolidacja) — adresat.
    po_adresie = {m['user_email']: m for m in maile}
    mail_a = po_adresie[sr_a.user.email]
    mail_b = po_adresie[sr_b.user.email]
    assert mail_a['is_recipient'] is True
    assert mail_b['is_recipient'] is False

    # Uczestnik widzi WYŁĄCZNIE swoje zamówienia w tej paczce, nigdy cudzych numerów.
    moje = {o.order_number for o in sr_b.display_orders}
    cudze = {o.order_number for o in sr_a.display_orders}
    assert set(mail_b['order_numbers']) == moje
    assert not (set(mail_b['order_numbers']) & cudze)

    # Nie-adresat dostaje WYŁĄCZNIE skróconą formę nazwiska adresata — asercja na
    # nieobecność pełnego nazwiska jest tu ważniejsza niż na obecność skrótu, bo to
    # ona łapie regres do sr.shipping_name (pełne imię i nazwisko obcej osoby).
    assert zbiorcze.short_addressee_name in mail_b['recipient_name']
    assert zbiorcze.shipping_name not in mail_b['recipient_name']
    assert 'Testowska' not in mail_b['recipient_name']


# ---------- Zdjęcie paczki (Task 17) ----------
#
# Mail ze zdjęciem leciał dotąd z pojedynczego zamówienia (group[0] w
# wms_packing.py) — przy paczce zbiorczej trafiał do właściciela przypadkowego
# zamówienia z grupy, a reszta uczestników nie dostawała nic.

@pytest.fixture
def zdjecia(monkeypatch):
    """Przechwytuje mail ze zdjęciem paczki — bez wysyłki i bez pliku na dysku."""
    import utils.email_sender as es
    dane = {'maile': [], 'batch_calls': []}
    monkeypatch.setattr(es, 'prepare_packing_photo_email',
                        lambda **kw: dane['maile'].append(kw) or None)
    monkeypatch.setattr(es, 'send_email_batch',
                        lambda messages: dane['batch_calls'].append(len(messages)))
    return dane


def _ze_zdjeciem(db, zbiorcze):
    """Bramka `notify_packing_photo` wymaga zdjęcia na zamówieniu."""
    for ro in zbiorcze.request_orders:
        ro.order.packing_photo = 'uploads/packing/test.jpg'
    db.session.commit()


def test_zdjecie_paczki_idzie_do_wszystkich_uczestnikow(db, zdjecia, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    _ze_zdjeciem(db, zbiorcze)

    from utils.email_manager import EmailManager
    EmailManager.notify_packing_photo_for_request(zbiorcze)

    # `set(...)` samo z siebie dowodzi tylko „co najmniej raz" — długość listy
    # obok zbioru dowodzi, że nikt nie dostał zdjęcia dwa razy (code review
    # rundy 1, task 17).
    assert len(zdjecia['maile']) == 2
    assert {m['user_email'] for m in zdjecia['maile']} == {sr_a.user.email, sr_b.user.email}
    # Jedno połączenie SMTP na całą paczkę, nie N osobnych wątków.
    assert zdjecia['batch_calls'] == [2]


def test_zdjecie_paczki_uprzedza_o_wspolnym_kartonie(db, zdjecia, make_user, make_order):
    """Zdjęcie kartonu zbiorczego pokazuje produkty obcych osób i może zawierać
    etykietę z pełnym adresem adresata — mail musi to uprzedzać, a adresata
    nazywać wyłącznie skróconą formą (spec, sekcja „Zdjęcie paczki")."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    _ze_zdjeciem(db, zbiorcze)

    from utils.email_manager import EmailManager
    EmailManager.notify_packing_photo_for_request(zbiorcze)

    po_adresie = {m['user_email']: m for m in zdjecia['maile']}
    mail_a = po_adresie[sr_a.user.email]   # adresat (sr_a jest wiodące)
    mail_b = po_adresie[sr_b.user.email]   # uczestnik niebędący adresatem

    assert mail_a['consolidation_note']
    assert 'zbiorcza' in mail_a['consolidation_note']
    assert mail_b['consolidation_note']
    assert zbiorcze.short_addressee_name in mail_b['consolidation_note']
    # Pełne nazwisko adresata nie może wyciec do obcej osoby.
    assert zbiorcze.shipping_name not in mail_b['consolidation_note']


def test_maile_nazywaja_adresata_takze_przy_paczkomacie(db, przechwycone, monkeypatch,
                                                        make_user, make_order):
    """Przy paczkomacie `shipping_name` jest puste, więc oba maile (o scaleniu i o
    wysyłce) wpadały w zastępnik „osoby odbierającej paczkę" — uczestnik czytał, że
    paczka jedzie do kogoś innego, ale nie dowiadywał się, u kogo ją odebrać."""
    import utils.email_sender as es
    maile_scalenie = []
    monkeypatch.setattr(es, 'prepare_shipment_consolidated_email',
                        lambda **kw: maile_scalenie.append(kw) or None)
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.address_type = 'pickup_point'
    zbiorcze.shipping_name = None
    zbiorcze.pickup_courier = 'InPost'
    zbiorcze.pickup_point_id = 'KRA01M'
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_consolidated(zbiorcze)
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    skrot = f'{sr_a.user.first_name} {sr_a.user.last_name[0]}.'
    assert zbiorcze.short_addressee_name == skrot

    mail_scalenie_b = {m['user_email']: m for m in maile_scalenie}[sr_b.user.email]
    assert mail_scalenie_b['recipient_name'] == skrot
    assert 'osoby odbierającej paczkę' not in mail_scalenie_b['recipient_name']

    mail_wysylka_b = {m['user_email']: m for m in przechwycone['email']}[sr_b.user.email]
    assert skrot in mail_wysylka_b['consolidation_note']
    # Pełne nazwisko obcej osoby nadal nie wychodzi z serwera.
    assert sr_a.user.last_name not in mail_wysylka_b['consolidation_note']


def test_wysylka_paczki_bez_nazwy_adresata_nie_pisze_none(db, przechwycone, make_user, make_order):
    """`_shipment_sent_consolidated` musi mieć ten sam fallback co reszta pliku —
    konto lidera bez nazwiska I paczkomat bez shipping_name dają
    `short_addressee_name` == None; bez zastępnika zdanie kończyło się dosłownym
    „na adres: None.” (dokładnie ten błąd żyje dziś na produkcji)."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.user.first_name = None
    sr_a.user.last_name = None
    zbiorcze.shipping_name = None  # paczkomat: adresu tekstowego nie ma
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    mail_b = {m['user_email']: m for m in przechwycone['email']}[sr_b.user.email]
    assert 'None' not in mail_b['consolidation_note']
    assert 'osoby odbierającej paczkę' in mail_b['consolidation_note']
    # Zdanie ma się kończyć dokładnie jedną kropką, nie zostać urwane.
    assert mail_b['consolidation_note'].endswith('paczkę.')


def test_wysylka_paczki_nie_ma_podwojnej_kropki(db, przechwycone, make_user, make_order):
    """`short_addressee_name` kończy się kropką skrótu nazwiska („Ola K.”) —
    doklejenie własnej kropki w zdaniu dawało „Ola K..” (błąd z produkcji)."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    mail_b = {m['user_email']: m for m in przechwycone['email']}[sr_b.user.email]
    assert zbiorcze.short_addressee_name.endswith('.')
    assert '..' not in mail_b['consolidation_note']
    assert mail_b['consolidation_note'].endswith(zbiorcze.short_addressee_name)


def test_szablon_scalenia_nie_dubluje_kropki_po_skrocie(app):
    """templates/emails/shipment_consolidated.html: ta sama pułapka co w
    email_manager, tylko w Jinja — recipient_name w formie „Ola K.” + własna
    kropka szablonu dawały „Ola K..”."""
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_consolidated.html',
            user_name='Ktoś',
            request_number='WYS/000300',
            order_numbers=['PO/00000001'],
            recipient_name='Ola K.',
            is_recipient=False,
            shipping_requests_url=None,
        )

    # Asercja na sam ciąg „Ola K.." NIE wystarcza: kropka szablonu ląduje POZA
    # <strong>, więc wersja z błędem renderowała „<strong>Ola K.</strong>." —
    # znacznik stał między kropkami i „Ola K.." nigdy w HTML nie istniało.
    # Sprawdzamy dokładnie ten kawałek znacznika (tak samo jak test niżej).
    assert '<strong>Ola K.</strong>.' not in html
    assert '<strong>Ola K.</strong>' in html
    assert 'Ola K..' not in html


def test_szablon_scalenia_pelna_nazwa_konczy_sie_jedna_kropka(app):
    """recipient_name bez skrótu (pełna nazwa paczkomatu) nie ma własnej kropki —
    szablon musi ją dołożyć, a nie zostawić zdanie urwane."""
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_consolidated.html',
            user_name='Ktoś',
            request_number='WYS/000300',
            order_numbers=['PO/00000001'],
            recipient_name='Paczkomat KRA01M',
            is_recipient=False,
            shipping_requests_url=None,
        )

    # Kropka doklejana przez szablon ląduje POZA <strong>, więc „Paczkomat KRA01M.”
    # nie jest ciągłym fragmentem HTML — sprawdzamy dokładnie ten kawałek znacznika.
    assert '<strong>Paczkomat KRA01M</strong>.' in html
    assert '<strong>Paczkomat KRA01M</strong>..' not in html


def test_szablon_scalenia_przezywa_brak_nazwy_adresata(app):
    """recipient_name == None nie może wywalić renderu.

    Wołający podstawia zastępnik sam, ale `.endswith` na None rzuca w Jinja —
    a wtedy prepare_email() zwraca None i uczestnik nie dostaje ŻADNEGO maila
    o scaleniu (przed dołożeniem kropki dostawał brzydkie „None”, ale dostawał).
    """
    from flask import render_template

    with app.test_request_context():
        html = render_template(
            'emails/shipment_consolidated.html',
            user_name='Ktoś',
            request_number='WYS/000300',
            order_numbers=['PO/00000001'],
            recipient_name=None,
            is_recipient=False,
            shipping_requests_url=None,
        )

    assert 'None' not in html
    assert '<strong>osoby odbierającej paczkę</strong>.' in html


# ---------------------------------------------------------------------------
# Status w mailu należy do UCZESTNIKA, nie do paczki (BUG 3.3)
#
# `notify_shipping_status_change` dostawało paczkę zbiorczą, więc
# `_status_change_consolidated` rozsyłało WSZYSTKIM uczestnikom przejście
# PACZKI — mimo że każdy uczestnik ma własny `source_request.status`.
# Uczestnik z „opłacone" dostawał mail „Czeka na opłacenie".
# Przypadek lustrzany: gdy podniesienie uczestnika nie ruszyło minimum paczki,
# nie szło nic do nikogo — także do tego, komu właśnie naliczono należność.
# ---------------------------------------------------------------------------

def _wyceny(zbiorcze, zrodlo, kwota):
    """Ustawia koszt wysyłki na zamówieniach danego uczestnika paczki.

    Po konsolidacji wiersze junction są przepięte na paczkę, więc
    `zrodlo.request_orders` jest puste — zamówienia uczestnika trzeba brać
    z `consolidation_participants`.
    """
    for uczestnik in zbiorcze.consolidation_participants:
        if uczestnik['source_request'].id == zrodlo.id:
            for o in uczestnik['orders']:
                o.shipping_cost = kwota


def test_mail_o_wycenie_idzie_tylko_do_wycenionego_uczestnika(
        db, przechwycone, make_user, make_order):
    """Uczestnik, którego status się nie zmienił, nie dostaje cudzego przejścia."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    # sr_a jest już opłacone, sr_b czeka na wycenę i właśnie ją dostaje.
    sr_a.status = 'oplacone'
    sr_b.status = 'czeka_na_wycene'
    _wyceny(zbiorcze, sr_b, 20)
    db.session.commit()

    from modules.orders.consolidation import przeprowadz_uczestnikow_na_oplacenie
    zmienione = przeprowadz_uczestnikow_na_oplacenie(zbiorcze)
    db.session.commit()

    assert [z.id for z, _ in zmienione] == [sr_b.id], (
        'Zmienić się miało tylko zlecenie, które dostało wycenę'
    )
    assert all(stary == 'czeka_na_wycene' for _, stary in zmienione), (
        'Kontrakt: funkcja zwraca (zlecenie, status_sprzed_zmiany) — bez starego '
        'statusu nie da się wysłać poprawnego maila o przejściu'
    )


def test_status_w_mailu_pochodzi_ze_zlecenia_zrodlowego(
        app, db, przechwycone, make_user, make_order):
    """Mail niesie status zlecenia uczestnika, nie minimum paczki."""
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    sr_a.status = 'oplacone'
    sr_b.status = 'czeka_na_oplacenie'
    db.session.commit()

    from utils.email_manager import EmailManager
    # Kontekst żądania: ścieżka pojedynczego zlecenia buduje link przez url_for
    # bez zabezpieczenia (w odróżnieniu od ścieżki konsolidacji).
    with app.test_request_context('/'):
        EmailManager.notify_shipping_status_change(sr_b, 'czeka_na_wycene')

    assert len(przechwycone['status_email']) == 1, (
        'Powiadomienie o przejściu uczestnika idzie do niego jednego'
    )
    mail = przechwycone['status_email'][0]
    assert mail['user_email'] == sr_b.user.email
    assert mail['request_number'] == sr_b.request_number
    assert mail['new_status_name'] == 'Czeka na opłacenie'
    assert mail['old_status_name'] == 'Czeka na wycenę'
    # Zamówienia przez display_orders, nie orders: po konsolidacji wiersze
    # junction wiszą przy paczce, więc `sr.orders` źródła jest puste i klient
    # dostawał potwierdzenie z pustą tabelą „Zamówienia w zleceniu".
    assert {o.order_number for o in mail['orders']} == {
        o.order_number for o in sr_b.display_orders
    }
    assert mail['orders'], 'Lista zamówień w mailu nie może być pusta'
