# Cło/VAT: zerowy podatek — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozróżnić „cło nieustalone" (NULL) od „cło ustalone na zero" (0), dodać przełącznik „bez cła/VAT" w modalu admina, ukryć etap E3 u klienta przy zerze i zablokować wyzerowanie cła już opłaconego.

**Architecture:** Trzy kolumny (`poland_order_items.customs_vat_percentage`, `.customs_vat_amount`, `orders.customs_vat_sale_cost`) przestają mieć domyślne `0.00` i przyjmują `NULL`. Obecność etapu E3 jest sterowana jednym warunkiem w `order_stage_keys()` — kanonicznym źródłem prawdy używanym przez widok webowy, walidację uploadu i API mobilne, więc zmiana propaguje się wszędzie sama. Blokada zlecenia wysyłki rozdziela dotychczasowy jeden kod błędu na „nieustalone" i „nieopłacone".

**Tech Stack:** Flask 3.0, SQLAlchemy, Flask-Migrate/Alembic (MariaDB/MySQL na produkcji, SQLite w testach), Jinja2, vanilla JS, pytest 9.1.

## Global Constraints

- Gałąź robocza: `feat/clo-vat-zerowy-podatek`. **Nigdy nie pracować na `main`.**
- **Nigdy nie wykonywać `git push`** — właścicielka udziela zgody osobno przed każdym pushem.
- Interpreter i testy: `venv/bin/python` (Python 3.12.13). Testy: `venv/bin/python -m pytest`.
  Systemowy `python3` to 3.9.6 i **nie zadziała**.
- Punkt odniesienia przed zmianami: **624 testy przechodzą**. Po każdym zadaniu liczba
  przechodzących testów nie może spaść.
- Commity: Polish conventional commits (`feat(clo-vat): ...`, `fix(...)`, `test(...)`).
  Każdy commit kończy się linią `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Nowa migracja Alembic musi mieć `down_revision = '749897e046c0'` (aktualny head).
- CSS: każda nowa reguła musi mieć wariant `[data-theme="dark"]`.
- Znaczenie wartości w trzech kolumnach cła — obowiązuje w całym planie:
  `NULL` = nie ustalono · `0` = ustalono, bez podatku · `> 0` = ustalono, z podatkiem.
- Spec źródłowy: `docs/superpowers/specs/2026-07-29-clo-vat-zerowy-podatek-design.md`.

---

## Struktura plików

| Plik | Odpowiedzialność | Zadanie |
|---|---|---|
| `migrations/versions/90fb5ad1c7b6_clo_vat_null_vs_zero.py` | jednorazowa migracja danych + zdjęcie `server_default` | 1 |
| `modules/products/models.py` | 2 kolumny `PolandOrderItem` nullable | 1 |
| `modules/orders/models.py` | kolumna `Order` nullable; `has_customs_vat_stage` (jedyna definicja reguły obecności etapu E3); `is_customs_vat_settled`; `payment_icon_state` | 1, 2, 3, 9 |
| `modules/client/payment_confirmation_service.py` | `order_stage_keys()` — kanoniczny zbiór etapów, oparty na `has_customs_vat_stage` | 2 |
| `modules/client/shipping_service.py` | rozdzielenie kodu błędu gate'u Cło/VAT | 3 |
| `modules/client/shipping.py` | komunikat webowy dla nowego kodu | 3 |
| `modules/api_mobile/shipping_routes.py` | mapy kodów błędów dla nowego kodu | 3 |
| `modules/products/routes.py` | propagacja zera, blokada wyzerowania, obsługa przełącznika | 4, 5, 6 |
| `templates/admin/warehouse/stock_orders.html` | przełącznik w modalu | 7 |
| `static/js/pages/admin/stock-orders.js` | logika przełącznika, zawsze widoczna sekcja globalna | 7 |
| `static/css/pages/admin/stock-orders.css` | układ przełącznika (jasny + ciemny) | 7 |
| `templates/client/payment_confirmations/list.html` | ukrycie wiersza E3 przy zerze | 8 |
| `static/js/pages/client/payment-confirmations.js` | zgodność indeksów wierszy z szablonem | 8 |
| `tests/test_customs_vat_zero.py` | nowy plik testowy dla całej funkcjonalności | 1-6, 8, 9 |

**API mobilne nie wymaga własnego zadania** — `_serialize_payment_stages()`
(`modules/api_mobile/orders_routes.py:97`) już wywołuje `order_stage_keys(order)`,
więc zmiana z zadania 2 propaguje się tam automatycznie. Zadanie 2 dopisuje test,
który to potwierdza.

---

### Task 1: Migracja i kolumny nullable

**Files:**
- Modify: `modules/products/models.py:445-447`
- Modify: `modules/orders/models.py:181`
- Create: `migrations/versions/90fb5ad1c7b6_clo_vat_null_vs_zero.py`
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: nic (pierwsze zadanie).
- Produces: kolumny `PolandOrderItem.customs_vat_percentage`, `PolandOrderItem.customs_vat_amount`,
  `Order.customs_vat_sale_cost` — wszystkie `Numeric`, `nullable=True`, `default=None`.
  Nowo tworzony `Order` bez jawnej wartości ma `customs_vat_sale_cost is None`.

- [ ] **Step 1: Napisz test sprawdzający, że kolumny przyjmują NULL i że NULL jest domyślne**

Utwórz nowy plik `tests/test_customs_vat_zero.py`:

```python
"""Testy rozróżnienia NULL (cło nieustalone) od 0 (cło ustalone na zero)."""
from decimal import Decimal


def test_new_order_has_null_customs_by_default(db, make_user, make_order):
    # NULL = "jeszcze nie ustalono"; wcześniej domyślną wartością było 0.00
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None


def test_order_accepts_explicit_zero(db, make_user, make_order):
    # 0 = "ustalono: bez podatku" — musi dać się zapisać i odczytać jako zero, nie NULL
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    db.session.refresh(o)
    assert o.customs_vat_sale_cost is not None
    assert o.customs_vat_sale_cost == 0


def test_poland_order_item_customs_defaults_to_null(db, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem
    p = make_product()
    proxy = ProxyOrder(order_number='PRX/TEST/1',
                       order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=p.id,
                                quantity=1, unit_price=10, total_price=10)
    db.session.add(proxy_item)
    db.session.flush()
    po = PolandOrder(order_number='PL/TEST/1', proxy_order_id=proxy.id, status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=proxy_item.id,
                           product_id=p.id, quantity=1)
    db.session.add(item)
    db.session.commit()
    assert item.customs_vat_percentage is None
    assert item.customs_vat_amount is None
```

- [ ] **Step 2: Uruchom test — musi nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v`
Expected: FAIL — `test_new_order_has_null_customs_by_default` i
`test_poland_order_item_customs_defaults_to_null` zwrócą `Decimal('0.00')` zamiast `None`.

- [ ] **Step 3: Zmień domyślne wartości kolumn w modelach**

W `modules/products/models.py` zamień linie 445-447:

```python
    # Cło/VAT — NULL: nie ustalono, 0: ustalono bez podatku, > 0: ustalono z podatkiem
    customs_vat_percentage = db.Column(db.Numeric(5, 2), nullable=True, default=None)
    customs_vat_amount = db.Column(db.Numeric(10, 2), nullable=True, default=None)
```

W `modules/orders/models.py` zamień linię 181:

```python
    customs_vat_sale_cost = db.Column(db.Numeric(10, 2), nullable=True, default=None)  # CŁO/VAT od ceny sprzedaży; NULL = nie ustalono, 0 = bez podatku
```

- [ ] **Step 4: Uruchom test — musi przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Napisz migrację**

Utwórz `migrations/versions/90fb5ad1c7b6_clo_vat_null_vs_zero.py`:

```python
"""Cło/VAT: rozróżnienie NULL (nie ustalono) od 0 (ustalono bez podatku)

Revision ID: 90fb5ad1c7b6
Revises: 749897e046c0
Create Date: 2026-07-29 20:30:00.000000

Zdejmuje server_default='0.00' z poland_order_items i zamienia wszystkie
dzisiejsze zera na NULL. Jest to bezpieczne, bo przed tą zmianą kod nie
potrafił zapisać ustalonego zera — filtr `percentage > 0` w
modules/products/routes.py pomijał takie pozycje przy dystrybucji.
Weryfikacja na produkcji 2026-07-29: 6 paczek z zapisanym cłem miało
wyłącznie stawki > 0, a 7 paczek bez zapisanego cła wyłącznie zera.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '90fb5ad1c7b6'
down_revision = '749897e046c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.alter_column('customs_vat_percentage',
                              existing_type=sa.Numeric(5, 2),
                              existing_nullable=True,
                              server_default=None)
        batch_op.alter_column('customs_vat_amount',
                              existing_type=sa.Numeric(10, 2),
                              existing_nullable=True,
                              server_default=None)

    op.execute("UPDATE poland_order_items SET customs_vat_percentage = NULL, "
               "customs_vat_amount = NULL WHERE customs_vat_percentage = 0")
    op.execute("UPDATE orders SET customs_vat_sale_cost = NULL "
               "WHERE customs_vat_sale_cost = 0")


def downgrade():
    op.execute("UPDATE orders SET customs_vat_sale_cost = 0 "
               "WHERE customs_vat_sale_cost IS NULL")
    op.execute("UPDATE poland_order_items SET customs_vat_percentage = 0, "
               "customs_vat_amount = 0 WHERE customs_vat_percentage IS NULL")

    with op.batch_alter_table('poland_order_items', schema=None) as batch_op:
        batch_op.alter_column('customs_vat_percentage',
                              existing_type=sa.Numeric(5, 2),
                              existing_nullable=True,
                              server_default='0.00')
        batch_op.alter_column('customs_vat_amount',
                              existing_type=sa.Numeric(10, 2),
                              existing_nullable=True,
                              server_default='0.00')
```

- [ ] **Step 6: Sprawdź, że migracja wpina się w head bez rozgałęzienia**

Run: `venv/bin/python -m flask db heads 2>&1 | tail -3`
Expected: dokładnie jedna linia z `90fb5ad1c7b6 (head)`. Jeśli pojawią się dwie głowy,
`down_revision` wskazuje na złą rewizję — popraw i powtórz.

- [ ] **Step 7: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 627 passed (624 wyjściowe + 3 nowe). Jeśli któryś stary test padnie — przeczytaj
komunikat: najpewniej zakłada `customs_vat_sale_cost == 0` dla świeżego zamówienia.
Zaktualizuj taki test, jawnie podając `customs_vat_sale_cost=Decimal('0.00')` tam, gdzie
intencją było „bez podatku", albo zostaw `None` tam, gdzie intencją było „nieustalone".

- [ ] **Step 8: Commit**

```bash
git add modules/products/models.py modules/orders/models.py \
        migrations/versions/90fb5ad1c7b6_clo_vat_null_vs_zero.py \
        tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): kolumny cła rozróżniają NULL od zera

NULL oznacza "cło nieustalone", 0 oznacza "ustalono: bez podatku".
Migracja zdejmuje server_default i zamienia dzisiejsze zera na NULL —
przed tą zmianą kod nie potrafił zapisać ustalonego zera, więc każde
istniejące zero znaczy "jeszcze nie policzono".

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 2: Etap E3 znika przy zerowym cle

**Files:**
- Modify: `modules/client/payment_confirmation_service.py:22-29` (`order_stage_keys`)
- Modify: `modules/client/payment_confirmation_service.py:204-211` (`get_confirmation_orders`)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: kolumna `Order.customs_vat_sale_cost` z zadania 1 (może być `None`).
- Produces:
  - `Order.has_customs_vat_stage -> bool` — **jedyna** definicja reguły „czy etap E3
    dotyczy tego zamówienia". Zadania 8 (szablon, JavaScript) i 9 (ikona admina) mają
    z niej korzystać, a nie powtarzać warunek. Spec pkt 19 wymaga, by reguła istniała
    w kodzie tylko raz.
  - `order_stage_keys(order) -> set[str]` — zbiór **bez** `'customs_vat'`, gdy
    `order.has_customs_vat_stage` jest `False`.

- [ ] **Step 1: Napisz testy obecności etapu**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_stage_keys_omit_customs_when_zero(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in order_stage_keys(o)


def test_stage_keys_include_customs_when_null(db, make_user, make_order):
    # NULL = nie ustalono → etap nadal obecny (klient widzi "Zablokowane")
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert 'customs_vat' in order_stage_keys(o)


def test_stage_keys_include_customs_when_positive(db, make_user, make_order):
    from modules.client.payment_confirmation_service import order_stage_keys
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert 'customs_vat' in order_stage_keys(o)


def test_upload_rejected_for_zero_customs(db, make_user, make_order):
    # Brak etapu → brak możliwości opłacenia (wymóg właścicielki)
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    ok, err = validate_bulk_upload(u.id, [{'order_id': o.id, 'stages': ['customs_vat']}])
    assert not ok and err['code'] == 'stage_not_applicable'


def test_mobile_stages_omit_customs_when_zero(db, make_user, make_order):
    # API mobilne czyta order_stage_keys — zmiana propaguje się bez osobnego kodu
    from modules.api_mobile.orders_routes import _serialize_payment_stages
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert 'customs_vat' not in [s['stage'] for s in _serialize_payment_stages(o)]
```

- [ ] **Step 2: Uruchom testy — muszą nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k "stage_keys or upload_rejected or mobile_stages"`
Expected: FAIL — `test_stage_keys_omit_customs_when_zero`, `test_upload_rejected_for_zero_customs`
i `test_mobile_stages_omit_customs_when_zero` (etap wciąż obecny). Dwa pozostałe przechodzą już teraz.

- [ ] **Step 3a: Dodaj właściwość `has_customs_vat_stage` do `Order`**

W `modules/orders/models.py` wstaw bezpośrednio przed `is_customs_vat_settled` (przed linią 959):

```python
    @property
    def has_customs_vat_stage(self):
        """Czy etap E3 Cło/VAT dotyczy tego zamówienia.

        JEDYNA definicja tej reguły — korzystają z niej order_stage_keys(),
        szablon konta klienta i podpowiedź ikony płatności w panelu admina.
        Nie powielaj warunku w innych miejscach.

        on_hand                → False (etap nigdy nie dotyczy).
        0 (ustalono: bez cła)  → False — brak wiersza, brak możliwości opłacenia.
        NULL (nie ustalono)    → True  — wiersz widoczny, klient widzi 'Zablokowane'.
        > 0                    → True.
        """
        if self.order_type == 'on_hand':
            return False
        return self.customs_vat_sale_cost != 0
```

Uwaga na porównanie: `None != 0` daje `True` (etap obecny), `Decimal('0.00') != 0` daje
`False` (etap nieobecny). Nie zamieniaj tego na `if not self.customs_vat_sale_cost` —
to zrównałoby `None` z zerem i zepsuło całe rozróżnienie.

- [ ] **Step 3b: Oprzyj `order_stage_keys` na nowej właściwości**

W `modules/client/payment_confirmation_service.py` zamień linie 22-29:

```python
def order_stage_keys(order):
    """Zbiór etapów STRUKTURALNIE obecnych dla zamówienia (kanon: web + E5 + walidacja bulku).

    customs_vat: obecność rozstrzyga Order.has_customs_vat_stage — patrz tam po
    znaczenie NULL / 0 / > 0. Etap nieobecny oznacza: brak wiersza u klienta,
    brak możliwości opłacenia, brak powiadomień, brak wpływu na 'w pełni opłacone'.
    """
    keys = {'product', 'domestic_shipping'}
    if order.payment_stages == 4:
        keys.add('korean_shipping')
    if order.has_customs_vat_stage:
        keys.add('customs_vat')
    return keys
```

- [ ] **Step 4: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Napisz test kwalifikacji do „w pełni opłacone"**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_zero_customs_order_reaches_fully_paid(db, make_user, make_order):
    # Zamówienie bez cła nie może wisieć w "do zapłaty" czekając na wpłatę, której nie ma
    from modules.orders.models import PaymentConfirmation
    from modules.client.payment_confirmation_service import get_confirmation_orders
    u = make_user()
    o = make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
                   customs_vat_sale_cost=Decimal('0.00'), shipping_cost=Decimal('15.00'))
    for stage in ('product', 'domestic_shipping'):
        db.session.add(PaymentConfirmation(order_id=o.id, payment_stage=stage,
                                           amount=Decimal('10.00'), status='approved'))
    db.session.commit()
    buckets = get_confirmation_orders(u.id)
    assert o.id in [x.id for x in buckets['recent_paid']]
    assert o.id not in [x.id for x in buckets['payable']]
```

- [ ] **Step 6: Uruchom test — musi nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py::test_zero_customs_order_reaches_fully_paid -v`
Expected: FAIL — zamówienie ląduje w `payable`, bo `get_confirmation_orders` wciąż pyta
o `stage_3_status` na podstawie `order_type`, nie `order_stage_keys`.

- [ ] **Step 7: Oprzyj `get_confirmation_orders` na `order_stage_keys`**

W `modules/client/payment_confirmation_service.py` zamień linie 205-211:

```python
    for order in all_orders:
        keys = order_stage_keys(order)                # jedno źródło prawdy o obecności etapów
        statuses = [order.product_payment_status]
        if 'korean_shipping' in keys:
            statuses.append(order.stage_2_status or 'none')
        if 'customs_vat' in keys:
            statuses.append(order.stage_3_status)
        statuses.append(order.stage_4_status)
```

- [ ] **Step 8: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 633 passed (627 + 6 nowych). Zero błędów.

- [ ] **Step 9: Commit**

```bash
git add modules/client/payment_confirmation_service.py tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): etap E3 znika przy cle ustalonym na zero

order_stage_keys pomija customs_vat gdy kwota wynosi 0 — tak jak dziś dla
on_hand. Skutki bez dodatkowego kodu: brak wiersza u klienta, brak opcji
opłacenia, brak powiadomień, zamówienie normalnie przechodzi do opłaconych.
API mobilne dziedziczy to samo, bo czyta ten sam zbiór etapów.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 3: Nieustalone cło blokuje zlecenie wysyłki

**Files:**
- Modify: `modules/orders/models.py:959-971` (`is_customs_vat_settled`)
- Modify: `modules/client/shipping_service.py:163-166`
- Modify: `modules/client/shipping.py:254-258`
- Modify: `modules/api_mobile/shipping_routes.py:138-154`
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: `Order.customs_vat_sale_cost` (zadanie 1).
- Produces: `Order.is_customs_vat_settled -> bool` (`None` → `False`, `0` → `True`,
  `> 0` → `True` tylko przy `stage_3_status == 'approved'`) oraz nowy kod błędu
  `'customs_vat_not_set'` z kluczem szczegółów `'customs_vat_not_set_order_ids'`.

- [ ] **Step 1: Napisz testy nowej logiki rozliczenia**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_settled_false_when_customs_not_set(db, make_user, make_order):
    # Decyzja właścicielki: dopóki cło nie jest ustalone, wysyłki zlecić nie można
    u = make_user()
    o = make_order(u, order_type='exclusive')
    assert o.customs_vat_sale_cost is None
    assert o.is_customs_vat_settled is False


def test_settled_true_when_customs_zero(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('0.00'))
    assert o.is_customs_vat_settled is True


def test_settled_false_when_customs_due_unpaid(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', customs_vat_sale_cost=Decimal('50.00'))
    assert o.is_customs_vat_settled is False


def test_settled_true_for_on_hand_regardless(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='on_hand')
    assert o.is_customs_vat_settled is True
```

- [ ] **Step 2: Uruchom testy — jeden musi nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k settled`
Expected: FAIL tylko `test_settled_false_when_customs_not_set` (zwraca `True`, bo obecny
warunek `if not self.customs_vat_sale_cost` traktuje `None` jak zero). Trzy pozostałe PASS.

- [ ] **Step 3: Rozróżnij NULL od zera w `is_customs_vat_settled`**

W `modules/orders/models.py` zamień linie 959-971:

```python
    @property
    def is_customs_vat_settled(self):
        """E3 Cło/VAT rozliczone — warunek dopuszczenia zlecenia wysyłki (task 869e674fd).

        on_hand                → True (etap nie dotyczy).
        NULL (nie ustalono)    → False — blokuje do czasu decyzji admina w modalu Cło/VAT.
        0 (ustalono bez cła)   → True.
        > 0                    → True dopiero gdy stage_3_status == 'approved'
                                 ('pending'/'rejected'/'none' nie wystarczają).
        """
        if self.order_type == 'on_hand':
            return True
        if self.customs_vat_sale_cost is None:
            return False
        if self.customs_vat_sale_cost <= 0:
            return True
        return self.stage_3_status == 'approved'
```

- [ ] **Step 4: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k settled`
Expected: PASS (4 passed)

- [ ] **Step 5: Napisz test rozdzielenia kodów błędu**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_shipping_blocked_with_not_set_code(db, make_user, make_order):
    # "Nieustalone" musi mieć własny kod — komunikat "opłać" byłby mylący,
    # bo klient nie ma czego opłacić
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive')
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_not_set'
    assert o.id in err['customs_vat_not_set_order_ids'] and req is None


def test_shipping_allowed_when_customs_zero(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('0.00'))
    ok, err, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert ok and req is not None


def test_shipping_unpaid_code_unchanged_for_due_customs(db, make_user, make_order):
    # Kwota > 0 nieopłacona → nadal stary kod, bez zmiany zachowania
    from modules.client.shipping_service import validate_and_create_request
    from tests.test_shipping_service import _seed_status, _allow, _addr
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom', order_type='exclusive',
                   customs_vat_sale_cost=Decimal('50.00'))
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'customs_vat_unpaid'
```

- [ ] **Step 6: Uruchom testy — dwa muszą nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k shipping`
Expected: FAIL `test_shipping_blocked_with_not_set_code` (dostaje `customs_vat_unpaid`
zamiast `customs_vat_not_set`). PASS pozostałe dwa.

- [ ] **Step 7: Rozdziel kod błędu w serwisie wysyłki**

W `modules/client/shipping_service.py` zamień linie 163-166:

```python
    # Gate Cło/VAT (task 869e674fd) — dwa różne powody odmowy:
    # 'not_set'  = admin nie ustalił jeszcze cła (klient nie ma czego opłacić),
    # 'unpaid'   = cło naliczone, ale niezatwierdzone (E3 != approved).
    not_set = sorted(oid for oid in order_ids
                     if owned[oid].has_customs_vat_stage
                     and owned[oid].customs_vat_sale_cost is None)
    if not_set:
        return False, {'code': 'customs_vat_not_set',
                       'customs_vat_not_set_order_ids': not_set}, None
    unpaid_tax = sorted(oid for oid in order_ids if not owned[oid].is_customs_vat_settled)
    if unpaid_tax:
        return False, {'code': 'customs_vat_unpaid', 'customs_vat_unpaid_order_ids': unpaid_tax}, None
```

- [ ] **Step 8: Dodaj komunikat webowy**

W `modules/client/shipping.py` wstaw przed blokiem `if code == 'customs_vat_unpaid':` (linia 254):

```python
            if code == 'customs_vat_not_set':
                return jsonify({
                    'success': False,
                    'error': 'Nie można zlecić wysyłki — trwa ustalanie Cła/VAT dla wybranych zamówień. Spróbuj ponownie, gdy będzie gotowe.'
                }), 400
```

- [ ] **Step 9: Dodaj kod do map API mobilnego**

W `modules/api_mobile/shipping_routes.py` dopisz po jednej pozycji do każdej z trzech map
(linie 138-154), zachowując istniejące wpisy:

```python
_CREATE_REQUEST_ERR_STATUS = {
    'no_orders': 400, 'no_address': 400,
    'orders_not_found': 404, 'orders_not_available': 409, 'address_not_found': 404,
    'customs_vat_unpaid': 409,
    'customs_vat_not_set': 409,
}
_CREATE_REQUEST_ERR_MSG = {
    'no_orders': 'Wybierz przynajmniej jedno zamówienie.',
    'no_address': 'Wybierz adres dostawy.',
    'orders_not_found': 'Zamówienie nie istnieje.',
    'orders_not_available': 'Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki.',
    'address_not_found': 'Adres dostawy nie istnieje.',
    'customs_vat_unpaid': 'Najpierw opłać Cło/VAT dla wybranych zamówień.',
    'customs_vat_not_set': 'Trwa ustalanie Cła/VAT — wysyłkę zlecisz, gdy będzie gotowe.',
}
_CREATE_REQUEST_ERR_DETAILS = {
    'orders_not_found': 'missing_order_ids', 'orders_not_available': 'unavailable_order_ids',
    'customs_vat_unpaid': 'customs_vat_unpaid_order_ids',
    'customs_vat_not_set': 'customs_vat_not_set_order_ids',
}
```

- [ ] **Step 10: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -25`
Expected: 640 passed. **Uwaga na regresję:** testy w `tests/test_shipping_service.py`, które
tworzą zamówienie `order_type='exclusive'` bez `customs_vat_sale_cost`, dotąd przechodziły
gate, a teraz dostaną `customs_vat_not_set`. Jeśli taki test padnie, dopisz mu
`customs_vat_sale_cost=Decimal('0.00')` (intencja: „bez podatku") — nie osłabiaj nowego
warunku w kodzie produkcyjnym.

- [ ] **Step 11: Commit**

```bash
git add modules/orders/models.py modules/client/shipping_service.py \
        modules/client/shipping.py modules/api_mobile/shipping_routes.py \
        tests/test_customs_vat_zero.py tests/test_shipping_service.py
git commit -F - <<'EOF'
feat(clo-vat): nieustalone cło blokuje zlecenie wysyłki

is_customs_vat_settled rozróżnia NULL (nie ustalono → blokuje) od 0
(bez podatku → przepuszcza). Nowy kod błędu customs_vat_not_set z własnym
komunikatem — dotychczasowe "najpierw opłać" byłoby mylące, skoro klient
nie ma jeszcze czego opłacić.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 4: Zerowa stawka propaguje się na zamówienia klientów

**Files:**
- Modify: `modules/products/routes.py:4065-4067`
- Modify: `modules/products/routes.py:3711-3756` (`_distribute_customs_vat_to_client_orders`)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: kolumny z zadania 1.
- Produces: `_distribute_customs_vat_to_client_orders(product_customs_percentages)` zwraca
  `dict[int, dict]` w kształcie `{order_id: {'old': float, 'new': float}}` również dla stawek
  zerowych i ustawia `order.customs_vat_sale_cost = Decimal('0')`. Zadanie 5 czyta ten słownik.

- [ ] **Step 1: Napisz test wyzerowania kwoty u klienta**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def _client_order_with_product(db, make_user, make_order, make_product, price, qty=1):
    """Zamówienie klienta z jedną pozycją danego produktu — wspólne dla testów dystrybucji."""
    from modules.orders.models import OrderItem
    from modules.offers.models import OfferPage
    u = make_user()
    admin = make_user(role='admin')
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.flush()
    p = make_product()
    o = make_order(u, order_type='exclusive', offer_page_id=page.id)
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=price, total=price * qty))
    db.session.commit()
    return o, p


def test_zero_percentage_clears_client_amount(db, make_user, make_order, make_product):
    # Scenariusz właścicielki: najpierw 23%, potem poprawka na "bez podatku"
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)

    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0          # zero, nie NULL — to zapisana decyzja
    assert o.customs_vat_sale_cost is not None
```

- [ ] **Step 2: Uruchom test — musi nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py::test_zero_percentage_clears_client_amount -v`
Expected: FAIL — po drugim wywołaniu kwota nadal wynosi `230.00`, bo filtr `percentage > 0`
pomija stawkę zerową.

- [ ] **Step 3: Usuń filtry blokujące stawkę zerową**

W `modules/products/routes.py` zamień linie 3719-3720 (wczesny `return`):

```python
    if not product_customs_percentages:
        return {}
```

Następnie zamień linie 3731-3754 (pętla po zamówieniach klientów):

```python
    updated_customs = {}
    for order in client_orders:
        customs_total = Decimal('0')
        has_match = False
        for item in order.items:
            if item.product_id not in product_ids:
                continue
            percentage = product_customs_percentages[item.product_id]
            qty = item.quantity
            if item.fulfilled_quantity is not None and item.fulfilled_quantity < item.quantity:
                qty = item.fulfilled_quantity
            if item.is_set_fulfilled is False:
                qty = 0
            # Stawka 0 to zapisana decyzja "bez podatku" — zeruje kwotę zawsze.
            # Stawka dodatnia dotyka zamówienia tylko gdy pozycja jest realizowana,
            # żeby zwykła korekta stawki nie kasowała kwot na pozycjach
            # niezrealizowanych (decyzja właścicielki).
            if percentage == 0 or qty > 0:
                has_match = True
            if percentage > 0 and item.price and qty > 0:
                sale_value = Decimal(str(item.price)) * qty
                customs_total += (sale_value * percentage / Decimal('100')).quantize(Decimal('0.01'))

        if has_match:
            updated_customs[order.id] = {
                'old': float(order.customs_vat_sale_cost) if order.customs_vat_sale_cost else 0,
                'new': float(customs_total)
            }
            order.customs_vat_sale_cost = customs_total

    return updated_customs
```

- [ ] **Step 4: Przepuść stawkę zerową do dystrybucji w endpoincie**

W `modules/products/routes.py` zamień linie 4065-4067:

```python
            # Zbierz procent cła per produkt do dystrybucji na zamówienia klientów.
            # Stawka 0 też musi tu trafić — to zapisana decyzja "bez podatku",
            # która ma wyzerować kwotę na zamówieniach klientów.
            if item.product_id:
                product_customs_percentages[item.product_id] = percentage
```

- [ ] **Step 5: Uruchom test — musi przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py::test_zero_percentage_clears_client_amount -v`
Expected: PASS

- [ ] **Step 5b: Dodaj testy regresyjne dla pozycji niezrealizowanych**

Decyzja właścicielki: zwykła korekta stawki nie może kasować kwoty na pozycji,
której klient i tak nie dostaje. Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_positive_rate_does_not_clear_unfulfilled_item(db, make_user, make_order, make_product):
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')

    o.items[0].is_set_fulfilled = False          # klient jednak nie dostaje tej pozycji
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('25')})   # korekta stawki
    db.session.commit()
    assert o.customs_vat_sale_cost == Decimal('230.00')   # kwota nietknięta


def test_zero_rate_clears_even_unfulfilled_item(db, make_user, make_order, make_product):
    # Stawka 0 = "bez podatku" — zeruje niezależnie od realizacji pozycji
    from modules.products.routes import _distribute_customs_vat_to_client_orders
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    _distribute_customs_vat_to_client_orders({p.id: Decimal('23')})
    db.session.commit()
    o.items[0].is_set_fulfilled = False
    db.session.commit()

    _distribute_customs_vat_to_client_orders({p.id: Decimal('0')})
    db.session.commit()
    assert o.customs_vat_sale_cost == 0
```

- [ ] **Step 6: Sprawdź, że wyzerowanie nie wysyła powiadomień**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_zeroing_sends_no_notifications(db, make_user, make_order, make_product, monkeypatch):
    # Decyzja właścicielki: przy zejściu kwoty do zera nie wysyłamy nic
    from modules.products import routes as product_routes
    sent = []
    monkeypatch.setattr(product_routes.EmailManager, 'notify_costs_added_bulk',
                        lambda *a, **kw: sent.append('email'), raising=False)
    product_routes._notify_distributed_costs({1: {'old': 230.0, 'new': 0.0}}, 'customs_vat')
    assert sent == []
```

- [ ] **Step 7: Uruchom test — musi przejść bez zmian w kodzie**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py::test_zeroing_sends_no_notifications -v`
Expected: PASS — warunek `costs['new'] > 0` w `_notify_distributed_costs`
(`modules/products/routes.py:3778`) już to zapewnia. Jeśli test padnie na `AttributeError`
przy `EmailManager`, zamień monkeypatch na import lokalny wewnątrz funkcji zgodnie z tym,
jak `_notify_distributed_costs` importuje `EmailManager` (import jest wewnątrz funkcji,
więc podmień `utils.email_manager.EmailManager.notify_costs_added_bulk`).

- [ ] **Step 8: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 644 passed (w tym 2 testy regresyjne dla pozycji niezrealizowanych)

- [ ] **Step 9: Commit**

```bash
git add modules/products/routes.py tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
fix(clo-vat): stawka 0% zeruje kwotę na zamówieniach klientów

Filtry `percentage > 0` powodowały, że poprawka cła na zero w ogóle nie
docierała do klienta — na jego koncie zostawała stara kwota. Teraz stawka
zerowa przechodzi przez dystrybucję i wyzerowuje customs_vat_sale_cost.
Powiadomień przy zejściu do zera nadal nie wysyłamy.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 5: Blokada wyzerowania opłaconego cła

**Files:**
- Modify: `modules/products/routes.py:4104-4107` (po dystrybucji, przed commitem)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: słownik zwracany przez `_distribute_customs_vat_to_client_orders` (zadanie 4)
  oraz helper testowy `_client_order_with_product(db, make_user, make_order, make_product, price, qty)`
  zdefiniowany w zadaniu 4 w tym samym pliku testowym.
- Produces: odpowiedź HTTP 409 z `{'success': False, 'error': str}` przy próbie wyzerowania
  cła, którego etap E3 ma status `approved` lub `pending`. Zadanie 7 (frontend) polega na
  tym, że pole `error` jest gotowym komunikatem do wyświetlenia. Dodatkowo helper testowy
  `_poland_setup(db, order, product, percentage) -> (PolandOrder, PolandOrderItem)`,
  używany ponownie w zadaniu 6.

- [ ] **Step 1: Napisz testy blokady**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def _poland_setup(db, order, product, percentage):
    """Paczka do Polski z jedną pozycją — minimalne dane dla endpointu cła."""
    from modules.products.models import (PolandOrder, PolandOrderItem,
                                          ProxyOrder, ProxyOrderItem)
    proxy = ProxyOrder(order_number=f'PRX/T/{order.id}',
                       order_type='proxy', status='zamowiono')
    db.session.add(proxy)
    db.session.flush()
    pi = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product.id,
                        quantity=1, unit_price=10, total_price=10)
    db.session.add(pi)
    db.session.flush()
    po = PolandOrder(order_number=f'PL/T/{order.id}', proxy_order_id=proxy.id,
                     status='zamowione')
    db.session.add(po)
    db.session.flush()
    item = PolandOrderItem(poland_order_id=po.id, proxy_order_item_id=pi.id,
                           product_id=product.id, quantity=1,
                           customs_vat_percentage=percentage)
    db.session.add(item)
    db.session.commit()
    return po, item


DEADLINE = '2026-12-31T23:59'   # termin w przyszłości — endpoint go dziś wymaga


def _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                              login, stage3_status):
    """Wspólny scenariusz: cło 230 zł opłacone/oczekujące, próba zejścia do zera."""
    from modules.orders.models import PaymentConfirmation
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    o.customs_vat_sale_cost = Decimal('230.00')
    db.session.add(PaymentConfirmation(order_id=o.id, payment_stage='customs_vat',
                                       amount=Decimal('230.00'), status=stage3_status))
    _, item = _poland_setup(db, o, p, Decimal('23'))
    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'customs_payment_deadline': DEADLINE})
    return o, r


def test_zeroing_blocked_when_stage3_approved(client, db, make_user, make_order,
                                              make_product, login):
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'approved')
    assert r.status_code == 409
    assert r.get_json()['success'] is False
    assert o.order_number in r.get_json()['error']


def test_zeroing_blocked_when_stage3_pending(client, db, make_user, make_order,
                                             make_product, login):
    # Wgrane potwierdzenie = przelew najpewniej już wyszedł
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'pending')
    assert r.status_code == 409


def test_zeroing_allowed_when_stage3_untouched(client, db, make_user, make_order,
                                               make_product, login):
    # Brak potwierdzenia → wyzerowanie przechodzi normalnie
    o, r = _blocked_zeroing_response(client, db, make_user, make_order, make_product,
                                     login, 'rejected')
    assert r.status_code == 200 and r.get_json()['success'] is True
```

Testy używają zwykłej stawki `0` wraz z terminem płatności, więc **nie zależą od pola
`no_customs`** dodawanego dopiero w zadaniu 6 — dzięki temu zadanie 5 domyka się samo.

- [ ] **Step 2: Uruchom testy — dwa muszą nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k zeroing`
Expected: FAIL `test_zeroing_blocked_when_stage3_approved` i
`test_zeroing_blocked_when_stage3_pending` (endpoint zwraca 200 i zeruje kwotę mimo
opłaconego etapu). PASS `test_zeroing_allowed_when_stage3_untouched`.

- [ ] **Step 3: Dodaj sprawdzenie przed commitem**

W `modules/products/routes.py` zamień linie 4104-4107:

```python
        # Auto-fill CŁO/VAT od ceny SPRZEDAŻY na zamówieniach klientów
        distributed_customs = _distribute_customs_vat_to_client_orders(product_customs_percentages) or {}

        # Blokada: nie wolno wyzerować cła, które klient już opłacił albo zgłosił
        # do weryfikacji — powstałaby nadpłata do ręcznego zwrotu.
        from modules.orders.models import Order as ClientOrder
        blocked = []
        for oid, costs in distributed_customs.items():
            if costs['old'] > 0 and costs['new'] == 0:
                client_order = db.session.get(ClientOrder, oid)
                if client_order and client_order.stage_3_status in ('approved', 'pending'):
                    blocked.append(client_order.order_number)
        if blocked:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': ('Nie można wyzerować Cła/VAT — zamówienia '
                          + ', '.join(sorted(blocked))
                          + ' mają już opłacony ten etap.')
            }), 409

        db.session.commit()
```

- [ ] **Step 4: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k zeroing`
Expected: PASS (3 passed)

- [ ] **Step 5: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 647 passed

- [ ] **Step 6: Commit**

```bash
git add modules/products/routes.py tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): blokada wyzerowania cła już opłaconego

Próba zejścia z kwoty dodatniej do zera dla zamówienia, którego etap E3 jest
approved albo pending, kończy się odmową 409 z listą numerów zamówień.
Chroni przed nadpłatą, o której wiedzielibyśmy dopiero przy rozliczeniach.
Odrzucenie jest całościowe — nic nie zapisuje się częściowo.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 6: Backend przełącznika „bez cła/VAT"

**Files:**
- Modify: `modules/products/routes.py:4026-4046` (odczyt parametrów, warunkowy termin)
- Modify: `modules/products/routes.py:4048-4062` (stawka wymuszona na zero)
- Modify: `modules/products/routes.py:4093-4095` (czyszczenie terminu)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: helpery testowe `_client_order_with_product` (zadanie 4) i `_poland_setup`
  (zadanie 5) — oba już w `tests/test_customs_vat_zero.py`.
- Produces: endpoint `PUT /admin/products/api/update-poland-customs-vat` przyjmuje pole
  `no_customs: bool`. Gdy `true`: pole `customs_payment_deadline` jest opcjonalne, wszystkie
  stawki zapisywane jako `Decimal('0')`, a `PolandOrder.customs_payment_deadline` czyszczony
  do `None`. Zadanie 7 (frontend) wysyła dokładnie to pole.

- [ ] **Step 1: Napisz testy trybu „bez cła"**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_no_customs_saves_zero_not_null(client, db, make_user, make_order,
                                        make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 0}],
                         'no_customs': True})
    assert r.status_code == 200 and r.get_json()['success'] is True
    db.session.refresh(item)
    assert item.customs_vat_percentage == 0        # zapisana decyzja, nie brak decyzji
    assert item.customs_vat_percentage is not None
    assert item.customs_vat_amount == 0


def test_no_customs_clears_payment_deadline(client, db, make_user, make_order,
                                            make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, Decimal('23'))
    from datetime import datetime
    po.customs_payment_deadline = datetime(2026, 12, 31, 23, 59)
    db.session.commit()

    client.put('/admin/products/api/update-poland-customs-vat',
               json={'items': [{'poland_order_item_id': item.id,
                                'customs_vat_percentage': 0}],
                     'no_customs': True})
    db.session.refresh(po)
    assert po.customs_payment_deadline is None     # nie ma płatności → nie ma terminu


def test_deadline_still_required_with_customs(client, db, make_user, make_order,
                                              make_product, login):
    admin = make_user(role='admin'); login(admin)
    o, p = _client_order_with_product(db, make_user, make_order, make_product,
                                      price=Decimal('100.00'), qty=10)
    po, item = _poland_setup(db, o, p, None)

    r = client.put('/admin/products/api/update-poland-customs-vat',
                   json={'items': [{'poland_order_item_id': item.id,
                                    'customs_vat_percentage': 23}]})
    assert r.status_code == 400
    assert 'Termin' in r.get_json()['error']
```

- [ ] **Step 2: Uruchom testy — muszą nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k "no_customs or deadline_still"`
Expected: FAIL dwa pierwsze (endpoint odrzuca brak terminu kodem 400). Trzeci PASS.

- [ ] **Step 3: Obsłuż parametr `no_customs` przy walidacji terminu**

W `modules/products/routes.py` zamień linie 4027-4042:

```python
        data = request.get_json()
        items_data = data.get('items', [])
        no_customs = bool(data.get('no_customs'))

        if not items_data:
            return jsonify({'success': False, 'error': 'Brak danych do zapisania'}), 400

        # Termin płatności wymagany tylko wtedy, gdy cło faktycznie będzie do zapłaty.
        # Przy 'bez cła/VAT' nie ma płatności, więc nie ma też terminu.
        from datetime import datetime
        customs_deadline = None
        if not no_customs:
            customs_deadline_str = data.get('customs_payment_deadline')
            if not customs_deadline_str:
                return jsonify({'success': False, 'error': 'Termin płatności za Cło/VAT jest wymagany.'}), 400
            try:
                customs_deadline = datetime.fromisoformat(customs_deadline_str)
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': 'Nieprawidłowy format daty terminu płatności.'}), 400
```

- [ ] **Step 4: Wymuś zerową stawkę w trybie „bez cła"**

W `modules/products/routes.py` zamień linię 4050:

```python
            percentage = (Decimal('0') if no_customs
                          else Decimal(str(item_data.get('customs_vat_percentage', 0))))
```

- [ ] **Step 5: Wyczyść termin płatności paczki w trybie „bez cła"**

W `modules/products/routes.py` zamień linie 4093-4095:

```python
            # Termin płatności za Cło/VAT: ustawiany przy naliczeniu, czyszczony przy 'bez cła'
            poland_order.customs_payment_deadline = None if no_customs else customs_deadline
```

- [ ] **Step 6: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v`
Expected: PASS (wszystkie, łącznie z dwoma z zadania 5)

- [ ] **Step 7: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 650 passed

- [ ] **Step 8: Commit**

```bash
git add modules/products/routes.py tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): endpoint przyjmuje tryb "bez cła/VAT"

Pole no_customs wymusza stawkę 0 na wszystkich pozycjach, zwalnia z wymogu
terminu płatności i czyści customs_payment_deadline paczki. Przy zwykłym
naliczaniu termin pozostaje obowiązkowy jak dotąd.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 7: Przełącznik w modalu admina

**Files:**
- Modify: `templates/admin/warehouse/stock_orders.html:771-789`
- Modify: `static/js/pages/admin/stock-orders.js:818-953` (widoczność sekcji)
- Modify: `static/js/pages/admin/stock-orders.js:1076-1181` (logika przełącznika, zapis)
- Modify: `static/css/pages/admin/stock-orders.css` (dopisz na końcu bloku Customs/VAT)

**Interfaces:**
- Consumes: endpoint z zadania 6 (pole `no_customs`).
- Produces: funkcja globalna `toggleNoCustoms()` wywoływana z `onchange` przełącznika;
  `saveCustomsVat()` wysyła `no_customs: bool` i pomija `customs_payment_deadline`, gdy
  przełącznik stoi na „bez cła".

**Uwaga o komponencie:** używamy istniejącego wzorca `.toggle-switch` > `.toggle-input` +
`.toggle-label` z `static/css/pages/admin/warehouse-settings.css:290-337`, który jest już
wczytywany na tej stronie (`stock_orders.html:7`) i ma komplet stylów wraz z trybem ciemnym.
**Nie używać** `.toggle-slider` z `modals.css` — brakuje mu reguły `::before`, więc bez
dodatkowego arkusza renderuje się jako samo tło bez gałki.

- [ ] **Step 1: Dodaj przełącznik do modala**

W `templates/admin/warehouse/stock_orders.html` zamień linie 772-781:

```html
                <div id="customsVatGlobalSection" class="customs-vat-global-section">
                    <div class="customs-vat-global-row">
                        <div id="customsVatGlobalGroup" class="customs-vat-global-percent">
                            <label for="customsVatGlobalPercent">Zastosuj % do wszystkich produktów:</label>
                            <div class="customs-vat-global-input-group">
                                <input type="number" id="customsVatGlobalPercent" class="form-control customs-vat-percent-input" min="0" max="100" step="0.01" placeholder="np. 23">
                                <span class="input-suffix">%</span>
                                <button type="button" class="btn btn-sm btn-primary" onclick="applyGlobalCustomsPercentage()">Zastosuj</button>
                            </div>
                        </div>
                        <div class="customs-vat-toggle-box">
                            <div class="toggle-switch">
                                <input type="checkbox" id="customsVatHasCustomsToggle" class="toggle-input" checked onchange="toggleNoCustoms()">
                                <label for="customsVatHasCustomsToggle" class="toggle-label"></label>
                            </div>
                            <span id="customsVatToggleLabel" class="customs-vat-toggle-text">Zamówienie z cłem/VAT</span>
                        </div>
                    </div>
                </div>
```

Zwróć uwagę: usunięty został inline `style="display: none;"` — sekcja ma być widoczna zawsze
(decyzja właścicielki). Przełącznik jest domyślnie `checked`, co oznacza „z cłem/VAT".

- [ ] **Step 2: Dodaj style układu przełącznika**

Dopisz w `static/css/pages/admin/stock-orders.css` po linii 2349 (po `.customs-vat-global-input-group`):

```css
.customs-vat-global-percent {
    display: flex;
    align-items: center;
    gap: 12px;
}

.customs-vat-toggle-box {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
}

.customs-vat-toggle-text {
    font-size: 13px;
    font-weight: 600;
    color: #374151;
    white-space: nowrap;
}

@media (max-width: 768px) {
    .customs-vat-global-row {
        flex-wrap: wrap;
    }
    .customs-vat-toggle-box {
        margin-left: 0;
    }
}
```

Dopisz wariant ciemny po linii 2495 (po `[data-theme="dark"] .customs-vat-global-row label`):

```css
[data-theme="dark"] .customs-vat-toggle-text {
    color: rgba(255, 255, 255, 0.9);
}
```

- [ ] **Step 3: Napisz funkcję przełącznika**

Dopisz w `static/js/pages/admin/stock-orders.js` bezpośrednio przed `applyGlobalCustomsPercentage`
(przed linią 1076):

```js
/**
 * Przełącznik "z cłem/VAT" ↔ "bez cła/VAT".
 * Zaznaczony = zamówienie ma cło (stan domyślny).
 * Odznaczony = bez cła: pola % zablokowane i wyzerowane, termin płatności zbędny.
 */
function toggleNoCustoms() {
    const toggle = document.getElementById('customsVatHasCustomsToggle');
    const hasCustoms = toggle ? toggle.checked : true;

    const label = document.getElementById('customsVatToggleLabel');
    if (label) {
        label.textContent = hasCustoms
            ? 'Zamówienie z cłem/VAT'
            : 'Bez cła/VAT — podatek nie będzie doliczany';
    }

    const deadlineBox = document.querySelector('#customsVatModal .deadline-box');
    if (deadlineBox) deadlineBox.style.display = hasCustoms ? '' : 'none';

    const globalPercent = document.getElementById('customsVatGlobalPercent');
    if (globalPercent) {
        globalPercent.disabled = !hasCustoms;
        if (!hasCustoms) globalPercent.value = '';
    }

    document.querySelectorAll('#customsVatItemsContainer .customs-vat-percent-input').forEach(input => {
        input.disabled = !hasCustoms;
        if (!hasCustoms) {
            input.value = '';
            calculateCustomsAmount(input);
        }
    });
}
```

- [ ] **Step 4: Ustaw sekcję globalną jako zawsze widoczną**

W `static/js/pages/admin/stock-orders.js` zamień linię 828 (w `openCustomsVatModal`):

```js
    globalSection.style.display = 'flex';
    document.getElementById('customsVatGlobalGroup').style.display = '';   // paczka ma wiele pozycji
```

Zamień linię 874 (w `openCustomsVatModalForItem`):

```js
    globalSection.style.display = 'flex';
    document.getElementById('customsVatGlobalGroup').style.display = 'none';  // jedna pozycja — "do wszystkich" bez sensu
```

Zamień linię 925 (w `openBulkCustomsVatModal`):

```js
    globalSection.style.display = 'flex';
    document.getElementById('customsVatGlobalGroup').style.display = '';
```

- [ ] **Step 5: Zresetuj przełącznik przy każdym otwarciu modala**

Dopisz w `static/js/pages/admin/stock-orders.js` w trzech funkcjach otwierających —
w `openCustomsVatModal` po linii 835, w `openCustomsVatModalForItem` po linii 875
i w `openBulkCustomsVatModal` po linii 926 — ten sam fragment:

```js
    const hasCustomsToggle = document.getElementById('customsVatHasCustomsToggle');
    if (hasCustomsToggle) hasCustomsToggle.checked = true;   // domyślnie: z cłem
    toggleNoCustoms();
```

- [ ] **Step 6: Wyślij `no_customs` przy zapisie**

W `static/js/pages/admin/stock-orders.js` zamień linie 1110-1139 (blok terminu i wywołanie fetch):

```js
    // Tryb "bez cła/VAT": termin płatności nie jest potrzebny
    const hasCustomsToggle = document.getElementById('customsVatHasCustomsToggle');
    const noCustoms = hasCustomsToggle ? !hasCustomsToggle.checked : false;

    const cdDateEl = document.getElementById('customsPaymentDeadlineDate');
    const cdTimeEl = document.getElementById('customsPaymentDeadlineTime');
    let customsPaymentDeadline = null;

    if (!noCustoms) {
        const cdDate = cdDateEl.value;
        const cdTime = cdTimeEl.value;

        if (!cdDate || !cdTime) {
            if (!cdDate) cdDateEl.classList.add('input-error');
            if (!cdTime) cdTimeEl.classList.add('input-error');
            if (typeof window.showToast === 'function') window.showToast('Termin płatności za Cło/VAT jest wymagany.', 'error');
            return;
        }
        cdDateEl.classList.remove('input-error');
        cdTimeEl.classList.remove('input-error');

        const cdDatetime = new Date(`${cdDate}T${cdTime}`);
        if (cdDatetime <= new Date()) {
            cdDateEl.classList.add('input-error');
            if (typeof window.showToast === 'function') window.showToast('Termin płatności musi być w przyszłości.', 'error');
            return;
        }
        customsPaymentDeadline = `${cdDate}T${cdTime}`;
    } else {
        cdDateEl.classList.remove('input-error');
        cdTimeEl.classList.remove('input-error');
    }

    fetch('/admin/products/api/update-poland-customs-vat', {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            items: items,
            customs_payment_deadline: customsPaymentDeadline,
            no_customs: noCustoms
        })
    })
```

- [ ] **Step 6b: Zastosuj stan przełącznika do świeżo doczytanych pozycji**

Pozycje produktów powstają dopiero po odpowiedzi serwera, więc przestawienie
przełącznika w trakcie ładowania nie zablokuje pól, które jeszcze nie istnieją.
Na końcu `renderCustomsVatItems()` — po `container.innerHTML = html;` i
`updateCustomsVatTotal();` — dodaj:

```js
    // Pozycje powstają asynchronicznie (dopiero po odpowiedzi serwera), więc mogły
    // nie istnieć w momencie, gdy administratorka przełączała "z cłem" / "bez cła".
    // Wymuszamy tu ponowne zastosowanie aktualnego stanu przełącznika do świeżo
    // wyrenderowanych pól, żeby interfejs nie kłamał o swoim stanie.
    toggleNoCustoms();
```

- [ ] **Step 7: Wydłuż czas wyświetlania komunikatu o blokadzie**

W `static/js/pages/admin/stock-orders.js` zamień linię 1174 (gałąź błędu w `saveCustomsVat`):

```js
            } else {
                // Komunikat o blokadzie wylicza numery zamówień — daj czas na przeczytanie
                if (typeof window.showToast === 'function') window.showToast('Błąd: ' + data.error, 'error', 12000);
            }
```

- [ ] **Step 8: Sprawdź składnię JavaScriptu**

Run: `node --check static/js/pages/admin/stock-orders.js && echo OK`
Expected: `OK`. Jeśli `node` nie jest dostępny, pomiń ten krok — weryfikacja nastąpi w kroku 9.

- [ ] **Step 9: Sprawdź działanie w przeglądarce**

Uruchom aplikację i przejdź do listy zamówień do Polski. Zweryfikuj kolejno:

1. Kliknij edycję cła **pojedynczej paczki** → niebieski pasek z przełącznikiem jest widoczny,
   pole „Zastosuj % do wszystkich" też (paczka ma wiele pozycji).
2. Kliknij edycję **pojedynczej pozycji** → pasek z przełącznikiem widoczny,
   pole „Zastosuj % do wszystkich" ukryte.
3. Zaznacz kilka paczek → edycja **zbiorcza** → oba elementy widoczne.
4. Przestaw przełącznik na „bez cła" → pola % wyszarzone i puste, kwoty `0.00 zł`,
   suma `0.00 zł`, pole terminu płatności znika.
5. Zapisz → komunikat sukcesu; po ponownym otwarciu stawki są zerowe.
6. Przełącz motyw na ciemny → przełącznik i etykieta czytelne.

Odnotuj wynik każdego punktu. Jeśli którykolwiek zawiedzie — napraw przed commitem.

- [ ] **Step 10: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 650 passed (zmiany są wyłącznie frontendowe, liczba bez zmian)

- [ ] **Step 11: Commit**

```bash
git add templates/admin/warehouse/stock_orders.html \
        static/js/pages/admin/stock-orders.js \
        static/css/pages/admin/stock-orders.css
git commit -F - <<'EOF'
feat(clo-vat): przełącznik "bez cła/VAT" w modalu admina

Sekcja globalna jest teraz widoczna zawsze — także przy edycji pojedynczej
paczki — a pole "Zastosuj % do wszystkich" tylko tam, gdzie ma sens.
Przełącznik domyślnie stoi na "z cłem"; przestawienie blokuje pola procentów,
zeruje kwoty i ukrywa termin płatności. Użyty istniejący komponent
toggle-switch z warehouse-settings.css (jasny + ciemny).

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 8: Konto klienta — ukrycie wiersza E3

**Files:**
- Modify: `templates/client/payment_confirmations/list.html:48-62` (nowy atrybut `data-*`)
- Modify: `templates/client/payment_confirmations/list.html:179` (warunek wiersza E3)
- Modify: `templates/client/payment_confirmations/list.html:323` (sekcja „w pełni opłacone")
- Modify: `static/js/pages/client/payment-confirmations.js:73-94` (`getStagesForOrder`)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: warunek obecności etapu z zadania 2.
- Produces: atrybut `data-has-customs-vat="true"|"false"` na `.pc-order-card` oraz
  `getStagesForOrder(paymentStages, hasCustomsVat)` — drugi parametr opcjonalny,
  domyślnie `true` (zachowanie zgodne z dotychczasowym dla istniejących wywołań).

**Uwaga o istniejącym błędzie:** `updateCardStageStatus()`
(`static/js/pages/client/payment-confirmations.js:1157-1163`) wylicza indeks wiersza
z `getStagesForOrder(paymentStages)`, podczas gdy szablon renderuje wiersz E3 na podstawie
`order_type != 'on_hand'`. Te dwa warunki już dziś potrafią się rozjechać (zamówienie
`on_hand` z `payment_stages` innym niż 2). Ukrycie E3 przy zerowym cle rozszerza ten problem,
dlatego krok 4 doprowadza oba źródła do zgodności.

- [ ] **Step 1: Napisz test renderowania widoku**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def _order_on_confirmations_page(db, make_user, make_order, login, **kwargs):
    """Zamówienie widoczne na stronie potwierdzeń płatności.

    get_confirmation_orders() filtruje `offer_page_id IS NOT NULL OR order_type == 'on_hand'`,
    więc samo pre_order bez strony ofertowej w ogóle nie trafia na listę.
    """
    from modules.offers.models import OfferPage
    u = make_user(profile_completed=True); login(u)
    admin = make_user(role='admin')
    page = OfferPage(name='Strona testowa', token=OfferPage.generate_token(),
                     status='active', created_by=admin.id)
    db.session.add(page)
    db.session.flush()
    make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
               offer_page_id=page.id, shipping_cost=Decimal('15.00'), **kwargs)
    db.session.commit()
    return u


def test_client_view_hides_customs_row_when_zero(client, db, make_user, make_order, login):
    _order_on_confirmations_page(db, make_user, make_order, login,
                                 customs_vat_sale_cost=Decimal('0.00'))
    html = client.get('/client/payment-confirmations').get_data(as_text=True)
    assert 'Cło/VAT' not in html
    assert 'data-has-customs-vat="false"' in html


def test_client_view_shows_customs_row_when_not_set(client, db, make_user, make_order, login):
    # NULL = nie ustalono → wiersz nadal widoczny (bez zmian wobec dziś)
    _order_on_confirmations_page(db, make_user, make_order, login)
    html = client.get('/client/payment-confirmations').get_data(as_text=True)
    assert 'Cło/VAT' in html
    assert 'data-has-customs-vat="true"' in html
```

Jeśli strona ofertowa typu `exclusive` wymaga dodatkowo zamknięcia (`is_fully_closed`),
użyj `order_type='pre_order'` jak wyżej — ten typ nie podlega temu filtrowi.

- [ ] **Step 2: Uruchom testy — muszą nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k client_view`
Expected: FAIL oba — brak atrybutu `data-has-customs-vat`, a wiersz „Cło/VAT" renderuje się
niezależnie od kwoty.

- [ ] **Step 3: Dodaj atrybut i warunki w szablonie**

Korzystaj z `Order.has_customs_vat_stage` (zadanie 2) — **nie powtarzaj warunku** o typie
zamówienia i kwocie. Ta reguła ma jedną definicję.

W `templates/client/payment_confirmations/list.html` dopisz po linii 58:

```jinja
                 data-has-customs-vat="{{ 'true' if order.has_customs_vat_stage else 'false' }}"
```

Zamień linię 179:

```jinja
                    {% if order.has_customs_vat_stage %}
```

Zamień linię 323:

```jinja
                    {% if order.has_customs_vat_stage %}
```

- [ ] **Step 4: Uzgodnij listę etapów w JavaScripcie z szablonem**

W `static/js/pages/client/payment-confirmations.js` zamień linie 67-94:

```js
    /**
     * Zwraca listę etapów dla danego zamówienia.
     * hasCustomsVat odzwierciedla warunek renderowania wiersza E3 w szablonie
     * (data-has-customs-vat): false gdy on_hand albo gdy cło ustalono na zero.
     * Musi zgadzać się z szablonem, bo updateCardStageStatus() indeksuje wiersze
     * po pozycji na tej liście.
     */
    function getStagesForOrder(paymentStages, hasCustomsVat) {
        var withCustoms = (hasCustomsVat !== false);
        var stages = [{ id: 'product', name: 'Produkty' }];
        if (paymentStages === 4) {
            stages.push({ id: 'korean_shipping', name: 'Wysyłka KR' });
        }
        if (withCustoms && paymentStages !== 2) {
            stages.push({ id: 'customs_vat', name: 'Cło i VAT' });
        }
        stages.push({ id: 'domestic_shipping', name: 'Wysyłka PL' });
        return stages;
    }
```

- [ ] **Step 5: Znajdź i uzupełnij wszystkie wywołania `getStagesForOrder`**

Run: `grep -n "getStagesForOrder" static/js/pages/client/payment-confirmations.js`

Dla każdego wywołania dopisz drugi argument odczytany z karty zamówienia. W
`updateCardStageStatus` (linia 1157) będzie to:

```js
        var stages = getStagesForOrder(paymentStages, card.dataset.hasCustomsVat !== 'false');
```

W pozostałych miejscach użyj obiektu danych zamówienia (`orderData`), dopisując wcześniej
odczyt atrybutu obok innych pól datasetu (przy linii 560):

```js
                hasCustomsVat: row ? (row.dataset.hasCustomsVat !== 'false') : true,
```

i przekazując `orderData.hasCustomsVat` jako drugi argument.

- [ ] **Step 6: Sprawdź składnię JavaScriptu**

Run: `node --check static/js/pages/client/payment-confirmations.js && echo OK`
Expected: `OK`

- [ ] **Step 7: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k client_view`
Expected: PASS (2 passed)

- [ ] **Step 8: Sprawdź stronę potwierdzeń w przeglądarce**

Otwórz `/client/payment-confirmations` jako klient posiadający:
- zamówienie z cłem `0` → **brak** wiersza „Cło/VAT", brak zaznaczalnej opcji jego opłacenia,
- zamówienie z cłem nieustalonym → wiersz „Cło/VAT — Zablokowane" jak dotąd,
- zamówienie z cłem `> 0` → wiersz „Do zapłaty" i możliwość wgrania potwierdzenia.

Wgraj potwierdzenie dla etapu innego niż cło (np. „Wysyłka PL") w zamówieniu z cłem `0`
i sprawdź, że po zatwierdzeniu status trafia we **właściwy** wiersz — to weryfikuje krok 4.

- [ ] **Step 9: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 652 passed

- [ ] **Step 10: Commit**

```bash
git add templates/client/payment_confirmations/list.html \
        static/js/pages/client/payment-confirmations.js \
        tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): wiersz Cło/VAT znika z konta klienta przy zerze

Szablon i JavaScript korzystają z tego samego warunku obecności etapu, co
serwis. Przy okazji naprawiony rozjazd indeksowania wierszy w
updateCardStageStatus — dotąd liczyło je z payment_stages, gdy szablon
renderował według order_type, więc status potrafił trafić w zły wiersz.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

### Task 9: Podpowiedź płatności w panelu admina

**Files:**
- Modify: `modules/orders/models.py:713-720` (`payment_icon_state`, gałąź E3)
- Test: `tests/test_customs_vat_zero.py`

**Interfaces:**
- Consumes: warunek obecności etapu z zadania 2.
- Produces: `Order.payment_icon_state` → `{'css_class': str, 'tooltip': str}`, w którym
  linia `E3 Cło/VAT:` nie występuje dla zamówień z cłem ustalonym na zero.

- [ ] **Step 1: Napisz test podpowiedzi**

Dopisz do `tests/test_customs_vat_zero.py`:

```python
def test_admin_tooltip_omits_customs_when_zero(db, make_user, make_order):
    # Ikona statusu na liście admina nie może czekać na wpłatę, której nie ma
    u = make_user()
    o = make_order(u, order_type='exclusive', payment_stages=3,
                   customs_vat_sale_cost=Decimal('0.00'))
    assert 'E3 Cło/VAT' not in o.payment_icon_state['tooltip']


def test_admin_tooltip_shows_customs_when_not_set(db, make_user, make_order):
    u = make_user()
    o = make_order(u, order_type='exclusive', payment_stages=3)
    assert 'E3 Cło/VAT' in o.payment_icon_state['tooltip']
```

- [ ] **Step 2: Uruchom testy — jeden musi nie przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k admin_tooltip`
Expected: FAIL `test_admin_tooltip_omits_customs_when_zero`. PASS drugi.

- [ ] **Step 3: Pomiń E3 przy zerowym cle**

W `modules/orders/models.py` zamień linię 714, korzystając z właściwości dodanej w zadaniu 2
(**nie powtarzaj warunku** — reguła ma jedną definicję):

```python
            # E3: Cło/VAT — obecność etapu rozstrzyga has_customs_vat_stage
            if self.has_customs_vat_stage:
```

- [ ] **Step 4: Uruchom testy — muszą przejść**

Run: `venv/bin/python -m pytest tests/test_customs_vat_zero.py -v -k admin_tooltip`
Expected: PASS (2 passed)

- [ ] **Step 5: Uruchom pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 654 passed

- [ ] **Step 6: Commit**

```bash
git add modules/orders/models.py tests/test_customs_vat_zero.py
git commit -F - <<'EOF'
feat(clo-vat): ikona płatności admina pomija etap E3 przy zerze

Zamówienie bez podatku nie ma etapu Cła/VAT, więc podpowiedź przy ikonie nie
może go wyliczać ani czekać na jego zatwierdzenie przy ustalaniu koloru.

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
```

---

## Weryfikacja końcowa (przed rozmową o wdrożeniu)

- [ ] **Pełny zestaw testów**

Run: `venv/bin/python -m pytest -q --tb=short 2>&1 | tail -20`
Expected: 654 passed, zero błędów.

- [ ] **Migracja w obie strony na lokalnej bazie**

```bash
venv/bin/python -m flask db upgrade
venv/bin/python -m flask db downgrade
venv/bin/python -m flask db upgrade
```
Expected: wszystkie trzy komendy kończą się bez błędu.

- [ ] **Przejście całej ścieżki w aplikacji**

1. Panel admina → paczka do Polski → modal Cło/VAT → przełącznik „bez cła" → zapis.
2. Konto klienta tego zamówienia → **brak** wiersza „Cło/VAT", brak opcji opłacenia.
3. Ten sam klient → próba zlecenia wysyłki → **przechodzi** (cło ustalone na zero).
4. Inne zamówienie, cło nieustalone → próba zlecenia wysyłki → komunikat
   „trwa ustalanie Cła/VAT", nie „najpierw opłać".
5. Zamówienie z cłem opłaconym → próba wyzerowania w modalu → odmowa z numerem zamówienia.

- [ ] **Przegląd całości zmian**

Run: `git diff main...HEAD --stat`
Sprawdź, czy nie ma przypadkowych plików (`.env`, pliki tymczasowe, katalog `uploads/`).

- [ ] **Zapytaj właścicielkę o zgodę na scalenie do `main` i push.**
      Nie wykonywać `git push` bez wyraźnej zgody — push oznacza wdrożenie na serwer.
      Po wdrożeniu: kopia bazy produkcyjnej, następnie `flask db upgrade` na serwerze.
