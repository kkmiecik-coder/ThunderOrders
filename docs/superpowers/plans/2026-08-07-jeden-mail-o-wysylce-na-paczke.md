# Jeden mail o wysyłce na paczkę — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zamiast maila i pusha na każde zamówienie w paczce klient dostaje jedną wiadomość na zlecenie wysyłki, z listą wszystkich zamówień jadących w tej paczce.

**Architecture:** Nowa metoda paczkowa w `EmailManager` i `PushManager` (wzorem istniejącego `notify_shipping_request_created`), nowy szablon maila z warunkowym blokiem śledzenia, oraz zamiana pętli `for order in sr.orders` na jedno wywołanie w dwóch miejscach paczkowych. Istniejące metody per-zamówienie zostają nietknięte — używają ich miejsca poza kontekstem paczki.

**Tech Stack:** Python 3.12, Flask, Flask-Mail, Jinja2, SQLAlchemy, pytest.

Spec: `docs/superpowers/specs/2026-08-07-jeden-mail-o-wysylce-na-paczke-design.md`
Zadanie ClickUp: [869efb233](https://app.clickup.com/t/869efb233)
Gałąź: `feat/jeden-mail-o-wysylce-na-paczke`

## Global Constraints

- Testy uruchamiamy przez `./venv/bin/python -m pytest` (pytest nie jest w systemowym Pythonie).
- Baseline przed startem: `./venv/bin/python -m pytest tests/test_wms_ship_and_reopen.py -q` → **17 passed**.
- Bez migracji bazy — żadnych nowych kolumn ani tabel.
- Bez nowych kluczy w `ALLOWED_KEYS` w `modules/orders/routes.py:2146` — mail o paczce korzysta z istniejących przełączników `notify_tracking_added` (gdy jest numer) i `notify_status_change` (gdy numeru nie ma).
- Komentarze i komunikaty po polsku, zgodnie z konwencją repozytorium.
- Commity po polsku w stylu conventional commits, z linią `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Nie pushujemy niczego** — praca zostaje lokalnie na gałęzi.
- `EmailManager.notify_tracking_added`, `EmailManager.notify_status_change`,
  `PushManager.notify_tracking_added`, `PushManager.notify_status_change`
  **nie mogą zostać zmienione ani usunięte** — wołają je `modules/orders/routes.py:719`,
  `modules/orders/routes.py:1087`, `modules/orders/routes.py:610`,
  `modules/orders/routes.py:1286`, `modules/orders/routes.py:3806`,
  `modules/products/routes.py:3072`, `utils/offer_closure.py:402`.

## File Structure

| Plik | Odpowiedzialność |
|---|---|
| `templates/emails/shipment_sent.html` | **nowy** — wygląd maila o wysłanej paczce; blok śledzenia warunkowy |
| `utils/email_sender.py` | **modyfikacja** — `send_shipment_sent_email()`: temat + przekazanie zmiennych do szablonu |
| `utils/email_manager.py` | **modyfikacja** — `EmailManager.notify_shipment_sent()`: przełącznik, adres klienta, tracking URL, lista numerów |
| `utils/push_manager.py` | **modyfikacja** — `_orders_label()` + `PushManager.notify_shipment_sent()` |
| `modules/orders/wms_utils.py` | **modyfikacja** — pętla powiadomień → jedno wywołanie na paczkę |
| `modules/orders/routes.py` | **modyfikacja** — to samo w `admin_update_shipping_request()` + dołożenie pusha |
| `tests/test_shipment_sent_notification.py` | **nowy** — testy szablonu, metod powiadomień i obu miejsc wywołania |
| `tests/test_wms_ship_and_reopen.py` | **modyfikacja** — fixture `notifications` i asercje przechodzą na poziom paczki |

---

### Task 1: Szablon maila o paczce i funkcja wysyłająca

**Files:**
- Create: `templates/emails/shipment_sent.html`
- Modify: `utils/email_sender.py` (dopisanie funkcji po `send_shipping_status_change_email`, tj. za linią 969)
- Test: `tests/test_shipment_sent_notification.py`

**Interfaces:**
- Consumes: `send_email(to, subject, template, **kwargs)` z `utils/email_sender.py:168` — renderuje `templates/emails/{template}.html`
- Produces: `send_shipment_sent_email(user_email, user_name, request_number, order_numbers, tracking_number=None, courier_name=None, tracking_url=None, shipping_requests_url=None) -> bool`
  - `order_numbers`: `list[str]` — same numery zamówień, np. `['PO/00000001', 'PO/00000002']`
  - Szablon `emails/shipment_sent.html` przyjmuje zmienne: `user_name`, `request_number`, `order_numbers`, `tracking_number`, `courier_name`, `tracking_url`, `shipping_requests_url`

- [ ] **Step 1: Napisz testy szablonu i tematu (mają nie przejść)**

Utwórz `tests/test_shipment_sent_notification.py`:

```python
"""Jeden mail i jeden push o wysyłce na paczkę zamiast na każde zamówienie."""

import pytest


# ---------- Task 1: szablon i funkcja wysyłająca ----------

def test_template_lists_all_order_numbers(app):
    """W mailu o paczce muszą być wszystkie numery zamówień, nie tylko pierwszy."""
    from flask import render_template

    with app.app_context():
        html = render_template(
            'emails/shipment_sent.html',
            user_name='Anna',
            request_number='WYS/000123',
            order_numbers=['PO/00000001', 'PO/00000002', 'PO/00000003'],
            tracking_number='123456789012',
            courier_name='InPost',
            tracking_url='https://inpost.pl/sledzenie/123456789012',
            shipping_requests_url='https://thunderorders.cloud/zlecenia',
        )

    assert 'WYS/000123' in html
    assert 'PO/00000001' in html
    assert 'PO/00000002' in html
    assert 'PO/00000003' in html
    assert '123456789012' in html
    assert 'InPost' in html
    assert 'https://inpost.pl/sledzenie/123456789012' in html


def test_template_without_tracking_hides_tracking_block(app):
    """Bez numeru przesyłki nie ma ramki kuriera ani przycisku śledzenia."""
    from flask import render_template

    with app.app_context():
        html = render_template(
            'emails/shipment_sent.html',
            user_name='Anna',
            request_number='WYS/000123',
            order_numbers=['PO/00000001'],
            tracking_number=None,
            courier_name=None,
            tracking_url=None,
            shipping_requests_url='https://thunderorders.cloud/zlecenia',
        )

    assert 'PO/00000001' in html
    assert 'Numer przesyłki' not in html
    assert 'Śledź przesyłkę' not in html


def test_subject_differs_with_and_without_tracking(app, monkeypatch):
    """Temat maila rozróżnia obie sytuacje — treść w środku jest ta sama."""
    import utils.email_sender as es

    captured = []
    monkeypatch.setattr(es, 'send_email',
                        lambda **kw: captured.append(kw) or True)

    with app.app_context():
        es.send_shipment_sent_email(
            user_email='klient@example.com', user_name='Anna',
            request_number='WYS/000123', order_numbers=['PO/00000001'],
            tracking_number='123456789012', courier_name='InPost',
            tracking_url=None, shipping_requests_url='https://x/zlecenia')
        es.send_shipment_sent_email(
            user_email='klient@example.com', user_name='Anna',
            request_number='WYS/000123', order_numbers=['PO/00000001'],
            shipping_requests_url='https://x/zlecenia')

    assert 'Numer przesyłki' in captured[0]['subject']
    assert 'WYS/000123' in captured[0]['subject']
    assert 'wysłana' in captured[1]['subject']
    assert captured[0]['template'] == 'shipment_sent'
    assert captured[1]['tracking_number'] is None
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: FAIL — `jinja2.exceptions.TemplateNotFound: emails/shipment_sent.html` oraz
`AttributeError: module 'utils.email_sender' has no attribute 'send_shipment_sent_email'`

- [ ] **Step 3: Utwórz szablon `templates/emails/shipment_sent.html`**

```html
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paczka wysłana - ThunderOrders</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background-color: #F5F5F5; line-height: 1.6;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F5F5F5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #FFFFFF; border-radius: 8px; overflow: hidden;">

                    <!-- Header with logo -->
                    <tr>
                        <td align="center" style="padding: 40px 40px 20px 40px;">
                            <img src="cid:logo@thunderorders" alt="ThunderOrders" style="height: 40px; width: auto; display: block;" />
                        </td>
                    </tr>

                    <!-- Main content -->
                    <tr>
                        <td style="padding: 20px 40px;">
                            <div style="text-align: center; font-size: 48px; margin: 20px 0;">
                                📦
                            </div>

                            <h1 style="margin: 0 0 20px 0; font-size: 24px; font-weight: 700; color: #240046; text-align: left;">
                                Twoja paczka jest w drodze
                            </h1>

                            <p style="margin: 0 0 16px 0; font-size: 16px; color: #212121;">
                                Cześć <strong>{{ user_name }}</strong>!
                            </p>

                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #212121;">
                                Spakowaliśmy Twoje zamówienia i wysłaliśmy je razem w jednej paczce.
                            </p>

                            <!-- Request number box -->
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 20px 0;">
                                <tr>
                                    <td style="background-color: #F5F5F5; padding: 20px; border-radius: 8px; text-align: center;">
                                        <p style="margin: 0; font-size: 20px; font-weight: 700; color: #240046;">
                                            🚚 {{ request_number }}
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <!-- Orders list -->
                            <h2 style="margin: 30px 0 16px 0; font-size: 18px; font-weight: 600; color: #240046;">
                                W tej paczce jadą
                            </h2>

                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 20px 0; border-collapse: collapse;">
                                <tbody>
                                    {% for order_number in order_numbers %}
                                    <tr>
                                        <td style="padding: 12px; border-bottom: 1px solid #E0E0E0; font-size: 15px; color: #212121; font-weight: 600;">
                                            {{ order_number }}
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>

                            {% if tracking_number %}
                            <!-- Tracking info box -->
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 30px 0;">
                                <tr>
                                    <td style="background-color: #e3f2fd; border: 2px solid #2196F3; border-radius: 8px; padding: 24px;">
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td style="padding: 0 0 12px 0;">
                                                    <p style="margin: 0; font-size: 14px; color: #616161; font-weight: 600;">Kurier:</p>
                                                    <p style="margin: 4px 0 0 0; font-size: 18px; color: #212121; font-weight: 700;">{{ courier_name }}</p>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 12px 0 0 0; border-top: 1px solid #bbdefb;">
                                                    <p style="margin: 0; font-size: 14px; color: #616161; font-weight: 600;">Numer przesyłki:</p>
                                                    <p style="margin: 4px 0 0 0; font-size: 18px; color: #212121; font-weight: 700; letter-spacing: 1px;">{{ tracking_number }}</p>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>

                            {% if tracking_url %}
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 30px 0;">
                                <tr>
                                    <td align="center">
                                        <a href="{{ tracking_url }}" style="display: inline-block; background-color: #2196F3; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 600; font-size: 16px; text-align: center;">
                                            Śledź przesyłkę
                                        </a>
                                    </td>
                                </tr>
                            </table>
                            {% endif %}
                            {% endif %}

                            <!-- Panel link -->
                            <p style="margin: 30px 0 10px 0; font-size: 14px; color: #616161;">
                                Szczegóły wysyłki znajdziesz w panelu klienta:
                            </p>
                            <p style="margin: 0 0 20px 0;">
                                <a href="{{ shipping_requests_url }}" style="color: #7B2CBF; text-decoration: underline; font-size: 14px;">
                                    {{ shipping_requests_url }}
                                </a>
                            </p>

                            <p style="margin: 30px 0 0 0; font-size: 16px; color: #212121; font-weight: 600;">
                                Dziękujemy!
                            </p>

                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 40px; background-color: #F5F5F5; border-top: 1px solid #E0E0E0; text-align: center;">
                            <img src="cid:logo@thunderorders" alt="ThunderOrders" style="height: 32px; width: auto; display: block; margin: 0 auto 12px auto;" />
                            <p style="margin: 0; font-size: 12px; color: #9E9E9E;">
                                <a href="https://thunderorders.cloud" style="color: #7B2CBF; text-decoration: none;">thunderorders.cloud</a> |
                                <a href="mailto:noreply@thunderorders.cloud" style="color: #7B2CBF; text-decoration: none;">noreply@thunderorders.cloud</a>
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

- [ ] **Step 4: Dopisz `send_shipment_sent_email` w `utils/email_sender.py`**

Wstaw bezpośrednio po funkcji `send_shipping_status_change_email` (kończy się w linii 969),
przed `def send_payment_reminder_email`:

```python
def send_shipment_sent_email(user_email, user_name, request_number, order_numbers,
                             tracking_number=None, courier_name=None, tracking_url=None,
                             shipping_requests_url=None):
    """
    Wysyła JEDEN mail o wysłanej paczce — na całe zlecenie wysyłki.

    Zastępuje mail per zamówienie: klient dostaje jedną wiadomość z listą
    wszystkich zamówień jadących w tej paczce. Blok ze śledzeniem pojawia się
    w szablonie tylko wtedy, gdy jest numer przesyłki — temat maila rozróżnia
    obie sytuacje, treść jest ta sama.

    Args:
        user_email (str): Email klienta
        user_name (str): Imię klienta
        request_number (str): Numer zlecenia wysyłki (np. WYS/000001)
        order_numbers (list): Lista numerów zamówień w paczce (same stringi)
        tracking_number (str): Numer przesyłki (opcjonalny)
        courier_name (str): Nazwa kuriera do wyświetlenia (opcjonalna)
        tracking_url (str): URL do śledzenia przesyłki (opcjonalny)
        shipping_requests_url (str): URL do listy zleceń wysyłki klienta
    """
    if tracking_number:
        subject = f'Numer przesyłki do Twojej paczki - {request_number} - ThunderOrders'
    else:
        subject = f'Twoja paczka została wysłana - {request_number} - ThunderOrders'

    return send_email(
        to=user_email,
        subject=subject,
        template='shipment_sent',
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url,
        shipping_requests_url=shipping_requests_url
    )
```

- [ ] **Step 5: Uruchom testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add templates/emails/shipment_sent.html utils/email_sender.py tests/test_shipment_sent_notification.py
git commit -m "feat(wysylka): szablon maila o wysłanej paczce z listą zamówień

Jeden szablon dla obu sytuacji — blok ze śledzeniem renderuje się tylko,
gdy jest numer przesyłki. Temat maila rozróżnia wysyłkę bez numeru
i dopisanie numeru.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `EmailManager.notify_shipment_sent`

**Files:**
- Modify: `utils/email_manager.py` (dopisanie metody po `notify_shipping_status_change`; zaktualizowanie listy metod w docstringu klasy przy linii 34)
- Test: `tests/test_shipment_sent_notification.py`

**Interfaces:**
- Consumes: `send_shipment_sent_email(...)` z Taska 1; `EmailManager.is_email_enabled(key)` z `utils/email_manager.py:62`; `ShippingRequest.orders`, `ShippingRequest.user`, `ShippingRequest.request_number`; `Order.customer_email` (`modules/orders/models.py:256` — zwraca `self.user.email`); `modules.orders.utils.get_tracking_url(courier, tracking_number)`
- Produces: `EmailManager.notify_shipment_sent(shipping_request, *, tracking_number=None, courier=None, courier_name=None, tracking_url=None) -> None`
  - Wołane w Tasku 4 i Tasku 5. Wszystkie parametry poza pierwszym są **keyword-only**.

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_shipment_sent_notification.py`:

```python
# ---------- Task 2: EmailManager.notify_shipment_sent ----------

def _sr_with_orders(db, make_user, make_order, count=3, tracking=None, courier=None):
    """Zlecenie wysyłki z podanym numerem zamówień, gotowe do powiadomienia."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='spakowane',
                         tracking_number=tracking, courier=courier)
    db.session.add(sr)
    db.session.commit()
    for _ in range(count):
        o = make_order(u, status='spakowane')
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


@pytest.fixture
def captured_email(monkeypatch):
    """Przechwytuje wywołania send_shipment_sent_email zamiast wysyłać maile."""
    import utils.email_sender as es

    calls = []
    monkeypatch.setattr(es, 'send_shipment_sent_email',
                        lambda **kw: calls.append(kw) or True)
    return calls


def test_email_sends_once_with_all_order_numbers(app, db, make_user, make_order,
                                                 captured_email):
    """Trzy zamówienia w paczce = jeden mail, w środku trzy numery."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=3,
                         tracking='ABC123', courier='inpost')

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='ABC123', courier='inpost',
            courier_name='InPost', tracking_url='https://inpost.pl/ABC123')

    assert len(captured_email) == 1
    assert len(captured_email[0]['order_numbers']) == 3
    assert captured_email[0]['request_number'] == sr.request_number
    assert captured_email[0]['tracking_number'] == 'ABC123'
    assert captured_email[0]['tracking_url'] == 'https://inpost.pl/ABC123'


def test_email_without_tracking_passes_none(app, db, make_user, make_order,
                                            captured_email):
    """Bez numeru przesyłki mail idzie, ale bez danych śledzenia."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=2)

    with app.test_request_context():
        EmailManager.notify_shipment_sent(sr)

    assert len(captured_email) == 1
    assert captured_email[0]['tracking_number'] is None
    assert len(captured_email[0]['order_numbers']) == 2


def test_email_builds_tracking_url_when_missing(app, db, make_user, make_order,
                                                captured_email):
    """Gdy URL nie podano, a jest kurier i numer — metoda go generuje."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=1,
                         tracking='XYZ999', courier='inpost')

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='XYZ999', courier='inpost', courier_name='InPost')

    assert len(captured_email) == 1
    assert captured_email[0]['tracking_url']
    assert 'XYZ999' in captured_email[0]['tracking_url']


def test_email_skipped_when_toggle_disabled(app, db, make_user, make_order,
                                            captured_email, monkeypatch):
    """Wyłączony przełącznik 'Numer przesyłki' blokuje mail o paczce z numerem."""
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=2,
                         tracking='ABC123', courier='inpost')
    monkeypatch.setattr(EmailManager, 'is_email_enabled',
                        classmethod(lambda cls, key: key != 'notify_tracking_added'))

    with app.test_request_context():
        EmailManager.notify_shipment_sent(
            sr, tracking_number='ABC123', courier='inpost', courier_name='InPost')

    assert captured_email == []


def test_email_skipped_when_no_recipient(app, db, make_user, make_order,
                                         captured_email):
    """Brak adresu e-mail kończy się cicho, bez wyjątku.

    Kolumna users.email jest NOT NULL, więc adresu nie da się wyzerować —
    brak odbiorcy odtwarzamy zleceniem bez konta klienta i bez zamówień,
    czyli dokładnie tą sytuacją, przed którą broni się metoda.
    """
    from utils.email_manager import EmailManager

    sr = _sr_with_orders(db, make_user, make_order, count=0)
    sr.user_id = None
    db.session.commit()

    with app.test_request_context():
        EmailManager.notify_shipment_sent(sr)

    assert captured_email == []
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: 3 passed z Taska 1, reszta FAIL — `AttributeError: type object 'EmailManager' has no attribute 'notify_shipment_sent'`

- [ ] **Step 3: Dopisz metodę w `utils/email_manager.py`**

Wstaw po metodzie `notify_shipping_status_change` (kończy się przed sekcją offer emails),
zachowując dekorator `@staticmethod`:

```python
    @staticmethod
    def notify_shipment_sent(shipping_request, *, tracking_number=None, courier=None,
                             courier_name=None, tracking_url=None):
        """Wysyła JEDEN mail o wysłanej paczce — na całe zlecenie wysyłki.

        Zastępuje mail per zamówienie: przy trzech zamówieniach w jednym kartonie
        klient dostawał trzy wiadomości o tej samej przesyłce. Teraz dostaje jedną,
        z listą wszystkich zamówień w środku.

        Przełączniki powiadomień: świadomie korzystamy z istniejących kluczy
        zamiast dokładać nowy — nowy klucz startowałby jako włączony i po cichu
        zmieniłby to, co sklep wysyła.

        Args:
            shipping_request: obiekt ShippingRequest
            tracking_number (str): numer przesyłki (opcjonalny)
            courier (str): slug kuriera, potrzebny do wygenerowania URL śledzenia
            courier_name (str): nazwa kuriera do wyświetlenia
            tracking_url (str): URL śledzenia; gdy brak, generowany z kuriera i numeru
        """
        tracking_number = (tracking_number or '').strip()
        toggle_key = 'notify_tracking_added' if tracking_number else 'notify_status_change'
        if not EmailManager.is_email_enabled(toggle_key):
            current_app.logger.info(
                f"Email notification '{toggle_key}' is disabled, skipping")
            return

        from utils.email_sender import send_shipment_sent_email

        orders = list(shipping_request.orders)
        user = shipping_request.user
        # Zlecenie bez użytkownika (usunięte konto) — adres bierzemy z zamówienia,
        # Order.customer_email i tak sięga do konta klienta.
        email = user.email if user else (orders[0].customer_email if orders else None)
        if not email:
            current_app.logger.warning(
                f"Cannot send shipment email for {shipping_request.request_number}: no email"
            )
            return

        if tracking_number and not tracking_url and courier:
            from modules.orders.utils import get_tracking_url
            tracking_url = get_tracking_url(courier, tracking_number)

        try:
            send_shipment_sent_email(
                user_email=email,
                user_name=(user.first_name if user else None) or 'Kliencie',
                request_number=shipping_request.request_number,
                order_numbers=[o.order_number for o in orders],
                tracking_number=tracking_number or None,
                courier_name=courier_name,
                tracking_url=tracking_url,
                shipping_requests_url=url_for('client.shipping_requests_list', _external=True),
            )
            current_app.logger.info(
                f"Shipment email sent for {shipping_request.request_number} to {email}"
            )
        except Exception as e:
            current_app.logger.error(
                f"Failed to send shipment email for {shipping_request.request_number}: {e}"
            )
```

Uwaga: metoda woła `send_shipment_sent_email` przez import z modułu, więc test podmieniający
`utils.email_sender.send_shipment_sent_email` zadziała tylko przy imporcie **wewnątrz** metody —
tak jak wyżej. Nie przenoś tego importu na górę pliku.

- [ ] **Step 4: Dopisz metodę do spisu w docstringu klasy**

W `utils/email_manager.py`, w docstringu klasy (okolice linii 35), po linii
`- notify_shipping_status_change(shipping_request, old_status_slug) -> zmiana statusu zlecenia wysyłki`
dodaj:

```
        - notify_shipment_sent(shipping_request, ...) -> jeden mail o wysłanej paczce
```

- [ ] **Step 5: Uruchom testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: `8 passed`

- [ ] **Step 6: Commit**

```bash
git add utils/email_manager.py tests/test_shipment_sent_notification.py
git commit -m "feat(wysylka): EmailManager.notify_shipment_sent — jeden mail na paczkę

Metoda bierze całe zlecenie wysyłki i składa jedną wiadomość z listą
zamówień. Korzysta z istniejących przełączników powiadomień, żeby nie
zmienić po cichu tego, co sklep wysyła.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `PushManager.notify_shipment_sent`

**Files:**
- Modify: `utils/push_manager.py` (dopisanie funkcji pomocniczej na poziomie modułu oraz metody po `notify_shipping_status_change`, tj. za linią 750)
- Test: `tests/test_shipment_sent_notification.py`

**Interfaces:**
- Consumes: `PushManager._fire_and_forget(user_id, title, body, url, tag, notification_type)`; wzorzec z `PushManager.notify_shipping_status_change` (`utils/push_manager.py:737`)
- Produces:
  - `_orders_label(count) -> str` — funkcja modułowa w `utils/push_manager.py`
  - `PushManager.notify_shipment_sent(shipping_request, tracking_number=None, courier_name=None) -> None`

- [ ] **Step 1: Napisz testy (mają nie przejść)**

Dopisz na końcu `tests/test_shipment_sent_notification.py`:

```python
# ---------- Task 3: PushManager.notify_shipment_sent ----------

@pytest.mark.parametrize('count,expected', [
    (1, '1 zamówienie'),
    (2, '2 zamówienia'),
    (4, '4 zamówienia'),
    (5, '5 zamówień'),
    (12, '12 zamówień'),
    (22, '22 zamówienia'),
])
def test_orders_label_polish_plural(count, expected):
    """Odmiana 'zamówienie' w treści pusha — 1/2-4/5+ i wyjątek dla 12-14."""
    from utils.push_manager import _orders_label

    assert _orders_label(count) == expected


def test_push_sends_once_per_package(app, db, make_user, make_order, monkeypatch):
    """Trzy zamówienia w paczce = jeden push, nie trzy."""
    from utils.push_manager import PushManager

    sr = _sr_with_orders(db, make_user, make_order, count=3,
                         tracking='ABC123', courier='inpost')
    calls = []
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: calls.append(kw)))

    with app.test_request_context():
        PushManager.notify_shipment_sent(sr, tracking_number='ABC123',
                                         courier_name='InPost')

    assert len(calls) == 1
    assert sr.request_number in calls[0]['title']
    assert 'InPost' in calls[0]['body']
    assert 'ABC123' in calls[0]['body']
    assert '3 zamówienia' in calls[0]['body']
    assert calls[0]['tag'] == f'shipment-sent-{sr.id}'


def test_push_without_tracking_has_no_number(app, db, make_user, make_order, monkeypatch):
    """Bez numeru przesyłki push mówi tylko o wysłaniu paczki."""
    from utils.push_manager import PushManager

    sr = _sr_with_orders(db, make_user, make_order, count=2)
    calls = []
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: calls.append(kw)))

    with app.test_request_context():
        PushManager.notify_shipment_sent(sr)

    assert len(calls) == 1
    assert 'Paczka wysłana' in calls[0]['body']
    assert '2 zamówienia' in calls[0]['body']


def test_push_skipped_when_no_user(app, db, make_user, make_order, monkeypatch):
    """Zlecenie bez konta klienta nie wywala pusha — po prostu go nie ma."""
    from utils.push_manager import PushManager

    sr = _sr_with_orders(db, make_user, make_order, count=1)
    sr.user_id = None
    db.session.commit()
    calls = []
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: calls.append(kw)))

    with app.test_request_context():
        PushManager.notify_shipment_sent(sr)

    assert calls == []
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: FAIL — `ImportError: cannot import name '_orders_label' from 'utils.push_manager'`

- [ ] **Step 3: Dopisz funkcję pomocniczą i metodę w `utils/push_manager.py`**

Funkcję `_orders_label` umieść na poziomie modułu, tuż przed `class PushManager`:

```python
def _orders_label(count):
    """Odmienia 'zamówienie' po polsku na potrzeby treści pusha.

    1 -> zamówienie, 2-4 -> zamówienia, 5+ -> zamówień,
    z wyjątkiem 12-14, które idą jak 5+ ('12 zamówień').
    """
    if count == 1:
        return '1 zamówienie'
    if 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f'{count} zamówienia'
    return f'{count} zamówień'
```

Metodę wstaw bezpośrednio po `notify_shipping_status_change` (kończy się w linii 750):

```python
    @staticmethod
    def notify_shipment_sent(shipping_request, tracking_number=None, courier_name=None):
        """Push o wysłanej paczce — JEDEN na zlecenie wysyłki, nie na zamówienie.

        Bez tego klient z trzema zamówieniami w jednym kartonie dostawał trzy
        powiadomienia o tej samej przesyłce.
        """
        user = shipping_request.user
        if not user:
            return

        from flask import url_for

        label = _orders_label(len(list(shipping_request.orders)))
        if tracking_number:
            body = f'{courier_name or "Kurier"}: {tracking_number} — {label}'
        else:
            body = f'Paczka wysłana — {label}'

        PushManager._fire_and_forget(
            user_id=user.id,
            title=f'Wysyłka: {shipping_request.request_number}',
            body=body,
            url=url_for('client.shipping_requests_list', _external=True),
            tag=f'shipment-sent-{shipping_request.id}',
            notification_type='shipping_updates'
        )
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: `17 passed` (8 z poprzednich tasków + 6 sparametryzowanych + 3 nowe)

- [ ] **Step 5: Commit**

```bash
git add utils/push_manager.py tests/test_shipment_sent_notification.py
git commit -m "feat(wysylka): PushManager.notify_shipment_sent — jeden push na paczkę

Jeden push zamiast jednego na każde zamówienie, prowadzi do listy zleceń
wysyłki klienta. Osobna funkcja _orders_label odmienia 'zamówienie'.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Podpięcie w `ship_shipping_request()` i aktualizacja testów WMS

**Files:**
- Modify: `modules/orders/wms_utils.py:296-339` (blok komentarza, pętla powiadomień)
- Modify: `tests/test_wms_ship_and_reopen.py:44-58` (fixture) oraz asercje w liniach 83, 102-103, 123, 138, 154, 169, 294, 348, 379-380
- Test: `tests/test_shipment_sent_notification.py`

**Interfaces:**
- Consumes: `EmailManager.notify_shipment_sent(...)` (Task 2), `PushManager.notify_shipment_sent(...)` (Task 3)
- Produces: brak nowych symboli — zmiana zachowania `ship_shipping_request()`

- [ ] **Step 1: Napisz test integracyjny (ma nie przejść)**

Dopisz na końcu `tests/test_shipment_sent_notification.py`:

```python
# ---------- Task 4: wysyłka zlecenia woła powiadomienie raz ----------

from test_wms_ship_and_reopen import _seed_statuses, _sr_packed   # noqa: E402


@pytest.fixture
def package_notifications(monkeypatch):
    """Przechwytuje powiadomienia paczkowe zamiast wysyłać maile i pushe."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    calls = {'email': [], 'push': []}
    monkeypatch.setattr(EmailManager, 'notify_shipment_sent',
                        staticmethod(lambda sr, **kw: calls['email'].append(kw.get('tracking_number'))))
    monkeypatch.setattr(PushManager, 'notify_shipment_sent',
                        staticmethod(lambda sr, **kw: calls['push'].append(kw.get('tracking_number'))))
    return calls


def test_ship_three_orders_notifies_once(client, db, make_user, make_order, login,
                                         package_notifications):
    """Trzy zamówienia w paczce = jeden mail i jeden push, nie trzy."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=3)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'courier': 'inpost', 'tracking_number': 'PACZKA1'})

    assert r.status_code == 200
    assert package_notifications['email'] == ['PACZKA1']
    assert package_notifications['push'] == ['PACZKA1']


def test_ship_without_tracking_notifies_once_without_number(client, db, make_user,
                                                            make_order, login,
                                                            package_notifications):
    """Bez numeru przesyłki też jedno powiadomienie, ale bez numeru."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=3)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship', json={})

    assert r.status_code == 200
    assert package_notifications['email'] == [None]
    assert package_notifications['push'] == [None]


def test_ship_single_order_notifies_once(client, db, make_user, make_order, login,
                                         package_notifications):
    """Paczka z jednym zamówieniem działa tą samą ścieżką — dokładnie jeden mail."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=1)

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'courier': 'dpd', 'tracking_number': 'JEDNO1'})

    assert r.status_code == 200
    assert package_notifications['email'] == ['JEDNO1']


def test_ship_with_existing_shipments_sends_nothing(client, db, make_user, make_order,
                                                    login, package_notifications):
    """Wpisy przesyłki już były — klient nie dostaje drugiego powiadomienia."""
    from modules.orders.models import OrderShipment

    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=2)
    for o in orders:
        o.status = 'wyslane'
        db.session.add(OrderShipment(order_id=o.id, tracking_number='JUZBYLO',
                                     courier='dpd'))
    db.session.commit()

    r = client.post(f'/admin/orders/shipping-requests/{sr.id}/ship',
                    json={'courier': 'dpd', 'tracking_number': 'JUZBYLO'})

    assert r.status_code == 200
    assert package_notifications['email'] == []
    assert package_notifications['push'] == []
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q -k "notifies_once or sends_nothing"`
Expected: FAIL — `assert [] == ['PACZKA1']` (stary kod woła metody per zamówienie, nie paczkowe)

- [ ] **Step 3: Zamień pętlę powiadomień w `modules/orders/wms_utils.py`**

Zamień komentarz nad blokiem `new_shipment_order_ids` (linie 298-300) na:

```python
    # Tylko NOWO powstałe wpisy przesyłki uruchamiają powiadomienie o trackingu —
    # inaczej klient, który dostał już maila z okna "Dodaj koszty", dostałby
    # identyczną wiadomość drugi raz przy "Oznacz jako wysłane".
```

Następnie zamień cały blok powiadomień (dziś linie 322-339, od `for order in sr.orders:`
do `f'Powiadomienie o wysyłce {sr.request_number}, zam. {order.order_number}: {err}')`) na:

```python
    # Jedna wiadomość na paczkę, nie na zamówienie: klient dostaje fizycznie jeden
    # karton, więc trzy maile o tej samej przesyłce były dla niego szumem.
    try:
        if new_shipment_order_ids:
            EmailManager.notify_shipment_sent(
                sr, tracking_number=tracking_number, courier=sr.courier,
                courier_name=courier_name, tracking_url=sr.tracking_url)
            PushManager.notify_shipment_sent(
                sr, tracking_number=tracking_number, courier_name=courier_name)
        elif order_status and changed_status_order_ids:
            # Bez numeru przesyłki — ta sama wiadomość, tylko bez bloku śledzenia.
            EmailManager.notify_shipment_sent(sr)
            PushManager.notify_shipment_sent(sr)
    except Exception as err:
        current_app.logger.error(
            f'Powiadomienie o wysyłce {sr.request_number}: {err}')
```

Zmienna `old_order_status_names` (linia 286) przestaje być używana — usuń jej przypisanie
razem z komentarzem nad nią (linie 285-286). Zbiór `changed_status_order_ids` zostaje,
bo decyduje teraz o wysłaniu powiadomienia bez numeru.

- [ ] **Step 4: Uruchom nowe testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: `21 passed`

- [ ] **Step 5: Uruchom stare testy WMS — mają się wywalić**

Run: `./venv/bin/python -m pytest tests/test_wms_ship_and_reopen.py -q`
Expected: kilka FAIL — fixture `notifications` podmienia metody per zamówienie, których
`ship_shipping_request()` już nie woła, więc listy zostają puste

- [ ] **Step 6: Przestaw fixture `notifications` na poziom paczki**

W `tests/test_wms_ship_and_reopen.py` zamień całą fixture (linie 44-58) na:

```python
@pytest.fixture
def notifications(monkeypatch):
    """Podmienia powiadomienia na zapis do listy — testy nie wysyłają maili.

    Powiadomienia idą raz na zlecenie wysyłki, więc listy zbierają id zlecenia,
    nie id zamówień. Rozdział na 'tracking'/'status' po tym, czy poszedł numer.
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    sent = {'tracking': [], 'status': []}

    def _email(shipping_request, **kw):
        bucket = 'tracking' if kw.get('tracking_number') else 'status'
        sent[bucket].append(shipping_request.id)

    monkeypatch.setattr(EmailManager, 'notify_shipment_sent', staticmethod(_email))
    monkeypatch.setattr(PushManager, 'notify_shipment_sent',
                        staticmethod(lambda shipping_request, **kw: None))
    return sent
```

- [ ] **Step 7: Popraw asercje w `tests/test_wms_ship_and_reopen.py`**

Zamień dokładnie te linie (numery sprzed edycji fixture; szukaj po treści):

| Było | Ma być |
|---|---|
| `assert notifications['tracking'] == [o.id for o in orders]` (linia 83) | `assert notifications['tracking'] == [sr.id]` |
| `assert notifications['status'] == [o.id for o in orders]` (linia 103) | `assert notifications['status'] == [sr.id]` |
| `assert sorted(notifications['tracking']) == sorted(o.id for o in orders)` (linia 123) | `assert notifications['tracking'] == [sr.id]` |
| `assert notifications['status'] == [o.id for o in orders]` (linia 138) | `assert notifications['status'] == [sr.id]` |
| `assert sorted(notifications['tracking']) == sorted(o.id for o in orders)` (linia 294) | `assert notifications['tracking'] == [sr.id]` |

Asercje `== []` w liniach 102, 154, 169, 348, 379, 380 zostają bez zmian — dalej znaczą
„żadnego powiadomienia".

- [ ] **Step 8: Uruchom wszystkie testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_wms_ship_and_reopen.py tests/test_shipment_sent_notification.py -q`
Expected: `38 passed` (17 starych + 21 nowych)

- [ ] **Step 9: Commit**

```bash
git add modules/orders/wms_utils.py tests/test_wms_ship_and_reopen.py tests/test_shipment_sent_notification.py
git commit -m "feat(wysylka): jedno powiadomienie na paczkę przy oznaczaniu jako wysłane

Pętla wołająca maila i pusha dla każdego zamówienia zastąpiona jednym
wywołaniem na zlecenie wysyłki. Zabezpieczenie przed dublem zostaje:
powiadomienie idzie tylko, gdy powstał nowy wpis przesyłki albo zmienił
się status.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Podpięcie w `admin_update_shipping_request()` i dołożenie pusha

**Files:**
- Modify: `modules/orders/routes.py:3926-3957`
- Test: `tests/test_shipment_sent_notification.py`

**Interfaces:**
- Consumes: `EmailManager.notify_shipment_sent(...)` (Task 2), `PushManager.notify_shipment_sent(...)` (Task 3)
- Produces: brak nowych symboli — zmiana zachowania endpointu `PUT /admin/orders/shipping-requests/<id>`

- [ ] **Step 1: Napisz test (ma nie przejść)**

Dopisz na końcu `tests/test_shipment_sent_notification.py`:

```python
# ---------- Task 5: dopisanie numeru przy edycji zlecenia ----------

def test_update_sr_with_tracking_notifies_once(client, db, make_user, make_order, login,
                                               package_notifications):
    """Dopisanie numeru przy edycji zlecenia = jeden mail i jeden push na paczkę."""
    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=3)

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'tracking_number': 'EDYCJA1', 'courier': 'inpost'})

    assert r.status_code == 200
    assert package_notifications['email'] == ['EDYCJA1']
    assert package_notifications['push'] == ['EDYCJA1']


def test_update_sr_creates_shipment_per_order(client, db, make_user, make_order, login,
                                              package_notifications):
    """Wpisy przesyłki dalej powstają dla każdego zamówienia — zmienia się tylko
    liczba wiadomości, nie liczba wpisów."""
    from modules.orders.models import OrderShipment

    login(make_user(role='admin'))
    _seed_statuses(db)
    sr, orders = _sr_packed(db, make_user, make_order, orders_count=3)

    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'tracking_number': 'WPISY1', 'courier': 'dpd'})

    assert r.status_code == 200
    assert OrderShipment.query.filter_by(tracking_number='WPISY1').count() == 3
```

- [ ] **Step 2: Uruchom testy — mają nie przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q -k update_sr`
Expected: FAIL — `assert [] == ['EDYCJA1']` (endpoint wciąż woła `notify_tracking_added` per zamówienie)

- [ ] **Step 3: Zamień blok w `modules/orders/routes.py`**

Zamień linie 3926-3957 (od komentarza `# Send tracking email and auto-create OrderShipment...`
do `db.session.commit()` domykającego ten blok) na:

```python
    # Auto-create OrderShipment + JEDNO powiadomienie na paczkę, gdy numer właśnie doszedł.
    # Wpisy przesyłki powstają nadal per zamówienie — jedna jest tylko wiadomość
    # do klienta, bo fizycznie dostaje jeden karton.
    tracking_just_added = sr.tracking_number and not old_tracking
    if tracking_just_added:
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        from modules.orders.models import OrderShipment
        courier_names = {'inpost': 'InPost', 'dpd': 'DPD', 'dhl': 'DHL', 'gls': 'GLS',
                       'poczta_polska': 'Poczta Polska', 'orlen': 'Orlen Paczka',
                       'ups': 'UPS', 'fedex': 'FedEx', 'other': 'Inny'}
        for order in sr.orders:
            existing = OrderShipment.query.filter_by(
                order_id=order.id,
                tracking_number=sr.tracking_number
            ).first()
            if not existing:
                shipment = OrderShipment(
                    order_id=order.id,
                    tracking_number=sr.tracking_number,
                    courier=sr.courier,
                    notes=f'Z zlecenia {sr.request_number}',
                    created_by=current_user.id
                )
                db.session.add(shipment)
        db.session.commit()

        courier_name = courier_names.get(sr.courier, sr.courier or 'Kurier')
        try:
            EmailManager.notify_shipment_sent(
                sr, tracking_number=sr.tracking_number, courier=sr.courier,
                courier_name=courier_name, tracking_url=sr.tracking_url)
            PushManager.notify_shipment_sent(
                sr, tracking_number=sr.tracking_number, courier_name=courier_name)
        except Exception as e:
            current_app.logger.error(
                f'Błąd powiadomienia o wysyłce zlecenia {sr.request_number}: {e}')
```

Blok poniżej (`status_actually_changed` / `notify_shipping_status_change`) zostaje bez zmian —
dotyczy zmiany statusu zlecenia, a nie wysyłki.

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `./venv/bin/python -m pytest tests/test_shipment_sent_notification.py -q`
Expected: `23 passed`

- [ ] **Step 5: Uruchom cały zestaw testów**

Run: `./venv/bin/python -m pytest tests/ -q`
Expected: wszystkie testy przechodzą; liczba niepowodzeń **0**. Gdyby coś padło poza
plikami z tego planu, to regresja — napraw przed commitem.

- [ ] **Step 6: Commit**

```bash
git add modules/orders/routes.py tests/test_shipment_sent_notification.py
git commit -m "feat(wysylka): jedno powiadomienie przy dopisaniu numeru do zlecenia

Drugie miejsce z pętlą per zamówienie — edycja zlecenia wysyłki. Przy
okazji dochodzi push, którego tam wcześniej w ogóle nie było.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Po wykonaniu planu

- Cały zestaw testów zielony: `./venv/bin/python -m pytest tests/ -q`
- Praca zostaje na gałęzi `feat/jeden-mail-o-wysylce-na-paczke` — **bez pusha**,
  merge do `main` i deploy dopiero po decyzji właścicielki.
- Zadanie ClickUp [869efb233](https://app.clickup.com/t/869efb233) do przestawienia
  na „complete" dopiero po jej akceptacji.
