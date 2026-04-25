# Powiadomienia o zmianie daty zakończenia sprzedaży — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Po zmianie daty zakończenia sprzedaży na stronie aktywnej, modal pyta admina o wysyłkę powiadomień (e-mail + push) do odpowiednich grup klientów (RODO-safe), a strona aktywna ma wyłączony autozapis.

**Architecture:** Modyfikujemy istniejący endpoint `offers_save` żeby przyjmował opcjonalne flagi powiadomień. Dodajemy nową kategorię `sale_date_changes` w `NotificationPreference`. Frontend porównuje datę z momentu otwarcia z aktualną i przed zapisem otwiera modal z checkboxami. Wysyłka leci po commicie DB w background thread, e-mail i push to dwa niezależne kanały.

**Tech Stack:** Flask, Flask-Migrate (Alembic), MariaDB, SQLAlchemy, Jinja2, vanilla JS (offer-builder.js), pywebpush, Flask-Mail.

**Spec:** `docs/superpowers/specs/2026-04-25-end-date-change-notification-design.md`

**Konwencje projektu:**
- Po każdej zmianie struktury bazy — migracja Flask-Migrate (nie ręcznie).
- Style CSS: light mode + dark mode (`[data-theme="dark"]`).
- Style modali: tylko w `static/css/components/modals.css`.
- JS/CSS w osobnych plikach, nie inline.
- Brak frameworku testów automatycznych — weryfikacja ręczna po każdym kroku.
- Commity bezpośrednio na `main` (zgodnie z istniejącym workflow projektu).

---

## Task 1: Migracja DB i model — kolumna `sale_date_changes`

**Files:**
- Modify: `modules/notifications/models.py:93-120` (klasa `NotificationPreference`)
- Create: `migrations/versions/<timestamp>_add_sale_date_changes_pref.py` (auto-generated)

- [ ] **Step 1.1: Dodaj kolumnę do modelu**

W pliku `modules/notifications/models.py`, w klasie `NotificationPreference`, dodaj nową kolumnę zaraz po `admin_alerts`:

```python
class NotificationPreference(db.Model):
    __tablename__ = 'notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)

    # Category toggles (all default True)
    order_status_changes = db.Column(db.Boolean, default=True, nullable=False)
    payment_updates = db.Column(db.Boolean, default=True, nullable=False)
    shipping_updates = db.Column(db.Boolean, default=True, nullable=False)
    new_exclusive_pages = db.Column(db.Boolean, default=True, nullable=False)
    cost_added = db.Column(db.Boolean, default=True, nullable=False)
    admin_alerts = db.Column(db.Boolean, default=True, nullable=False)
    sale_date_changes = db.Column(db.Boolean, default=True, nullable=False)

    user = db.relationship('User', backref=db.backref('notification_preference', uselist=False))

    def __repr__(self):
        return f'<NotificationPreference user={self.user_id}>'

    def to_dict(self):
        return {
            'order_status_changes': self.order_status_changes,
            'payment_updates': self.payment_updates,
            'shipping_updates': self.shipping_updates,
            'new_exclusive_pages': self.new_exclusive_pages,
            'cost_added': self.cost_added,
            'admin_alerts': self.admin_alerts,
            'sale_date_changes': self.sale_date_changes,
        }
```

- [ ] **Step 1.2: Wygeneruj migrację**

Run:
```bash
flask db migrate -m "Add sale_date_changes preference to notification_preferences"
```

Expected: nowy plik w `migrations/versions/` z `op.add_column(...)`.

- [ ] **Step 1.3: Edytuj migrację — dodaj backfill**

Otwórz wygenerowany plik migracji. W funkcji `upgrade()`, **po** `op.add_column(...)`, dodaj backfill (ustawi `TRUE` tylko jeśli WSZYSTKIE inne kategorie są `TRUE`, inaczej `FALSE`):

```python
def upgrade():
    # Auto-generated:
    op.add_column('notification_preferences',
        sa.Column('sale_date_changes', sa.Boolean(), nullable=False, server_default=sa.text('1')))

    # Backfill: TRUE tylko gdy wszystkie inne kategorie są TRUE
    op.execute("""
        UPDATE notification_preferences
        SET sale_date_changes = CASE
            WHEN order_status_changes = 1
             AND payment_updates = 1
             AND shipping_updates = 1
             AND new_exclusive_pages = 1
             AND cost_added = 1
             AND admin_alerts = 1
            THEN 1
            ELSE 0
        END
    """)


def downgrade():
    op.drop_column('notification_preferences', 'sale_date_changes')
```

- [ ] **Step 1.4: Wykonaj migrację lokalnie**

Run:
```bash
flask db upgrade
```

Expected: bez błędów, w bazie pojawia się kolumna `sale_date_changes`.

- [ ] **Step 1.5: Weryfikacja w phpMyAdmin / CLI MariaDB**

Lokalnie sprawdź:
```sql
DESCRIBE notification_preferences;
SELECT user_id, order_status_changes, sale_date_changes FROM notification_preferences LIMIT 10;
```

Sprawdź ręcznie:
- Kolumna `sale_date_changes` istnieje, jest `tinyint(1)` NOT NULL
- Użytkownicy, którzy mają wszystkie kategorie `1` → mają `sale_date_changes = 1`
- Użytkownicy, którzy mają choć jedną `0` → mają `sale_date_changes = 0`

- [ ] **Step 1.6: Commit**

```bash
git add modules/notifications/models.py migrations/versions/
git commit -m "feat: add sale_date_changes preference column with RODO-safe backfill

Backfill TRUE only for users with all other categories enabled (selective
opt-out users are not opted into the new category by default).
"
```

---

## Task 2: UI ustawień powiadomień — toggle dla nowej kategorii

**Files:**
- Modify: `templates/profile/index.html:243-291` (sekcja `pushCategories`)
- Verify: `static/js/pages/profile/push-settings.js` (już obsługuje generycznie wszystkie `data-category`)

- [ ] **Step 2.1: Dodaj nowy toggle w UI**

W pliku `templates/profile/index.html`, w sekcji `<div id="pushCategories">`, dodaj nowy `<div class="push-category-item">` **po** „Nowe koszty zamówień" (po linii ~281), **przed** `{% if current_user.role in ['admin', 'mod'] %}`:

```html
<div class="push-category-item">
    <span>Zmiana daty zakończenia sprzedaży</span>
    <label class="toggle-switch toggle-switch-sm">
        <input type="checkbox" class="push-category-toggle" data-category="sale_date_changes" checked>
        <span class="toggle-slider"></span>
    </label>
</div>
```

- [ ] **Step 2.2: Sprawdź endpoint preferencji w backend**

Otwórz `modules/notifications/routes.py` i znajdź endpoint obsługujący `POST /notifications/preferences`. Upewnij się, że obsługuje generycznie wszystkie pola (przez `setattr` lub jawną listę).

Jeśli jest jawna lista pól — dodaj `'sale_date_changes'`. Jeśli obsługuje generycznie (np. iteruje po `data.keys()` i sprawdza `hasattr(pref, key)`) — nic nie trzeba zmieniać.

- [ ] **Step 2.3: Test ręczny w przeglądarce**

Uruchom serwer dev:
```bash
flask run --port=5001
```

Otwórz `http://localhost:5001/profile`, zaloguj się, przejdź do sekcji preferencji push.

Sprawdź ręcznie:
- Nowy toggle „Zmiana daty zakończenia sprzedaży" jest widoczny
- Toggle reaguje na kliknięcie (zmienia stan wizualnie)
- Po zmianie sprawdź w DevTools → Network że `POST /notifications/preferences` przeszedł 200
- W DB: `SELECT sale_date_changes FROM notification_preferences WHERE user_id = <id>` zwraca aktualną wartość
- Wygląd OK w trybie jasnym i ciemnym

- [ ] **Step 2.4: Commit**

```bash
git add templates/profile/index.html
# Jeśli routes.py wymagał zmiany:
# git add modules/notifications/routes.py
git commit -m "feat: add 'sale date changes' toggle to user notification preferences"
```

---

## Task 3: Szablony e-maila — HTML i TXT

**Files:**
- Create: `templates/emails/sale_end_date_changed.html`
- Create: `templates/emails/sale_end_date_changed.txt`

Szablony naśladują wzorzec z `templates/emails/new_offer_page.html` (ten sam projekt, ten sam ton) — przed pisaniem otwórz tamten plik aby skopiować strukturę nagłówka i stopki.

- [ ] **Step 3.1: Sprawdź wzorzec referencyjny**

Run:
```bash
ls -la templates/emails/new_offer_page.html
```

Otwórz plik i zapamiętaj strukturę: head/style → header → content → footer. Użyj tej samej palety i tych samych klas.

- [ ] **Step 3.2: Utwórz HTML template**

Utwórz nowy plik `templates/emails/sale_end_date_changed.html`. Skopiuj nagłówek i stopkę z `new_offer_page.html`, zmień content na:

```html
{# Variables: user_name, page_name, old_ends_at_display, new_ends_at_display, page_url #}
{% extends "emails/_base.html" if false else none %}
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zaktualizowano datę zakończenia sprzedaży</title>
    {# Skopiuj <style> z templates/emails/new_offer_page.html — ten sam wygląd #}
</head>
<body>
    <div class="email-container">
        <div class="email-header">
            <h1>ThunderOrders</h1>
        </div>
        <div class="email-body">
            <p>Cześć {{ user_name }},</p>

            <p>Zaktualizowaliśmy datę zakończenia sprzedaży strony <strong>{{ page_name }}</strong>.</p>

            <table class="info-table" cellpadding="8" cellspacing="0" style="border-collapse: collapse; margin: 16px 0;">
                <tr>
                    <td><strong>Poprzednia data:</strong></td>
                    <td>{{ old_ends_at_display }}</td>
                </tr>
                <tr>
                    <td><strong>Nowa data:</strong></td>
                    <td>{{ new_ends_at_display }}</td>
                </tr>
            </table>

            <p style="text-align: center; margin: 24px 0;">
                <a href="{{ page_url }}" class="btn-primary"
                   style="background:#f093fb; color:#fff; padding:12px 24px; text-decoration:none; border-radius:6px; display:inline-block;">
                    Przejdź do strony sprzedaży
                </a>
            </p>

            <p style="font-size: 12px; color: #666; margin-top: 24px;">
                Otrzymujesz tę wiadomość, ponieważ masz zamówienie na tej stronie lub wyraziłeś/aś zgodę
                na otrzymywanie informacji marketingowych.
            </p>
        </div>
        {# Skopiuj footer z templates/emails/new_offer_page.html #}
    </div>
</body>
</html>
```

**Ważne:** rzeczywisty `<style>` i `<footer>` skopiuj 1:1 z `new_offer_page.html` żeby zachować spójność wizualną.

- [ ] **Step 3.3: Utwórz TXT template**

Utwórz `templates/emails/sale_end_date_changed.txt` (plain-text fallback):

```
Cześć {{ user_name }},

Zaktualizowaliśmy datę zakończenia sprzedaży strony "{{ page_name }}".

Poprzednia data: {{ old_ends_at_display }}
Nowa data:       {{ new_ends_at_display }}

Przejdź do strony sprzedaży:
{{ page_url }}

---
Otrzymujesz tę wiadomość, ponieważ masz zamówienie na tej stronie lub
wyraziłeś/aś zgodę na otrzymywanie informacji marketingowych.

ThunderOrders
```

- [ ] **Step 3.4: Test ręczny — render templatów**

Z poziomu shella Flask:
```bash
flask shell
```

Wewnątrz shella:
```python
from flask import render_template
print(render_template(
    'emails/sale_end_date_changed.txt',
    user_name='Test',
    page_name='Drop kwiecień 2026',
    old_ends_at_display='01.05.2026, 18:00',
    new_ends_at_display='08.05.2026, 18:00',
    page_url='http://localhost:5001/exclusive/abc'
))
```

Expected: tekst renderuje się bez błędów, podstawione zmienne widoczne.

Wyjdź z shella (`exit()`).

- [ ] **Step 3.5: Commit**

```bash
git add templates/emails/sale_end_date_changed.html templates/emails/sale_end_date_changed.txt
git commit -m "feat: email templates for sale end date change notification"
```

---

## Task 4: Funkcja `send_sale_end_date_changed_email` w email_sender.py

**Files:**
- Modify: `utils/email_sender.py` (dodaj nową funkcję na końcu pliku, przed ewentualnymi helperami modułowymi)

- [ ] **Step 4.1: Dodaj funkcję wysyłki**

Otwórz `utils/email_sender.py`, znajdź funkcję `send_back_in_stock_email` (~linia 652) jako wzorzec. Pod nią dodaj:

```python
def send_sale_end_date_changed_email(user_email, user_name, page_name,
                                      old_ends_at_display, new_ends_at_display,
                                      page_url):
    """
    Wysyła e-mail o zmianie daty zakończenia sprzedaży strony.

    Args:
        user_email (str): Adres e-mail odbiorcy
        user_name (str): Imię odbiorcy (lub 'Kliencie' jeśli brak)
        page_name (str): Nazwa strony sprzedaży
        old_ends_at_display (str): Poprzednia data sformatowana po polsku
                                   (lub 'bez limitu czasowego' jeśli brak)
        new_ends_at_display (str): Nowa data sformatowana po polsku
                                   (lub 'bez limitu czasowego' jeśli brak)
        page_url (str): Pełny URL strony sprzedaży

    Returns:
        bool: True jeśli wysłano, False w przypadku błędu
    """
    if not user_email:
        logger.warning("Cannot send sale end date changed email: no email address")
        return False

    try:
        return send_email(
            to=user_email,
            subject=f'Zaktualizowano datę zakończenia sprzedaży — {page_name}',
            template='sale_end_date_changed',
            user_name=user_name,
            page_name=page_name,
            old_ends_at_display=old_ends_at_display,
            new_ends_at_display=new_ends_at_display,
            page_url=page_url,
        )
    except Exception as e:
        logger.error(f"Failed to send sale end date changed email to {user_email}: {e}")
        return False
```

- [ ] **Step 4.2: Test ręczny — wywołanie z shella**

```bash
flask shell
```

```python
from utils.email_sender import send_sale_end_date_changed_email
result = send_sale_end_date_changed_email(
    user_email='dostepy@rsholding.com.pl',
    user_name='Konrad',
    page_name='Drop testowy',
    old_ends_at_display='01.05.2026, 18:00',
    new_ends_at_display='08.05.2026, 18:00',
    page_url='http://localhost:5001/'
)
print('Result:', result)
```

Expected: `True`, e-mail w skrzynce testowej. Sprawdź wizualnie HTML.

Wyjdź (`exit()`).

- [ ] **Step 4.3: Commit**

```bash
git add utils/email_sender.py
git commit -m "feat: add send_sale_end_date_changed_email helper"
```

---

## Task 5: `EmailManager.notify_sale_end_date_changed`

**Files:**
- Modify: `utils/email_manager.py` (dodaj nową metodę pod `notify_new_offer_page` ~linia 628)

- [ ] **Step 5.1: Dodaj metodę dispatchera**

W `utils/email_manager.py`, **bezpośrednio po** metodzie `notify_new_offer_page` (zaraz przed komentarzem `# SHIPPING REQUEST EMAILS`), dodaj:

```python
@staticmethod
def notify_sale_end_date_changed(page, old_ends_at, new_ends_at, recipients):
    """
    Wysyła e-mail o zmianie daty zakończenia sprzedaży do listy odbiorców.

    Args:
        page: obiekt OfferPage
        old_ends_at: datetime lub None — poprzednia data
        new_ends_at: datetime lub None — nowa data
        recipients: lista obiektów User (już rozwiązana — bez duplikatów)

    Returns:
        int: liczba wysłanych e-maili
    """
    if not EmailManager.is_email_enabled('notify_sale_end_date_changed'):
        current_app.logger.info(
            "Email notification 'notify_sale_end_date_changed' is disabled, skipping"
        )
        return 0

    from utils.email_sender import send_sale_end_date_changed_email

    def _format_date(dt):
        if dt is None:
            return 'bez limitu czasowego'
        return dt.strftime('%d.%m.%Y, %H:%M')

    old_display = _format_date(old_ends_at)
    new_display = _format_date(new_ends_at)

    page_url = url_for('offers.order_page', token=page.token, _external=True)
    sent_count = 0

    for client in recipients:
        email = client.email
        if not email:
            continue

        name = client.first_name or 'Kliencie'

        try:
            ok = send_sale_end_date_changed_email(
                user_email=email,
                user_name=name,
                page_name=page.name,
                old_ends_at_display=old_display,
                new_ends_at_display=new_display,
                page_url=page_url,
            )
            if ok:
                sent_count += 1
        except Exception as e:
            current_app.logger.error(
                f"Failed to send sale end date changed email to {email}: {e}"
            )

    current_app.logger.info(
        f"Sale end date changed emails sent: {sent_count}/{len(recipients)} for '{page.name}'"
    )
    return sent_count
```

- [ ] **Step 5.2: Test ręczny — wywołanie metody**

```bash
flask shell
```

```python
from utils.email_manager import EmailManager
from modules.offers.models import OfferPage
from modules.auth.models import User
from datetime import datetime

page = OfferPage.query.first()
me = User.query.filter_by(email='dostepy@rsholding.com.pl').first()
print('Page:', page.name, '| User:', me.email if me else None)

count = EmailManager.notify_sale_end_date_changed(
    page=page,
    old_ends_at=datetime(2026, 5, 1, 18, 0),
    new_ends_at=datetime(2026, 5, 8, 18, 0),
    recipients=[me]
)
print('Sent:', count)
```

Expected: `Sent: 1`, e-mail z poprawną treścią.

- [ ] **Step 5.3: Commit**

```bash
git add utils/email_manager.py
git commit -m "feat: EmailManager.notify_sale_end_date_changed dispatcher"
```

---

## Task 6: `PushManager.notify_sale_end_date_changed`

**Files:**
- Modify: `utils/push_manager.py` (dodaj nową metodę po istniejących `notify_*` metodach)

- [ ] **Step 6.1: Sprawdź wzorzec istniejących `notify_*` w PushManager**

Run:
```bash
grep -n "def notify_\|notification_type=" utils/push_manager.py
```

Otwórz `utils/push_manager.py` i znajdź metodę `notify_new_offer_page` (lub podobną). Zwróć uwagę jak buduje URL strony i jak woła `_fire_and_forget`.

- [ ] **Step 6.2: Dodaj metodę**

W `utils/push_manager.py`, na końcu klasy `PushManager`, dodaj:

```python
@staticmethod
def notify_sale_end_date_changed(page, new_ends_at, user_ids):
    """
    Wysyła push notification o zmianie daty zakończenia sprzedaży.

    Args:
        page: obiekt OfferPage
        new_ends_at: datetime lub None — nowa data
        user_ids: lista ID użytkowników do powiadomienia

    Returns:
        int: liczba użytkowników, do których push został wystrzelony
             (sukces dostarczenia weryfikuje się asynchronicznie)
    """
    from flask import url_for

    if new_ends_at is None:
        body = f'Sprzedaż przedłużona bez limitu czasowego'
    else:
        body = f'Nowa data zakończenia: {new_ends_at.strftime("%d.%m.%Y, %H:%M")}'

    title = f'{page.name} — zmiana daty zakończenia'

    try:
        url = url_for('offers.order_page', token=page.token, _external=False)
    except Exception:
        url = '/'

    tag = f'sale-date-{page.id}'
    sent = 0

    for user_id in user_ids:
        try:
            PushManager._fire_and_forget(
                user_id=user_id,
                title=title,
                body=body,
                url=url,
                tag=tag,
                notification_type='sale_date_changes',
            )
            sent += 1
        except Exception as e:
            current_app.logger.error(
                f"Failed to fire sale_date_changes push for user {user_id}: {e}"
            )

    current_app.logger.info(
        f"Sale end date changed push fired for {sent}/{len(user_ids)} users (page={page.id})"
    )
    return sent
```

- [ ] **Step 6.3: Test ręczny — wywołanie metody**

```bash
flask shell
```

```python
from utils.push_manager import PushManager
from modules.offers.models import OfferPage
from modules.auth.models import User
from datetime import datetime

page = OfferPage.query.first()
me = User.query.filter_by(email='dostepy@rsholding.com.pl').first()

PushManager.notify_sale_end_date_changed(
    page=page,
    new_ends_at=datetime(2026, 5, 8, 18, 0),
    user_ids=[me.id]
)
```

Expected: w logu `Sale end date changed push fired for 1/1 users`. Jeśli masz aktywną subskrypcję push w przeglądarce — push faktycznie przychodzi.

- [ ] **Step 6.4: Commit**

```bash
git add utils/push_manager.py
git commit -m "feat: PushManager.notify_sale_end_date_changed dispatcher"
```

---

## Task 7: Resolver odbiorców i koordynator wysyłki

**Files:**
- Modify: `modules/admin/offers.py` (dodaj funkcje na końcu pliku, przed ostatnim trailing newline)

- [ ] **Step 7.1: Dodaj resolver odbiorców**

Otwórz `modules/admin/offers.py`. Na samym końcu pliku (po wszystkich istniejących endpointach i helperach) dodaj:

```python
# ============================================
# Powiadomienia o zmianie daty zakończenia
# ============================================

def _resolve_end_date_change_recipients(page):
    """
    Rozwiązuje listy odbiorców powiadomień o zmianie daty zakończenia sprzedaży.

    E-mail (zgodnie z RODO):
        - Klienci z aktywnym (nieanulowanym) zamówieniem na tej stronie
          → mail transakcyjny (wykonanie umowy)
        - Klienci z marketing_consent=True
          → mail informacyjny
        - Wynik = unia obu zbiorów (po User.id, bez duplikatów)
        - Filtr bazowy: User.role='client', User.is_active=True

    Push:
        - Wszyscy aktywni klienci z włączoną kategorią sale_date_changes

    Returns:
        dict: {'email_users': [User, ...], 'push_user_ids': [int, ...]}
    """
    from modules.auth.models import User
    from modules.orders.models import Order
    from modules.notifications.models import NotificationPreference
    from sqlalchemy import or_

    # E-mail recipients
    buyer_ids_subq = (
        db.session.query(Order.user_id)
        .filter(
            Order.offer_page_id == page.id,
            Order.user_id.isnot(None),
            Order.status != 'anulowane',
        )
        .distinct()
        .subquery()
    )

    email_users = (
        User.query
        .filter(User.role == 'client', User.is_active == True)
        .filter(or_(
            User.marketing_consent == True,
            User.id.in_(buyer_ids_subq),
        ))
        .all()
    )

    # Push recipients
    push_users = (
        db.session.query(User.id)
        .join(NotificationPreference, NotificationPreference.user_id == User.id)
        .filter(
            User.role == 'client',
            User.is_active == True,
            NotificationPreference.sale_date_changes == True,
        )
        .all()
    )
    push_user_ids = [row[0] for row in push_users]

    return {
        'email_users': email_users,
        'push_user_ids': push_user_ids,
    }
```

- [ ] **Step 7.2: Dodaj koordynator wysyłki**

W tym samym pliku, **bezpośrednio pod** resolverem:

```python
def _dispatch_end_date_change_notifications(app, page_id, old_ends_at, new_ends_at,
                                             email_user_ids, push_user_ids):
    """
    Uruchamia wysyłki w background thread. Każdy kanał ma osłonę try/except,
    błąd jednego nie zatrzymuje drugiego.

    Args:
        app: Flask app instance (do app_context w threadzie)
        page_id (int): ID strony (re-load wewnątrz threadu, bo obiekty SA
                       z głównego requestu mogą być detached)
        old_ends_at: datetime lub None
        new_ends_at: datetime lub None
        email_user_ids: lista ID Userów do wysyłki e-mail (puste = pomiń kanał)
        push_user_ids: lista ID Userów do wysyłki push (puste = pomiń kanał)
    """
    import threading

    def _run():
        with app.app_context():
            try:
                from modules.auth.models import User
                page = OfferPage.query.get(page_id)
                if not page:
                    return

                if email_user_ids:
                    try:
                        from utils.email_manager import EmailManager
                        users = User.query.filter(User.id.in_(email_user_ids)).all()
                        EmailManager.notify_sale_end_date_changed(
                            page, old_ends_at, new_ends_at, users
                        )
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(
                            f"Email channel failed for end date change (page={page_id}): {e}"
                        )

                if push_user_ids:
                    try:
                        from utils.push_manager import PushManager
                        PushManager.notify_sale_end_date_changed(
                            page, new_ends_at, push_user_ids
                        )
                    except Exception as e:
                        from flask import current_app
                        current_app.logger.error(
                            f"Push channel failed for end date change (page={page_id}): {e}"
                        )
            except Exception as e:
                from flask import current_app
                current_app.logger.error(
                    f"Dispatcher fatal error for end date change (page={page_id}): {e}"
                )

    thread = threading.Thread(target=_run)
    thread.daemon = True
    thread.start()
```

**Uwaga architektoniczna:** dispatcher dostaje **gotowe listy ID**, a nie wywołuje resolvera samodzielnie. Resolver jest wywoływany w endpoincie (synchronicznie) — dzięki temu endpoint może zwrócić liczbę odbiorców do frontendu, a sama wysyłka leci w tle.

- [ ] **Step 7.3: Test ręczny — resolver na realnych danych**

```bash
flask shell
```

```python
from modules.admin.offers import _resolve_end_date_change_recipients
from modules.offers.models import OfferPage

page = OfferPage.query.first()
result = _resolve_end_date_change_recipients(page)
print('Email users:', len(result['email_users']))
for u in result['email_users']:
    has_order = any(o.offer_page_id == page.id and o.status != 'anulowane' for o in u.orders) if hasattr(u, 'orders') else None
    print(f"  - {u.email} | marketing={u.marketing_consent} | has_active_order={has_order}")

print('Push user IDs:', len(result['push_user_ids']))
print('  IDs:', result['push_user_ids'][:5])
```

Expected:
- Każdy klient w `email_users` ma albo `marketing_consent=True`, albo aktywne zamówienie na tej stronie
- Brak duplikatów (klient z obojgiem widnieje raz)
- `push_user_ids` zawiera tylko klientów z `sale_date_changes=True`

- [ ] **Step 7.4: Commit**

```bash
git add modules/admin/offers.py
git commit -m "feat: resolver and dispatcher for end-date-change notifications

Resolver enforces RODO: e-mail goes to active buyers (transactional) or
marketing-consent users (informational). Push goes to users with the
sale_date_changes preference enabled. Dispatcher runs both channels in
a background thread with per-channel error isolation.
"
```

---

## Task 8: Endpoint `offers_save` — przyjmowanie flag i wywołanie dispatchera

**Files:**
- Modify: `modules/admin/offers.py:211-284` (funkcja `offers_save`)

- [ ] **Step 8.1: Zaimportuj `current_app` (jeśli nie ma)**

Sprawdź na górze pliku:
```bash
grep -n "from flask import" modules/admin/offers.py | head -3
```

Jeśli `current_app` nie ma w importach, dodaj go.

- [ ] **Step 8.2: Zmodyfikuj `offers_save`**

Otwórz `modules/admin/offers.py` linia ~211 (funkcja `offers_save`). Zastąp całą funkcję poniższą wersją (zachowując identyczne zachowanie dla wszystkich pól oprócz nowego bloku flag):

```python
@admin_bp.route('/offers/<int:page_id>/save', methods=['POST'])
@login_required
@admin_required
def offers_save(page_id):
    """
    Zapisuje stronę offers (AJAX)
    Obsługuje zarówno auto-save jak i ręczny zapis.

    Dodatkowo: jeśli payload zawiera notify_email_on_end_date_change
    lub notify_push_on_end_date_change i ends_at faktycznie się zmieniła,
    po commit'cie odpala dispatcher powiadomień w background thread.
    """
    page = OfferPage.query.get_or_404(page_id)
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': 'Brak danych'}), 400

    # Flagi powiadomień (opcjonalne — domyślnie False)
    notify_email = bool(data.get('notify_email_on_end_date_change', False))
    notify_push = bool(data.get('notify_push_on_end_date_change', False))

    # Zapamiętaj starą wartość zanim ją nadpiszemy
    old_ends_at = page.ends_at

    try:
        # Aktualizacja podstawowych danych strony
        if 'name' in data:
            page.name = data['name'].strip()

        if 'description' in data:
            page.description = data['description'].strip() if data['description'] else None

        if 'footer_content' in data:
            page.footer_content = data['footer_content'].strip() if data['footer_content'] else None

        if 'starts_at' in data:
            if data['starts_at']:
                new_starts_at = datetime.strptime(data['starts_at'], '%Y-%m-%dT%H:%M')
                page.starts_at = new_starts_at

                if page.status == 'active' and new_starts_at > datetime.now():
                    page.status = 'scheduled'
            else:
                page.starts_at = None

        if 'ends_at' in data:
            if data['ends_at']:
                page.ends_at = datetime.strptime(data['ends_at'], '%Y-%m-%dT%H:%M')
            else:
                page.ends_at = None

        if 'payment_stages' in data:
            payment_stages = int(data['payment_stages'])
            if payment_stages in (3, 4):
                page.payment_stages = payment_stages

        if 'notify_clients_on_publish' in data:
            page.notify_clients_on_publish = bool(data['notify_clients_on_publish'])

        # Aktualizacja sekcji
        limit_changes = []
        if 'sections' in data:
            limit_changes = _update_sections(page, data['sections'])

        page.updated_at = datetime.now()

        db.session.commit()

        # Po commit: powiadomienia dla sekcji ze zwiększonymi limitami (jak dotąd)
        if limit_changes:
            _send_notifications_for_limit_changes(page.id, limit_changes)

        # Po commit: powiadomienia o zmianie daty zakończenia
        ends_at_changed = (old_ends_at != page.ends_at)
        notifications_sent = {'email': 0, 'push': 0}

        if ends_at_changed and (notify_email or notify_push):
            # Resolver synchronicznie — żeby zwrócić liczby do frontendu
            recipients = _resolve_end_date_change_recipients(page)

            email_user_ids = [u.id for u in recipients['email_users']] if notify_email else []
            push_user_ids = recipients['push_user_ids'] if notify_push else []

            notifications_sent['email'] = len(email_user_ids)
            notifications_sent['push'] = len(push_user_ids)

            # Faktyczna wysyłka w tle
            _dispatch_end_date_change_notifications(
                app=current_app._get_current_object(),
                page_id=page.id,
                old_ends_at=old_ends_at,
                new_ends_at=page.ends_at,
                email_user_ids=email_user_ids,
                push_user_ids=push_user_ids,
            )
            current_app.logger.info(
                f"End date change dispatched for page={page.id} "
                f"({old_ends_at} → {page.ends_at}, "
                f"email={len(email_user_ids)}, push={len(push_user_ids)})"
            )

        return jsonify({
            'success': True,
            'message': 'Zapisano',
            'updated_at': page.updated_at.strftime('%H:%M:%S') if page.updated_at else None,
            'notifications_sent': notifications_sent,
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
```

- [ ] **Step 8.3: Test ręczny — endpoint z curl**

W jednym terminalu uruchom serwer:
```bash
flask run --port=5001
```

W drugim — zaloguj się przez przeglądarkę jako admin, otwórz DevTools → Application → Cookies, skopiuj `session` cookie i `csrf_token` cookie.

Następnie wykonaj curl (zastąp wartości tokenów i page ID):
```bash
curl -X POST http://localhost:5001/admin/offers/<PAGE_ID>/save \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <CSRF_TOKEN>" \
  -b "session=<SESSION>; csrf_token=<CSRF_TOKEN>" \
  -d '{
    "ends_at": "2026-12-31T23:59",
    "notify_email_on_end_date_change": false,
    "notify_push_on_end_date_change": false
  }'
```

Expected: `{"success": true, "end_date_change_dispatched": false, ...}` (bo flagi są false).

Powtórz z `"notify_email_on_end_date_change": true` — w logu serwera pojawia się „End date change dispatched", a po sekundzie e-mail dochodzi.

Zweryfikuj że `page.ends_at` w DB ma nową wartość.

- [ ] **Step 8.4: Commit**

```bash
git add modules/admin/offers.py
git commit -m "feat: offers_save endpoint dispatches end-date-change notifications

After successful commit, if ends_at actually changed and at least one
notification flag is true, fires the dispatcher in a background thread.
"
```

---

## Task 9: Frontend — banner i wyłączenie autosave dla strony aktywnej

**Files:**
- Modify: `templates/admin/offers/edit.html` (znajdź `builderConfig` i dodaj nowe pola; dodaj banner HTML)
- Modify: `static/js/pages/admin/offer-builder.js` (autoSave + savePage)
- Modify: `static/css/pages/admin/offer-builder.css` (style banneru)

**Notatka:** banner nie jest modalem, więc jego style trafiają do dedykowanego CSS edytora — `static/css/pages/admin/offer-builder.css` (już podpięty w `edit.html` linia 6). `modals.css` rezerwujemy wyłącznie na modale.

- [ ] **Step 9.1: Dodaj `isPageActive` i `originalEndsAt` do `builderConfig`**

Otwórz `templates/admin/offers/edit.html`, znajdź miejsce gdzie definiowany jest `builderConfig` (szukaj `builderConfig = {`):

```bash
grep -n "builderConfig\|var builderConfig\|const builderConfig" templates/admin/offers/edit.html
```

W obiekcie `builderConfig` dodaj pola:

```javascript
const builderConfig = {
    pageId: {{ page.id }},
    csrfToken: '{{ csrf_token() }}',
    // ... istniejące pola ...
    isPageActive: {{ 'true' if page.status == 'active' else 'false' }},
    originalEndsAt: {% if page.ends_at %}'{{ page.ends_at|format_datetime_local }}'{% else %}null{% endif %},
    pageName: {{ page.name|tojson }},
};
```

- [ ] **Step 9.2: Dodaj banner HTML**

W `templates/admin/offers/edit.html`, znajdź główny kontener edytora (np. `<div class="builder-container">` lub element po nagłówku). Dodaj banner **bezpośrednio po** nagłówku strony, **przed** sidebarem:

```html
{% if page.status == 'active' %}
<div class="builder-active-banner" role="status">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm.93-9.412-1 4.705c-.07.34.029.533.304.533.194 0 .487-.07.686-.246l-.088.416c-.287.346-.92.598-1.465.598-.703 0-1.002-.422-.808-1.319l.738-3.468c.064-.293.006-.399-.287-.47l-.451-.081.082-.381 2.29-.287zM8 5.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/>
    </svg>
    <span>Strona jest aktywna — automatyczny zapis wyłączony, zmiany zapisuj ręcznie przyciskiem „Zapisz".</span>
</div>
{% endif %}
```

- [ ] **Step 9.3: Dodaj style banneru (light + dark mode)**

Otwórz `static/css/pages/admin/offer-builder.css` i dodaj na końcu:

```css
/* === Active page banner === */
.builder-active-banner {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    margin: 0 0 16px 0;
    background: #fff7e6;
    border: 1px solid #ffd591;
    border-left: 4px solid #fa8c16;
    border-radius: 6px;
    color: #874d00;
    font-size: 14px;
}
.builder-active-banner svg {
    flex-shrink: 0;
    color: #fa8c16;
}

/* Dark mode */
[data-theme="dark"] .builder-active-banner {
    background: rgba(250, 140, 22, 0.08);
    border: 1px solid rgba(250, 140, 22, 0.3);
    border-left: 4px solid #fa8c16;
    color: rgba(255, 255, 255, 0.9);
}
[data-theme="dark"] .builder-active-banner svg {
    color: #ffa940;
}

@media (max-width: 768px) {
    .builder-active-banner {
        font-size: 13px;
        padding: 10px 12px;
    }
}
```

- [ ] **Step 9.4: Wyłącz autosave dla strony aktywnej**

Otwórz `static/js/pages/admin/offer-builder.js`. Znajdź funkcję `autoSave` (~linia 1033). Na samym jej początku dodaj wczesny return:

```javascript
async function autoSave() {
    // Strona aktywna — autosave wyłączony, admin zapisuje ręcznie
    if (builderConfig.isPageActive) return;

    if (!isDirty) return;

    try {
        await savePage();
        showToast('Automatycznie zapisano', 'info');
    } catch (error) {
        console.error('Auto-save error:', error);
    }
}
```

- [ ] **Step 9.5: Test ręczny w przeglądarce**

Uruchom serwer (`flask run --port=5001`) i:

1. Otwórz **stronę aktywną** w edytorze
   - ✓ Banner widoczny u góry
   - ✓ W konsoli wpisz `builderConfig.isPageActive` → `true`
   - ✓ Wpisz `builderConfig.originalEndsAt` → poprawna data ISO
   - ✓ Zmień nazwę strony i poczekaj 60s — autosave **NIE** powinien się wykonać (sprawdź Network — brak requesta)

2. Otwórz **stronę draft**
   - ✓ Banner **niewidoczny**
   - ✓ `builderConfig.isPageActive` → `false`
   - ✓ Po zmianie i 60s — autosave wystrzeliwuje (request `/save` w Network)

3. Sprawdź wygląd banneru w trybie jasnym i ciemnym (przełącznik motywu).

4. Sprawdź mobile (DevTools → Toggle device toolbar) — banner się mieści, jest czytelny.

- [ ] **Step 9.6: Commit**

```bash
git add templates/admin/offers/edit.html static/js/pages/admin/offer-builder.js static/css/pages/admin/offer-builder.css
git commit -m "feat: disable autosave on active offer pages, show info banner

Active sales pages no longer auto-save in the background — admins must
explicitly click Save. A status banner explains this at the top of the
editor.
"
```

---

## Task 10: Frontend — modal HTML + CSS

**Files:**
- Modify: `templates/admin/offers/edit.html` (dodaj HTML modala)
- Modify: `static/css/components/modals.css` (style modala — light + dark)

- [ ] **Step 10.1: Dodaj HTML modala**

W `templates/admin/offers/edit.html`, na końcu pliku **przed** zamykającym `{% endblock %}` (lub przed innymi modalami jeśli już jakieś tam są), dodaj:

```html
<!-- Modal: zmiana daty zakończenia sprzedaży -->
<div id="endDateChangeModal" class="modal-overlay" aria-hidden="true">
    <div class="modal-content end-date-change-modal" role="dialog" aria-labelledby="endDateChangeModalTitle">
        <div class="modal-header">
            <h3 id="endDateChangeModalTitle">Zmieniono datę zakończenia sprzedaży</h3>
            <button type="button" class="modal-close" aria-label="Zamknij" data-end-date-cancel>&times;</button>
        </div>
        <div class="modal-body">
            <p class="end-date-change-page">
                Strona: <strong id="endDateChangePageName">—</strong>
            </p>

            <div class="end-date-change-comparison">
                <div class="end-date-change-row">
                    <span class="end-date-change-label">Stara data:</span>
                    <span id="endDateChangeOldValue" class="end-date-change-value">—</span>
                </div>
                <div class="end-date-change-row">
                    <span class="end-date-change-label">Nowa data:</span>
                    <span id="endDateChangeNewValue" class="end-date-change-value end-date-change-value-new">—</span>
                </div>
            </div>

            <div id="endDateChangePastWarning" class="end-date-change-warning" hidden>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z"/>
                </svg>
                <span>Ta data spowoduje natychmiastowe zakończenie sprzedaży.</span>
            </div>

            <div class="end-date-change-options">
                <p class="end-date-change-options-label">Powiadom klientów o zmianie:</p>
                <label class="end-date-change-checkbox">
                    <input type="checkbox" id="endDateChangeNotifyEmail" checked>
                    <span>Wyślij e-mail</span>
                </label>
                <label class="end-date-change-checkbox">
                    <input type="checkbox" id="endDateChangeNotifyPush" checked>
                    <span>Wyślij powiadomienie push</span>
                </label>
            </div>
        </div>
        <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-end-date-cancel>Anuluj</button>
            <button type="button" class="btn btn-primary" id="endDateChangeConfirm">Zapisz</button>
        </div>
    </div>
</div>
```

- [ ] **Step 10.2: Dodaj style w `modals.css` (light + dark mode)**

W `static/css/components/modals.css` na końcu pliku:

```css
/* === Modal: zmiana daty zakończenia sprzedaży === */
.end-date-change-modal {
    max-width: 480px;
}

.end-date-change-page {
    margin: 0 0 16px 0;
    font-size: 14px;
    color: #555;
}

.end-date-change-comparison {
    background: #fafafa;
    border: 1px solid #e8e8e8;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 16px;
}

.end-date-change-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
}

.end-date-change-label {
    font-size: 13px;
    color: #666;
}

.end-date-change-value {
    font-size: 14px;
    font-weight: 600;
    color: #333;
}

.end-date-change-value-new {
    color: #f5576c;
}

.end-date-change-warning {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #fff1f0;
    border: 1px solid #ffa39e;
    border-left: 4px solid #f5222d;
    border-radius: 6px;
    padding: 10px 12px;
    margin-bottom: 16px;
    color: #cf1322;
    font-size: 13px;
}

.end-date-change-warning svg {
    flex-shrink: 0;
    color: #f5222d;
}

.end-date-change-options {
    margin-top: 8px;
}

.end-date-change-options-label {
    margin: 0 0 8px 0;
    font-size: 13px;
    font-weight: 600;
    color: #444;
}

.end-date-change-checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    cursor: pointer;
    font-size: 14px;
    /* Mobile-friendly touch target ≥ 44px */
    min-height: 44px;
}

.end-date-change-checkbox input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
}

/* === Dark mode === */
[data-theme="dark"] .end-date-change-page {
    color: rgba(255, 255, 255, 0.7);
}

[data-theme="dark"] .end-date-change-comparison {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .end-date-change-label {
    color: rgba(255, 255, 255, 0.6);
}

[data-theme="dark"] .end-date-change-value {
    color: #ffffff;
}

[data-theme="dark"] .end-date-change-value-new {
    color: #f093fb;
}

[data-theme="dark"] .end-date-change-warning {
    background: rgba(245, 34, 45, 0.1);
    border: 1px solid rgba(245, 34, 45, 0.3);
    border-left: 4px solid #f5222d;
    color: #ff7875;
}

[data-theme="dark"] .end-date-change-warning svg {
    color: #ff7875;
}

[data-theme="dark"] .end-date-change-options-label {
    color: rgba(255, 255, 255, 0.85);
}

[data-theme="dark"] .end-date-change-checkbox {
    color: rgba(255, 255, 255, 0.9);
}
```

- [ ] **Step 10.3: Test ręczny — wymuszenie pokazania modala**

Otwórz `http://localhost:5001/admin/offers/<page_id>/edit` w przeglądarce (dowolnej strony, draft też wystarczy).

W konsoli przeglądarki:
```javascript
const modal = document.getElementById('endDateChangeModal');
document.getElementById('endDateChangePageName').textContent = 'Drop testowy';
document.getElementById('endDateChangeOldValue').textContent = '01.05.2026, 18:00';
document.getElementById('endDateChangeNewValue').textContent = '08.05.2026, 18:00';
document.getElementById('endDateChangePastWarning').hidden = false;
modal.classList.add('active');
```

Sprawdź:
- ✓ Modal się pokazuje, jest scentrowany
- ✓ Nazwa strony, stara/nowa data są widoczne
- ✓ Czerwone ostrzeżenie widoczne
- ✓ Dwa checkboxy zaznaczone
- ✓ Wygląd OK w trybie jasnym i ciemnym
- ✓ Mobile: checkboxy klikalne, tekst się mieści

Ukryj modal:
```javascript
modal.classList.remove('active');
document.getElementById('endDateChangePastWarning').hidden = true;
```

- [ ] **Step 10.4: Commit**

```bash
git add templates/admin/offers/edit.html static/css/components/modals.css
git commit -m "feat: end-date-change modal markup and styles (light + dark)"
```

---

## Task 11: Frontend — JS modala i integracja z `savePage`

**Files:**
- Modify: `static/js/pages/admin/offer-builder.js` (funkcje modala + hook w `savePage`)

- [ ] **Step 11.1: Dodaj funkcje modala**

Otwórz `static/js/pages/admin/offer-builder.js`. Znajdź funkcję `savePage` (~linia 993). **Bezpośrednio przed nią** dodaj funkcje pomocnicze:

```javascript
/**
 * Format ISO datetime-local value to Polish display string.
 * Returns 'bez limitu czasowego' for null/empty.
 */
function formatEndsAtForDisplay(isoValue) {
    if (!isoValue) return 'bez limitu czasowego';
    // isoValue format: "2026-05-08T18:00"
    const [datePart, timePart] = isoValue.split('T');
    const [y, m, d] = datePart.split('-');
    const [hh, mm] = (timePart || '00:00').split(':');
    return `${d}.${m}.${y}, ${hh}:${mm}`;
}

/**
 * Open the end-date change modal and resolve with the user's decision.
 * Returns Promise<{cancelled: bool, notifyEmail: bool, notifyPush: bool}>.
 */
function openEndDateChangeModal(oldEndsAt, newEndsAt, pageName) {
    return new Promise((resolve) => {
        const modal = document.getElementById('endDateChangeModal');
        const pageNameEl = document.getElementById('endDateChangePageName');
        const oldValueEl = document.getElementById('endDateChangeOldValue');
        const newValueEl = document.getElementById('endDateChangeNewValue');
        const warningEl = document.getElementById('endDateChangePastWarning');
        const emailCb = document.getElementById('endDateChangeNotifyEmail');
        const pushCb = document.getElementById('endDateChangeNotifyPush');
        const confirmBtn = document.getElementById('endDateChangeConfirm');
        const cancelEls = modal.querySelectorAll('[data-end-date-cancel]');

        pageNameEl.textContent = pageName || '';
        oldValueEl.textContent = formatEndsAtForDisplay(oldEndsAt);
        newValueEl.textContent = formatEndsAtForDisplay(newEndsAt);

        // Past-date warning
        const isPast = newEndsAt && new Date(newEndsAt) < new Date();
        warningEl.hidden = !isPast;

        // Reset checkboxy do domyślnych (oba zaznaczone)
        emailCb.checked = true;
        pushCb.checked = true;

        const cleanup = () => {
            modal.classList.remove('active');
            confirmBtn.removeEventListener('click', onConfirm);
            cancelEls.forEach(el => el.removeEventListener('click', onCancel));
            modal.removeEventListener('click', onOverlayClick);
        };

        const onConfirm = () => {
            const decision = {
                cancelled: false,
                notifyEmail: emailCb.checked,
                notifyPush: pushCb.checked,
            };
            cleanup();
            resolve(decision);
        };

        const onCancel = () => {
            cleanup();
            resolve({ cancelled: true, notifyEmail: false, notifyPush: false });
        };

        const onOverlayClick = (e) => {
            if (e.target === modal) onCancel();
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelEls.forEach(el => el.addEventListener('click', onCancel));
        modal.addEventListener('click', onOverlayClick);

        modal.classList.add('active');
    });
}
```

- [ ] **Step 11.2: Zmodyfikuj `savePage`**

Zastąp funkcję `savePage` (~linia 993) tą wersją:

```javascript
async function savePage() {
    const data = collectPageData();

    if (!validatePageData(data)) {
        return false;
    }

    // Hook: strona aktywna + zmiana ends_at → modal
    if (builderConfig.isPageActive && data.ends_at !== builderConfig.originalEndsAt) {
        const decision = await openEndDateChangeModal(
            builderConfig.originalEndsAt,
            data.ends_at,
            builderConfig.pageName
        );

        if (decision.cancelled) {
            // Przywróć datę w polu i pomiń zapis
            const endsAtInput = document.getElementById('endsAt');
            if (endsAtInput) {
                endsAtInput.value = builderConfig.originalEndsAt || '';
            }
            return false;
        }

        data.notify_email_on_end_date_change = decision.notifyEmail;
        data.notify_push_on_end_date_change = decision.notifyPush;
    }

    try {
        const response = await fetch(`/admin/offers/${builderConfig.pageId}/save`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': builderConfig.csrfToken
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            isDirty = false;
            lastSaveTime = new Date();
            document.getElementById('lastSaved').textContent = `Ostatni zapis: ${result.updated_at}`;

            // Aktualizuj originalEndsAt — kolejne zmiany porównujemy z nową bazą
            builderConfig.originalEndsAt = data.ends_at;

            const sent = result.notifications_sent || { email: 0, push: 0 };
            if (sent.email > 0 || sent.push > 0) {
                showToast(
                    `Zapisano. Wysyłka do ${sent.email} maili, ${sent.push} powiadomień push.`,
                    'success'
                );
            } else {
                showToast('Zapisano zmiany', 'success');
            }
            return true;
        } else {
            showToast(result.error || 'Błąd zapisu', 'error');
            return false;
        }
    } catch (error) {
        console.error('Save error:', error);
        showToast('Błąd połączenia', 'error');
        return false;
    }
}
```

- [ ] **Step 11.3: Test ręczny — pełna ścieżka happy path**

1. Uruchom serwer: `flask run --port=5001`.
2. Zaloguj się jako admin, otwórz **stronę aktywną** w edytorze.
3. **Test 1: anulowanie**
   - Zmień datę zakończenia w polu `endsAt`
   - Kliknij „Zapisz"
   - ✓ Modal się otwiera ze starą i nową datą
   - Kliknij „Anuluj"
   - ✓ Modal się zamyka, data w polu wraca do pierwotnej
   - ✓ W bazie `page.ends_at` bez zmian (sprawdź phpMyAdmin)

4. **Test 2: zapis bez powiadomień**
   - Zmień datę
   - Kliknij „Zapisz" → modal
   - **Odznacz** oba checkboxy
   - Kliknij „Zapisz" w modalu
   - ✓ Toast: „Zapisano zmiany"
   - ✓ W bazie nowa data
   - ✓ Brak wpisu „End date change dispatched" w logu

5. **Test 3: zapis z e-mailem**
   - Zmień datę ponownie
   - Modal → checkbox e-mail zaznaczony, push odznaczony → „Zapisz"
   - ✓ Toast: „Zapisano. Powiadomienia wysłane do klientów."
   - ✓ W logu: „End date change dispatched for page=X"
   - ✓ E-mail dochodzi (do skrzynki testowej, jeśli ona spełnia kryteria odbiorców)

6. **Test 4: data w przeszłości**
   - Wpisz datę z wczoraj
   - Modal pokazuje czerwone ostrzeżenie „Ta data spowoduje natychmiastowe zakończenie sprzedaży"
   - „Zapisz" → status strony zmienia się na `ended` (sprawdź w DB lub po przeładowaniu strony)

7. **Test 5: zmiana innego pola**
   - Otwórz stronę aktywną, zmień nazwę strony lub opis
   - Kliknij „Zapisz"
   - ✓ Modal **nie** się pokazuje
   - ✓ Zwykły zapis

8. **Test 6: strona nieaktywna**
   - Otwórz stronę draft, zmień datę
   - Kliknij „Zapisz"
   - ✓ Modal **nie** się pokazuje (zwykły zapis bez modala)

- [ ] **Step 11.4: Commit**

```bash
git add static/js/pages/admin/offer-builder.js
git commit -m "feat: modal flow for end date change on active offer pages

savePage detects ends_at change on active pages, opens modal asking which
channels (email/push) to notify, and includes the decision in the save
payload. Cancel restores original date without saving.
"
```

---

## Task 12: Smoke test pełnej ścieżki + lista kontrolna ze specu

**Files:** brak modyfikacji — tylko weryfikacja.

- [ ] **Step 12.1: Pełna lista kontrolna ze specu**

Wyciągnij `docs/superpowers/specs/2026-04-25-end-date-change-notification-design.md` sekcja „Plan testów ręcznych" i przejdź każdy punkt:

**Edytor strony**
- [ ] Strona `draft` / `scheduled` / `paused` → autozapis działa, banner się nie pokazuje
- [ ] Strona `active` → autozapis nie działa, banner widoczny
- [ ] Zmiana innego pola na stronie aktywnej → modal się nie pokazuje
- [ ] Zmiana daty na aktywnej → modal się pokazuje
- [ ] Modal w trybie jasnym i ciemnym
- [ ] Modal na mobile (touch targets ≥ 44px, ostrzeżenie i checkboxy klikalne)

**Wysyłka — e-mail**
- [ ] Klient z aktywnym zamówieniem na tej stronie, bez zgody marketingowej → mail dochodzi
- [ ] Klient ze zgodą marketingową, bez zamówienia → mail dochodzi
- [ ] Klient bez zamówienia i bez zgody → mail nie dochodzi
- [ ] Klient z zamówieniem **i** zgodą → mail dochodzi raz (bez duplikatów)
- [ ] Klient z **anulowanym** zamówieniem na tej stronie i bez zgody → mail **nie** dochodzi

**Wysyłka — push**
- [ ] Klient z włączoną kategorią `sale_date_changes` → push dochodzi
- [ ] Klient z wyłączoną kategorią → push nie dochodzi
- [ ] Klient bez aktywnej subskrypcji push → pomijany bez błędu

**Migracja**
- [ ] Po migracji: użytkownik miał wszystkie kategorie włączone → ma `sale_date_changes = 1`
- [ ] Użytkownik wyłączył jedną z istniejących → ma `sale_date_changes = 0`
- [ ] Nowy użytkownik (zarejestruj świeże konto) → domyślnie `sale_date_changes = 1`

**Strona ustawień**
- [ ] Nowy przełącznik „Zmiana daty zakończenia sprzedaży" widoczny
- [ ] Działa w trybie jasnym i ciemnym
- [ ] Zapis utrwala się w bazie (sprawdź `SELECT sale_date_changes FROM notification_preferences WHERE user_id = ?`)

**Logi serwera**
- [ ] Po zapisie z włączonymi powiadomieniami: wpis „End date change dispatched for page=X (... → ..., email=True/False, push=True/False)"
- [ ] Wpis informujący o liczbie wysłanych e-maili i pushów (z metod EmailManager / PushManager)
- [ ] Brak wpisu przy zapisie strony nieaktywnej

- [ ] **Step 12.2: Brak commit'a**

To zadanie tylko weryfikuje. Jeśli któryś punkt nie przechodzi — wróć do odpowiedniego task'a, popraw, dorób commit. Nie commituj samych checkboxów listy.

---

## Po zakończeniu wszystkich tasków

- [ ] **Push do GitHub:**

```bash
git push origin main
```

GitHub webhook automatycznie deployuje na produkcję (włącznie z migracją). Zweryfikuj na produkcji:
- Otwórz `https://thunderorders.cloud/admin/offers/<page_id>/edit`
- Zaloguj się jako admin
- Sprawdź banner i nową kategorię w preferencjach klienta

- [ ] **Smoke test na produkcji:**

Powtórz minimum 2 testy z listy 12.1 (banner widoczny + jeden test wysyłki) na produkcji.
