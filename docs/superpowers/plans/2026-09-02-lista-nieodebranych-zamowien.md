# Lista nieodebranych zamówień — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ekran w panelu admina pokazujący, którzy klienci mają w magazynie
nieodebrane zamówienia — w ujęciu klientów i produktów — z ręcznym przypomnieniem
mailem, pushem i wpisem w centrum powiadomień.

**Architecture:** Definicja „nieodebrane" wydzielona z istniejącego
`get_available_orders()` do wspólnego zapytania, żeby ekran admina i strefa klienta
korzystały z jednego warunku. Wiek zaległości liczony z nowej kolumny
`orders.status_changed_at` (stemplowanej jednym listenerem SQLAlchemy), z fallbackiem
na `activity_log` dla zamówień sprzed wdrożenia. Agregacja i wysyłka w osobnym serwisie
`modules/orders/unclaimed_service.py`; trasy w `modules/orders/routes.py`.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), Jinja2, Flask-Mail,
pywebpush, pytest.

Projekt: `docs/superpowers/specs/2026-09-02-lista-nieodebranych-zamowien-design.md`

## Global Constraints

- Testy uruchamiane przez `venv/bin/python -m pytest` (Python 3.12, pytest 9.1.1).
  Samo `python`/`pytest` to systemowe 3.9 — nie zadziała.
- Baseline przed startem: **1538 testów zebranych**. Po każdym zadaniu liczba ma rosnąć,
  nigdy maleć.
- NIE potokować pytesta przez `| tail` — kod wyjścia jest wtedy z `tail`, nie z pytesta,
  i przegrany przebieg wygląda na zielony. Czytać podsumowanie wprost.
- Każda zmiana schematu bazy = migracja Alembic. Historia migracji ma dziś **trzy
  głowy**; nowa migracja podpina się pod żywą gałąź `6b335dbff596`. Nie scalamy
  pozostałych głów — to poza zakresem tego planu.
- Nowe pliki w `docs/` wymagają `git add -f` (wpis `/docs` w `.gitignore` nie
  obejmuje już śledzonych plików).
- CSS: konwencja BEM, reguły ciemnego motywu jako `[data-theme="dark"] .selektor`
  na końcu pliku — każdy nowy styl musi mieć wariant jasny i ciemny.
- Maile masowe wyłącznie przez `send_email_batch()` (jedno połączenie SMTP —
  limit AUTH Hostingera). Nigdy pętla `send_email()`.
- Testy renderujące szablony maili wymagają `app.test_request_context()`, nie
  `app.app_context()` — globalny context processor czyta `flask.session`.
- Commity: polski conventional commits (`feat(nieodebrane): ...`).
- **Nie pushować.** Cała praca lokalnie na gałęzi `feat/lista-nieodebranych-zamowien`.

---

### Task 1: Wspólne zapytanie „nieodebrane"

Wydziela warunek z `get_available_orders()`, żeby admin i klient nie mogli się
rozjechać. Bez tego kroku każde kolejne zadanie kopiowałoby ten sam filtr.

**Files:**
- Modify: `modules/client/shipping_service.py:113-121`
- Test: `tests/test_nieodebrane_zamowienia.py` (nowy)

**Interfaces:**
- Consumes: `allowed_request_statuses()` (istnieje, `modules/client/shipping_service.py:98`)
- Produces: `unclaimed_orders_query()` → `flask_sqlalchemy.query.Query` zamówień
  gotowych do wysyłki i nieprzypisanych do żadnego zlecenia. **Zwraca Query, nie listę** —
  wołający dokłada własne `options()`/`order_by()`.

- [ ] **Step 1: Write the failing test**

Utwórz `tests/test_nieodebrane_zamowienia.py`:

```python
"""Testy listy nieodebranych zamówień (projekt 2026-09-02).

„Nieodebrane" = zamówienie w statusie pozwalającym zamówić wysyłkę, którego klient
nie wrzucił do żadnego zlecenia WYS/. Ta sama definicja, którą widzi klient u siebie —
testy pilnują, żeby oba widoki nie zaczęły pokazywać czegoś innego.
"""
import pytest


@pytest.fixture
def zamowienie_gotowe(db, make_user, make_order):
    """Zamówienie w statusie 'dostarczone_gom', bez zlecenia wysyłki."""
    def _make(user=None, **kwargs):
        u = user or make_user()
        return make_order(u, status='dostarczone_gom', **kwargs)
    return _make


def test_gotowe_bez_zlecenia_jest_nieodebrane(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query

    o = zamowienie_gotowe()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_zamowienie_w_zleceniu_znika_z_listy(app, db, make_user, zamowienie_gotowe):
    from modules.client.shipping_service import unclaimed_orders_query
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    o = zamowienie_gotowe()
    zlecenie = ShippingRequest(request_number='WYS/1', user_id=o.user_id)
    db.session.add(zlecenie)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=zlecenie.id, order_id=o.id))
    db.session.commit()

    assert unclaimed_orders_query().all() == []


def test_anulowane_nie_trafia_na_liste(app, db, make_user, make_order):
    from modules.client.shipping_service import unclaimed_orders_query

    make_order(make_user(), status='anulowane')

    assert unclaimed_orders_query().all() == []


def test_zmiana_ustawienia_statusow_przestawia_liste(app, db, make_user, make_order):
    """Lista czyta Settings, nie zaszytą stałą."""
    from modules.auth.models import Settings
    from modules.client.shipping_service import unclaimed_orders_query

    o = make_order(make_user(), status='spakowane')
    assert unclaimed_orders_query().all() == []

    db.session.add(Settings(key='shipping_request_allowed_statuses',
                            value='["spakowane"]'))
    db.session.commit()

    assert [z.id for z in unclaimed_orders_query().all()] == [o.id]


def test_parytet_ze_strefa_klienta(app, db, make_user, zamowienie_gotowe):
    """Admin i klient widzą ten sam zbiór zamówień tego klienta."""
    from modules.client.shipping_service import (
        get_available_orders, unclaimed_orders_query,
    )

    u = make_user()
    zamowienie_gotowe(user=u)
    zamowienie_gotowe(user=u)
    zamowienie_gotowe()  # inny klient — nie może wejść do porównania

    admin = {z.id for z in unclaimed_orders_query().filter_by(user_id=u.id).all()}
    klient = {z.id for z in get_available_orders(u.id)}

    assert admin == klient
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -v`
Expected: FAIL — `ImportError: cannot import name 'unclaimed_orders_query'`

- [ ] **Step 3: Write minimal implementation**

W `modules/client/shipping_service.py` zastąp `get_available_orders()` (linie 113-121):

```python
def unclaimed_orders_query():
    """Zamówienia gotowe do wysyłki, których klient nie wrzucił do żadnego zlecenia.

    Zwraca Query, nie listę — panel admina dokłada własne `options()` i sortowanie,
    a strefa klienta zawęża do jednego użytkownika. Jedno źródło warunku: gdyby admin
    miał własną kopię, zmiana `shipping_request_allowed_statuses` przestawiłaby tylko
    jeden z widoków i lista zaczęłaby kłamać.
    """
    in_req = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id).exists()
    return Order.query.filter(Order.status.in_(allowed_request_statuses()), ~in_req)


def get_available_orders(user_id):
    """Zamówienia usera w dozwolonym statusie i bez aktywnego zlecenia (parytet web l. 277-288)."""
    return unclaimed_orders_query().filter(Order.user_id == user_id).order_by(
        Order.created_at.desc()).all()
```

Usuń nieużywany już import `and_` z ciała `get_available_orders` (był lokalny, znika
razem ze starym ciałem).

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -v`
Expected: PASS (5 testów)

Run: `venv/bin/python -m pytest tests/ -k "shipping or wysylka" -q`
Expected: PASS — refaktor nie rusza zachowania strefy klienta ani API mobilnego.

- [ ] **Step 5: Commit**

```bash
git add modules/client/shipping_service.py tests/test_nieodebrane_zamowienia.py
git commit -m "refactor(wysylka): wspolne zapytanie o zamowienia bez zlecenia wysylki"
```

---

### Task 2: Kolumny `status_changed_at` i `pickup_reminder_sent_at`

Dwie kolumny w jednej migracji — obie dotyczą tego samego ekranu, osobne migracje
znaczyłyby dwa razy przestój przy wdrożeniu.

`status_changed_at` stempluje **jeden listener SQLAlchemy**, nie ręczne przypisania
w trasach. Sprawdzone: zmiana pojedyncza (`admin_update_status`,
`modules/orders/routes.py:592`) i hurtowa (`bulk_status_change`,
`modules/orders/routes.py:1263`) przypisują `order.status` przez ORM, więc listener
łapie obie i każdą przyszłą ścieżkę.

**Files:**
- Modify: `modules/orders/models.py:236` (po `updated_at` w klasie `Order`)
- Modify: `modules/orders/models.py` (koniec pliku — listener)
- Create: `migrations/versions/c9d1e2f3a4b5_nieodebrane_zamowienia.py`
- Test: `tests/test_nieodebrane_zamowienia.py`

**Interfaces:**
- Produces: `Order.status_changed_at` (DateTime, nullable),
  `Order.pickup_reminder_sent_at` (DateTime, nullable)

- [ ] **Step 1: Write the failing test**

Dopisz na końcu `tests/test_nieodebrane_zamowienia.py`:

```python
# ============================================
# Stemplowanie daty zmiany statusu
# ============================================

def test_utworzenie_zamowienia_stempluje_date(app, db, make_user, make_order):
    """Nowe zamówienie też wchodzi w status — stempel powstaje od razu."""
    o = make_order(make_user(), status='nowe')

    assert o.status_changed_at is not None


def test_zmiana_statusu_przesuwa_date(app, db, make_user, make_order):
    """Listener działa niezależnie od tego, która trasa zmienia status."""
    from datetime import timedelta

    o = make_order(make_user(), status='nowe')
    o.status_changed_at = o.status_changed_at - timedelta(days=30)
    db.session.commit()
    stary_stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at > stary_stempel


def test_edycja_innego_pola_nie_rusza_daty(app, db, make_user, make_order):
    """Notatka dopisana do zamówienia nie może „odmłodzić" zaległości."""
    o = make_order(make_user(), status='nowe')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.admin_notes = 'klient prosił o wstrzymanie'
    db.session.commit()

    assert o.status_changed_at == stempel


def test_przypisanie_tego_samego_statusu_nie_rusza_daty(app, db, make_user, make_order):
    o = make_order(make_user(), status='dostarczone_gom')
    o.status = 'dostarczone_gom'
    db.session.commit()
    stempel = o.status_changed_at

    o.status = 'dostarczone_gom'
    db.session.commit()

    assert o.status_changed_at == stempel
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k "stempl or przesuwa" -v`
Expected: FAIL — `AttributeError: 'Order' object has no attribute 'status_changed_at'`

- [ ] **Step 3: Add columns to the model**

W `modules/orders/models.py`, w klasie `Order`, tuż za `updated_at` (linia 236):

```python
    # Kiedy zamówienie weszło w obecny status. Stemplowane listenerem (koniec pliku),
    # nie w trasach — ścieżek zmiany statusu jest kilka i każda nowa musiałaby
    # pamiętać o stemplu. NULL = zamówienie sprzed wdrożenia; wiek zaległości
    # liczy się wtedy z activity_log.
    status_changed_at = db.Column(db.DateTime, nullable=True)

    # Ostatnie przypomnienie „odbierz swoje rzeczy". Kolumna, nie tabela logu —
    # interesuje nas wyłącznie „kiedy ostatnio", tak samo jak przy
    # ShippingRequest.delivery_reminder_sent_at.
    pickup_reminder_sent_at = db.Column(db.DateTime, nullable=True)
```

- [ ] **Step 4: Add the listener**

Na końcu `modules/orders/models.py`:

```python
@db.event.listens_for(Order.status, 'set')
def _stempluj_zmiane_statusu(order, nowy, stary, initiator):
    """Zapisuje moment wejścia zamówienia w nowy status.

    Listener zamiast przypisań w trasach: status zmieniają dziś co najmniej
    `admin_update_status` i `bulk_status_change`, obie przez ORM, a kolejne ścieżki
    powstaną bez wiedzy o tej kolumnie. Jedno miejsce łapie wszystkie.

    Przy tworzeniu zamówienia `stary` jest symbolem NO_VALUE, więc porównanie
    wypada fałszywie i stempel powstaje — tak ma być, nowe zamówienie też wchodzi
    w status. Ponowne przypisanie tej samej wartości stempla NIE rusza: „leży
    47 dni" ma znaczyć wiek zaległości, a nie datę ostatniego zapisu formularza.
    """
    if nowy == stary:
        return
    order.status_changed_at = get_local_now()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k "stempl or przesuwa" -v`
Expected: PASS (4 testy)

- [ ] **Step 6: Write the migration**

Utwórz `migrations/versions/c9d1e2f3a4b5_nieodebrane_zamowienia.py`:

```python
"""Kolumny pod listę nieodebranych zamówień.

`orders.status_changed_at` — moment wejścia w obecny status; źródło kolumny
„leży X dni". Nullable i BEZ backfillu: dla zamówień sprzed wdrożenia wiek liczy
się z `activity_log`, a wpisanie im tu daty migracji byłoby cichym kłamstwem
(wszystkie zaległości wyglądałyby na świeże).

`orders.pickup_reminder_sent_at` — kiedy ostatnio poszło przypomnienie o odbiorze.
Nullable, bo przed wdrożeniem żadne nie poszło.

Podpięte pod 6b335dbff596: historia migracji ma trzy głowy, z czego dwie pochodzą
z grudnia 2025. Żywa jest ta gałąź.

Revision ID: c9d1e2f3a4b5
Revises: 6b335dbff596
Create Date: 2026-09-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1e2f3a4b5'
down_revision = '6b335dbff596'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('status_changed_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('pickup_reminder_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('orders', 'pickup_reminder_sent_at')
    op.drop_column('orders', 'status_changed_at')
```

- [ ] **Step 7: Verify the migration applies**

Run: `venv/bin/python -m flask db upgrade c9d1e2f3a4b5`
Expected: `Running upgrade 6b335dbff596 -> c9d1e2f3a4b5`

Jeśli Alembic zgłosi błąd o wielu głowach, użyj wersji z jawnym celem (jak wyżej) —
nie uruchamiaj `flask db upgrade heads`, bo pociągnęłoby to dwie porzucone gałęzie
z 2025 roku. Zgłoś problem właścicielce zamiast go obchodzić.

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS — nowe kolumny są nullable, nic istniejącego nie zależy od ich wartości.

- [ ] **Step 8: Commit**

```bash
git add modules/orders/models.py migrations/versions/c9d1e2f3a4b5_nieodebrane_zamowienia.py tests/test_nieodebrane_zamowienia.py
git commit -m "feat(nieodebrane): kolumny status_changed_at i pickup_reminder_sent_at"
```

---

### Task 3: Wiek zaległości z fallbackiem na dziennik

**Files:**
- Create: `modules/orders/unclaimed_service.py`
- Test: `tests/test_nieodebrane_zamowienia.py`

**Interfaces:**
- Consumes: `Order.status_changed_at` (Task 2), `ActivityLog`
  (`modules/admin/models.py:232`, pola: `action`, `entity_type`, `entity_id`,
  `new_value` — JSON tekstowy, `created_at`)
- Produces: `wiek_zaleglosci(orders) -> dict[int, tuple[int | None, bool]]`
  — `order_id` → `(liczba_dni, czy_dokladne)`. `(None, False)` = brak obu źródeł.

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_nieodebrane_zamowienia.py`:

```python
# ============================================
# Wiek zaległości
# ============================================

def test_wiek_z_kolumny_jest_dokladny(app, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = get_local_now() - timedelta(days=47)
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (47, True)}


def test_wiek_z_dziennika_jest_przyblizony(app, db, make_user, make_order):
    """Zamówienie sprzed wdrożenia — kolumna pusta, ale dziennik pamięta."""
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=o.id,
        new_value=json.dumps({'status': 'dostarczone_gom'}),
        created_at=get_local_now() - timedelta(days=120),
    ))
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (120, False)}


def test_dziennik_o_innym_statusie_jest_ignorowany(app, db, make_user, make_order):
    """Wpis o wejściu w JAKIŚ status nie mówi nic o wieku OBECNEJ zaległości."""
    import json
    from datetime import timedelta
    from modules.admin.models import ActivityLog
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.add(ActivityLog(
        action='order_status_change', entity_type='order', entity_id=o.id,
        new_value=json.dumps({'status': 'urzad_celny'}),
        created_at=get_local_now() - timedelta(days=200),
    ))
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (None, False)}


def test_brak_obu_zrodel_daje_none(app, db, make_user, make_order):
    from modules.orders.unclaimed_service import wiek_zaleglosci

    o = make_order(make_user(), status='dostarczone_gom')
    o.status_changed_at = None
    db.session.commit()

    assert wiek_zaleglosci([o]) == {o.id: (None, False)}


def test_wiek_liczony_jednym_zapytaniem_dla_wielu(app, db, make_user, make_order):
    """Regresja na N+1: 30 zamówień to nadal jedno zapytanie do dziennika."""
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import wiek_zaleglosci

    zamowienia = []
    for i in range(30):
        o = make_order(make_user(), status='dostarczone_gom')
        o.status_changed_at = get_local_now() - timedelta(days=i + 1)
        zamowienia.append(o)
    db.session.commit()

    wynik = wiek_zaleglosci(zamowienia)

    assert len(wynik) == 30
    assert wynik[zamowienia[0].id] == (1, True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k wiek -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.orders.unclaimed_service'`

- [ ] **Step 3: Write the implementation**

Utwórz `modules/orders/unclaimed_service.py`:

```python
"""Dane ekranu „Nieodebrane" (projekt 2026-09-02).

Osobny moduł, bo `modules/orders/routes.py` ma już ponad 5000 linii — agregacja
i wysyłka przypomnień żyją tu, trasy zostają cienkie.
"""

import json

from sqlalchemy import desc

from extensions import db
from modules.admin.models import ActivityLog
from modules.orders.models import Order, get_local_now


def wiek_zaleglosci(orders):
    """Ile dni każde zamówienie leży w obecnym statusie.

    Zwraca {order_id: (dni, czy_dokladne)}. `czy_dokladne=False` znaczy, że data
    pochodzi z dziennika zmian, a nie z kolumny — interfejs pokazuje wtedy tyldę,
    żeby właścicielka wiedziała, której liczbie ufać co do dnia.
    `(None, False)` = zamówienie sprzed wdrożenia, którego zmiany statusu nikt nie
    zalogował; ekran sortuje takie na górę, bo leżą najdłużej.

    Dziennik czytany JEDNYM zapytaniem dla całej listy — po jednym na wiersz
    zrobiłoby z ekranu N+1 na tabeli, która rośnie z każdą akcją w systemie.
    """
    if not orders:
        return {}

    teraz = get_local_now()
    wynik = {}
    bez_kolumny = {}

    for o in orders:
        if o.status_changed_at is not None:
            wynik[o.id] = ((teraz - o.status_changed_at).days, True)
        else:
            bez_kolumny[o.id] = o.status

    if bez_kolumny:
        wpisy = ActivityLog.query.filter(
            ActivityLog.action == 'order_status_change',
            ActivityLog.entity_type == 'order',
            ActivityLog.entity_id.in_(bez_kolumny.keys()),
        ).order_by(desc(ActivityLog.created_at)).all()

        znalezione = set()
        for wpis in wpisy:
            if wpis.entity_id in znalezione:
                continue  # wpisy posortowane malejąco — pierwszy trafiony jest najnowszy
            try:
                status_z_wpisu = (json.loads(wpis.new_value) or {}).get('status')
            except (TypeError, ValueError):
                continue
            if status_z_wpisu != bez_kolumny[wpis.entity_id]:
                continue  # wpis o wejściu w inny status nie datuje obecnej zaległości
            znalezione.add(wpis.entity_id)
            wynik[wpis.entity_id] = ((teraz - wpis.created_at).days, False)

        for order_id in bez_kolumny:
            wynik.setdefault(order_id, (None, False))

    return wynik
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k wiek -v`
Expected: PASS (5 testów)

- [ ] **Step 5: Commit**

```bash
git add modules/orders/unclaimed_service.py tests/test_nieodebrane_zamowienia.py
git commit -m "feat(nieodebrane): wiek zaleglosci z kolumny lub dziennika zmian"
```

---

### Task 4: Agregacja danych ekranu

**Files:**
- Modify: `modules/orders/unclaimed_service.py`
- Test: `tests/test_nieodebrane_zamowienia.py`

**Interfaces:**
- Consumes: `unclaimed_orders_query()` (Task 1), `wiek_zaleglosci()` (Task 3)
- Produces: `zbierz_nieodebrane() -> dict` o kluczach:
  - `klienci`: lista dictów `{'user': User, 'zamowienia': [Order], 'dni': int|None,
    'dokladne': bool, 'ostatnie_przypomnienie': datetime|None}`, posortowana
    malejąco po `dni` (brak danych = najstarsze, na górze)
  - `produkty`: lista dictów `{'product_id': int|None, 'nazwa': str, 'sztuk': int,
    'klientow': int, 'wlasny': bool}`, posortowana malejąco po `sztuk`;
    pozycje własne (`product_id is None`) zawsze na końcu

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_nieodebrane_zamowienia.py`:

```python
# ============================================
# Agregacja ekranu
# ============================================

def _pozycja(db, order, product=None, nazwa=None, qty=1):
    from decimal import Decimal
    from modules.orders.models import OrderItem

    it = OrderItem(
        order_id=order.id,
        product_id=product.id if product else None,
        custom_name=nazwa,
        is_custom=product is None,
        quantity=qty,
        price=Decimal('100.00'),
        total=Decimal('100.00') * qty,
    )
    db.session.add(it)
    db.session.commit()
    return it


def test_klient_z_trzema_zamowieniami_to_jeden_wiersz(app, db, make_user, make_order):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    u = make_user()
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    dane = zbierz_nieodebrane()

    assert len(dane['klienci']) == 1
    assert dane['klienci'][0]['user'].id == u.id
    assert len(dane['klienci'][0]['zamowienia']) == 3


def test_klienci_sortowani_od_najstarszej_zaleglosci(app, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    swiezy = make_user(email='swiezy@example.com')
    stary = make_user(email='stary@example.com')
    o1 = make_order(swiezy, status='dostarczone_gom')
    o2 = make_order(stary, status='dostarczone_gom')
    o1.status_changed_at = get_local_now() - timedelta(days=3)
    o2.status_changed_at = get_local_now() - timedelta(days=90)
    db.session.commit()

    dane = zbierz_nieodebrane()

    assert [k['user'].id for k in dane['klienci']] == [stary.id, swiezy.id]
    assert dane['klienci'][0]['dni'] == 90


def test_produkty_sumuja_sztuki_i_licza_klientow(app, db, make_user, make_order,
                                                  make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    ls = make_product(name='Light stick ATEEZ')
    for qty in (2, 3):
        o = make_order(make_user(), status='dostarczone_gom')
        _pozycja(db, o, product=ls, qty=qty)

    dane = zbierz_nieodebrane()

    assert len(dane['produkty']) == 1
    assert dane['produkty'][0]['nazwa'] == 'Light stick ATEEZ'
    assert dane['produkty'][0]['sztuk'] == 5
    assert dane['produkty'][0]['klientow'] == 2


def test_ten_sam_klient_liczony_raz_na_produkt(app, db, make_user, make_order,
                                                make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    ls = make_product(name='Light stick ATEEZ')
    u = make_user()
    for _ in range(2):
        o = make_order(u, status='dostarczone_gom')
        _pozycja(db, o, product=ls, qty=1)

    dane = zbierz_nieodebrane()

    assert dane['produkty'][0]['sztuk'] == 2
    assert dane['produkty'][0]['klientow'] == 1


def test_pozycje_wlasne_ida_na_koniec(app, db, make_user, make_order, make_product):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    o1 = make_order(make_user(), status='dostarczone_gom')
    _pozycja(db, o1, nazwa='Zestaw niespodzianka', qty=99)
    o2 = make_order(make_user(), status='dostarczone_gom')
    _pozycja(db, o2, product=make_product(name='Album TXT'), qty=1)

    dane = zbierz_nieodebrane()

    assert [p['wlasny'] for p in dane['produkty']] == [False, True]
    assert dane['produkty'][1]['nazwa'] == 'Zestaw niespodzianka'


def test_pusta_baza_nie_wywraca_ekranu(app, db):
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    assert zbierz_nieodebrane() == {'klienci': [], 'produkty': []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k "klient or produkt or pusta" -v`
Expected: FAIL — `ImportError: cannot import name 'zbierz_nieodebrane'`

- [ ] **Step 3: Write the implementation**

Dopisz do `modules/orders/unclaimed_service.py` (import `joinedload` do nagłówka pliku):

```python
from sqlalchemy.orm import joinedload
```

```python
def zbierz_nieodebrane():
    """Dane obu zakładek ekranu „Nieodebrane" — jedno przejście po zamówieniach.

    Zwraca {'klienci': [...], 'produkty': [...]}. Obie zakładki renderują się
    z jednego żądania, więc przełączanie ich jest czysto wizualne.
    """
    zamowienia = unclaimed_orders_query().options(
        joinedload(Order.user),
        joinedload(Order.items).joinedload(OrderItem.product),
    ).all()

    if not zamowienia:
        return {'klienci': [], 'produkty': []}

    wiek = wiek_zaleglosci(zamowienia)

    # --- zakładka „Wg klientów" ---
    wg_klienta = {}
    for o in zamowienia:
        wpis = wg_klienta.setdefault(o.user_id, {
            'user': o.user, 'zamowienia': [], 'dni': None, 'dokladne': True,
            'ostatnie_przypomnienie': None,
        })
        wpis['zamowienia'].append(o)

        dni, dokladne = wiek.get(o.id, (None, False))
        # Wiersz klienta pokazuje jego NAJSTARSZĄ zaległość — to ona decyduje,
        # jak pilnie trzeba mu przypomnieć.
        if dni is not None and (wpis['dni'] is None or dni > wpis['dni']):
            wpis['dni'] = dni
        if not dokladne:
            wpis['dokladne'] = False  # jedna niepewna data brudzi cały wiersz

        if o.pickup_reminder_sent_at is not None and (
            wpis['ostatnie_przypomnienie'] is None
            or o.pickup_reminder_sent_at > wpis['ostatnie_przypomnienie']
        ):
            wpis['ostatnie_przypomnienie'] = o.pickup_reminder_sent_at

    # Klient bez policzalnego wieku trafia na górę: skoro nie ma śladu po zmianie
    # statusu, leży od dawna. `-1` sortowałoby go na dół, stąd nieskończoność.
    klienci = sorted(
        wg_klienta.values(),
        key=lambda w: float('inf') if w['dni'] is None else w['dni'],
        reverse=True,
    )

    # --- zakładka „Wg produktów" ---
    wg_produktu = {}
    for o in zamowienia:
        for it in o.items:
            wlasny = it.product_id is None
            klucz = ('custom', it.custom_name or 'Bez nazwy') if wlasny else ('id', it.product_id)
            wpis = wg_produktu.setdefault(klucz, {
                'product_id': it.product_id,
                'nazwa': (it.custom_name or 'Bez nazwy') if wlasny
                         else (it.product.name if it.product else f'Produkt #{it.product_id}'),
                'sztuk': 0,
                'klienci': set(),
                'wlasny': wlasny,
            })
            wpis['sztuk'] += it.quantity or 0
            wpis['klienci'].add(o.user_id)

    produkty = [
        {'product_id': w['product_id'], 'nazwa': w['nazwa'], 'sztuk': w['sztuk'],
         'klientow': len(w['klienci']), 'wlasny': w['wlasny']}
        for w in wg_produktu.values()
    ]
    # Pozycje własne zawsze na końcu — nie mają karty w magazynie, więc mieszanie
    # ich z katalogiem tylko zaśmieca listę.
    produkty.sort(key=lambda p: (p['wlasny'], -p['sztuk']))

    return {'klienci': klienci, 'produkty': produkty}
```

Uzupełnij import modeli na górze pliku:

```python
from modules.orders.models import Order, OrderItem, get_local_now
```

oraz import zapytania:

```python
from modules.client.shipping_service import unclaimed_orders_query
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -v`
Expected: PASS (wszystkie testy pliku)

- [ ] **Step 5: Commit**

```bash
git add modules/orders/unclaimed_service.py tests/test_nieodebrane_zamowienia.py
git commit -m "feat(nieodebrane): agregacja wg klientow i wg produktow"
```

---

### Task 5: Ekran w panelu admina

**Files:**
- Modify: `modules/orders/routes.py` (nowa trasa; dodaj obok `admin_delivery_reviews`)
- Create: `templates/admin/orders/unclaimed.html`
- Create: `static/css/pages/admin/unclaimed.css`
- Modify: `templates/components/sidebar_admin.html:41` (za pozycją „Lista zamówień")
- Test: `tests/test_nieodebrane_zamowienia.py`

**Interfaces:**
- Consumes: `zbierz_nieodebrane()` (Task 4)
- Produces: endpoint `orders.admin_unclaimed` pod `/admin/orders/nieodebrane`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_nieodebrane_zamowienia.py`:

```python
# ============================================
# Ekran admina
# ============================================

def test_ekran_wymaga_admina(app, client, db, make_user, login):
    login(make_user(role='client'))

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code in (302, 403)


def test_ekran_pokazuje_klienta_i_produkt(app, client, db, make_user, make_order,
                                           make_product, login):
    login(make_user(role='admin', email='admin@example.com'))
    o = make_order(make_user(email='zalegacz@example.com'), status='dostarczone_gom')
    _pozycja(db, o, product=make_product(name='Light stick ATEEZ'), qty=5)

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code == 200
    tresc = r.get_data(as_text=True)
    assert 'zalegacz@example.com' in tresc
    assert 'Light stick ATEEZ' in tresc


def test_ekran_bez_zaleglosci_nie_wywala_sie(app, client, db, make_user, login):
    login(make_user(role='admin', email='admin@example.com'))

    r = client.get('/admin/orders/nieodebrane')

    assert r.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -k ekran -v`
Expected: FAIL — 404 zamiast 200

- [ ] **Step 3: Add the route**

W `modules/orders/routes.py`, obok pozostałych tras admina:

```python
@orders_bp.route('/admin/orders/nieodebrane')
@login_required
@role_required('admin', 'mod')
def admin_unclaimed():
    """Kto nie odebrał swoich rzeczy — ujęcie klientów i produktów.

    Bez paginacji: lista jest krótka z definicji (tylko zaległości), a stronicowanie
    rozbiłoby zaznaczanie do przypomnień na kilka ekranów.
    """
    from modules.orders.unclaimed_service import zbierz_nieodebrane

    return render_template('admin/orders/unclaimed.html', **zbierz_nieodebrane())
```

- [ ] **Step 4: Create the template**

Utwórz `templates/admin/orders/unclaimed.html`:

```html
{% extends "admin/base_admin.html" %}

{% block title %}Nieodebrane - ThunderOrders{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/unclaimed.css') }}">
{% endblock %}

{% block content %}
<div class="unclaimed">
    <h1 class="unclaimed__title">Nieodebrane</h1>
    <p class="unclaimed__lead">
        Zamówienia gotowe do wysyłki, do których klient nie zamówił jeszcze przesyłki.
    </p>

    <div class="unclaimed__tabs" role="tablist">
        <button type="button" class="unclaimed__tab is-active" data-tab="klienci" role="tab">
            Wg klientów ({{ klienci|length }})
        </button>
        <button type="button" class="unclaimed__tab" data-tab="produkty" role="tab">
            Wg produktów ({{ produkty|length }})
        </button>
    </div>

    {# ===== Zakładka: klienci ===== #}
    <section class="unclaimed__panel is-active" data-panel="klienci">
        {% if klienci %}
        <div class="unclaimed__actions">
            <label class="unclaimed__checkbox">
                <input type="checkbox" id="unclaimedSelectAll">
                <span>Zaznacz wszystkich</span>
            </label>
            <button type="button" class="btn btn-primary" id="unclaimedRemindBtn" disabled>
                Wyślij przypomnienie (<span id="unclaimedCount">0</span>)
            </button>
        </div>

        <div class="unclaimed__table-wrap">
            <table class="unclaimed__table">
                <thead>
                    <tr>
                        <th class="unclaimed__col-check"></th>
                        <th>Klient</th>
                        <th>Zaległych</th>
                        <th>Najstarsze leży</th>
                        <th>Ostatnie przypomnienie</th>
                    </tr>
                </thead>
                <tbody>
                    {% for wpis in klienci %}
                    <tr class="unclaimed__row" data-user-id="{{ wpis.user.id }}">
                        <td class="unclaimed__col-check">
                            <input type="checkbox" class="unclaimed__pick"
                                   value="{{ wpis.user.id }}"
                                   data-ostatnie="{{ wpis.ostatnie_przypomnienie.isoformat() if wpis.ostatnie_przypomnienie else '' }}">
                        </td>
                        <td>
                            <button type="button" class="unclaimed__expand" data-target="klient-{{ wpis.user.id }}">
                                {{ wpis.user.email }}
                            </button>
                        </td>
                        <td>{{ wpis.zamowienia|length }}</td>
                        <td>
                            {% if wpis.dni is none %}
                                <span class="unclaimed__age unclaimed__age--unknown" title="Brak śladu po zmianie statusu">~ b.d.</span>
                            {% else %}
                                <span class="unclaimed__age{% if not wpis.dokladne %} unclaimed__age--approx{% endif %}"
                                      {% if not wpis.dokladne %}title="Data z dziennika zmian — wartość przybliżona"{% endif %}>
                                    {% if not wpis.dokladne %}~{% endif %}{{ wpis.dni }} dni
                                </span>
                            {% endif %}
                        </td>
                        <td>
                            {% if wpis.ostatnie_przypomnienie %}
                                {{ wpis.ostatnie_przypomnienie.strftime('%d.%m.%Y') }}
                            {% else %}
                                &mdash;
                            {% endif %}
                        </td>
                    </tr>
                    <tr class="unclaimed__details" id="klient-{{ wpis.user.id }}" hidden>
                        <td colspan="5">
                            <ul class="unclaimed__orders">
                                {% for z in wpis.zamowienia %}
                                <li>
                                    <a href="{{ url_for('orders.admin_detail', order_id=z.id) }}">{{ z.order_number }}</a>
                                    <span class="unclaimed__items">
                                        {% for it in z.items %}{{ it.product.name if it.product else it.custom_name }} &times;{{ it.quantity }}{% if not loop.last %}, {% endif %}{% endfor %}
                                    </span>
                                </li>
                                {% endfor %}
                            </ul>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p class="unclaimed__empty">Nikt nie zalega — wszystko odebrane. 🎉</p>
        {% endif %}
    </section>

    {# ===== Zakładka: produkty ===== #}
    <section class="unclaimed__panel" data-panel="produkty">
        {% if produkty %}
        <div class="unclaimed__table-wrap">
            <table class="unclaimed__table">
                <thead>
                    <tr>
                        <th>Produkt</th>
                        <th>Sztuk</th>
                        <th>Osób</th>
                    </tr>
                </thead>
                <tbody>
                    {% for p in produkty %}
                    <tr{% if p.wlasny %} class="unclaimed__row--custom"{% endif %}>
                        <td>
                            {{ p.nazwa }}
                            {% if p.wlasny %}<span class="unclaimed__badge">produkt własny</span>{% endif %}
                        </td>
                        <td>{{ p.sztuk }} szt.</td>
                        <td>{{ p.klientow }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <p class="unclaimed__empty">Żaden towar nie czeka na odbiór.</p>
        {% endif %}
    </section>
</div>

<script src="{{ url_for('static', filename='js/pages/admin/unclaimed.js') }}" defer></script>
{% endblock %}
```

Uwaga: `admin_detail` to istniejący endpoint szczegółów zamówienia
(`/admin/orders/<int:order_id>`). Jeśli w `modules/orders/routes.py` nazywa się
inaczej, użyj faktycznej nazwy funkcji spod tej trasy.

- [ ] **Step 5: Create the stylesheet**

Utwórz `static/css/pages/admin/unclaimed.css`:

```css
/* Lista nieodebranych zamówień (projekt 2026-09-02) */

.unclaimed {
    padding: 24px;
}

.unclaimed__title {
    margin: 0 0 8px;
    color: #333333;
}

.unclaimed__lead {
    margin: 0 0 20px;
    color: #4b5563;
    font-size: 0.9rem;
}

/* ===== Zakładki ===== */

.unclaimed__tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    border-bottom: 1px solid #e5e7eb;
}

.unclaimed__tab {
    padding: 10px 16px;
    min-height: 44px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #6b7280;
    font-size: 0.95rem;
    cursor: pointer;
}

.unclaimed__tab.is-active {
    color: #240046;
    border-bottom-color: #240046;
    font-weight: 600;
}

.unclaimed__panel {
    display: none;
}

.unclaimed__panel.is-active {
    display: block;
}

/* ===== Akcje ===== */

.unclaimed__actions {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}

.unclaimed__checkbox {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    font-size: 0.9rem;
    color: #4b5563;
}

/* ===== Tabela ===== */

.unclaimed__table-wrap {
    overflow-x: auto;
    background: #ffffff;
    border-radius: 8px;
}

.unclaimed__table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}

.unclaimed__table th,
.unclaimed__table td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid #f3f4f6;
    color: #212121;
}

.unclaimed__table th {
    color: #6b7280;
    font-weight: 600;
}

.unclaimed__col-check {
    width: 44px;
}

.unclaimed__expand {
    background: none;
    border: none;
    padding: 0;
    color: #240046;
    font-size: 0.9rem;
    text-align: left;
    cursor: pointer;
    text-decoration: underline;
}

.unclaimed__age--approx,
.unclaimed__age--unknown {
    color: #92400e;
}

.unclaimed__orders {
    margin: 0;
    padding: 8px 0 8px 20px;
}

.unclaimed__items {
    color: #6b7280;
    font-size: 0.85rem;
}

.unclaimed__badge {
    display: inline-block;
    margin-left: 8px;
    padding: 2px 8px;
    border-radius: 999px;
    background: #f3f4f6;
    color: #6b7280;
    font-size: 0.75rem;
}

.unclaimed__empty {
    padding: 32px;
    text-align: center;
    color: #6b7280;
}

/* ===== Ciemny motyw ===== */

[data-theme="dark"] .unclaimed__title {
    color: #f3f4f6;
}

[data-theme="dark"] .unclaimed__lead,
[data-theme="dark"] .unclaimed__checkbox,
[data-theme="dark"] .unclaimed__table th,
[data-theme="dark"] .unclaimed__items,
[data-theme="dark"] .unclaimed__empty {
    color: #9ca3af;
}

[data-theme="dark"] .unclaimed__tabs {
    border-bottom-color: #374151;
}

[data-theme="dark"] .unclaimed__tab {
    color: #9ca3af;
}

[data-theme="dark"] .unclaimed__tab.is-active {
    color: #c4b5fd;
    border-bottom-color: #c4b5fd;
}

[data-theme="dark"] .unclaimed__table-wrap {
    background: #1f2937;
}

[data-theme="dark"] .unclaimed__table td {
    color: #e5e7eb;
    border-bottom-color: #374151;
}

[data-theme="dark"] .unclaimed__expand {
    color: #c4b5fd;
}

[data-theme="dark"] .unclaimed__age--approx,
[data-theme="dark"] .unclaimed__age--unknown {
    color: #fbbf24;
}

[data-theme="dark"] .unclaimed__badge {
    background: #374151;
    color: #9ca3af;
}
```

- [ ] **Step 6: Add the sidebar entry**

W `templates/components/sidebar_admin.html`, bezpośrednio za elementem `<li>`
z `orders.admin_list` (kończy się w linii 41):

```html
                    <li class="sidebar-subitem">
                        <a href="{{ url_for('orders.admin_unclaimed') }}"
                           class="sidebar-sublink {% if request.endpoint == 'orders.admin_unclaimed' %}active{% endif %}"
                           data-tooltip="Nieodebrane">
                            <span class="sidebar-text">Nieodebrane</span>
                        </a>
                    </li>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_zamowienia.py -v`
Expected: PASS

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS — nowa pozycja w sidebarze renderuje się na każdym ekranie admina,
więc awaria `url_for` wywaliłaby cały panel; pełna suita to wychwyci.

- [ ] **Step 8: Commit**

```bash
git add modules/orders/routes.py templates/admin/orders/unclaimed.html static/css/pages/admin/unclaimed.css templates/components/sidebar_admin.html tests/test_nieodebrane_zamowienia.py
git commit -m "feat(nieodebrane): ekran admina z zakladkami klienci i produkty"
```

---

### Task 6: Przypomnienie — mail, push, trasa

**Files:**
- Create: `templates/emails/pickup_reminder.html`
- Modify: `utils/email_sender.py` (koniec pliku)
- Modify: `utils/email_manager.py` (obok `notify_costs_added_bulk`)
- Modify: `utils/push_manager.py` (sekcja SHIPPING)
- Modify: `modules/admin/models.py:371` (`EMAIL_TYPE_LABELS`)
- Modify: `modules/orders/routes.py:2137-2148` (`ALLOWED_KEYS`)
- Modify: `templates/admin/orders/settings.html:674` (przełącznik)
- Modify: `modules/orders/unclaimed_service.py`
- Modify: `modules/orders/routes.py` (trasa POST)
- Test: `tests/test_nieodebrane_przypomnienia.py` (nowy)

**Interfaces:**
- Consumes: `unclaimed_orders_query()` (Task 1), `prepare_email()`,
  `send_email_batch()` (`utils/email_sender.py`), `PushManager._fire_and_forget()`
- Produces:
  - `prepare_pickup_reminder_email(user_email, user_name, orders_summary, shipping_url, log_context=None) -> Message | None`
  - `EmailManager.notify_pickup_reminder_bulk(users_orders) -> int` gdzie
    `users_orders` to lista krotek `(User, [Order])`
  - `PushManager.notify_pickup_reminder(user_id, liczba_zamowien)`
  - `wyslij_przypomnienia(user_ids) -> dict` o kluczach `wyslane` (int),
    `pominieci` (lista adresów bez maila)

- [ ] **Step 1: Write the failing test**

Utwórz `tests/test_nieodebrane_przypomnienia.py`:

```python
"""Przypomnienia „odbierz swoje rzeczy" (projekt 2026-09-02).

Reguła nadrzędna: jedna osoba = jeden mail, choćby zalegała z pięcioma paczkami.
Wysyłka jednym batchem — limit AUTH Hostingera, tak samo jak przy kosztach.
"""
import pytest


@pytest.fixture
def batch_capture(monkeypatch):
    """Przechwytuje send_email_batch — zwraca listę wywołań (każde = lista Message)."""
    import utils.email_sender as es
    calls = []
    monkeypatch.setattr(es, 'send_email_batch', lambda msgs: calls.append(msgs))
    return calls


def test_klient_z_trzema_zamowieniami_dostaje_jeden_mail(app, db, make_user,
                                                          make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user(email='zalegacz@example.com')
    for _ in range(3):
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['wyslane'] == 1
    assert len(batch_capture) == 1
    assert len(batch_capture[0]) == 1
    assert batch_capture[0][0].recipients == ['zalegacz@example.com']


def test_trzech_klientow_jednym_batchem(app, db, make_user, make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    users = [make_user(email=f'k{i}@example.com') for i in range(3)]
    for u in users:
        make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id for u in users])

    assert wynik['wyslane'] == 3
    assert len(batch_capture) == 1  # jedno połączenie SMTP, nie trzy
    assert len(batch_capture[0]) == 3


def test_wysylka_stempluje_wszystkie_zamowienia(app, db, make_user, make_order,
                                                 batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    zamowienia = [make_order(u, status='dostarczone_gom') for _ in range(3)]

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    for z in zamowienia:
        db.session.refresh(z)
        assert z.pickup_reminder_sent_at is not None


def test_zamowienie_juz_w_zleceniu_nie_dostaje_stempla(app, db, make_user, make_order,
                                                        batch_capture):
    """Przypomnienie dotyczy tylko tego, co realnie zalega."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    zalega = make_order(u, status='dostarczone_gom')
    zamowione = make_order(u, status='dostarczone_gom')
    zlecenie = ShippingRequest(request_number='WYS/9', user_id=u.id)
    db.session.add(zlecenie)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=zlecenie.id,
                                        order_id=zamowione.id))
    db.session.commit()

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    db.session.refresh(zalega)
    db.session.refresh(zamowione)
    assert zalega.pickup_reminder_sent_at is not None
    assert zamowione.pickup_reminder_sent_at is None


def test_klient_bez_zaleglosci_nie_dostaje_maila(app, db, make_user, make_order,
                                                  batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    make_order(u, status='nowe')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['wyslane'] == 0
    assert batch_capture == []


def test_wylaczony_przelacznik_blokuje_maile(app, db, make_user, make_order,
                                              batch_capture, monkeypatch):
    from utils.email_manager import EmailManager
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    monkeypatch.setattr(
        EmailManager, 'is_email_enabled',
        staticmethod(lambda key: key != 'notify_pickup_reminder'),
    )
    u = make_user()
    make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wynik = wyslij_przypomnienia([u.id])

    assert wynik['wyslane'] == 0
    assert batch_capture == []


def test_mail_wymienia_numery_zamowien(app, db, make_user, make_order, batch_capture):
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    u = make_user()
    z = make_order(u, status='dostarczone_gom')

    with app.test_request_context():
        wyslij_przypomnienia([u.id])

    assert z.order_number in batch_capture[0][0].html


def test_trasa_wymaga_admina(app, client, db, make_user, login):
    login(make_user(role='client'))

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': [1]})

    assert r.status_code in (302, 403)


def test_trasa_zwraca_liczbe_wyslanych(app, client, db, make_user, make_order,
                                        login, batch_capture):
    login(make_user(role='admin', email='admin@example.com'))
    u = make_user(email='zalegacz@example.com')
    make_order(u, status='dostarczone_gom')

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': [u.id]})

    assert r.status_code == 200
    assert r.get_json()['wyslane'] == 1


def test_trasa_odrzuca_pusta_liste(app, client, db, make_user, login):
    login(make_user(role='admin', email='admin@example.com'))

    r = client.post('/admin/orders/nieodebrane/przypomnij', json={'user_ids': []})

    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_przypomnienia.py -v`
Expected: FAIL — `ImportError: cannot import name 'wyslij_przypomnienia'`

- [ ] **Step 3: Create the email template**

Utwórz `templates/emails/pickup_reminder.html`:

```html
<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twoje rzeczy czekają na odbiór - ThunderOrders</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background-color: #F5F5F5; line-height: 1.6;">
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #F5F5F5; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%; background-color: #FFFFFF; border-radius: 8px; overflow: hidden;">
                    <tr>
                        <td align="center" style="padding: 40px 40px 20px 40px;">
                            <img src="cid:logo@thunderorders" alt="ThunderOrders" style="height: 40px; width: auto; display: block;" />
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 40px;">
                            <h1 style="margin: 0 0 20px 0; font-size: 24px; font-weight: 700; color: #240046; text-align: left;">
                                Twoje rzeczy czekają na odbiór
                            </h1>
                            <p style="margin: 0 0 16px 0; font-size: 16px; color: #212121;">
                                Cześć <strong>{{ user_name }}</strong>!
                            </p>
                            <p style="margin: 0 0 20px 0; font-size: 16px; color: #212121;">
                                {% if orders_summary|length == 1 %}
                                    Twoje zamówienie dotarło do nas i czeka na wysyłkę — ale nie mamy jeszcze od Ciebie zlecenia wysyłki.
                                {% else %}
                                    Twoje zamówienia dotarły do nas i czekają na wysyłkę — ale nie mamy jeszcze od Ciebie zlecenia wysyłki.
                                {% endif %}
                            </p>
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 24px 0; border: 1px solid #E5E7EB; border-radius: 6px;">
                                {% for z in orders_summary %}
                                <tr>
                                    <td style="padding: 12px 16px; border-bottom: 1px solid #F3F4F6; font-size: 15px; color: #212121;">
                                        <strong>{{ z.numer }}</strong><br>
                                        <span style="font-size: 14px; color: #6B7280;">{{ z.pozycje }}</span>
                                    </td>
                                </tr>
                                {% endfor %}
                            </table>
                            <p style="margin: 0 0 24px 0; font-size: 16px; color: #212121;">
                                Żeby je odebrać, zamów wysyłkę w swoim panelu — wybierzesz adres i formę dostawy.
                            </p>
                            <table cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 8px 0;">
                                <tr>
                                    <td align="center" style="background-color: #240046; border-radius: 6px;">
                                        <a href="{{ shipping_url }}" style="display: inline-block; padding: 14px 28px; font-size: 16px; font-weight: 600; color: #FFFFFF; text-decoration: none;">
                                            Zamów wysyłkę
                                        </a>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 40px 40px 40px; font-size: 13px; color: #9CA3AF;">
                            Wiadomość wysłana automatycznie z panelu ThunderOrders.
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
```

- [ ] **Step 4: Add the email builder**

Na końcu `utils/email_sender.py`:

```python
def prepare_pickup_reminder_email(user_email, user_name, orders_summary,
                                  shipping_url, log_context=None):
    """Buduje Message z przypomnieniem o odbiorze (BEZ wysyłania) — do send_email_batch().

    `orders_summary` to lista dictów {'numer': str, 'pozycje': str} — jeden mail
    obejmuje WSZYSTKIE zaległe zamówienia klienta, więc szablon dostaje listę,
    nie pojedyncze zamówienie.
    """
    liczba = len(orders_summary)
    temat = ('Twoje zamówienie czeka na odbiór' if liczba == 1
             else f'Twoje zamówienia ({liczba}) czekają na odbiór')
    return prepare_email(
        to=user_email,
        subject=temat,
        template='pickup_reminder',
        log_context=log_context,
        user_name=user_name,
        orders_summary=orders_summary,
        shipping_url=shipping_url,
    )
```

- [ ] **Step 5: Add the EmailManager entry point**

W `utils/email_manager.py`, bezpośrednio za `notify_costs_added_bulk`:

```python
    @staticmethod
    def notify_pickup_reminder_bulk(users_orders):
        """Przypomnienia o odbiorze — jeden mail na klienta, jeden batch na całość.

        Args:
            users_orders: lista krotek (user, [order, ...]) — zamówienia zaległe
                tego klienta. Jedna krotka = jeden mail; klient z trzema paczkami
                dostaje jedną wiadomość, nie trzy.

        Returns:
            int: liczba zakolejkowanych wiadomości
        """
        if not EmailManager.is_email_enabled('notify_pickup_reminder'):
            current_app.logger.info(
                "Email notification 'notify_pickup_reminder' is disabled, skipping bulk")
            return 0

        from utils.email_sender import prepare_pickup_reminder_email, send_email_batch

        shipping_url = url_for('client.shipping_requests_list', _external=True)

        messages = []
        for user, orders in users_orders:
            email = getattr(user, 'email', None)
            if not email:
                current_app.logger.warning(
                    f"Cannot send pickup reminder for user {getattr(user, 'id', '?')}: no email")
                continue

            podsumowanie = [{
                'numer': o.order_number,
                'pozycje': ', '.join(
                    f"{it.product.name if it.product else it.custom_name} ×{it.quantity}"
                    for it in o.items
                ) or 'brak pozycji',
            } for o in orders]

            msg = prepare_pickup_reminder_email(
                user_email=email,
                user_name=getattr(user, 'first_name', None) or email,
                orders_summary=podsumowanie,
                shipping_url=shipping_url,
                log_context={'entity_type': 'user', 'entity_id': user.id},
            )
            if msg:
                messages.append(msg)

        if messages:
            send_email_batch(messages)
            current_app.logger.info(f"Queued batch of {len(messages)} pickup reminders")
        return len(messages)
```

- [ ] **Step 6: Add the push notification**

W `utils/push_manager.py`, w sekcji SHIPPING:

```python
    @staticmethod
    def notify_pickup_reminder(user_id, liczba_zamowien):
        """Push + wpis w centrum powiadomień: „odbierz swoje rzeczy".

        Kategoria `shipping_updates`, nie własne pole w NotificationPreference —
        z punktu widzenia klienta to powiadomienie o wysyłce, a dokładanie kolumny
        znaczyłoby migrację dla jednego przełącznika.
        """
        from flask import url_for

        try:
            url = url_for('client.shipping_requests_list', _external=True)
        except RuntimeError:
            url = '/'

        tresc = ('Twoje zamówienie czeka na odbiór — zamów wysyłkę'
                 if liczba_zamowien == 1
                 else f'{liczba_zamowien} Twoje zamówienia czekają na odbiór — zamów wysyłkę')

        PushManager._fire_and_forget(
            user_id=user_id,
            title='Odbierz swoje rzeczy',
            body=tresc,
            url=url,
            tag=f'pickup-reminder-{user_id}',
            notification_type='shipping_updates',
        )
```

- [ ] **Step 7: Register the new email type**

W `modules/admin/models.py`, w `EMAIL_TYPE_LABELS` (za `'payment_reminder'`):

```python
    'pickup_reminder': 'przypomnienie o odbiorze',
```

W `modules/orders/routes.py`, w `ALLOWED_KEYS` funkcji
`update_email_notification_settings` (linie 2137-2148), dopisz do zbioru:

```python
        'notify_pickup_reminder',
```

W `templates/admin/orders/settings.html`, za blokiem `notify_cost_added`
(kończy się w linii 674):

```html
                            <div class="email-notif-item">
                                <div class="email-notif-info">
                                    <div class="email-notif-name">Przypomnienie o odbiorze</div>
                                    <div class="email-notif-desc">Rzeczy czekają, klient nie zamówił wysyłki</div>
                                </div>
                                <label class="email-toggle-switch">
                                    <input type="checkbox" class="email-notif-toggle" data-key="notify_pickup_reminder" {{ 'checked' if email_notif_config.get('notify_pickup_reminder', true) != false }}>
                                    <span class="email-toggle-slider"></span>
                                </label>
                            </div>
```

- [ ] **Step 8: Add the service function**

Dopisz do `modules/orders/unclaimed_service.py`:

```python
def wyslij_przypomnienia(user_ids):
    """Wysyła przypomnienia o odbiorze do wskazanych klientów.

    Zaległości pobierane są tu na nowo, a nie przyjmowane z przeglądarki: między
    wyrenderowaniem ekranu a kliknięciem przycisku klient mógł już zamówić wysyłkę
    i przypominanie mu o tym byłoby wpadką.

    Returns:
        dict: {'wyslane': int, 'pominieci': [str]} — pominięci to adresy klientów,
        którzy w międzyczasie przestali zalegać.
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    if not user_ids:
        return {'wyslane': 0, 'pominieci': []}

    zamowienia = unclaimed_orders_query().filter(
        Order.user_id.in_(user_ids)
    ).options(
        joinedload(Order.user),
        joinedload(Order.items).joinedload(OrderItem.product),
    ).all()

    wg_klienta = {}
    for o in zamowienia:
        wg_klienta.setdefault(o.user_id, {'user': o.user, 'zamowienia': []})
        wg_klienta[o.user_id]['zamowienia'].append(o)

    pominieci = [str(uid) for uid in user_ids if uid not in wg_klienta]
    if not wg_klienta:
        return {'wyslane': 0, 'pominieci': pominieci}

    wyslane = EmailManager.notify_pickup_reminder_bulk(
        [(w['user'], w['zamowienia']) for w in wg_klienta.values()]
    )

    if wyslane:
        teraz = get_local_now()
        for user_id, w in wg_klienta.items():
            for o in w['zamowienia']:
                o.pickup_reminder_sent_at = teraz
            PushManager.notify_pickup_reminder(user_id, len(w['zamowienia']))
        db.session.commit()

    return {'wyslane': wyslane, 'pominieci': pominieci}
```

- [ ] **Step 9: Add the route**

W `modules/orders/routes.py`, tuż za `admin_unclaimed`:

```python
@orders_bp.route('/admin/orders/nieodebrane/przypomnij', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_unclaimed_remind():
    """Wysyła przypomnienia o odbiorze do zaznaczonych klientów."""
    from modules.orders.unclaimed_service import wyslij_przypomnienia

    data = request.get_json() or {}
    user_ids = data.get('user_ids') or []
    if not user_ids:
        return jsonify({'success': False, 'message': 'Nie wybrano nikogo'}), 400

    wynik = wyslij_przypomnienia([int(uid) for uid in user_ids])
    return jsonify({'success': True, **wynik})
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_nieodebrane_przypomnienia.py -v`
Expected: PASS (10 testów)

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add templates/emails/pickup_reminder.html utils/email_sender.py utils/email_manager.py utils/push_manager.py modules/admin/models.py modules/orders/routes.py modules/orders/unclaimed_service.py templates/admin/orders/settings.html tests/test_nieodebrane_przypomnienia.py
git commit -m "feat(nieodebrane): reczne przypomnienie o odbiorze mailem i pushem"
```

---

### Task 7: Obsługa ekranu w przeglądarce

Projekt nie ma oprzyrządowania do testów JavaScriptu (patrz projekt
`2026-09-01-przelacznik-cala-paczka-incl-design.md`) — weryfikacja przez
`node --check` i przeklikanie po stronie właścicielki.

**Files:**
- Create: `static/js/pages/admin/unclaimed.js`

**Interfaces:**
- Consumes: endpoint `POST /admin/orders/nieodebrane/przypomnij` (Task 6),
  atrybuty `data-tab`, `data-panel`, `data-target`, `data-ostatnie` z szablonu (Task 5)

- [ ] **Step 1: Write the script**

Utwórz `static/js/pages/admin/unclaimed.js`:

```javascript
/* Ekran „Nieodebrane" — zakładki, zaznaczanie klientów, wysyłka przypomnień. */
(function () {
    'use strict';

    const DNI_OSTRZEZENIA = 7;

    /* ===== Zakładki ===== */
    document.querySelectorAll('.unclaimed__tab').forEach(function (tab) {
        tab.addEventListener('click', function () {
            const nazwa = tab.dataset.tab;
            document.querySelectorAll('.unclaimed__tab').forEach(function (t) {
                t.classList.toggle('is-active', t === tab);
            });
            document.querySelectorAll('.unclaimed__panel').forEach(function (p) {
                p.classList.toggle('is-active', p.dataset.panel === nazwa);
            });
        });
    });

    /* ===== Rozwijanie szczegółów ===== */
    document.querySelectorAll('.unclaimed__expand').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const wiersz = document.getElementById(btn.dataset.target);
            if (wiersz) {
                wiersz.hidden = !wiersz.hidden;
            }
        });
    });

    /* ===== Zaznaczanie ===== */
    const przycisk = document.getElementById('unclaimedRemindBtn');
    const licznik = document.getElementById('unclaimedCount');
    const zaznaczWszystkie = document.getElementById('unclaimedSelectAll');
    if (!przycisk) {
        return;  // ekran bez zaległości — nie ma czego obsługiwać
    }

    function zaznaczone() {
        return Array.from(document.querySelectorAll('.unclaimed__pick:checked'));
    }

    function odswiezLicznik() {
        const n = zaznaczone().length;
        licznik.textContent = n;
        przycisk.disabled = n === 0;
    }

    document.querySelectorAll('.unclaimed__pick').forEach(function (cb) {
        cb.addEventListener('change', odswiezLicznik);
    });

    if (zaznaczWszystkie) {
        zaznaczWszystkie.addEventListener('change', function () {
            document.querySelectorAll('.unclaimed__pick').forEach(function (cb) {
                cb.checked = zaznaczWszystkie.checked;
            });
            odswiezLicznik();
        });
    }

    /* ===== Wysyłka ===== */
    function niedawnoPrzypomniane(pola) {
        // Ostrzegamy, zanim admin drugi raz w tym tygodniu napisze do tej samej osoby.
        const prog = Date.now() - DNI_OSTRZEZENIA * 24 * 60 * 60 * 1000;
        return pola.filter(function (cb) {
            const data = cb.dataset.ostatnie;
            return data && Date.parse(data) > prog;
        });
    }

    przycisk.addEventListener('click', function () {
        const pola = zaznaczone();
        if (pola.length === 0) {
            return;
        }

        const swiezo = niedawnoPrzypomniane(pola);
        if (swiezo.length > 0) {
            const ilu = swiezo.length === 1 ? 'jednej osobie' : swiezo.length + ' osobom';
            if (!window.confirm(
                'Do ' + ilu + ' przypomnienie poszło w ciągu ostatnich ' +
                DNI_OSTRZEZENIA + ' dni. Wysłać mimo to?'
            )) {
                return;
            }
        }

        przycisk.disabled = true;
        fetch('/admin/orders/nieodebrane/przypomnij', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content || ''
            },
            body: JSON.stringify({ user_ids: pola.map(function (cb) { return Number(cb.value); }) })
        })
            .then(function (r) { return r.json(); })
            .then(function (dane) {
                if (dane.success) {
                    window.showToast?.('Wysłano przypomnień: ' + dane.wyslane, 'success');
                    window.location.reload();
                } else {
                    window.showToast?.(dane.message || 'Nie udało się wysłać', 'error');
                    przycisk.disabled = false;
                }
            })
            .catch(function () {
                window.showToast?.('Nie udało się wysłać przypomnień', 'error');
                przycisk.disabled = false;
            });
    });

    odswiezLicznik();
})();
```

- [ ] **Step 2: Verify the syntax**

Run: `node --check static/js/pages/admin/unclaimed.js`
Expected: brak wyjścia (składnia poprawna)

- [ ] **Step 3: Verify the CSRF and toast conventions**

Run: `grep -rn "X-CSRFToken" static/js/pages/admin/orders-list.js | head -3`
Expected: ten sam nagłówek i to samo źródło tokenu. Jeśli projekt pobiera token
inaczej (np. z ukrytego pola formularza), przepisz `headers` na tamten wzorzec —
niespójność skończy się odrzuconym żądaniem.

Run: `grep -rn "showToast" static/js/pages/admin/orders-list.js | head -3`
Expected: potwierdzenie nazwy globalnej funkcji toastów. Jeśli nazywa się inaczej,
podmień oba wywołania.

- [ ] **Step 4: Run the full suite**

Run: `venv/bin/python -m pytest tests/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/admin/unclaimed.js
git commit -m "feat(nieodebrane): obsluga zakladek i wysylki przypomnien w przegladarce"
```

---

## Po wykonaniu planu

1. `venv/bin/python -m pytest tests/ -q` — cała suita zielona.
2. `venv/bin/python -m flask db upgrade c9d1e2f3a4b5` na bazie deweloperskiej.
3. Przekazać właścicielce do przeklikania: ekran „Nieodebrane" w menu, obie
   zakładki, rozwijanie wierszy, zaznaczanie, ostrzeżenie o 7 dniach, wygląd
   w ciemnym motywie, wygląd na telefonie.
4. **Nie pushować** bez jej wyraźnej zgody — push oznacza wdrożenie na produkcję.
