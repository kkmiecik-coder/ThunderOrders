"""Kontrakt ustawień domykania oferty: co admin zapisze, tym silnik ma się posłużyć.

Te testy istnieją, bo rename z `b7b10ea` (2026-03-31) rozjechał jedną nazwę klucza
na dwie: panel zapisywał `offers_closure_status_*`, a silnik czytał
`offer_closure_status_*`. Obie strony miały testy sprawdzające własną połowę na
literale i obie świeciły na zielono przez pięć miesięcy — bo żaden test nie przeszedł
całej drogi zapis → odczyt. Dlatego asercje niżej celowo NIE nazywają klucza:
sprawdzają zachowanie widoczne z zewnątrz, więc przeżyją kolejny rename.

Druga rzecz tu pilnowana: bramka wysyłki maili anulacyjnych. Sprawdzała istnienie
wiersza Settings, nie jego wartość, więc na instalacji, gdzie nikt nigdy nie ruszył
ustawień (czyli na produkcji), `send_cancellation_emails` nie odpaliło się ani razu.
"""
import pytest


@pytest.fixture
def make_page(db, make_user):
    from modules.offers.models import OfferPage

    counter = {'n': 0}

    def _make(**kwargs):
        counter['n'] += 1
        # close_offer_page przyjmuje tylko strony zakończone
        kwargs.setdefault('status', 'ended')
        page = OfferPage(
            name=f'Zbiorka {counter["n"]}',
            token=f'kontrakt-token-{counter["n"]}',
            created_by=make_user(role='admin').id,
            **kwargs,
        )
        db.session.add(page)
        db.session.commit()
        return page
    return _make


@pytest.fixture
def zamowienie_z_pozycjami(db, make_user, make_order, make_product):
    """Zamówienie z jedną pozycją o zadanej realizacji.

    `make_order` z conftestu tworzy zamówienie BEZ pozycji, a klasyfikator liczy
    właśnie pozycje — zamówienie puste wpada do 'not_fulfilled' niezależnie od
    intencji testu. Dlatego pozycję trzeba dołożyć jawnie.
    """
    from decimal import Decimal
    from modules.orders.models import OrderItem

    def _make(page, zrealizowana, email):
        order = make_order(make_user(email=email), status='nowe', offer_page_id=page.id)
        produkt = make_product()
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=produkt.id,
            quantity=1,
            price=Decimal('99.00'),
            total=Decimal('99.00'),
            is_set_fulfilled=zrealizowana,
        ))
        db.session.commit()
        db.session.refresh(order)
        assert len(order.items) == 1, 'fixture ma dać dokładnie jedną pozycję'
        return order
    return _make


@pytest.fixture
def zamowienie_bez_kompletu(zamowienie_z_pozycjami):
    """Zamówienie, którego żadna pozycja się nie załapała → kategoria not_fulfilled."""
    def _make(page, email='klientka@example.com'):
        return zamowienie_z_pozycjami(page, zrealizowana=False, email=email)
    return _make


@pytest.fixture
def zamowienie_z_kompletem(zamowienie_z_pozycjami):
    """Zamówienie z wszystkimi pozycjami zrealizowanymi → kategoria fully_fulfilled."""
    def _make(page, email='komplet@example.com'):
        return zamowienie_z_pozycjami(page, zrealizowana=True, email=email)
    return _make


# ============================================================
# Kontrakt zapis → odczyt (to, czego zabrakło przy b7b10ea)
# ============================================================

def test_status_zapisany_przez_panel_jest_uzyty_przy_domykaniu(
        app, db, client, make_user, login, make_page, zamowienie_bez_kompletu):
    """Pełna droga: admin zapisuje ustawienia w panelu → silnik ich używa.

    Celowo wybrany status ('do_zwrotu') różni się od twardego defaultu
    ('anulowane') — inaczej test przechodziłby także wtedy, gdy ustawienia są
    ignorowane, a dokładnie ten fałszywy zielony przykrywał bug przez 5 miesięcy.
    """
    from utils.offer_closure import auto_update_order_statuses

    admin = make_user(role='admin', email='admin-kontrakt@example.com', profile_completed=True)
    login(admin)

    odpowiedz = client.post('/admin/offers/settings', data={
        'offers_closure_status_fully_fulfilled': 'dostarczone_gom',
        'offers_closure_status_partially_fulfilled': 'oczekujace',
        'offers_closure_status_not_fulfilled': 'do_zwrotu',
    }, follow_redirects=False)
    assert odpowiedz.status_code in (302, 303), 'zapis ustawień miał przekierować'
    assert 'complete-profile' not in (odpowiedz.headers.get('Location') or ''), (
        'POST został odbity przez bramkę uzupełnienia profilu i nigdy nie dotarł '
        'do trasy zapisu — test sprawdzałby wtedy zupełnie co innego'
    )

    page = make_page()
    order = zamowienie_bez_kompletu(page)

    with app.test_request_context():
        auto_update_order_statuses(page.id, admin.id)
    db.session.refresh(order)

    assert order.status == 'do_zwrotu', (
        'silnik zignorował ustawienie zapisane przez panel i użył wartości domyślnej — '
        'to dokładnie regresja z b7b10ea (rozjazd nazwy klucza Settings)'
    )


def test_kategoria_zrealizowana_tez_bierze_status_z_panelu(
        app, db, client, make_user, login, make_page, zamowienie_z_kompletem):
    """Ten sam kontrakt dla drugiej kategorii — rozjazd dotyczył wszystkich trzech kluczy."""
    from utils.offer_closure import auto_update_order_statuses

    admin = make_user(role='admin', email='admin-kontrakt2@example.com', profile_completed=True)
    login(admin)

    odpowiedz = client.post('/admin/offers/settings', data={
        'offers_closure_status_fully_fulfilled': 'dostarczone_gom',
        'offers_closure_status_partially_fulfilled': 'oczekujace',
        'offers_closure_status_not_fulfilled': 'anulowane',
    })
    assert 'complete-profile' not in (odpowiedz.headers.get('Location') or '')

    page = make_page()
    order = zamowienie_z_kompletem(page)

    with app.test_request_context():
        auto_update_order_statuses(page.id, admin.id)
    db.session.refresh(order)

    assert order.status == 'dostarczone_gom'


# ============================================================
# Walidacja przy zapisie (Order.status to klucz obcy, nie dowolny string)
# ============================================================

def test_nieistniejacy_status_jest_odrzucany_przy_zapisie(
        app, db, client, make_user, login):
    """Slug spoza słownika nie może wejść do Settings.

    Bez tej walidacji `order.status = <nieistniejący slug>` wywala IntegrityError
    w środku transakcji domykania oferty i rolluje całe zamknięcie — alokację setów
    i wyzerowane ceny — a admin dostaje 500 przy operacji opisanej jako nieodwracalna.
    """
    from modules.auth.models import Settings

    admin = make_user(role='admin', email='admin-walidacja@example.com', profile_completed=True)
    login(admin)

    odpowiedz = client.post('/admin/offers/settings', data={
        'offers_closure_status_fully_fulfilled': 'status_ktory_nie_istnieje',
        'offers_closure_status_partially_fulfilled': 'oczekujace',
        'offers_closure_status_not_fulfilled': 'anulowane',
    })
    assert 'complete-profile' not in (odpowiedz.headers.get('Location') or '')

    zapisane = Settings.query.filter(
        Settings.key.like('%closure_status_fully_fulfilled')
    ).first()
    assert zapisane is None or zapisane.value != 'status_ktory_nie_istnieje', (
        'nieistniejący slug statusu trafił do Settings — przy najbliższym domknięciu '
        'oferty wywali IntegrityError i zrolluje całe zamknięcie'
    )


def test_uszkodzone_ustawienie_nie_wywraca_domykania(
        app, db, make_user, make_page, zamowienie_bez_kompletu):
    """Gdy w Settings siedzi już martwy slug (np. status zdezaktywowany po zapisie),
    silnik ma zejść na wartość domyślną, a nie wywrócić transakcję domykania."""
    from modules.auth.models import Settings
    from utils.offer_closure import auto_update_order_statuses

    admin = make_user(role='admin', email='admin-uszkodzone@example.com')
    db.session.add(Settings(key='offers_closure_status_not_fulfilled',
                            value='slug_po_dezaktywacji', type='string'))
    db.session.commit()

    page = make_page()
    order = zamowienie_bez_kompletu(page)

    with app.test_request_context():
        auto_update_order_statuses(page.id, admin.id)
    db.session.refresh(order)

    assert order.status == 'anulowane', (
        'silnik powinien zejść na status domyślny zamiast ustawiać slug spoza słownika'
    )


# ============================================================
# Bramka maili anulacyjnych
# ============================================================

def test_maile_anulacyjne_ida_takze_bez_zapisanych_ustawien(
        app, db, make_user, make_page, zamowienie_bez_kompletu, monkeypatch):
    """Domyślna instalacja (zero wierszy Settings) też ma wysyłać maile anulacyjne.

    Bramka sprawdzała `if Settings.query...first():` — czyli istnienie wiersza.
    Na produkcji tego wiersza nigdy nie było, więc od 2026-03-31 nie wyszedł ani
    jeden mail o anulowaniu, mimo 251 zamówień automatycznie przestawionych na
    'anulowane'.
    """
    from modules.auth.models import Settings
    from utils import offer_closure

    assert Settings.query.filter(Settings.key.like('%closure%')).count() == 0, \
        'ten test opisuje instalację BEZ zapisanych ustawień'

    wywolania = []
    monkeypatch.setattr(offer_closure, 'send_cancellation_emails',
                        lambda page_id, ids: wywolania.append((page_id, list(ids))))
    monkeypatch.setattr(offer_closure, 'send_closure_emails',
                        lambda *a, **kw: None)

    admin = make_user(role='admin', email='admin-maile@example.com')
    page = make_page()
    order = zamowienie_bez_kompletu(page)

    with app.test_request_context():
        offer_closure.close_offer_page(page.id, admin.id, send_emails=True)

    assert wywolania, 'send_cancellation_emails nie zostało wywołane mimo zamówienia bez kompletu'
    assert order.id in wywolania[0][1]


def test_mail_anulacyjny_nie_idzie_do_klientki_z_kompletem(
        app, db, client, make_user, login, make_page,
        zamowienie_bez_kompletu, zamowienie_z_kompletem, monkeypatch):
    """Adresaci wybierani po KLASYFIKACJI, nie po samym statusie.

    Gdy admin ustawi ten sam slug dla dwóch kategorii, filtrowanie po `order.status`
    wysyła 'żaden produkt się nie załapał' do klientek z pełnym kompletem.
    """
    from utils import offer_closure

    admin = make_user(role='admin', email='admin-filtr@example.com', profile_completed=True)
    login(admin)
    odpowiedz = client.post('/admin/offers/settings', data={
        'offers_closure_status_fully_fulfilled': 'anulowane',
        'offers_closure_status_partially_fulfilled': 'anulowane',
        'offers_closure_status_not_fulfilled': 'anulowane',
    })
    assert 'complete-profile' not in (odpowiedz.headers.get('Location') or '')

    wywolania = []
    monkeypatch.setattr(offer_closure, 'send_cancellation_emails',
                        lambda page_id, ids: wywolania.append((page_id, list(ids))))
    monkeypatch.setattr(offer_closure, 'send_closure_emails', lambda *a, **kw: None)

    page = make_page()
    bez_kompletu = zamowienie_bez_kompletu(page, email='bez-kompletu@example.com')
    z_kompletem = zamowienie_z_kompletem(page, email='z-kompletem@example.com')

    with app.test_request_context():
        offer_closure.close_offer_page(page.id, admin.id, send_emails=True)

    assert wywolania, 'send_cancellation_emails nie zostało wywołane'
    adresaci = wywolania[0][1]
    assert bez_kompletu.id in adresaci
    assert z_kompletem.id not in adresaci, (
        'klientka z pełnym kompletem dostała mail "nic się nie załapało" tylko dlatego, '
        'że oba statusy mają ten sam slug'
    )
