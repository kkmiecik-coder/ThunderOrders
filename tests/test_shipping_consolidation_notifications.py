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
    # Pełny adres z nazwiskiem pod kontrolą testu — inaczej `_sr()` buduje go z
    # first_name/last_name usera, które fixture make_user zostawia puste (None None),
    # a wtedy asercja „pełne nazwisko nie wyciekło” byłaby pusta (sprawdzałaby brak
    # napisu 'None', nie realny wyciek).
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
