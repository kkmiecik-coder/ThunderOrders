"""Moderator nie widzi przycisków, których i tak nie wykona.

Karta zamówienia (`admin_detail`) i lista zleceń (`wms_dashboard`) są dostępne
dla ról `admin` i `mod`, ale trzy akcje dodane w audycie WMS mają
`@role_required('admin')`: księgowanie wpłaty przy etapie, księgowanie wpłaty
uczestnikowi paczki zbiorczej i cofnięcie wysyłki.

W szablonach nie było przy nich żadnego warunku roli, więc moderator widział
komplet przycisków. Po kliknięciu `role_required` robi `abort(403)`, a handler
403 renderuje stronę HTML — front woła na niej `res.json()`, wywraca się i
pokazuje „Błąd połączenia. Spróbuj ponownie.". Moderator dostawał więc komunikat
sugerujący awarię sieci zamiast informacji o braku uprawnień.

Dwie strony naprawy:
1. przyciski akcji administracyjnych renderują się tylko dla roli `admin`
   (wzorzec z `templates/admin/offers/_list_items.html`),
2. odmowa 403 na żądanie oczekujące JSON-a wraca JSON-em — bo starą kartę,
   otwartą przed odebraniem uprawnień, i tak trzeba obsłużyć czytelnie.
"""

import pytest


def _seed_statuses(db):
    from modules.orders.models import OrderStatus, ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        if not ShippingRequestStatus.query.filter_by(slug=slug).first():
            db.session.add(ShippingRequestStatus(
                slug=slug, name=name, sort_order=i, is_active=True,
                is_initial=(slug == 'czeka_na_wycene')))
    for slug, name in [('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'), ('wyslane', 'Wysłane')]:
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _osoba(make_user, rola):
    return make_user(role=rola, email=f'{rola}-uprawnienia@example.com',
                     profile_completed=True)


def _zamowienie_z_naleznoscia(db, make_user, make_order):
    """Zamówienie, przy którym przycisk księgowania NA PEWNO się renderuje.

    Wiersz „Produkty" wymaga `effective_total > 0`, a ta suma liczy się z pozycji
    zamówienia — samo `total_amount` jej nie ustawia. Bez pozycji przycisku nie ma
    dla nikogo i test moderatora przechodziłby z niewłaściwego powodu.
    """
    from decimal import Decimal
    from modules.orders.models import OrderItem

    user = make_user(email='klient-uprawnienia@example.com')
    o = make_order(user=user, status='dostarczone_gom')
    o.shipping_cost = Decimal('30.00')
    db.session.add(OrderItem(
        order_id=o.id, is_custom=True, custom_name='Pozycja testowa',
        quantity=1, price=Decimal('100.00'), total=Decimal('100.00')))
    db.session.commit()
    return o


def _zlecenie_wyslane(db, make_user, make_order):
    """Zlecenie w statusie „wysłane" bez opinii — „Cofnij wysyłkę" ma się renderować."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    user = make_user(email='klient-unship@example.com')
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status='wyslane', tracking_number='UPR123')
    db.session.add(sr)
    db.session.flush()
    o = make_order(user=user, status='wyslane')
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


# ---------------------------------------------------------------------------
# Karta zamówienia — księgowanie wpłaty
# ---------------------------------------------------------------------------

def test_moderator_nie_widzi_przycisku_ksiegowania_wplaty(
        db, client, login, make_user, make_order):
    _seed_statuses(db)
    o = _zamowienie_z_naleznoscia(db, make_user, make_order)
    login(_osoba(make_user, 'mod'))

    r = client.get(f'/admin/orders/{o.id}')
    html = r.get_data(as_text=True)

    assert r.status_code == 200
    assert 'js-register-payment' not in html, (
        'Moderator widział przycisk księgowania wpłaty — po kliknięciu dostaje '
        '„Błąd połączenia" zamiast informacji o braku uprawnień'
    )


def test_admin_widzi_przycisk_ksiegowania_wplaty(
        db, client, login, make_user, make_order):
    """Regresja: ukrycie przed moderatorem nie może zabrać funkcji adminowi."""
    _seed_statuses(db)
    o = _zamowienie_z_naleznoscia(db, make_user, make_order)
    login(_osoba(make_user, 'admin'))

    r = client.get(f'/admin/orders/{o.id}')

    assert 'js-register-payment' in r.get_data(as_text=True)


def test_moderator_nie_widzi_okna_ksiegowania(
        db, client, login, make_user, make_order):
    """Samo okno modalne też jest zbędne — bez przycisku nie ma czym go otworzyć."""
    _seed_statuses(db)
    o = _zamowienie_z_naleznoscia(db, make_user, make_order)
    login(_osoba(make_user, 'mod'))

    assert 'registerPaymentModal' not in client.get(f'/admin/orders/{o.id}').get_data(as_text=True)


# ---------------------------------------------------------------------------
# Lista zleceń — cofnięcie wysyłki i księgowanie uczestnikowi
# ---------------------------------------------------------------------------

def test_moderator_nie_widzi_cofnij_wysylke(db, client, login, make_user, make_order):
    _seed_statuses(db)
    _zlecenie_wyslane(db, make_user, make_order)
    login(_osoba(make_user, 'mod'))

    r = client.get('/admin/orders/wms')
    html = r.get_data(as_text=True)

    assert r.status_code == 200
    assert 'js-unship' not in html, (
        'Moderator widział „Cofnij wysyłkę", choć trasa wymaga roli admin'
    )


def test_admin_widzi_cofnij_wysylke(db, client, login, make_user, make_order):
    _seed_statuses(db)
    _zlecenie_wyslane(db, make_user, make_order)
    login(_osoba(make_user, 'admin'))

    assert 'js-unship' in client.get('/admin/orders/wms').get_data(as_text=True)


@pytest.mark.parametrize('rola,oczekiwana', [('admin', 'true'), ('mod', 'false')])
def test_strona_wms_niesie_flage_uprawnien_dla_js(
        db, client, login, make_user, rola, oczekiwana):
    """Przycisk „Zaksięguj wpłatę" przy uczestniku paczki rysuje JavaScript,
    więc front musi wiedzieć, czy wolno go pokazać."""
    _seed_statuses(db)
    login(_osoba(make_user, rola))

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert f'data-can-register-payment="{oczekiwana}"' in html, (
        f'Strona WMS nie niesie flagi uprawnień dla roli {rola} — JS nie ma jak '
        f'zdecydować, czy narysować przycisk księgowania wpłaty'
    )


# ---------------------------------------------------------------------------
# Odmowa musi być czytelna także dla starej karty
# ---------------------------------------------------------------------------

def test_odmowa_403_na_zadanie_json_wraca_jsonem(
        db, client, login, make_user, make_order):
    """Front woła `res.json()` — HTML-owa strona błędu wywraca go w `catch`
    i zamienia brak uprawnień w „Błąd połączenia"."""
    _seed_statuses(db)
    o = _zamowienie_z_naleznoscia(db, make_user, make_order)
    login(_osoba(make_user, 'mod'))

    r = client.post(f'/admin/payment-confirmations/register/{o.id}',
                    json={'payment_stage': 'domestic_shipping', 'amount': '30.00'})

    assert r.status_code == 403
    assert r.is_json, (
        f'Odmowa przyszła jako {r.content_type} — front pokaże „Błąd połączenia" '
        f'zamiast powodu'
    )
    dane = r.get_json()
    # Oba fronty (order-detail.js, shipping-requests.js) czytają dokładnie te dwa
    # klucze: `success` bramkuje ścieżkę błędu, `message` ląduje w komunikacie.
    assert dane.get('success') is False, dane
    assert 'uprawnie' in (dane.get('message') or '').lower(), (
        f'Komunikat pokazywany użytkownikowi ma mówić o uprawnieniach: {dane}'
    )


def test_odmowa_403_dla_zwyklej_strony_nadal_renderuje_html(
        db, client, login, make_user):
    """Regresja: przeglądarkowe wejście na zakazaną stronę ma dalej dostać
    stronę błędu, nie surowy JSON."""
    login(_osoba(make_user, 'mod'))

    r = client.get('/admin/users')

    if r.status_code == 403:
        assert not r.is_json, 'Zwykła nawigacja ma dostać stronę HTML'
