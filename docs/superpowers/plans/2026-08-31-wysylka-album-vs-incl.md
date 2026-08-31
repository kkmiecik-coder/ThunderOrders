# Wysyłka KR osobno dla całego albumu i dla samego incl — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Koszt Wysyłki KR ma się rozdzielać na zamówienia klientów wg tego, czy dana sztuka to cały album (drożej), czy samo incl (taniej), zamiast po równo na każdą sztukę.

**Architecture:** Wybór album/incl zapisuje się trwale przy pozycji zamówienia klienta (`order_items.incl_only_quantity`), a stawki za sztukę — przy pozycji partii do Polski (`poland_order_items.shipping_cost_album_per_unit` / `_incl_per_unit`). Podział FIFO nie zmienia zasady (partie wg daty utworzenia, sztuki klientów wg daty złożenia zamówienia); zmienia się tylko cena pojedynczej sztuki, zależna od jej typu. Admin zaznacza wszystko w oknie „Zamówienie do Polski", które dostaje podgląd przydziału klientów.

**Tech Stack:** Flask + SQLAlchemy + Flask-Migrate (MariaDB na produkcji, SQLite w testach), Jinja2, waniliowy JS, pytest.

**Projekt (spec):** `docs/superpowers/specs/2026-08-31-wysylka-album-vs-incl-design.md`
**Zadanie ClickUp:** [869erz1q0](https://app.clickup.com/t/869erz1q0)
**Gałąź:** `feat/wysylka-album-vs-incl`

## Global Constraints

- Gałąź robocza: `feat/wysylka-album-vs-incl`. Nigdy nie commitować na `main`.
- **Nie wolno pushować.** Commity tylko lokalne; push wykonuje Karolina po swojej akceptacji.
- Testy uruchamiać przez `python -m pytest` (nie samo `pytest`).
- Każda zmiana schematu bazy przez Flask-Migrate/Alembic — żadnego ręcznego ALTER-a.
- Domyślne zachowanie musi zostać nietknięte: `incl_only_quantity = 0` i stawki `NULL` → wyniki identyczne jak przed zmianą. Żadnego backfillu istniejących danych.
- Komunikaty i etykiety po polsku; komentarze w kodzie po polsku, zgodnie z otoczeniem w `modules/products/routes.py`.
- Commity w konwencji `feat(wysylka): ...` / `test(wysylka): ...` / `fix(wysylka): ...`.
- CSS pisać w wariancie jasnym i ciemnym; style modali tylko w `static/css/modals.css`.
- **Poza zakresem:** edycja kosztów wysyłki na już utworzonej partii (nie istnieje dziś taki endpoint i nie dorabiamy go), oraz wybór album/incl przez klienta przy składaniu zamówienia.

---

### Task 1: Kolumny w bazie i migracja

**Files:**
- Modify: `modules/orders/models.py:1257` (klasa `OrderItem`, przy `selected_size`)
- Modify: `modules/products/models.py:443` (klasa `PolandOrderItem`, przy `shipping_cost`)
- Create: `migrations/versions/<wygenerowany>_wysylka_album_vs_incl.py`
- Test: `tests/test_wysylka_album_vs_incl.py`

**Interfaces:**
- Produces: `OrderItem.incl_only_quantity` (int, NOT NULL, default 0), `PolandOrderItem.shipping_cost_album_per_unit` i `PolandOrderItem.shipping_cost_incl_per_unit` (Numeric(10,2), nullable, default None).

- [ ] **Step 1: Napisz test na domyślne wartości nowych kolumn**

Utwórz `tests/test_wysylka_album_vs_incl.py`:

```python
"""Testy podziału Wysyłki KR na cały album i samo incl.

Model: przy pozycji zamówienia klienta siedzi `incl_only_quantity` (ile sztuk
klient bierze jako samo incl), a przy pozycji partii do Polski dwie stawki za
sztukę. Podział FIFO bez zmian — zmienia się tylko cena sztuki, zależna od typu.
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def test_domyslne_wartosci_nowych_kolumn(db, make_user, make_order, make_product):
    """Bez jawnego ustawienia: pozycja klienta ma 0 incl, partia nie ma stawek."""
    from modules.orders.models import OrderItem
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )

    produkt = make_product()
    zamowienie = make_order(make_user(), offer_page_id=1)
    pozycja = OrderItem(
        order_id=zamowienie.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'),
    )
    db.session.add(pozycja)

    proxy = ProxyOrder(order_number='PRX/T1', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    )
    db.session.add(proxy_item)
    db.session.flush()
    partia = PolandOrder(
        order_number='PRX/PL/T1', proxy_order_id=proxy.id,
        status='zamowione', shipping_cost=Decimal('100'),
    )
    db.session.add(partia)
    db.session.flush()
    pozycja_partii = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=produkt.id, quantity=2, shipping_cost=Decimal('100'),
    )
    db.session.add(pozycja_partii)
    db.session.commit()

    assert pozycja.incl_only_quantity == 0
    assert pozycja_partii.shipping_cost_album_per_unit is None
    assert pozycja_partii.shipping_cost_incl_per_unit is None
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py::test_domyslne_wartosci_nowych_kolumn -v`
Expected: FAIL — `AttributeError: 'OrderItem' object has no attribute 'incl_only_quantity'`

- [ ] **Step 3: Dodaj kolumnę do `OrderItem`**

W `modules/orders/models.py`, bezpośrednio pod `selected_size` (linia 1257):

```python
    # Ile sztuk z tej pozycji klient bierze jako SAMO INCL (bez całego albumu).
    # Reszta (quantity - incl_only_quantity) to całe albumy. 0 = wszystko albumy,
    # czyli zachowanie sprzed rozdzielenia stawek wysyłki KR.
    incl_only_quantity = db.Column(db.Integer, nullable=False, default=0, server_default='0')
```

- [ ] **Step 4: Dodaj kolumny do `PolandOrderItem`**

W `modules/products/models.py`, bezpośrednio pod `shipping_cost` (linia 443):

```python
    # Stawki wysyłki KR za sztukę, osobno dla całego albumu i dla samego incl.
    # NULL w obu = partia sprzed rozdzielenia stawek → koszt dzieli się po równo
    # (shipping_cost / quantity), dokładnie jak wcześniej. Bez backfillu.
    shipping_cost_album_per_unit = db.Column(db.Numeric(10, 2), nullable=True, default=None)
    shipping_cost_incl_per_unit = db.Column(db.Numeric(10, 2), nullable=True, default=None)
```

- [ ] **Step 5: Sprawdź aktualną głowę migracji**

Run: `python -m flask db heads`
Zapisz wypisany identyfikator — będzie `down_revision` nowej migracji.

- [ ] **Step 6: Wygeneruj migrację**

Run: `python -m flask db revision -m "wysylka album vs incl"`

W wygenerowanym pliku w `migrations/versions/` wpisz `down_revision` z kroku 5 i uzupełnij treść:

```python
def upgrade():
    op.add_column('order_items', sa.Column(
        'incl_only_quantity', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('poland_order_items', sa.Column(
        'shipping_cost_album_per_unit', sa.Numeric(10, 2), nullable=True))
    op.add_column('poland_order_items', sa.Column(
        'shipping_cost_incl_per_unit', sa.Numeric(10, 2), nullable=True))


def downgrade():
    op.drop_column('poland_order_items', 'shipping_cost_incl_per_unit')
    op.drop_column('poland_order_items', 'shipping_cost_album_per_unit')
    op.drop_column('order_items', 'incl_only_quantity')
```

Docstring migracji (po polsku, wzorem `migrations/versions/pk2026080401_klucze_glowne_i_autonumeracja.py`) ma tłumaczyć: `server_default='0'` jest konieczny, bo tabela `order_items` ma na produkcji dane, a kolumna jest NOT NULL — bez domyślnej wartości MariaDB odrzuci ALTER.

- [ ] **Step 7: Uruchom migrację lokalnie**

Run: `python -m flask db upgrade`
Expected: kończy się bez błędu; `python -m flask db heads` pokazuje nową rewizję.

- [ ] **Step 8: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py::test_domyslne_wartosci_nowych_kolumn -v`
Expected: PASS

- [ ] **Step 9: Sprawdź, że nic się nie zepsuło**

Run: `python -m pytest tests/test_proxy_shipping_distribution.py tests/test_poland_order_item_allocation.py -v`
Expected: wszystkie PASS

- [ ] **Step 10: Commit**

```bash
git add modules/orders/models.py modules/products/models.py migrations/versions tests/test_wysylka_album_vs_incl.py
git commit -m "feat(wysylka): kolumny na wybór album/incl i stawki per sztuka"
```

---

### Task 2: Algorytm podziału ze stawkami album/incl

**Files:**
- Modify: `modules/products/routes.py:3900-3970` (`_client_item_qty`, `_allocate_product_shipping_fifo`)
- Modify: `modules/products/routes.py:3972-4035` (`_allocate_batch_units_to_orders`)
- Test: `tests/test_wysylka_album_vs_incl.py`

**Interfaces:**
- Consumes: `OrderItem.incl_only_quantity`, `PolandOrderItem.shipping_cost_album_per_unit`, `PolandOrderItem.shipping_cost_incl_per_unit` (Task 1).
- Produces:
  - `_order_product_quantities(order, product_id) -> tuple[int, int]` — `(ilość efektywna, ile z niej to incl)`.
  - `_batch_allocation_for_range(product_id, batch_start, batch_end) -> list[tuple[int, int]]` — lista `(order_id, ilość)`.
  - `_allocate_product_shipping_fifo(product_id) -> dict[int, Decimal]` — bez zmian w sygnaturze.
  - `_allocate_batch_units_to_orders(poland_item) -> list[tuple[int, int]]` — bez zmian w sygnaturze.

- [ ] **Step 1: Dopisz helpery testowe do pliku testów**

Dopisz na końcu sekcji importów w `tests/test_wysylka_album_vs_incl.py`:

```python
def _partia(db, product_id, qty, shipping, created_at,
            album_rate=None, incl_rate=None, status='zamowione'):
    """Tworzy ProxyOrder+Item oraz PolandOrder+Item — jedną partię danego produktu."""
    from modules.products.models import (
        PolandOrder, PolandOrderItem, ProxyOrder, ProxyOrderItem,
    )
    suffix = f'{product_id}-{int(created_at.timestamp())}'
    proxy = ProxyOrder(order_number=f'PRX/T{suffix}', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
        unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(
        order_number=f'PRX/PL/T{suffix}', proxy_order_id=proxy.id,
        status=status, shipping_cost=Decimal(str(shipping)),
    )
    partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()
    pozycja = PolandOrderItem(
        poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
        product_id=product_id, quantity=qty, shipping_cost=Decimal(str(shipping)),
        shipping_cost_album_per_unit=(
            None if album_rate is None else Decimal(str(album_rate))),
        shipping_cost_incl_per_unit=(
            None if incl_rate is None else Decimal(str(incl_rate))),
    )
    db.session.add(pozycja)
    db.session.commit()
    return partia


def _zamowienie_klienta(db, make_user, make_order, product_id, qty, created_at,
                        incl=0, price=130):
    """Zamówienie klienta (exclusive) z jedną pozycją i wskazaną liczbą sztuk incl."""
    from modules.orders.models import OrderItem
    zam = make_order(make_user(), offer_page_id=1, created_at=created_at)
    poz = OrderItem(
        order_id=zam.id, product_id=product_id, quantity=qty,
        price=Decimal(str(price)), total=Decimal(str(price)) * qty,
        incl_only_quantity=incl,
    )
    db.session.add(poz)
    db.session.commit()
    return zam
```

- [ ] **Step 2: Napisz testy algorytmu**

Dopisz do `tests/test_wysylka_album_vs_incl.py`:

```python
def test_bez_incl_podzial_jak_dotad(db, make_user, make_order, make_product):
    """Regresja: gdy nikt nie bierze incl, wynik jest identyczny jak przed zmianą."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='200', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=2))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2, baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('100.00')
    assert alokacja[b.id] == Decimal('100.00')


def test_partia_bez_stawek_stara_logika(db, make_user, make_order, make_product):
    """Stara partia (stawki NULL) dzieli po równo, nawet gdy klient ma incl."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='100', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2), incl=1)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('50.00')
    assert alokacja[b.id] == Decimal('50.00')


def test_klient_w_calosci_na_incl(db, make_user, make_order, make_product):
    """3 szt. samego incl po 12 zł = 36 zł, mimo że album kosztuje 45 zł/szt."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=4, shipping='81', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=2), incl=3)
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=1))

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('36.00')
    assert alokacja[b.id] == Decimal('45.00')


def test_klient_mieszany_album_i_incl(db, make_user, make_order, make_product):
    """2 szt. = 1 album (45) + 1 incl (12) = 57 zł na jednym zamówieniu."""
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='57', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('57.00')


def test_dwie_partie_rozne_stawki_bez_dublowania(db, make_user, make_order, make_product):
    """Dwie partie, każda ze swoimi stawkami; przeliczenie od zera daje ten sam wynik."""
    from modules.products.routes import (
        _allocate_product_shipping_fifo, _distribute_proxy_shipping_to_client_orders,
    )
    from modules.orders.models import Order

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='57', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    _partia(db, produkt.id, qty=2, shipping='40', created_at=baza + timedelta(days=1),
            album_rate='30.00', incl_rate='10.00')

    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3), incl=1)   # 1. partia: 45 + 12
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=2)   # 2. partia: 10 + 10

    alokacja = _allocate_product_shipping_fifo(produkt.id)
    assert alokacja[a.id] == Decimal('57.00')
    assert alokacja[b.id] == Decimal('20.00')

    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()
    _distribute_proxy_shipping_to_client_orders({produkt.id: Decimal('1')})
    db.session.commit()

    assert db.session.get(Order, a.id).proxy_shipping_cost == Decimal('57.00')
    assert db.session.get(Order, b.id).proxy_shipping_cost == Decimal('20.00')


def test_incl_przyciete_do_ilosci_zrealizowanej(db, make_user, make_order, make_product):
    """Set zrealizowany częściowo: incl nie może przekroczyć ilości, którą klient dostał."""
    from modules.orders.models import OrderItem
    from modules.products.routes import _allocate_product_shipping_fifo

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=1, shipping='12', created_at=baza,
            album_rate='45.00', incl_rate='12.00')
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=2), incl=3)
    pozycja = OrderItem.query.filter_by(order_id=a.id).one()
    pozycja.fulfilled_quantity = 1
    db.session.commit()

    alokacja = _allocate_product_shipping_fifo(produkt.id)

    assert alokacja[a.id] == Decimal('12.00')
```

- [ ] **Step 3: Uruchom testy — mają paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -v`
Expected: `test_klient_w_calosci_na_incl`, `test_klient_mieszany_album_i_incl`, `test_dwie_partie_rozne_stawki_bez_dublowania`, `test_incl_przyciete_do_ilosci_zrealizowanej` — FAIL (koszt dzielony po równo); pozostałe PASS

- [ ] **Step 4: Dodaj `_order_product_quantities`**

W `modules/products/routes.py`, bezpośrednio pod `_client_item_qty` (kończy się na linii 3908):

```python
def _order_product_quantities(order, product_id):
    """Ile sztuk danego produktu ma zamówienie i ile z nich to SAMO INCL.

    Ilość efektywna liczona przez `_client_item_qty` (sety, częściowa realizacja);
    `incl_only_quantity` przycinamy do niej per pozycja, żeby przy częściowo
    zrealizowanym secie nie policzyć incl-a, którego klient nie dostał.

    Zwraca (ilość, ilość_incl).
    """
    ilosc = 0
    incl = 0
    for item in order.items:
        if item.product_id != product_id:
            continue
        efektywna = _client_item_qty(item)
        if efektywna <= 0:
            continue
        ilosc += efektywna
        incl += min(item.incl_only_quantity or 0, efektywna)
    return ilosc, incl
```

- [ ] **Step 5: Przepisz budowanie slotów i konsumpcję w `_allocate_product_shipping_fifo`**

W `modules/products/routes.py` zamień fragment od `slots = []` do `return alloc` (linie 3925-3970) na:

```python
    # Sloty jednostkowe: para stawek (album, incl) dla każdej sztuki, w kolejności partii.
    # Partia bez stawek (obie NULL) = sprzed rozdzielenia — obie stawki równe
    # shipping_cost / quantity, czyli stary podział po równo.
    slots = []
    for pi in poland_items:
        qty = pi.quantity or 0
        if qty <= 0:
            continue
        stawka_album = pi.shipping_cost_album_per_unit
        stawka_incl = pi.shipping_cost_incl_per_unit
        if stawka_album is None or stawka_incl is None:
            po_rowno = Decimal(str(pi.shipping_cost or 0)) / Decimal(qty)
            stawka_album = stawka_incl = po_rowno
        else:
            stawka_album = Decimal(str(stawka_album))
            stawka_incl = Decimal(str(stawka_incl))
        slots.extend([(stawka_album, stawka_incl)] * qty)

    # Zamówienia klientów (exclusive) w kolejności daty złożenia (FIFO)
    client_orders = (
        Order.query
        .filter(Order.offer_page_id.isnot(None), Order.status != 'anulowane')
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )

    alloc = {}
    idx = 0
    for order in client_orders:
        qty, incl_qty = _order_product_quantities(order, product_id)
        if qty <= 0:
            continue
        album_qty = qty - incl_qty
        total = Decimal('0')
        for numer_sztuki in range(qty):
            if idx >= len(slots):
                break  # brak partii dla tych sztuk — koszt naliczy się przy kolejnej
            stawka_album, stawka_incl = slots[idx]
            total += stawka_album if numer_sztuki < album_qty else stawka_incl
            idx += 1
        alloc[order.id] = total.quantize(Decimal('0.01'))
    return alloc
```

Usuń przy tym stary blok liczący `qty` przez `sum(_client_item_qty(...))` — zastępuje go `_order_product_quantities`.

- [ ] **Step 6: Wydziel `_batch_allocation_for_range` i oprzyj na nim `_allocate_batch_units_to_orders`**

W `modules/products/routes.py` zamień ciało `_allocate_batch_units_to_orders` od `client_orders = (` do `return result` na wywołanie nowego helpera, a sam helper dopisz **nad** `_allocate_batch_units_to_orders`:

```python
def _batch_allocation_for_range(product_id, batch_start, batch_end):
    """Które zamówienia klientów (i ile sztuk) wpadają w zakres [batch_start, batch_end)
    kolejki FIFO sztuk danego produktu.

    Kolejka: zamówienia exclusive wg daty złożenia, każde zajmuje tyle miejsc, ile ma
    sztuk efektywnych. Zwraca listę (order_id, ilość) w kolejności FIFO.
    """
    from modules.orders.models import Order

    client_orders = (
        Order.query
        .filter(Order.offer_page_id.isnot(None), Order.status != 'anulowane')
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )

    result = []
    cursor = 0
    for order in client_orders:
        qty, _ = _order_product_quantities(order, product_id)
        if qty <= 0:
            continue
        order_start, order_end = cursor, cursor + qty
        cursor = order_end

        overlap = min(order_end, batch_end) - max(order_start, batch_start)
        if overlap > 0:
            result.append((order.id, overlap))

    return result
```

Ogon `_allocate_batch_units_to_orders` (po wyliczeniu `batch_start` / `batch_end`) staje się:

```python
    return _batch_allocation_for_range(product_id, batch_start, batch_end)
```

Import `from modules.orders.models import Order` na górze `_allocate_batch_units_to_orders` przestaje być potrzebny — usuń go, zostaw tylko `from modules.products.models import PolandOrder`.

- [ ] **Step 7: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -v`
Expected: wszystkie PASS

- [ ] **Step 8: Sprawdź regresję na istniejących testach**

Run: `python -m pytest tests/test_proxy_shipping_distribution.py tests/test_poland_order_item_allocation.py tests/test_customs_vat_zero.py -v`
Expected: wszystkie PASS

- [ ] **Step 9: Commit**

```bash
git add modules/products/routes.py tests/test_wysylka_album_vs_incl.py
git commit -m "feat(wysylka): stawka sztuki zalezna od typu album/incl w podziale FIFO"
```

---

### Task 3: Podgląd przydziału klientów w oknie partii (backend)

**Files:**
- Modify: `modules/products/routes.py:3855-3897` (`get_proxy_orders_details`)
- Modify: `modules/products/routes.py` (nowy helper `_preview_batch_allocation` obok `_batch_allocation_for_range`)
- Test: `tests/test_wysylka_album_vs_incl.py`

**Interfaces:**
- Consumes: `_batch_allocation_for_range`, `_order_product_quantities` (Task 2).
- Produces:
  - `_preview_batch_allocation(product_id, quantity, offset=0) -> list[tuple[int, int]]`.
  - `/admin/products/api/get-proxy-orders-details` zwraca dla każdej pozycji dodatkowe pole `clients`: lista `{order_id, order_number, client_name, quantity, incl_only_quantity}`.

- [ ] **Step 1: Napisz test podglądu**

Dopisz do `tests/test_wysylka_album_vs_incl.py`:

```python
def test_podglad_przydziela_klientow_do_tworzonej_partii(db, make_user, make_order,
                                                         make_product):
    """Nowa partia trafia na koniec kolejki: pierwsze 2 szt. zjadł klient A z wcześniejszej
    partii, więc podgląd partii na 2 szt. pokazuje klienta B."""
    from modules.products.routes import _preview_batch_allocation

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    _partia(db, produkt.id, qty=2, shipping='90', created_at=baza)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)

    podglad = _preview_batch_allocation(produkt.id, quantity=2)

    assert podglad == [(b.id, 2)]
    assert a.id not in [oid for oid, _ in podglad]


def test_podglad_z_offsetem_dla_dwoch_pozycji_tego_samego_produktu(
        db, make_user, make_order, make_product):
    """Dwie pozycje z tym samym produktem w jednym oknie nie mogą wskazać tych samych sztuk."""
    from modules.products.routes import _preview_batch_allocation

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2))

    pierwsza = _preview_batch_allocation(produkt.id, quantity=1, offset=0)
    druga = _preview_batch_allocation(produkt.id, quantity=1, offset=1)

    assert pierwsza == [(a.id, 1)]
    assert druga == [(b.id, 1)]
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -k podglad -v`
Expected: FAIL — `ImportError: cannot import name '_preview_batch_allocation'`

- [ ] **Step 3: Dodaj `_preview_batch_allocation`**

W `modules/products/routes.py`, bezpośrednio pod `_batch_allocation_for_range`:

```python
def _preview_batch_allocation(product_id, quantity, offset=0):
    """Podgląd przydziału dla partii, której jeszcze NIE ma w bazie (tworzonej w modalu).

    Nowa partia trafia na koniec kolejki FIFO, więc zaczyna się za wszystkimi
    istniejącymi (nieanulowanymi) partiami tego produktu. `offset` przesuwa start,
    gdy w jednym oknie jest kilka pozycji z tym samym produktem — bez niego obie
    wskazywałyby te same sztuki.
    """
    from modules.products.models import PolandOrder

    juz_w_partiach = db.session.query(
        db.func.coalesce(db.func.sum(PolandOrderItem.quantity), 0)
    ).join(
        PolandOrder, PolandOrderItem.poland_order_id == PolandOrder.id
    ).filter(
        PolandOrderItem.product_id == product_id,
        PolandOrder.status != 'anulowane',
    ).scalar() or 0

    start = int(juz_w_partiach) + offset
    return _batch_allocation_for_range(product_id, start, start + quantity)
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -k podglad -v`
Expected: PASS

- [ ] **Step 5: Napisz test endpointu**

Dopisz do `tests/test_wysylka_album_vs_incl.py`:

```python
def test_endpoint_szczegolow_zwraca_klientow(db, client, login, make_user, make_order,
                                             make_product):
    """Okno partii dostaje z backendu listę klientów z ich obecnym `incl_only_quantity`."""
    from modules.products.models import ProxyOrder, ProxyOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=2), incl=1)

    proxy = ProxyOrder(order_number='PRX/T99', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    db.session.add(ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    ))
    db.session.commit()

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/get-proxy-orders-details',
                      json={'proxy_order_ids': [proxy.id]})

    assert odp.status_code == 200
    dane = odp.get_json()
    assert dane['success'] is True
    klienci = dane['orders'][0]['items'][0]['clients']
    assert klienci == [{
        'order_id': a.id,
        'order_number': a.order_number,
        'client_name': klienci[0]['client_name'],
        'quantity': 2,
        'incl_only_quantity': 1,
    }]
```

- [ ] **Step 6: Uruchom test — ma paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py::test_endpoint_szczegolow_zwraca_klientow -v`
Expected: FAIL — `KeyError: 'clients'`

- [ ] **Step 7: Dorzuć `clients` do endpointu**

W `modules/products/routes.py`, w `get_proxy_orders_details`, przed pętlą po `proxy_orders` dodaj licznik przesunięć, a w pętli po pozycjach — wyliczenie klientów:

```python
        orders_data = []
        # Ile sztuk danego produktu zajęły już wcześniejsze pozycje w TYM oknie —
        # bez tego dwie pozycje z tym samym produktem wskazałyby te same sztuki.
        offsety = {}
        for order in proxy_orders:
            items_data = []
            for item in order.items:
                primary_image = item.product.primary_image
                image_url = url_for('static', filename=f'uploads/products/compressed/{primary_image.filename}') if primary_image else url_for('static', filename='img/product-placeholder.svg')

                pid = item.product_id
                offset = offsety.get(pid, 0)
                klienci = []
                for order_id, ilosc in _preview_batch_allocation(pid, item.quantity, offset):
                    from modules.orders.models import Order as ZamowienieKlienta
                    zam = db.session.get(ZamowienieKlienta, order_id)
                    if not zam:
                        continue
                    _, incl = _order_product_quantities(zam, pid)
                    klienci.append({
                        'order_id': zam.id,
                        'order_number': zam.order_number,
                        'client_name': (zam.user.full_name if zam.user else '—'),
                        'quantity': ilosc,
                        'incl_only_quantity': min(incl, ilosc),
                    })
                offsety[pid] = offset + (item.quantity or 0)

                items_data.append({
                    'id': item.id,
                    'product': {
                        'id': item.product.id,
                        'name': item.product.name,
                        'image_url': image_url
                    },
                    'quantity': item.quantity,
                    'unit_price': float(item.unit_price) if item.unit_price else 0,
                    'total_price': float(item.total_price) if item.total_price else 0,
                    'clients': klienci,
                })
```

Import `Order` przenieś na górę funkcji (`from modules.orders.models import Order as ZamowienieKlienta`), żeby nie robić go w pętli.

`User.full_name` to property (`modules/auth/models.py:532`) — jest dostępne bez dodatkowych zapytań.

- [ ] **Step 8: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -v`
Expected: wszystkie PASS

- [ ] **Step 9: Commit**

```bash
git add modules/products/routes.py tests/test_wysylka_album_vs_incl.py
git commit -m "feat(wysylka): podglad przydzialu klientow w oknie partii"
```

---

### Task 4: Zapis stawek i wyboru album/incl przy tworzeniu partii

**Files:**
- Modify: `modules/products/routes.py:4188-4330` (`create_poland_order`)
- Modify: `modules/products/routes.py` (nowy helper `_zapisz_incl_na_zamowieniu`)
- Test: `tests/test_wysylka_album_vs_incl.py`

**Interfaces:**
- Consumes: `_order_product_quantities` (Task 2).
- Produces:
  - `_zapisz_incl_na_zamowieniu(order_id, product_id, incl_qty) -> None`.
  - `create_poland_order` przyjmuje w każdej pozycji `items[]` opcjonalne `album_rate`, `incl_rate` oraz `clients: [{order_id, incl_only_quantity}]`.

- [ ] **Step 1: Napisz testy zapisu**

Dopisz do `tests/test_wysylka_album_vs_incl.py`:

```python
def _proxy_z_pozycja(db, product_id, qty, numer='PRX/T50'):
    from modules.products.models import ProxyOrder, ProxyOrderItem
    proxy = ProxyOrder(order_number=numer, order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    poz = ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=product_id, quantity=qty,
        unit_price=Decimal('100'), total_price=Decimal('100') * qty,
    )
    db.session.add(poz)
    db.session.commit()
    return proxy, poz


def test_tworzenie_partii_zapisuje_stawki_i_incl(db, client, login, make_user,
                                                 make_order, make_product):
    """Okno partii przysyła stawki i rozbicie klientów — obie rzeczy lądują w bazie,
    a klient z incl płaci mniej."""
    from modules.orders.models import Order, OrderItem
    from modules.products.models import PolandOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=3))
    b = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=2))
    proxy, poz = _proxy_z_pozycja(db, produkt.id, qty=2)

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/create-poland-order', json={
        'proxy_order_ids': [proxy.id],
        'shipping_cost_total': 57,
        'tracking_number': 'KB88900-RS1',
        'payment_deadline': (baza + timedelta(days=7)).isoformat(),
        'note': '',
        'items': [{
            'proxy_order_item_id': poz.id,
            'shipping_cost': 57,
            'album_rate': 45,
            'incl_rate': 12,
            'clients': [
                {'order_id': a.id, 'incl_only_quantity': 0},
                {'order_id': b.id, 'incl_only_quantity': 1},
            ],
        }],
    })

    assert odp.status_code == 200, odp.get_json()
    assert odp.get_json()['success'] is True

    pozycja_partii = PolandOrderItem.query.filter_by(product_id=produkt.id).one()
    assert pozycja_partii.shipping_cost_album_per_unit == Decimal('45.00')
    assert pozycja_partii.shipping_cost_incl_per_unit == Decimal('12.00')
    assert pozycja_partii.shipping_cost == Decimal('57.00')

    assert OrderItem.query.filter_by(order_id=b.id).one().incl_only_quantity == 1
    assert db.session.get(Order, a.id).proxy_shipping_cost == Decimal('45.00')
    assert db.session.get(Order, b.id).proxy_shipping_cost == Decimal('12.00')


def test_tworzenie_partii_bez_stawek_dziala_jak_dotad(db, client, login, make_user,
                                                      make_order, make_product):
    """Brak `album_rate`/`incl_rate` w payloadzie = stara ścieżka, stawki zostają NULL."""
    from modules.orders.models import Order
    from modules.products.models import PolandOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                            baza - timedelta(days=3))
    proxy, poz = _proxy_z_pozycja(db, produkt.id, qty=2, numer='PRX/T51')

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/create-poland-order', json={
        'proxy_order_ids': [proxy.id],
        'shipping_cost_total': 100,
        'tracking_number': 'KB88900-RS2',
        'payment_deadline': (baza + timedelta(days=7)).isoformat(),
        'note': '',
        'items': [{'proxy_order_item_id': poz.id, 'shipping_cost': 100}],
    })

    assert odp.get_json()['success'] is True
    pozycja_partii = PolandOrderItem.query.filter_by(product_id=produkt.id).one()
    assert pozycja_partii.shipping_cost_album_per_unit is None
    assert db.session.get(Order, a.id).proxy_shipping_cost == Decimal('100.00')


def test_odrzuca_incl_wieksze_niz_ilosc(db, client, login, make_user, make_order,
                                        make_product):
    """Ochrona przed rozjechanymi kwotami: incl nie może przekroczyć sztuk klienta."""
    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 1,
                            baza - timedelta(days=3))
    proxy, poz = _proxy_z_pozycja(db, produkt.id, qty=1, numer='PRX/T52')

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/create-poland-order', json={
        'proxy_order_ids': [proxy.id],
        'shipping_cost_total': 12,
        'tracking_number': 'KB88900-RS3',
        'payment_deadline': (baza + timedelta(days=7)).isoformat(),
        'note': '',
        'items': [{
            'proxy_order_item_id': poz.id,
            'shipping_cost': 12,
            'album_rate': 45,
            'incl_rate': 12,
            'clients': [{'order_id': a.id, 'incl_only_quantity': 5}],
        }],
    })

    assert odp.status_code == 400
    assert 'incl' in odp.get_json()['error'].lower()
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -k tworzenie_partii -v`
Expected: FAIL — stawki zostają `None`, `proxy_shipping_cost` po 28.50 zamiast 45/12

- [ ] **Step 3: Dodaj helper zapisujący incl na pozycjach zamówienia**

W `modules/products/routes.py`, pod `_order_product_quantities`:

```python
def _zapisz_incl_na_zamowieniu(order_id, product_id, incl_qty):
    """Rozkłada `incl_qty` sztuk „samo incl" na pozycje zamówienia z danym produktem.

    Jedno zamówienie może mieć ten sam produkt w kilku pozycjach (np. różne sety),
    a okno partii operuje na sumie — rozdzielamy zachłannie po kolei, przycinając
    do ilości efektywnej każdej pozycji.

    Podnosi ValueError, gdy `incl_qty` przekracza sumę sztuk klienta.
    """
    from modules.orders.models import Order

    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f'Nie znaleziono zamówienia {order_id}')

    if incl_qty < 0:
        raise ValueError('Liczba sztuk „samo incl" nie może być ujemna')

    dostepne = 0
    pozycje = []
    for item in order.items:
        if item.product_id != product_id:
            continue
        efektywna = _client_item_qty(item)
        if efektywna <= 0:
            continue
        dostepne += efektywna
        pozycje.append((item, efektywna))

    if incl_qty > dostepne:
        raise ValueError(
            f'Zamówienie {order.order_number}: „samo incl" = {incl_qty}, '
            f'a klient ma tylko {dostepne} szt. tego produktu'
        )

    zostalo = incl_qty
    for item, efektywna in pozycje:
        przypisane = min(zostalo, efektywna)
        item.incl_only_quantity = przypisane
        zostalo -= przypisane
```

- [ ] **Step 4: Wczytaj stawki i rozbicie klientów w `create_poland_order`**

W `modules/products/routes.py`, w pętli `for item_data in items_data:` (zaczyna się na linii 4237), zaraz po `shipping_cost = Decimal(str(item_data.get('shipping_cost', 0)))` i po pobraniu `proxy_item`, wstaw:

```python
            raw_album = item_data.get('album_rate')
            raw_incl = item_data.get('incl_rate')
            stawki_podane = raw_album is not None and raw_incl is not None

            album_rate = incl_rate = None
            if stawki_podane:
                album_rate = Decimal(str(raw_album))
                incl_rate = Decimal(str(raw_incl))
                if album_rate < 0 or incl_rate < 0:
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': 'Stawki wysyłki nie mogą być ujemne.'
                    }), 400

            # Zapis wyboru album/incl na zamówieniach klientów MUSI się wykonać przed
            # dystrybucją kosztów — _distribute_proxy_shipping_to_client_orders czyta
            # incl_only_quantity prosto z pozycji zamówienia.
            incl_lacznie = 0
            for wpis in item_data.get('clients') or []:
                try:
                    incl_klienta = int(wpis.get('incl_only_quantity') or 0)
                    _zapisz_incl_na_zamowieniu(
                        wpis.get('order_id'), proxy_item.product_id, incl_klienta)
                except ValueError as blad:
                    db.session.rollback()
                    return jsonify({'success': False, 'error': str(blad)}), 400
                incl_lacznie += incl_klienta

            if stawki_podane:
                album_lacznie = (proxy_item.quantity or 0) - incl_lacznie
                if album_lacznie < 0:
                    db.session.rollback()
                    return jsonify({
                        'success': False,
                        'error': ('Suma sztuk „samo incl" przekracza ilość w partii '
                                  f'produktu {proxy_item.product_id}.')
                    }), 400
                # Suma linijki liczona po stronie serwera — front pokazuje ją tylko poglądowo.
                shipping_cost = (album_rate * album_lacznie
                                 + incl_rate * incl_lacznie).quantize(Decimal('0.01'))
```

- [ ] **Step 5: Zapisz stawki na pozycji partii**

W tej samej pętli, w konstruktorze `PolandOrderItem` (linia ~4256), dopisz dwa pola:

```python
                shipping_cost=shipping_cost,
                shipping_cost_album_per_unit=album_rate,
                shipping_cost_incl_per_unit=incl_rate,
                selected_size=proxy_item.selected_size,
```

- [ ] **Step 6: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -v`
Expected: wszystkie PASS

- [ ] **Step 7: Sprawdź regresję**

Run: `python -m pytest tests/test_proxy_shipping_distribution.py tests/test_poland_order_item_allocation.py tests/test_cost_notifications_bulk.py -v`
Expected: wszystkie PASS

- [ ] **Step 8: Commit**

```bash
git add modules/products/routes.py tests/test_wysylka_album_vs_incl.py
git commit -m "feat(wysylka): zapis stawek album/incl i wyboru klientow przy tworzeniu partii"
```

---

### Task 5: Okno „Zamówienie do Polski" — lista klientów i dwie stawki

**Files:**
- Modify: `static/js/pages/admin/stock-orders.js:176-269` (`renderPolandModal`)
- Modify: `static/js/pages/admin/stock-orders.js:596-690` (walidacja i payload wysyłki formularza)
- Modify: `static/css/pages/admin/stock-orders.css` (style listy klientów i wiersza stawek)

**Interfaces:**
- Consumes: pole `clients` z `/admin/products/api/get-proxy-orders-details` (Task 3); kontrakt `items[].album_rate` / `incl_rate` / `clients` w `/admin/products/api/create-poland-order` (Task 4).
- Produces: `polandOrderData.items[i].clients` — tablica `{order_id, order_number, client_name, quantity, incl_only_quantity}`; funkcje globalne `handleInclQtyChange(itemIndex, clientIndex)` i `handleRateChange(itemIndex)`.

- [ ] **Step 1: Zapamiętaj klientów w stanie modala**

W `static/js/pages/admin/stock-orders.js`, w `renderPolandModal`, w miejscu `polandOrderData.items.push({...})` (linia ~218) dopisz pole:

```javascript
            polandOrderData.items.push({
                proxy_order_item_id: item.id,
                product_id: item.product.id,
                product_name: item.product.name,
                quantity: item.quantity,
                shipping_cost: 0,
                order_index: orderIndex,
                clients: (item.clients || []).map(c => ({
                    order_id: c.order_id,
                    order_number: c.order_number,
                    client_name: c.client_name,
                    quantity: c.quantity,
                    incl_only_quantity: c.incl_only_quantity || 0
                }))
            });
```

- [ ] **Step 2: Wyrenderuj listę klientów i wiersz stawek pod każdym produktem**

W `renderPolandModal`, zaraz po zamknięciu wiersza produktu (`html += '</tr>';`, linia ~254), dodaj drugi wiersz rozpięty na całą szerokość tabeli:

```javascript
            const klienci = polandOrderData.items[globalItemIndex].clients;
            if (klienci.length) {
                html += `<tr class="poland-incl-row"><td colspan="4">`;
                html += `<div class="poland-incl-clients">`;
                klienci.forEach((k, clientIndex) => {
                    html += `<div class="poland-incl-client">`;
                    html += `<span class="poland-incl-client-name">${escapeHtml(k.client_name)}</span>`;
                    html += `<span class="poland-incl-client-order">${escapeHtml(k.order_number)}</span>`;
                    html += `<span class="poland-incl-client-qty">${k.quantity} szt</span>`;
                    html += `<label class="poland-incl-label">samo incl:`;
                    html += `<input type="number" class="form-input poland-incl-input" `;
                    html += `data-item-index="${globalItemIndex}" data-client-index="${clientIndex}" `;
                    html += `value="${k.incl_only_quantity}" min="0" max="${k.quantity}" step="1" `;
                    html += `oninput="handleInclQtyChange(${globalItemIndex}, ${clientIndex})">`;
                    html += `<span class="poland-incl-of">z ${k.quantity}</span>`;
                    html += `</label>`;
                    html += `</div>`;
                });
                html += `</div>`;

                html += `<div class="poland-rates" data-item-index="${globalItemIndex}">`;
                html += `<div class="poland-rate-line">`;
                html += `<span class="poland-rate-label">cały album</span>`;
                html += `<span class="poland-rate-qty" data-role="album-qty">0 szt</span>`;
                html += `<span class="poland-rate-times">×</span>`;
                html += `<input type="number" class="form-input poland-rate-input" `;
                html += `data-item-index="${globalItemIndex}" data-role="album-rate" `;
                html += `placeholder="0,00" step="0.01" min="0" `;
                html += `oninput="handleRateChange(${globalItemIndex})">`;
                html += `<span class="poland-rate-sum" data-role="album-sum">0,00 zł</span>`;
                html += `</div>`;
                html += `<div class="poland-rate-line">`;
                html += `<span class="poland-rate-label">samo incl</span>`;
                html += `<span class="poland-rate-qty" data-role="incl-qty">0 szt</span>`;
                html += `<span class="poland-rate-times">×</span>`;
                html += `<input type="number" class="form-input poland-rate-input" `;
                html += `data-item-index="${globalItemIndex}" data-role="incl-rate" `;
                html += `placeholder="0,00" step="0.01" min="0" `;
                html += `oninput="handleRateChange(${globalItemIndex})">`;
                html += `<span class="poland-rate-sum" data-role="incl-sum">0,00 zł</span>`;
                html += `</div>`;
                html += `</div>`;
                html += `</td></tr>`;
            }
```

- [ ] **Step 3: Dodaj obsługę zmian ilości incl i stawek**

Dopisz na końcu `static/js/pages/admin/stock-orders.js` (obok pozostałych handlerów modala):

```javascript
/**
 * Zlicza sztuki album/incl dla pozycji i odświeża wiersz stawek.
 * Gdy nikt nie bierze incl, wiersz stawek chowamy — okno wygląda jak wcześniej.
 */
function refreshRatesRow(itemIndex) {
    const item = polandOrderData.items[itemIndex];
    const box = document.querySelector(`.poland-rates[data-item-index="${itemIndex}"]`);
    if (!item || !box) return;

    const inclQty = item.clients.reduce((s, c) => s + (c.incl_only_quantity || 0), 0);
    const albumQty = (item.quantity || 0) - inclQty;

    box.style.display = inclQty > 0 ? '' : 'none';
    box.querySelector('[data-role="album-qty"]').textContent = `${albumQty} szt`;
    box.querySelector('[data-role="incl-qty"]').textContent = `${inclQty} szt`;

    const albumInput = box.querySelector('[data-role="album-rate"]');
    const inclInput = box.querySelector('[data-role="incl-rate"]');
    const albumRate = parseFloat(albumInput.value) || 0;

    // Podpowiedź stawki incl: reszta z wartości linijki po opłaceniu albumów.
    const wartosc = parseFloat(
        document.querySelector(`.shipping-value-input[data-item-index="${itemIndex}"]`)?.value) || 0;
    const reszta = wartosc - albumRate * albumQty;
    const podpowiedz = inclQty > 0 && reszta > 0 ? (reszta / inclQty) : 0;
    inclInput.placeholder = podpowiedz > 0 ? podpowiedz.toFixed(2).replace('.', ',') : '0,00';

    const inclRate = parseFloat(inclInput.value) || podpowiedz;
    box.querySelector('[data-role="album-sum"]').textContent =
        (albumRate * albumQty).toFixed(2).replace('.', ',') + ' zł';
    box.querySelector('[data-role="incl-sum"]').textContent =
        (inclRate * inclQty).toFixed(2).replace('.', ',') + ' zł';
}

function handleInclQtyChange(itemIndex, clientIndex) {
    const item = polandOrderData.items[itemIndex];
    const input = document.querySelector(
        `.poland-incl-input[data-item-index="${itemIndex}"][data-client-index="${clientIndex}"]`);
    if (!item || !input) return;

    const klient = item.clients[clientIndex];
    let wartosc = parseInt(input.value, 10);
    if (isNaN(wartosc) || wartosc < 0) wartosc = 0;
    if (wartosc > klient.quantity) wartosc = klient.quantity;
    input.value = wartosc;
    klient.incl_only_quantity = wartosc;

    refreshRatesRow(itemIndex);
}

function handleRateChange(itemIndex) {
    refreshRatesRow(itemIndex);
}

window.handleInclQtyChange = handleInclQtyChange;
window.handleRateChange = handleRateChange;
```

Na końcu `renderPolandModal`, tuż przed zamknięciem funkcji, odśwież wszystkie wiersze stawek (żeby zaczynały schowane):

```javascript
    polandOrderData.items.forEach((_, idx) => refreshRatesRow(idx));
```

- [ ] **Step 4: Odśwież wiersz stawek przy zmianie wartości linijki**

W `handleShippingValueChange` (linia ~475) i `handleShippingPriceChange` (linia ~450), na końcu każdej z funkcji dopisz:

```javascript
    refreshRatesRow(itemIndex);
```

- [ ] **Step 5: Dołóż stawki i klientów do payloadu**

W budowaniu `itemsPayload` (linia ~657) zamień zwracany obiekt na:

```javascript
    const itemsPayload = polandOrderData.items.map((item, idx) => {
        const input = document.querySelector(`.shipping-value-input[data-item-index="${idx}"]`);
        const shippingCost = input ? (parseFloat(input.value) || 0) : 0;

        const inclQty = item.clients.reduce((s, c) => s + (c.incl_only_quantity || 0), 0);
        const payload = {
            proxy_order_item_id: item.proxy_order_item_id,
            shipping_cost: shippingCost,
            clients: item.clients.map(c => ({
                order_id: c.order_id,
                incl_only_quantity: c.incl_only_quantity || 0
            }))
        };

        // Stawki wysyłamy tylko wtedy, gdy ktokolwiek bierze samo incl — inaczej
        // backend idzie starą ścieżką (jedna kwota dzielona po równo).
        if (inclQty > 0) {
            const box = document.querySelector(`.poland-rates[data-item-index="${idx}"]`);
            const albumInput = box.querySelector('[data-role="album-rate"]');
            const inclInput = box.querySelector('[data-role="incl-rate"]');
            payload.album_rate = parseFloat(albumInput.value) || 0;
            payload.incl_rate = parseFloat(inclInput.value)
                || parseFloat((inclInput.placeholder || '0').replace(',', '.'))
                || 0;
        }
        return payload;
    });
```

- [ ] **Step 5b: Ostrzeżenie, gdy pozycja klienta rozjeżdża się między partie**

Decyzja właścicielki z 2026-08-31: sztuki jednego klienta dla jednego produktu w praktyce
nie przyjeżdżają w dwóch partiach, więc „samo incl" zostaje **jedną liczbą na pozycję
zamówienia**, a nie liczbą per partia. Na wypadek, gdyby taki przypadek jednak wystąpił,
admin ma to zobaczyć — inaczej wpisałby liczbę myśląc, że dotyczy tylko tej partii, a
zapisze się jako całość zamówienia.

W `modules/products/routes.py`, w `get_proxy_orders_details`, do słownika klienta dołóż
pole z łączną ilością sztuk tego produktu w całym zamówieniu:

```python
                    ilosc_calego_zamowienia, incl = _order_product_quantities(zam, pid)
                    klienci.append({
                        'order_id': zam.id,
                        'order_number': zam.order_number,
                        'client_name': (zam.user.full_name if zam.user else '—'),
                        'quantity': ilosc,
                        'order_total_quantity': ilosc_calego_zamowienia,
                        'incl_only_quantity': min(incl, ilosc),
                    })
```

(Zastępuje to dotychczasowe `_, incl = _order_product_quantities(zam, pid)` — ta sama
funkcja, tylko wykorzystana jest też pierwsza zwracana wartość.)

W `renderPolandModal`, przy renderowaniu wiersza klienta, po `poland-incl-client-qty`
dodaj ostrzeżenie widoczne tylko wtedy, gdy klient ma w tym zamówieniu więcej sztuk, niż
przypada na tę partię:

```javascript
                    if (k.order_total_quantity > k.quantity) {
                        html += `<span class="poland-incl-warning" title="Reszta sztuk tego klienta jest w innej partii. Liczba „samo incl” dotyczy całego zamówienia (${k.order_total_quantity} szt.), nie tylko tej partii.">⚠ ${k.quantity} z ${k.order_total_quantity} szt. w tej partii</span>`;
                    }
```

Pole `clients[].order_total_quantity` dopisz też do stanu modala w Kroku 1
(`polandOrderData.items[].clients`), obok pozostałych pól:

```javascript
                    order_total_quantity: c.order_total_quantity,
```

Test do dopisania w `tests/test_wysylka_album_vs_incl.py`:

```python
def test_endpoint_podaje_laczna_ilosc_zamowienia(db, client, login, make_user,
                                                 make_order, make_product):
    """Gdy część sztuk klienta jest w innej partii, endpoint podaje obie liczby —
    ile przypada na tę partię i ile klient ma w całym zamówieniu."""
    from modules.products.models import ProxyOrder, ProxyOrderItem

    produkt = make_product()
    baza = datetime(2026, 8, 1, 10, 0)
    a = _zamowienie_klienta(db, make_user, make_order, produkt.id, 3,
                            baza - timedelta(days=3))

    proxy = ProxyOrder(order_number='PRX/T77', order_type='proxy')
    db.session.add(proxy)
    db.session.flush()
    db.session.add(ProxyOrderItem(
        proxy_order_id=proxy.id, product_id=produkt.id, quantity=2,
        unit_price=Decimal('100'), total_price=Decimal('200'),
    ))
    db.session.commit()

    login(make_user(role='admin'))
    odp = client.post('/admin/products/api/get-proxy-orders-details',
                      json={'proxy_order_ids': [proxy.id]})

    klient_json = odp.get_json()['orders'][0]['items'][0]['clients'][0]
    assert klient_json['order_id'] == a.id
    assert klient_json['quantity'] == 2
    assert klient_json['order_total_quantity'] == 3
```

Styl ostrzeżenia dopisz razem z pozostałymi w Kroku 7:

```css
.poland-incl-warning {
    font-size: 12px;
    color: #b45309;
    cursor: help;
}

[data-theme="dark"] .poland-incl-warning { color: #fbbf24; }
```

- [ ] **Step 6: Dodaj walidację stawek przed wysłaniem**

W bloku walidacji, zaraz po pętli sprawdzającej `shipping-value-input` (linia ~617), dopisz:

```javascript
    let stawkiOk = true;
    polandOrderData.items.forEach((item, idx) => {
        const inclQty = item.clients.reduce((s, c) => s + (c.incl_only_quantity || 0), 0);
        if (inclQty === 0) return;
        const box = document.querySelector(`.poland-rates[data-item-index="${idx}"]`);
        const albumInput = box.querySelector('[data-role="album-rate"]');
        const albumQty = (item.quantity || 0) - inclQty;
        const raw = (albumInput.value || '').trim();
        if (albumQty > 0 && (raw === '' || isNaN(parseFloat(raw)) || parseFloat(raw) < 0)) {
            stawkiOk = false;
            albumInput.classList.add('input-error');
        } else {
            albumInput.classList.remove('input-error');
        }
    });

    if (!stawkiOk) {
        errors.push('Wpisz stawkę za cały album w produktach, gdzie ktoś bierze samo incl');
    }
```

- [ ] **Step 7: Dodaj style (jasny i ciemny motyw)**

Style okna partii mieszkają w `static/css/pages/admin/stock-orders.css` razem z pozostałymi regułami `.poland-*` (93 wystąpienia) — dopisz tam, obok nich, a nie w `static/css/components/modals.css`. Ciemny motyw w tym projekcie to selektor `[data-theme="dark"]`.

Na końcu sekcji `.poland-*` w `static/css/pages/admin/stock-orders.css`:

```css
/* Lista klientów i stawki album/incl w oknie „Zamówienie do Polski" */
.poland-incl-row td { padding-top: 0; }

.poland-incl-clients {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 0 10px 0;
}

.poland-incl-client {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 13px;
    color: #374151;
}

.poland-incl-client-name { font-weight: 600; }
.poland-incl-client-order { color: #6b7280; }
.poland-incl-client-qty { color: #6b7280; }

.poland-incl-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
}

.poland-incl-input {
    width: 64px;
    min-height: 44px;
    text-align: center;
}

.poland-incl-of { color: #6b7280; }

.poland-rates {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 0 4px 0;
    border-top: 1px solid #e5e7eb;
}

.poland-rate-line {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    color: #374151;
}

.poland-rate-label { min-width: 90px; }
.poland-rate-qty { min-width: 56px; color: #6b7280; }
.poland-rate-input { width: 100px; min-height: 44px; }
.poland-rate-sum { margin-left: auto; font-weight: 600; }

[data-theme="dark"] .poland-incl-client,
[data-theme="dark"] .poland-rate-line { color: #d1d5db; }

[data-theme="dark"] .poland-incl-client-order,
[data-theme="dark"] .poland-incl-client-qty,
[data-theme="dark"] .poland-incl-of,
[data-theme="dark"] .poland-rate-qty { color: #9ca3af; }

[data-theme="dark"] .poland-rates { border-top-color: #374151; }
```

- [ ] **Step 8: Sprawdź składnię JS**

Run: `node --check static/js/pages/admin/stock-orders.js`
Expected: brak wyjścia (składnia poprawna)

- [ ] **Step 9: Commit**

```bash
git add static/js/pages/admin/stock-orders.js static/css/pages/admin/stock-orders.css
git commit -m "feat(wysylka): lista klientow i stawki album/incl w oknie partii"
```

---

### Task 6: Plakietka „SAMO INCL" u admina, u klienta i w API mobilnym

**Files:**
- Modify: `templates/admin/orders/detail.html:64` oraz `:161` i `:251` (nazwa produktu w pozycji)
- Modify: `templates/client/orders/detail.html:170` (nazwa produktu w pozycji)
- Modify: `modules/api_mobile/orders_routes.py:124-140` (`_serialize_order_item`)
- Modify: `static/css/pages/client/order-detail.css:345` (obok `.od-product-row__badge--full-set`)
- Modify: `static/css/pages/admin/order-detail.css:4559` (obok `.size-badge`)
- Test: `tests/test_wysylka_album_vs_incl.py`

**Interfaces:**
- Consumes: `OrderItem.incl_only_quantity` (Task 1).
- Produces: `_serialize_order_item` zwraca dodatkowy klucz `incl_only_quantity` (int).

Plakietka jest **tylko do odczytu** — również u admina. Wybór album/incl zaznacza się w oknie partii; edycja w szczegółach zamówienia nic by nie przeliczyła (nie ma ścieżki ponownego naliczenia kosztów istniejącej partii — patrz Global Constraints), więc byłaby myląca.

- [ ] **Step 1: Napisz testy**

Dopisz do `tests/test_wysylka_album_vs_incl.py`:

```python
def test_api_mobilne_zwraca_incl_only_quantity(db, make_user, make_order, make_product):
    """Apka dostaje to samo pole co web, żeby pokazać tę samą plakietkę."""
    from modules.api_mobile.orders_routes import _serialize_order_item
    from modules.orders.models import OrderItem

    produkt = make_product()
    zam = _zamowienie_klienta(db, make_user, make_order, produkt.id, 2,
                              datetime(2026, 8, 1, 10, 0), incl=1)
    pozycja = OrderItem.query.filter_by(order_id=zam.id).one()

    assert _serialize_order_item(pozycja)['incl_only_quantity'] == 1


def test_plakietka_samo_incl_w_panelu_klienta(db, client, login, make_user,
                                              make_order, make_product):
    """Plakietka pokazuje się przy pozycji z incl i znika przy zerze.

    Idziemy przez trasę `/client/orders/<id>` (`modules/orders/routes.py:1800`), a nie
    przez `render_template` — widok podaje szablonowi kilkanaście zmiennych i ręczne
    renderowanie rozjeżdżałoby się przy każdej ich zmianie.
    """
    from modules.orders.models import OrderItem

    produkt = make_product(name='Album Testowy')
    wlasciciel = make_user()
    zam = make_order(wlasciciel, offer_page_id=1, created_at=datetime(2026, 8, 1, 10, 0))
    pozycja = OrderItem(
        order_id=zam.id, product_id=produkt.id, quantity=2,
        price=Decimal('130'), total=Decimal('260'), incl_only_quantity=1,
    )
    db.session.add(pozycja)
    db.session.commit()

    login(wlasciciel)
    odp = client.get(f'/client/orders/{zam.id}')
    assert odp.status_code == 200
    assert 'SAMO INCL' in odp.get_data(as_text=True)

    pozycja.incl_only_quantity = 0
    db.session.commit()
    odp = client.get(f'/client/orders/{zam.id}')
    assert 'SAMO INCL' not in odp.get_data(as_text=True)
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -k "mobilne or plakietka" -v`
Expected: FAIL — `KeyError: 'incl_only_quantity'` oraz brak tekstu „SAMO INCL"

- [ ] **Step 3: Dodaj pole do serializacji mobilnej**

W `modules/api_mobile/orders_routes.py`, w `_serialize_order_item`, pod `'selected_size': item.selected_size,`:

```python
        'incl_only_quantity': item.incl_only_quantity or 0,
```

- [ ] **Step 4: Dodaj plakietkę w panelu klienta**

W `templates/client/orders/detail.html:170`, wewnątrz `<span class="od-product-row__name">`, zaraz za blokiem `size-badge`, wstaw:

```jinja
{% if item.incl_only_quantity %}<span class="od-product-row__badge od-product-row__badge--incl">SAMO INCL{% if item.incl_only_quantity < item.quantity %} {{ item.incl_only_quantity }}/{{ item.quantity }}{% endif %}</span>{% endif %}
```

- [ ] **Step 5: Dodaj plakietkę w szczegółach zamówienia u admina**

W `templates/admin/orders/detail.html` w trzech miejscach, gdzie renderowana jest nazwa produktu — linie 64, 161 i 251 — zaraz za blokiem `size-badge` wstaw ten sam fragment:

```jinja
{% if item.incl_only_quantity %}<span class="size-badge size-badge--incl">SAMO INCL{% if item.incl_only_quantity < item.quantity %} {{ item.incl_only_quantity }}/{{ item.quantity }}{% endif %}</span>{% endif %}
```

- [ ] **Step 6: Dodaj styl plakietki**

W `static/css/pages/client/order-detail.css`, zaraz za `.od-product-row__badge--bonus` (linia 354) i jego wariantem ciemnym (linia 359):

```css
/* Plakietka „SAMO INCL" — klient bierze z albumu tylko inclusions */
.od-product-row__badge--incl {
    background: #ede9fe;
    color: #5b21b6;
}

[data-theme="dark"] .od-product-row__badge--incl {
    background: #3c2a63;
    color: #ddd6fe;
}
```

W `static/css/pages/admin/order-detail.css`, zaraz za `[data-theme="dark"] .size-badge` (linia 4571):

```css
/* Plakietka „SAMO INCL" — klient bierze z albumu tylko inclusions */
.size-badge--incl {
    background: #ede9fe;
    color: #5b21b6;
}

[data-theme="dark"] .size-badge--incl {
    background: #3c2a63;
    color: #ddd6fe;
}
```

- [ ] **Step 7: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_wysylka_album_vs_incl.py -v`
Expected: wszystkie PASS

- [ ] **Step 8: Uruchom pełny zestaw testów**

Run: `python -m pytest -q`
Expected: brak nowych porażek względem stanu sprzed zmian

- [ ] **Step 9: Commit**

```bash
git add templates/client/orders/detail.html templates/admin/orders/detail.html static/css/pages/client/order-detail.css static/css/pages/admin/order-detail.css modules/api_mobile/orders_routes.py tests/test_wysylka_album_vs_incl.py
git commit -m "feat(wysylka): plakietka SAMO INCL u klienta, admina i w API mobilnym"
```

---

## Po wykonaniu wszystkich zadań

- [ ] Uruchom pełny zestaw: `python -m pytest -q`
- [ ] Zaktualizuj spec (`docs/superpowers/specs/2026-08-31-wysylka-album-vs-incl-design.md`): sekcja „Edycja już utworzonej partii" przenosi się do „Poza zakresem" (decyzja Karoliny: partie dla tych exclusive dopiero powstaną), a plakietka u admina jest tylko do odczytu.
- [ ] Zgłoś Karolinie gotowość do przeklikania w przeglądarce — okna partii nie da się zweryfikować bez zalogowania do panelu, więc ten krok zostaje po jej stronie.
- [ ] **Nie pushować.** Push i merge do `main` wykonuje Karolina po swojej akceptacji.
