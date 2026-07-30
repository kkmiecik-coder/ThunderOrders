# Zaległości płatnicze — kafelek, lista i przypomnienia dla wszystkich etapów Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Daj Karolinie jeden kafelek na dashboardzie i jedną stronę pokazującą wszystkie zamówienia, które zalegają z płatnością na dowolnym etapie (E1–E4), oraz rozszerz automatyczne przypomnienia mailowe z etapu 1/2 na wszystkie cztery etapy z jedną wspólną regułą.

**Architecture:** Cała logika „czy i o ile zamówienie zalega" żyje w jednym nowym module `modules/orders/payment_overdue_service.py`, w słowniku `STAGE_DEFINITIONS` — jedynym miejscu opisującym cztery etapy płatności (status, kwota, termin, czy dotyczy zamówienia). Dashboard, nowa strona listy, cron przypomnień i builder maila korzystają z tego samego słownika, więc nie ma czterech kopii tej samej logiki rozsianych po repo.

**Tech Stack:** Flask, SQLAlchemy, Alembic (Flask-Migrate), Jinja2, pytest.

## Global Constraints

- Liczymy na bieżąco (bez cache'a) — decyzja ze specu, bez cache'owania w tle.
- Kryterium zaległości: `deadline` etapu ustawiony I minął I kwota etapu > 0 I status etapu w (`none`, `rejected`) — status `pending`/`approved` nigdy nie jest zaległością. Etap bez ustalonego terminu nigdy nie jest zaległy.
- Zamówienia w statusie `anulowane` są pomijane wszędzie (istniejąca konwencja repo — brak osobnego statusu „zakończone" w kodzie; w pełni opłacone zamówienie nigdy nie ma zaległej kwoty, więc nie wymaga osobnego filtra).
- Jedna wspólna reguła przypomnień (`PaymentReminderConfig`) obowiązuje wszystkie 4 etapy — bez dodatkowego wymiaru per-etap w UI ani w cronie.
- `PaymentReminderLog` musi rozróżniać etap (`stage`), inaczej jeden wysłany mail zablokuje wysyłkę przypomnienia o innym etapie tego samego zamówienia pod tą samą regułą.
- Reguła `after_order_placed` pozostaje ograniczona do etapu `product` (jedyny etap liczony „od złożenia zamówienia" — pozostałe trzy mają realne terminy w bazie, więc liczą się tylko regułą `before_deadline`).
- Kod PL, komentarze tylko tam gdzie nieoczywiste, styl istniejącego repo (Decimal do kwot, `get_local_now()` do czasu, wzorce z `modules/orders/models.py`).

---

## Plik `modules/orders/payment_overdue_service.py` — mapa odpowiedzialności

Nowy plik, jedyne miejsce z definicją czterech etapów płatności:
- `STAGE_DEFINITIONS`: dict `{stage_kod: {'label', 'status', 'amount', 'deadline', 'applies'}}` — każda wartość poza `label` to funkcja `lambda order: ...`.
- `get_order_overdue_stages(order, now=None)`: zwraca listę zaległych etapów jednego zamówienia.
- `get_overdue_orders_summary()`: zwraca listę wszystkich aktywnych zamówień z ≥1 zaległym etapem, posortowaną od najdłużej zalegających.

Konsumenci tego pliku (kolejne zadania): `modules/admin/routes.py` (kafelek + strona listy), `app.py` (cron), `utils/email_manager.py` (treść maila).

---

### Task 1: `Order.get_product_deadline()` — brakujący getter terminu E1

Dziś istnieją gettery terminu dla E2/E3/E4 (`get_shipping_kr_deadline`, `get_customs_vat_deadline`, `get_shipping_pl_deadline`, `modules/orders/models.py:1009-1030`), ale nie ma odpowiednika dla E1 (produkt) — cron dziś czyta `page.payment_deadline` bezpośrednio w pętli. Potrzebny jest getter na `Order`, żeby `payment_overdue_service.py` mógł traktować wszystkie 4 etapy jednolicie.

**Files:**
- Modify: `modules/orders/models.py:1009` (dodać metodę bezpośrednio przed `get_shipping_kr_deadline`)
- Test: `tests/test_order_deadline_getters.py`

**Interfaces:**
- Produces: `Order.get_product_deadline() -> datetime | None` — termin E1 z powiązanej `OfferPage`; `None` gdy zamówienie nie ma `offer_page` (on_hand/pre_order bez strony sprzedaży nie mają stałego terminu, tylko relatywny „X godzin po złożeniu").

- [ ] **Step 1: Write the failing test**

```python
# tests/test_order_deadline_getters.py
from datetime import datetime, timezone


def test_get_product_deadline_from_offer_page(db, make_user, make_order):
    from modules.offers.models import OfferPage

    user = make_user()
    deadline = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    page = OfferPage(name='Test Page', slug='test-page-deadline', payment_deadline=deadline)
    db.session.add(page)
    db.session.commit()

    order = make_order(user, offer_page_id=page.id)

    assert order.get_product_deadline() == deadline


def test_get_product_deadline_none_without_offer_page(db, make_user, make_order):
    user = make_user()
    order = make_order(user)

    assert order.get_product_deadline() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_order_deadline_getters.py -v`
Expected: FAIL with `AttributeError: 'Order' object has no attribute 'get_product_deadline'`

- [ ] **Step 3: Write minimal implementation**

```python
# modules/orders/models.py, wstawić przed `def get_shipping_kr_deadline(self):` (linia 1009)
    def get_product_deadline(self):
        """Get payment deadline for E1 (product) from the offer page.

        Zamówienia on_hand/pre_order bez strony sprzedaży nie mają stałego
        terminu — ich przypomnienie liczy się regułą 'after_order_placed'
        (godziny od created_at), nie tym getterem.
        """
        if self.offer_page:
            return self.offer_page.payment_deadline
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_order_deadline_getters.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add modules/orders/models.py tests/test_order_deadline_getters.py
git commit -m "feat(zaleglosci): dodaj Order.get_product_deadline() jako odpowiednik gettera E1"
```

---

### Task 2: `payment_overdue_service.py` — rdzeń logiki „kto zalega"

**Files:**
- Create: `modules/orders/payment_overdue_service.py`
- Test: `tests/test_payment_overdue_service.py`

**Interfaces:**
- Consumes: `Order.get_product_deadline()` (Task 1), `Order.get_shipping_kr_deadline()`, `Order.get_customs_vat_deadline()`, `Order.get_shipping_pl_deadline()`, `Order.product_payment_status`, `Order.stage_2_status`, `Order.stage_3_status`, `Order.stage_4_status`, `Order.has_customs_vat_stage`, `Order.payment_stages`, `Order.total_amount`, `Order.proxy_shipping_cost`, `Order.customs_vat_sale_cost`, `Order.shipping_cost` (wszystkie istniejące, `modules/orders/models.py`), `get_local_now()` (`modules/orders/models.py`).
- Produces:
  - `STAGE_DEFINITIONS: dict` — klucze `'product' | 'shipping_kr' | 'customs_vat' | 'domestic_shipping'`, każda wartość ma `'label': str`, `'status': callable(order) -> str`, `'amount': callable(order) -> Decimal|None`, `'deadline': callable(order) -> datetime|None`, `'applies': callable(order) -> bool`.
  - `get_order_overdue_stages(order, now=None) -> list[dict]` — każdy element: `{'stage': str, 'stage_label': str, 'amount': Decimal, 'deadline': datetime, 'days_overdue': int}`.
  - `get_overdue_orders_summary() -> list[dict]` — każdy element: `{'order': Order, 'overdue_stages': list[dict], 'primary_stage': dict}`, posortowane malejąco po `primary_stage['days_overdue']`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payment_overdue_service.py
from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def _confirm(db, order, stage, status='approved', amount=Decimal('10.00')):
    from modules.orders.models import PaymentConfirmation
    c = PaymentConfirmation(order_id=order.id, payment_stage=stage, status=status, amount=amount)
    db.session.add(c)
    db.session.commit()
    return c


def test_no_overdue_when_no_deadlines(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: None
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order) == []


def test_product_overdue_when_deadline_passed_and_unpaid(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=3)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    stages = get_order_overdue_stages(order, now=now)

    assert len(stages) == 1
    assert stages[0]['stage'] == 'product'
    assert stages[0]['amount'] == Decimal('100.00')
    assert stages[0]['days_overdue'] == 3


def test_not_overdue_when_deadline_in_future(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now + timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order, now=now) == []


def test_not_overdue_when_already_approved(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None
    _confirm(db, order, 'product', status='approved')

    assert get_order_overdue_stages(order, now=now) == []


def test_not_overdue_when_pending_confirmation(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None
    _confirm(db, order, 'product', status='pending')

    assert get_order_overdue_stages(order, now=now) == []


def test_customs_vat_not_overdue_when_stage_not_applicable(db, make_user, make_order):
    """order_type='on_hand' -> has_customs_vat_stage=False, etap E3 pomijany nawet z minionym terminem."""
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(
        make_user(), total_amount=Decimal('100.00'),
        order_type='on_hand', customs_vat_sale_cost=Decimal('20.00')
    )
    order.get_product_deadline = lambda: None
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: now - timedelta(days=5)
    order.get_shipping_pl_deadline = lambda: None

    assert get_order_overdue_stages(order, now=now) == []


def test_multiple_overdue_stages_on_one_order(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_order_overdue_stages

    now = get_local_now()
    order = make_order(
        make_user(), total_amount=Decimal('100.00'),
        order_type='exclusive', payment_stages=4,
        proxy_shipping_cost=Decimal('30.00'),
        customs_vat_sale_cost=Decimal('20.00'),
        shipping_cost=Decimal('15.00'),
    )
    order.get_product_deadline = lambda: now - timedelta(days=5)
    order.get_shipping_kr_deadline = lambda: now - timedelta(days=2)
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    stages = get_order_overdue_stages(order, now=now)

    assert {s['stage'] for s in stages} == {'product', 'shipping_kr'}
    days = {s['stage']: s['days_overdue'] for s in stages}
    assert days['product'] == 5 and days['shipping_kr'] == 2


def test_summary_sorts_by_most_overdue_first(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_overdue_orders_summary

    now = get_local_now()
    u = make_user()
    o1 = make_order(u, total_amount=Decimal('50.00'))
    o1.get_product_deadline = lambda: now - timedelta(days=1)
    o1.get_shipping_kr_deadline = lambda: None
    o1.get_customs_vat_deadline = lambda: None
    o1.get_shipping_pl_deadline = lambda: None

    o2 = make_order(u, total_amount=Decimal('50.00'))
    o2.get_product_deadline = lambda: now - timedelta(days=10)
    o2.get_shipping_kr_deadline = lambda: None
    o2.get_customs_vat_deadline = lambda: None
    o2.get_shipping_pl_deadline = lambda: None

    result = get_overdue_orders_summary()

    ids_in_order = [r['order'].id for r in result if r['order'].id in (o1.id, o2.id)]
    assert ids_in_order == [o2.id, o1.id]


def test_summary_excludes_cancelled_orders(db, make_user, make_order):
    from modules.orders.payment_overdue_service import get_overdue_orders_summary

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('50.00'), status='anulowane')
    order.get_product_deadline = lambda: now - timedelta(days=1)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    result = get_overdue_orders_summary()

    assert order.id not in [r['order'].id for r in result]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_payment_overdue_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'modules.orders.payment_overdue_service'`

- [ ] **Step 3: Write minimal implementation**

```python
# modules/orders/payment_overdue_service.py
"""
Jedyne źródło prawdy o tym, które etapy płatności (E1-E4) danego zamówienia
są zaległe — termin minął, kwota nieopłacona. Używane przez kafelek i stronę
zaległości w panelu admina, cron przypomnień i builder maila przypomnienia.
"""
from modules.orders.models import get_local_now

STAGE_DEFINITIONS = {
    'product': {
        'label': 'Płatność za produkt',
        'status': lambda order: order.product_payment_status,
        'amount': lambda order: order.total_amount,
        'deadline': lambda order: order.get_product_deadline(),
        'applies': lambda order: True,
    },
    'shipping_kr': {
        'label': 'Płatność za wysyłkę z Korei',
        'status': lambda order: order.stage_2_status,
        'amount': lambda order: order.proxy_shipping_cost,
        'deadline': lambda order: order.get_shipping_kr_deadline(),
        'applies': lambda order: order.payment_stages == 4,
    },
    'customs_vat': {
        'label': 'Cło/VAT',
        'status': lambda order: order.stage_3_status,
        'amount': lambda order: order.customs_vat_sale_cost,
        'deadline': lambda order: order.get_customs_vat_deadline(),
        'applies': lambda order: order.has_customs_vat_stage,
    },
    'domestic_shipping': {
        'label': 'Wysyłka krajowa (PL)',
        'status': lambda order: order.stage_4_status,
        'amount': lambda order: order.shipping_cost,
        'deadline': lambda order: order.get_shipping_pl_deadline(),
        'applies': lambda order: True,
    },
}

# Statusy etapu, przy których zamówienie NIGDY nie jest liczone jako zaległe:
# 'pending' (klient już wgrał dowód, czeka na weryfikację admina) i 'approved'.
_NOT_OVERDUE_STATUSES = ('pending', 'approved')


def get_order_overdue_stages(order, now=None):
    """Zwraca listę zaległych etapów jednego zamówienia.

    Etap liczy się jako zaległy, gdy: dotyczy zamówienia (`applies`), ma
    ustalony termin (`deadline` nie jest None), termin minął, kwota > 0
    i status etapu to 'none' lub 'rejected'. Brak ustalonego terminu NIE
    jest zaległością (nie da się przekroczyć terminu, którego nie ma).
    """
    now = now or get_local_now()
    overdue = []

    for stage, definition in STAGE_DEFINITIONS.items():
        if not definition['applies'](order):
            continue

        status = definition['status'](order)
        if status in _NOT_OVERDUE_STATUSES:
            continue

        deadline = definition['deadline'](order)
        if deadline is None or deadline >= now:
            continue

        amount = definition['amount'](order)
        if not amount or amount <= 0:
            continue

        overdue.append({
            'stage': stage,
            'stage_label': definition['label'],
            'amount': amount,
            'deadline': deadline,
            'days_overdue': (now - deadline).days,
        })

    return overdue


def get_overdue_orders_summary():
    """Zwraca aktywne zamówienia z >=1 zaległym etapem, najdłużej zalegające pierwsze."""
    from modules.orders.models import Order

    now = get_local_now()
    results = []

    for order in Order.query.filter(Order.status != 'anulowane').all():
        stages = get_order_overdue_stages(order, now=now)
        if not stages:
            continue
        primary_stage = max(stages, key=lambda s: s['days_overdue'])
        results.append({
            'order': order,
            'overdue_stages': stages,
            'primary_stage': primary_stage,
        })

    results.sort(key=lambda r: r['primary_stage']['days_overdue'], reverse=True)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_payment_overdue_service.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add modules/orders/payment_overdue_service.py tests/test_payment_overdue_service.py
git commit -m "feat(zaleglosci): dodaj payment_overdue_service z jedyna definicja etapow E1-E4"
```

---

### Task 3: Kafelek „Zaległości płatnicze" na dashboardzie

**Files:**
- Modify: `modules/admin/routes.py:288-308` (funkcja `dashboard()`)
- Modify: `templates/admin/dashboard.html:16-64`
- Test: `tests/test_dashboard_overdue_widget.py`

**Interfaces:**
- Consumes: `get_overdue_orders_summary()` (Task 2, `modules/orders/payment_overdue_service.py`).
- Produces: kontekst szablonu `overdue_payments_count: int` przekazywany do `admin/dashboard.html`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_overdue_widget.py
from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def test_dashboard_shows_overdue_count(app, db, make_user, make_order, client, login):
    admin = make_user(role='admin')
    login(admin)

    now = get_local_now()
    order = make_order(make_user(), total_amount=Decimal('100.00'))
    order.get_product_deadline = lambda: now - timedelta(days=2)

    resp = client.get('/admin/dashboard')

    assert resp.status_code == 200
    assert b'zalega' in resp.data


def test_dashboard_hides_widget_when_nothing_overdue(app, db, make_user, client, login):
    admin = make_user(role='admin')
    login(admin)

    resp = client.get('/admin/dashboard')

    assert resp.status_code == 200
    assert b'z p\xc5\x82atno\xc5\x9bci\xc4\x85' not in resp.data
```

**Uwaga:** pierwszy test polega na monkeypatchu instancji `order.get_product_deadline`, który przeżyje request tylko dlatego, że test i request działają w tej samej sesji SQLAlchemy/pamięci procesu (SQLite in-memory z fixture `db`) — obiekt `order` pobrany przez `dashboard()` w tym samym procesie to ten sam obiekt Pythona dzięki identity mapowi sesji. Jeśli test się nie powiedzie z tego powodu, zamiast monkeypatcha ustaw realny `OfferPage.payment_deadline` i `order.offer_page_id` (patrz Task 1 test).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_overdue_widget.py -v`
Expected: FAIL — `assert b'zalega' in resp.data` fails (kafelek jeszcze nie istnieje)

- [ ] **Step 3: Write minimal implementation**

W `modules/admin/routes.py`, dodaj import i wywołanie przed `return render_template(...)` w `dashboard()`:

```python
    # 11. Zaległości płatnicze (kafelek "Zaległości płatnicze")
    from modules.orders.payment_overdue_service import get_overdue_orders_summary
    overdue_payments_count = len(get_overdue_orders_summary())

    return render_template(
        'admin/dashboard.html',
        title='Panel Administratora',
        revenue=revenue,
        orders=orders,
        clients=clients,
        recent_orders=recent_orders,
        sales_chart=sales_chart,
        top_products=top_products,
        tasks=tasks,
        offer_pages=offer_pages,
        pending_payment_confirmations=pending_payment_confirmations,
        sr_to_quote=shipping_alerts['to_quote'],
        sr_to_pay=shipping_alerts['to_pay'],
        sr_to_pack=shipping_alerts['to_pack'],
        overdue_payments_count=overdue_payments_count
    )
```

W `templates/admin/dashboard.html`, zmień warunek wiersza alertów (linia 17) i dodaj trzeci kafelek:

```html
    {% if pending_payment_confirmations > 0 or (sr_to_quote + sr_to_pay + sr_to_pack) > 0 or overdue_payments_count > 0 %}
    <div class="dashboard-alerts-row">
        <!-- Zaległości płatnicze -->
        {% if overdue_payments_count > 0 %}
        <div class="pc-dashboard-widget">
            <div class="pc-dashboard-widget-left">
                <div class="pc-dashboard-widget-icon">&#9200;</div>
                <div class="pc-dashboard-widget-text">
                    <h3>{{ overdue_payments_count }} {{ 'zamówienie zalega' if overdue_payments_count == 1 else 'zamówień zalega' }} z płatnością</h3>
                    <p>Termin płatności minął, a kwota nie wpłynęła</p>
                </div>
            </div>
            <a href="{{ url_for('admin.overdue_payments_list') }}" class="pc-dashboard-widget-link">
                Sprawdź &rarr;
            </a>
        </div>
        {% endif %}

        <!-- Oczekujące potwierdzenia płatności -->
        {% if pending_payment_confirmations > 0 %}
```

(reszta bloku `pending_payment_confirmations` i `wms-dashboard-widget` bez zmian, zostają pod spodem w tym samym `dashboard-alerts-row`).

Odwołanie do `url_for('admin.overdue_payments_list')` zadziała dopiero po Task 4 (routa jeszcze nie istnieje) — to celowe, obie zmiany trafią razem przy code review, ale test z Task 3 sam w sobie nie odpala tego linku, więc może przejść przed Task 4. Jeśli wolisz uniknąć chwilowo martwego endpointu, wykonaj Task 4 od razu po tym kroku przed commitem.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_overdue_widget.py -v`
Expected: PASS (2 passed) — **uwaga:** przejdzie dopiero gdy `admin.overdue_payments_list` istnieje (Task 4) lub w Jinja `url_for` rzuci `BuildError` i request zwróci 500. Wykonaj Task 4 razem z tym zadaniem przed uruchomieniem testu.

- [ ] **Step 5: Commit**

```bash
git add modules/admin/routes.py templates/admin/dashboard.html tests/test_dashboard_overdue_widget.py
git commit -m "feat(zaleglosci): kafelek zaleglosci platniczych na dashboardzie admina"
```

---

### Task 4: Strona `/admin/payments/overdue` z listą zaległości

**Files:**
- Modify: `modules/admin/routes.py` (nowa routa, obok `dashboard()`)
- Create: `templates/admin/payments/overdue.html`
- Test: `tests/test_overdue_payments_route.py`

**Interfaces:**
- Consumes: `get_overdue_orders_summary()` (Task 2).
- Produces: routa `admin.overdue_payments_list` pod `/admin/payments/overdue` (blueprint `admin_bp` ma pusty `url_prefix`, więc pełna ścieżka to dokładnie `/admin/payments/overdue` zgodnie z `@admin_bp.route('/payments/overdue')` — sprawdź istniejące trasy w tym pliku, wszystkie zaczynają się od `/`, np. `/dashboard`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overdue_payments_route.py
from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def test_overdue_payments_page_lists_order(app, db, make_user, make_order, client, login):
    admin = make_user(role='admin')
    login(admin)

    now = get_local_now()
    customer = make_user(email='klient@example.com')
    order = make_order(customer, total_amount=Decimal('150.00'))
    order.get_product_deadline = lambda: now - timedelta(days=4)

    resp = client.get('/admin/payments/overdue')

    assert resp.status_code == 200
    assert order.order_number.encode() in resp.data


def test_overdue_payments_page_empty_state(app, db, make_user, client, login):
    admin = make_user(role='admin')
    login(admin)

    resp = client.get('/admin/payments/overdue')

    assert resp.status_code == 200


def test_overdue_payments_page_requires_login(app, db, client):
    resp = client.get('/admin/payments/overdue')
    assert resp.status_code in (302, 401)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_overdue_payments_route.py -v`
Expected: FAIL with 404 (routa nie istnieje)

- [ ] **Step 3: Write minimal implementation**

W `modules/admin/routes.py`, dodaj routę zaraz po `dashboard()` (przed `@admin_bp.route('/dashboard/sales-data')`):

```python
@admin_bp.route('/payments/overdue')
@login_required
@role_required('admin', 'mod')
def overdue_payments_list():
    """Lista zamówień z przekroczonym terminem płatności na dowolnym etapie (E1-E4)."""
    from modules.orders.payment_overdue_service import get_overdue_orders_summary
    overdue = get_overdue_orders_summary()
    return render_template(
        'admin/payments/overdue.html',
        title='Zaległości płatnicze',
        overdue=overdue
    )
```

Nowy szablon:

```html
{# templates/admin/payments/overdue.html #}
{% extends "admin/base_admin.html" %}

{% block title %}Zaległości płatnicze - ThunderOrders{% endblock %}

{% block content %}
<div class="admin-page">
    <div class="page-header">
        <div class="page-header-left">
            <h1>Zaległości płatnicze</h1>
            <p>Zamówienia z przekroczonym terminem płatności na dowolnym etapie</p>
        </div>
    </div>

    {% if not overdue %}
    <div class="empty-state">
        <p>Brak zaległości — wszystkie terminy dotrzymane. 🎉</p>
    </div>
    {% else %}
    <div class="table-responsive">
        <table class="data-table overdue-payments-table">
            <thead>
                <tr>
                    <th>Zamówienie</th>
                    <th>Klient</th>
                    <th>Produkt</th>
                    <th>Etap</th>
                    <th>Kwota</th>
                    <th>Dni po terminie</th>
                </tr>
            </thead>
            <tbody>
                {% for row in overdue %}
                <tr>
                    <td><a href="{{ url_for('orders.admin_order_detail', order_id=row.order.id) }}">{{ row.order.order_number }}</a></td>
                    <td>{{ row.order.customer_name }}</td>
                    <td>{{ row.order.items[0].product_name if row.order.items else '-' }}</td>
                    <td>{{ row.primary_stage.stage_label }}</td>
                    <td>{{ '%.2f'|format(row.primary_stage.amount) }} zł</td>
                    <td>{{ row.primary_stage.days_overdue }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
</div>
{% endblock %}
```

**Uwaga:** `url_for('orders.admin_order_detail', order_id=...)` — sprawdź dokładną nazwę endpointu i parametru w `modules/orders/routes.py` przed wklejeniem (routa szczegółów zamówienia w panelu admina); jeśli nazwa się różni, popraw link zanim odpalisz test. Reszta strony (klasa `data-table`, `table-responsive`, `page-header`, `empty-state`) korzysta z klas CSS już używanych w innych stronach admina (`templates/admin/clients/list.html`, `templates/admin/feedback/list.html`) — nie wymaga nowego CSS.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_overdue_payments_route.py tests/test_dashboard_overdue_widget.py -v`
Expected: PASS (wszystkie, w tym testy z Task 3 które czekały na tę routę)

- [ ] **Step 5: Commit**

```bash
git add modules/admin/routes.py templates/admin/payments/overdue.html tests/test_overdue_payments_route.py
git commit -m "feat(zaleglosci): strona /admin/payments/overdue z lista zaleglosci"
```

---

### Task 5: `PaymentReminderLog.stage` — migracja i model

Bez tej kolumny jedna reguła obejmująca 4 etapy zablokuje się sama: log dedupu jest dziś unikalny po `(order_id, config_id)`, więc pierwsze wysłane przypomnienie (np. za etap produktu) zapisze się jako "już wysłano dla tego configu" i zablokuje wysyłkę przypomnienia o zupełnie innym etapie (np. cle) tego samego zamówienia pod tą samą regułą.

**Files:**
- Modify: `modules/offers/reminder_models.py:25-42` (klasa `PaymentReminderLog`)
- Create: `migrations/versions/<nowy_revision>_payment_reminder_log_stage.py`
- Test: `tests/test_payment_reminder_log_stage.py`

**Interfaces:**
- Produces: `PaymentReminderLog.stage: str | None` (nullable — istniejące wiersze historyczne nie mają wartości), unikalność `(order_id, config_id, stage)` zamiast `(order_id, config_id)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payment_reminder_log_stage.py
def test_same_order_and_config_different_stage_both_allowed(db, make_user, make_order):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    order = make_order(make_user())
    config = PaymentReminderConfig(reminder_type='before_deadline', hours=24, payment_stage='product')
    db.session.add(config)
    db.session.commit()

    db.session.add(PaymentReminderLog(order_id=order.id, config_id=config.id, stage='product'))
    db.session.add(PaymentReminderLog(order_id=order.id, config_id=config.id, stage='customs_vat'))
    db.session.commit()

    logs = PaymentReminderLog.query.filter_by(order_id=order.id, config_id=config.id).all()
    assert {l.stage for l in logs} == {'product', 'customs_vat'}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_payment_reminder_log_stage.py -v`
Expected: FAIL with `TypeError: 'stage' is an invalid keyword argument for PaymentReminderLog`

- [ ] **Step 3: Write minimal implementation**

W `modules/offers/reminder_models.py`, zmień klasę `PaymentReminderLog`:

```python
class PaymentReminderLog(db.Model):
    """Log wysłanych przypomnień — zapobiega duplikacji (per zamówienie, regułę i etap)."""
    __tablename__ = 'payment_reminder_logs'
    __table_args__ = (
        db.UniqueConstraint('order_id', 'config_id', 'stage', name='uq_reminder_log_order_config_stage'),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    config_id = db.Column(db.Integer, db.ForeignKey('payment_reminder_configs.id'), nullable=True)
    stage = db.Column(db.String(30), nullable=True)  # 'product'|'shipping_kr'|'customs_vat'|'domestic_shipping'; NULL dla wpisów sprzed migracji
    reminder_type = db.Column(db.String(30), nullable=True)  # 'deadline_exceeded' gdy config_id=NULL
    sent_at = db.Column(db.DateTime, default=get_local_now, nullable=False)

    config = db.relationship('PaymentReminderConfig', back_populates='logs')
    order = db.relationship('Order', backref=db.backref('reminder_logs', lazy='dynamic'))

    def __repr__(self):
        return f'<PaymentReminderLog order={self.order_id} config={self.config_id} stage={self.stage}>'
```

Nowa migracja (sprawdź aktualny head przed wygenerowaniem revision id — na dzień pisania planu head to `90fb5ad1c7b6`, `migrations/versions/90fb5ad1c7b6_clo_vat_null_vs_zero.py`; jeśli w międzyczasie doszły nowe migracje, zmień `down_revision` na faktyczny head z `flask db heads`):

```python
# migrations/versions/<wygenerowany_hash>_payment_reminder_log_stage.py
"""Dodaje kolumnę stage do payment_reminder_logs i poszerza unikalność o etap

Revision ID: <wygenerowany_hash>
Revises: 90fb5ad1c7b6
Create Date: 2026-07-30 12:00:00.000000

Bez tej kolumny jedna wspólna reguła przypomnień obejmująca wszystkie 4 etapy
płatności blokowałaby się sama — dedup po (order_id, config_id) uznawałby
przypomnienie o etapie produktu za "już wysłane dla tego zamówienia i reguły",
co blokowałoby wysyłkę przypomnienia o zupełnie innym etapie (np. cle) tego
samego zamówienia pod tą samą regułą.

Istniejące wiersze (sprzed rozszerzenia na wszystkie etapy) zostają z NULL —
dotyczyły wyłącznie etapu produktu, ale nie zapisywały tego jawnie.
"""
from alembic import op
import sqlalchemy as sa

revision = '<wygenerowany_hash>'
down_revision = '90fb5ad1c7b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=30), nullable=True))
        batch_op.drop_constraint('uq_reminder_log_order_config', type_='unique')
        batch_op.create_unique_constraint(
            'uq_reminder_log_order_config_stage', ['order_id', 'config_id', 'stage']
        )


def downgrade():
    with op.batch_alter_table('payment_reminder_logs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_reminder_log_order_config_stage', type_='unique')
        batch_op.create_unique_constraint(
            'uq_reminder_log_order_config', ['order_id', 'config_id']
        )
        batch_op.drop_column('stage')
```

Wygeneruj właściwy revision id poleceniem `flask db revision -m "payment reminder log stage"` (lokalnie, z aktywnym env), zamiast ręcznie wymyślać hash — wklej wygenerowany plik i uzupełnij `upgrade()`/`downgrade()` jak wyżej.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_payment_reminder_log_stage.py -v`
Expected: PASS

Testy `pytest` używają `_db.create_all()` (patrz `tests/conftest.py:11`), czyli tworzą schemat bezpośrednio z modeli — **nie** przechodzą przez Alembic. Test przejdzie od razu po zmianie modelu w Kroku 3, niezależnie od migracji. Migrację uruchom osobno lokalnie: `flask db upgrade` i sprawdź `flask db current` pokazuje nowy revision.

- [ ] **Step 5: Commit**

```bash
git add modules/offers/reminder_models.py migrations/versions/
git commit -m "feat(zaleglosci): dodaj stage do PaymentReminderLog, dedup per etap"
```

---

### Task 6: `EmailManager.build_payment_reminder_message()` obsługuje dowolny etap

**Files:**
- Modify: `utils/email_manager.py:1219-1265`
- Test: `tests/test_email_payment_reminder_stages.py`

**Interfaces:**
- Consumes: `STAGE_DEFINITIONS` (Task 2, `modules/orders/payment_overdue_service.py`).
- Produces: `EmailManager.build_payment_reminder_message(order, stage='product', payment_deadline=None, reminder_context='before_deadline') -> Message | None` — nowy parametr `stage` (domyślnie `'product'` dla zgodności wstecznej wywołań, które go nie podadzą).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_email_payment_reminder_stages.py
from decimal import Decimal


def test_build_reminder_message_for_customs_vat_stage(app, db, make_user, make_order):
    from utils.email_manager import EmailManager

    order = make_order(
        make_user(email='klient@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )

    msg = EmailManager.build_payment_reminder_message(order, stage='customs_vat')

    assert msg is not None
    assert 'klient@example.com' in msg.recipients


def test_build_reminder_message_none_when_stage_already_paid(app, db, make_user, make_order):
    from decimal import Decimal
    from modules.orders.models import PaymentConfirmation
    from utils.email_manager import EmailManager

    order = make_order(
        make_user(email='klient2@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )
    db.session.add(PaymentConfirmation(
        order_id=order.id, payment_stage='customs_vat', status='approved', amount=Decimal('45.00')
    ))
    db.session.commit()

    msg = EmailManager.build_payment_reminder_message(order, stage='customs_vat')

    assert msg is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_email_payment_reminder_stages.py -v`
Expected: FAIL — `build_payment_reminder_message() got an unexpected keyword argument 'stage'`

- [ ] **Step 3: Write minimal implementation**

W `utils/email_manager.py`, zamień treść metody (linie 1219-1265):

```python
    @staticmethod
    def build_payment_reminder_message(order, stage='product', payment_deadline=None, reminder_context='before_deadline'):
        """
        Buduje wiadomość przypomnienia o płatności (BEZ wysyłania) do batch sendingu,
        dla dowolnego z czterech etapów (product/shipping_kr/customs_vat/domestic_shipping).

        Returns:
            Message lub None (gdy: powiadomienia wyłączone / brak emaila /
            etap już opłacony lub w trakcie weryfikacji / błąd budowania).
        """
        if not EmailManager.is_email_enabled('notify_payment_reminder'):
            current_app.logger.info("Email notification 'notify_payment_reminder' is disabled, skipping")
            return None

        from utils.email_sender import prepare_payment_reminder_email
        from modules.orders.payment_overdue_service import STAGE_DEFINITIONS

        email = order.customer_email
        if not email:
            current_app.logger.warning(f"Cannot send payment reminder for {order.order_number}: no email")
            return None

        definition = STAGE_DEFINITIONS[stage]
        status = definition['status'](order)
        if status not in ('none', 'rejected'):
            return None

        amount = definition['amount'](order)
        unpaid_stages = [{
            'name': definition['label'],
            'amount': float(amount or 0),
            'status': status,
        }]

        confirmations_url = url_for('client.payment_confirmations', _external=True)

        return prepare_payment_reminder_email(
            user_email=email,
            user_name=order.customer_name,
            order_number=order.order_number,
            unpaid_stages=unpaid_stages,
            order_detail_url=confirmations_url,
            payment_deadline=payment_deadline,
            reminder_context=reminder_context
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_email_payment_reminder_stages.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add utils/email_manager.py tests/test_email_payment_reminder_stages.py
git commit -m "feat(zaleglosci): build_payment_reminder_message obsluguje dowolny etap E1-E4"
```

---

### Task 7: Cron `check-payment-reminders` sprawdza wszystkie 4 etapy jedną regułą

**Files:**
- Modify: `app.py:548-804` (funkcja `check_payment_reminders`)
- Test: `tests/test_check_payment_reminders_cli.py`

**Interfaces:**
- Consumes: `STAGE_DEFINITIONS` (Task 2), `EmailManager.build_payment_reminder_message(order, stage=..., ...)` (Task 6), `PaymentReminderLog.stage` (Task 5).
- Produces: bez zmian w publicznym interfejsie (to nadal `flask check-payment-reminders --dry-run`), ale teraz iteruje po wszystkich zamówieniach i wszystkich etapach zamiast tylko `product`/`shipping_kr`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_payment_reminders_cli.py
from datetime import timedelta
from decimal import Decimal

from modules.orders.models import get_local_now


def test_cron_sends_reminder_for_customs_vat_stage(app, db, make_user, make_order, monkeypatch):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient3@example.com'),
        total_amount=Decimal('100.00'),
        order_type='exclusive',
        customs_vat_sale_cost=Decimal('45.00'),
    )
    order.get_product_deadline = lambda: None
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: now - timedelta(hours=5)
    order.get_shipping_pl_deadline = lambda: None

    config = PaymentReminderConfig(reminder_type='before_deadline', hours=1, payment_stage='product', enabled=True)
    db.session.add(config)
    db.session.commit()

    monkeypatch.setattr('utils.email_sender.send_email_batch_sync', lambda messages: [True] * len(messages))

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders'])

    assert result.exit_code == 0
    log = PaymentReminderLog.query.filter_by(order_id=order.id, stage='customs_vat').first()
    assert log is not None


def test_cron_dry_run_does_not_write_log(app, db, make_user, make_order):
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog

    now = get_local_now()
    order = make_order(
        make_user(email='klient4@example.com'),
        total_amount=Decimal('100.00'),
    )
    order.get_product_deadline = lambda: now - timedelta(hours=5)
    order.get_shipping_kr_deadline = lambda: None
    order.get_customs_vat_deadline = lambda: None
    order.get_shipping_pl_deadline = lambda: None

    config = PaymentReminderConfig(reminder_type='before_deadline', hours=1, payment_stage='product', enabled=True)
    db.session.add(config)
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=['check-payment-reminders', '--dry-run'])

    assert result.exit_code == 0
    assert PaymentReminderLog.query.filter_by(order_id=order.id).count() == 0
```

**Uwaga o monkeypatchu w teście 1:** `order.get_customs_vat_deadline = lambda: ...` działa tylko w obrębie tego samego procesu/sesji — cron w `app.test_cli_runner()` odpytuje bazę na nowo (`Order.query...all()`), więc **nie zobaczy** monkeypatcha na już istniejącym obiekcie `order`, tylko świeżo załadowany wiersz z bazy. Zamiast monkeypatcha, ten test **musi** ustawić prawdziwy termin w bazie: stwórz `PolandOrder`+`PolandOrderItem` (dla `get_customs_vat_deadline`) powiązane z zamówieniem, z `customs_payment_deadline = now - timedelta(hours=5)`. Sprawdź dokładne wymagane pola tych modeli w `modules/products/models.py` przed napisaniem fixture (m.in. `PolandOrderItem.order_id`, `poland_order_id`, oraz FK-i wymagane przez `PolandOrder`) i dopiero wtedy dopisz helper `_seed_poland_order_with_deadline(db, order, deadline)` w teście.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_payment_reminders_cli.py -v`
Expected: FAIL (log ze `stage='customs_vat'` nie istnieje — dzisiejszy cron nie sprawdza etapu 3)

- [ ] **Step 3: Write minimal implementation**

Zamień treść `check_payment_reminders` (`app.py:548-804`) — zachowaj dekoratory, `--dry-run`, batch SMTP i blok „Sprawdź przekroczone deadline'y" (E1/OfferPage, `app.py:738-786`) **bez zmian**, zmień tylko pętlę budującą `pending_reminders`:

```python
    @app.cli.command('check-payment-reminders')
    @_with_request_context
    @click.option('--dry-run', is_flag=True, help='Tylko wyświetl, nie wysyłaj')
    def check_payment_reminders(dry_run):
        """Sprawdza i wysyła przypomnienia o płatnościach (uruchamiany co godzinę przez cron)."""
        from modules.orders.models import Order, get_local_now
        from modules.offers.models import OfferPage
        from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog
        from modules.orders.payment_overdue_service import STAGE_DEFINITIONS
        from modules.auth.models import Settings
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        from utils.activity_logger import log_activity
        from datetime import timedelta

        now = get_local_now()
        sent_count = 0
        pending_reminders = []

        rules = PaymentReminderConfig.query.filter_by(enabled=True).all()
        click.echo(f"Aktywnych reguł: {len(rules)}")

        active_orders = Order.query.filter(Order.status != 'anulowane').all()

        for order in active_orders:
            for stage, definition in STAGE_DEFINITIONS.items():
                if not definition['applies'](order):
                    continue

                status = definition['status'](order)
                if status not in ('none', 'rejected'):
                    continue

                deadline = definition['deadline'](order)

                for rule in rules:
                    if rule.reminder_type == 'before_deadline':
                        if deadline is None:
                            continue
                        trigger_time = deadline - timedelta(hours=rule.hours)
                    elif rule.reminder_type == 'after_order_placed':
                        if stage != 'product':
                            continue  # after_order_placed dotyczy tylko etapu produktu
                        trigger_time = order.created_at + timedelta(hours=rule.hours)
                    else:
                        continue

                    if trigger_time > now:
                        continue

                    already_sent = PaymentReminderLog.query.filter_by(
                        order_id=order.id, config_id=rule.id, stage=stage
                    ).first()
                    if already_sent:
                        continue

                    if dry_run:
                        click.echo(f"  [DRY RUN] {order.order_number} <- {definition['label']}, {rule.hours}h ({rule.reminder_type})")
                        sent_count += 1
                        continue

                    pending_reminders.append({
                        'order': order,
                        'config_id': rule.id,
                        'stage': stage,
                        'payment_deadline': deadline,
                        'reminder_context': rule.reminder_type,
                        'activity_value': f"Wysłano przypomnienie ({definition['label']}, {rule.hours}h, {rule.reminder_type})",
                        'echo': f"  Wysłano: {order.order_number} ({definition['label']}, {rule.hours}h)",
                    })

        # Wyślij zebrane przypomnienia JEDNYM połączeniem SMTP (jeden AUTH).
        if pending_reminders and not dry_run:
            from utils.email_sender import send_email_batch_sync

            messages = []
            valid = []
            for p in pending_reminders:
                msg = EmailManager.build_payment_reminder_message(
                    p['order'],
                    stage=p['stage'],
                    payment_deadline=p['payment_deadline'],
                    reminder_context=p['reminder_context']
                )
                if msg is None:
                    continue
                messages.append(msg)
                valid.append(p)

            results = send_email_batch_sync(messages)

            for p, ok in zip(valid, results):
                if not ok:
                    continue
                order = p['order']
                PushManager.notify_payment_reminder(order, payment_deadline=p['payment_deadline'])
                db.session.add(PaymentReminderLog(
                    order_id=order.id, config_id=p['config_id'], stage=p['stage']
                ))
                log_activity(
                    action='payment_reminder_sent',
                    entity_type='order',
                    entity_id=order.id,
                    new_value=p['activity_value']
                )
                sent_count += 1
                click.echo(p['echo'])

        # Sprawdź przekroczone deadline'y (bez zmian — dotyczy tylko OfferPage/E1,
        # to osobna funkcja: powiadomienie ADMINA, nie klienta)
        exceeded_pages = OfferPage.query.filter(
            OfferPage.payment_deadline.isnot(None),
            OfferPage.payment_deadline < now,
            OfferPage.is_fully_closed == True
        ).all()

        exceeded_count = 0
        exceeded_orders_by_page = {}

        for page in exceeded_pages:
            orders = Order.query.filter(
                Order.offer_page_id == page.id,
                Order.status != 'anulowane'
            ).all()
            for order in orders:
                if order.product_payment_status not in ('none', 'rejected'):
                    continue

                already_notified = PaymentReminderLog.query.filter_by(
                    order_id=order.id, config_id=None, reminder_type='deadline_exceeded'
                ).first()
                if already_notified:
                    continue

                if not dry_run:
                    db.session.add(PaymentReminderLog(
                        order_id=order.id, config_id=None, reminder_type='deadline_exceeded'
                    ))
                    log_activity(
                        action='payment_deadline_exceeded',
                        entity_type='order',
                        entity_id=order.id,
                        new_value='Przekroczono termin płatności — powiadomiono administrację'
                    )

                if page.id not in exceeded_orders_by_page:
                    exceeded_orders_by_page[page.id] = {'page': page, 'orders': []}
                exceeded_orders_by_page[page.id]['orders'].append(order)
                exceeded_count += 1

        if exceeded_orders_by_page and not dry_run:
            for page_data in exceeded_orders_by_page.values():
                EmailManager.notify_admin_deadline_exceeded(
                    page_data['page'], page_data['orders']
                )

        if exceeded_count > 0:
            click.echo(f"  Przekroczone deadline: {exceeded_count} zamówień")

        if not dry_run:
            db.session.commit()

            def set_setting(key, value):
                setting = Settings.query.filter_by(key=key).first()
                if setting:
                    setting.value = str(value)
                else:
                    setting = Settings(key=key, value=str(value), type='string')
                    db.session.add(setting)

            set_setting('payment_reminder_last_check', now.strftime('%d/%m/%Y %H:%M'))
            set_setting('payment_reminder_last_count', str(sent_count))
            db.session.commit()

        click.echo(f"\nGotowe. Wysłano przypomnień: {sent_count}, Przekroczone deadline: {exceeded_count}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_check_payment_reminders_cli.py -v`
Expected: PASS. Jeśli test 1 nadal failuje z powodu monkeypatcha (patrz uwaga w Step 1) — dokończ fixture z prawdziwym `PolandOrder`/`PolandOrderItem` zamiast monkeypatcha przed uznaniem kroku za gotowy.

Uruchom też pełną regresję cronu:

Run: `python -m pytest tests/ -k "reminder or overdue" -v`
Expected: wszystkie testy z Task 1-7 przechodzą razem.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_check_payment_reminders_cli.py
git commit -m "feat(zaleglosci): cron check-payment-reminders obejmuje wszystkie etapy E1-E4"
```

---

### Task 8: Panel admina — jedna wspólna reguła zamiast per-etapowej

Dziś UI (`modules/admin/offers.py:100-124,1861-1939`) zarządza regułami TYLKO dla `payment_stage='product'` (twardo zakodowane) — mimo że w cronie istniała gałąź dla `shipping_kr`, nie było jak dodać dla niej reguły z panelu. Efekt: w praktyce jedyne kiedykolwiek konfigurowalne reguły to i tak reguły „product". Task 7 sprawił, że KAŻDA reguła (niezależnie od `payment_stage` zapisanego w rekordzie) obowiązuje już wszystkie 4 etapy — więc ten task to tylko uczciwe zaktualizowanie UI, żeby nie sugerowało false, że reguła dotyczy tylko produktu/On-hand/Pre-order.

**Files:**
- Modify: `modules/admin/offers.py:100-124` (przekazywanie reguł do szablonu — usunięcie filtra `payment_stage='product'`)
- Modify: `templates/admin/offers/settings.html:299` (tekst „Dotyczy")
- Test: `tests/test_admin_offers_split.py` (dopisać przypadek do istniejącego pliku) lub nowy `tests/test_payment_reminder_settings_ui.py`

**Interfaces:**
- Consumes: brak nowych — czysta zmiana zapytania i tekstu.
- Produces: bez zmian sygnatur, `reminder_rules_before`/`reminder_rules_after` przestają filtrować po `payment_stage`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payment_reminder_settings_ui.py
def test_settings_page_lists_rule_regardless_of_saved_stage(app, db, make_user, client, login):
    from modules.offers.reminder_models import PaymentReminderConfig

    admin = make_user(role='admin')
    login(admin)

    rule = PaymentReminderConfig(reminder_type='before_deadline', hours=48, payment_stage='shipping_kr', enabled=True)
    db.session.add(rule)
    db.session.commit()

    resp = client.get('/admin/offers/settings')

    assert resp.status_code == 200
    assert b'48h przed terminem p' in resp.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_payment_reminder_settings_ui.py -v`
Expected: FAIL — reguła z `payment_stage='shipping_kr'` nie pojawia się dziś na liście (filtr `payment_stage='product'` ją wycina)

- [ ] **Step 3: Write minimal implementation**

W `modules/admin/offers.py`, usuń filtr `payment_stage='product'` z obu zapytań (linie 103-109):

```python
    reminder_rules_before = PaymentReminderConfig.query.filter_by(
        reminder_type='before_deadline', enabled=True
    ).order_by(PaymentReminderConfig.hours.desc()).all()

    reminder_rules_after = PaymentReminderConfig.query.filter_by(
        reminder_type='after_order_placed', enabled=True
    ).order_by(PaymentReminderConfig.hours.asc()).all()
```

W `add_payment_reminder_rule()` (`modules/admin/offers.py:1880-1884`), usuń też filtr z `existing` (samo `payment_stage='product'` przy tworzeniu rekordu, linia 1889, może zostać bez zmian — to tylko metadana historyczna, cron jej już nie czyta):

```python
    existing = PaymentReminderConfig.query.filter_by(
        reminder_type=reminder_type, hours=hours, enabled=True
    ).first()
```

W `templates/admin/offers/settings.html`, zmień linię 299:

```html
                                <span class="reminder-section-info">Dotyczy: wszystkich etapów płatności (produkt, wysyłka KR, cło/VAT, wysyłka PL)</span>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_payment_reminder_settings_ui.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/admin/offers.py templates/admin/offers/settings.html tests/test_payment_reminder_settings_ui.py
git commit -m "feat(zaleglosci): panel reguł przypomnień pokazuje wszystkie etapy, nie tylko produkt"
```

---

## Pełna regresja przed zakończeniem

```bash
python -m pytest -v
```

Expected: wszystkie testy przechodzą, w tym istniejące `tests/test_dashboard_shipping_alert.py`, `tests/test_admin_offers_split.py` i cała reszta pakietu (żadna zmiana nie usuwa istniejących pól/zachowań poza opisanymi w tym planie).

Migracja na produkcji: kolejność `kopia bazy → flask db upgrade → wdrożenie kodu`, zgodnie z ustalonym wzorcem repo (`docs/superpowers/specs/2026-07-29-clo-vat-zerowy-podatek-design.md`, sekcja „Migracja danych") — nowa kolumna `stage` jest `nullable`, więc stary kod (sprzed wdrożenia) działa na niej bez zmian, co czyni kolejność bezpieczną.
