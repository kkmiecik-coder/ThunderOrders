# Podział partii Polska — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin może wydzielić zaznaczone pozycje partii Polska do nowej partii, bez zmiany kwot u klientów i bez wysyłki powiadomień.

**Architecture:** Dwa endpointy JSON w `modules/products/routes.py` (podgląd + wykonanie podziału) plus okno w zakładce Polska. Podział przenosi całe `PolandOrderItem` do nowej `PolandOrder`, która dostaje własnego `ProxyOrder` (rodzica) i dziedziczy po oryginale status, `created_at` oraz oba terminy płatności. Żadna funkcja przeliczająca koszty klientów ani wysyłająca powiadomienia nie jest wywoływana.

**Tech Stack:** Flask + SQLAlchemy (MariaDB na produkcji, SQLite w testach), Jinja2, waniliowy JS, pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-podzial-partii-polska-design.md`
**ClickUp:** https://app.clickup.com/t/869ezbu3c

## Global Constraints

- Gałąź robocza: `feat/podzial-partii-polska`. Nigdy nie pracujemy na `main`, nie pushujemy bez zgody właścicielki.
- Komunikaty widoczne dla użytkownika: po polsku, pełne zdania z polskimi znakami.
- Komentarze i nazwy nowych funkcji pomocniczych: po polsku, zgodnie z konwencją nowszego kodu w `modules/products/routes.py`.
- Wiadomości commitów: konwencjonalne, po polsku, bez polskich znaków (jak w historii repo).
- Testy uruchamiamy `python -m pytest` (nie samo `pytest`).
- CSS zawsze w dwóch wariantach: jasny i ciemny (`[data-theme="dark"] .selektor`). Style okien wyłącznie w `static/css/components/modals.css`.
- Endpointy podziału: `@login_required` + `@role_required('admin')`.
- Kwoty w bazie to `Numeric(10, 2)` — po stronie Pythona zawsze `Decimal`, nigdy `float`.
- Zakaz wywoływania z kodu podziału: `_distribute_proxy_shipping_to_client_orders`, `_distribute_customs_vat_to_client_orders`, `_update_client_orders_on_polska_ordered`, `_notify_distributed_costs`.

---

### Task 1: Wspólny przelicznik sum partii

Wzór na `total_amount` partii żyje dziś wewnątrz endpointu Cła/VAT. Podział potrzebuje tego samego wzoru, więc najpierw wyciągamy go do funkcji pomocniczej i podmieniamy istniejące użycie.

**Files:**
- Modify: `modules/products/routes.py` (nowa funkcja przed `_allocate_product_shipping_fifo`, czyli przed linią 4020; podmiana użycia w `update_poland_customs_vat`, linie 4812–4823)
- Test: `tests/test_poland_order_split.py` (nowy plik)

**Interfaces:**
- Consumes: nic
- Produces: `_przelicz_sumy_partii(poland_order) -> Decimal` — ustawia `poland_order.total_amount` na `wartość zakupu pozycji + shipping_cost + customs_cost` i zwraca samą wartość zakupu pozycji (`Decimal`). Nie robi `commit`.

- [ ] **Step 1: Napisz test, który ma nie przejść**

Utwórz `tests/test_poland_order_split.py`:

```python
"""Testy podziału partii Polska — wydzielenie pozycji do nowej partii.

Projekt: docs/superpowers/specs/2026-09-09-podzial-partii-polska-design.md
"""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _strona_sprzedazy(strona_sprzedazy):
    """Zamówienia w tym pliku powstają z `offer_page_id=1`, a to kolumna FK — strona
    o tym id musi realnie istnieć (fixture `strona_sprzedazy` w conftest)."""


def test_przelicz_sumy_partii_sumuje_zakup_wysylke_i_clo(db, make_product):
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem
    from modules.products.routes import _przelicz_sumy_partii

    produkt = make_product(purchase_price_pln=Decimal('25.00'))

    proxy = ProxyOrder(order_number='PRX/S1', order_type='polska')
    db.session.add(proxy)
    db.session.flush()
    proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=produkt.id,
                                quantity=4, unit_price=Decimal('25'), total_price=Decimal('100'))
    db.session.add(proxy_item)
    db.session.flush()

    partia = PolandOrder(order_number='PL/S1', proxy_order_id=proxy.id, status='zamowione',
                         shipping_cost=Decimal('30.00'), customs_cost=Decimal('12.00'))
    db.session.add(partia)
    db.session.flush()
    db.session.add(PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                   product_id=produkt.id, quantity=4))
    db.session.commit()

    wartosc_produktow = _przelicz_sumy_partii(partia)

    assert wartosc_produktow == Decimal('100.00')
    assert partia.total_amount == Decimal('142.00')
```

- [ ] **Step 2: Uruchom test i sprawdź, że nie przechodzi**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: FAIL — `ImportError: cannot import name '_przelicz_sumy_partii'`

- [ ] **Step 3: Dodaj funkcję pomocniczą**

W `modules/products/routes.py`, bezpośrednio przed `def _allocate_product_shipping_fifo(product_id):`:

```python
def _przelicz_sumy_partii(poland_order):
    """Ustawia `total_amount` partii: wartość zakupu pozycji + wysyłka + cło.

    Zwraca samą wartość zakupu pozycji — endpoint Cła/VAT raportuje ją w odpowiedzi.
    Nie commituje; wołający decyduje, kiedy zamknąć transakcję.
    """
    from decimal import Decimal

    wartosc_produktow = Decimal('0')
    for item in poland_order.items:
        product = item.product
        cena = (Decimal(str(product.purchase_price_pln or product.purchase_price or 0))
                if product else Decimal('0'))
        wartosc_produktow += cena * item.quantity

    poland_order.total_amount = (
        wartosc_produktow
        + Decimal(str(poland_order.shipping_cost or 0))
        + Decimal(str(poland_order.customs_cost or 0))
    )
    return wartosc_produktow
```

- [ ] **Step 4: Uruchom test i sprawdź, że przechodzi**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: PASS

- [ ] **Step 5: Podmień istniejące użycie w endpoincie Cła/VAT**

W `update_poland_customs_vat` zastąp blok liczący sumy (linie 4812–4823) tym:

```python
            total_customs = Decimal('0')
            for item in poland_order.items:
                total_customs += item.customs_vat_amount or Decimal('0')

            poland_order.customs_cost = total_customs
            total_product_value = _przelicz_sumy_partii(poland_order)
```

Reszta bloku (`poland_order.customs_payment_deadline = ...` oraz `updated_orders.append({...})`) zostaje bez zmian — `total_product_value` i `poland_order.total_amount` mają te same wartości co przed refaktorem.

- [ ] **Step 6: Sprawdź, że testy Cła/VAT dalej przechodzą**

Run: `python -m pytest tests/test_customs_vat_zero.py tests/test_poland_order_split.py -v`
Expected: PASS — wszystkie

- [ ] **Step 7: Commit**

```bash
git add modules/products/routes.py tests/test_poland_order_split.py
git commit -m "refactor(polska): wspolny przelicznik sum partii"
```

---

### Task 2: Endpoint podglądu do okna podziału

**Files:**
- Modify: `modules/products/routes.py` (nowy endpoint po `delete_poland_order`, czyli po linii 3737)
- Test: `tests/test_poland_order_split.py`

**Interfaces:**
- Consumes: `_przelicz_sumy_partii` (Task 1) — nie wprost, ale ten sam wzór ceny zakupu
- Produces: `GET /admin/products/api/poland-orders/<int:id>/split-preview` zwracający
  `{'success': True, 'numer': str, 'status': str, 'shipping_cost': float, 'customs_cost': float,
  'pozycje': [{'id': int, 'nazwa': str, 'rozmiar': str|None, 'ilosc': int, 'wartosc_zakupu': float}]}`

- [ ] **Step 1: Dodaj do pliku testowego wspólny budowniczy partii**

Dopisz w `tests/test_poland_order_split.py` (pod fixture `_strona_sprzedazy`):

```python
def _zbuduj_partie(db, produkty_i_ilosci, numer='PL/S9', created_at=None,
                   shipping=Decimal('0'), customs=Decimal('0'), status='zamowione',
                   order_type='polska', stawka_za_szt=None):
    """Partia Polska z własnym rodzicem: ProxyOrder + ProxyOrderItem + PolandOrder + PolandOrderItem.

    produkty_i_ilosci: lista (product_id, ilość).
    stawka_za_szt: gdy podana, każda pozycja dostaje shipping_cost = stawka * ilość
                   oraz obie stawki za sztukę (album/incl) równe tej stawce.
    Zwraca (partia, [pozycje]).
    """
    from modules.products.models import ProxyOrder, ProxyOrderItem, PolandOrder, PolandOrderItem

    proxy = ProxyOrder(order_number=f'PRX/{numer.replace("/", "-")}', order_type=order_type)
    db.session.add(proxy)
    db.session.flush()

    partia = PolandOrder(order_number=numer, proxy_order_id=proxy.id, status=status,
                         shipping_cost=shipping, customs_cost=customs)
    if created_at is not None:
        partia.created_at = created_at
    db.session.add(partia)
    db.session.flush()

    pozycje = []
    for product_id, ilosc in produkty_i_ilosci:
        proxy_item = ProxyOrderItem(proxy_order_id=proxy.id, product_id=product_id,
                                    quantity=ilosc, unit_price=Decimal('25'),
                                    total_price=Decimal('25') * ilosc)
        db.session.add(proxy_item)
        db.session.flush()
        pozycja = PolandOrderItem(poland_order_id=partia.id, proxy_order_item_id=proxy_item.id,
                                  product_id=product_id, quantity=ilosc)
        if stawka_za_szt is not None:
            pozycja.shipping_cost = Decimal(str(stawka_za_szt)) * ilosc
            pozycja.shipping_cost_album_per_unit = Decimal(str(stawka_za_szt))
            pozycja.shipping_cost_incl_per_unit = Decimal(str(stawka_za_szt))
        db.session.add(pozycja)
        db.session.flush()
        pozycje.append(pozycja)

    db.session.commit()
    return partia, pozycje
```

- [ ] **Step 2: Napisz test, który ma nie przejść**

```python
def test_podglad_podzialu_zwraca_pozycje_i_kwoty(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-split@example.com')
    login(admin)

    p1 = make_product(name='Album A', purchase_price_pln=Decimal('25.00'))
    p2 = make_product(name='Poca B', purchase_price_pln=Decimal('10.00'))
    partia, _ = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S2',
                               shipping=Decimal('80.00'), customs=Decimal('20.00'))

    odpowiedz = client.get(f'/admin/products/api/poland-orders/{partia.id}/split-preview')

    assert odpowiedz.status_code == 200
    dane = odpowiedz.get_json()
    assert dane['success'] is True
    assert dane['numer'] == 'PL/S2'
    assert dane['shipping_cost'] == 80.0
    assert dane['customs_cost'] == 20.0
    assert [p['nazwa'] for p in dane['pozycje']] == ['Album A', 'Poca B']
    assert [p['ilosc'] for p in dane['pozycje']] == [4, 6]
    assert [p['wartosc_zakupu'] for p in dane['pozycje']] == [100.0, 60.0]
```

- [ ] **Step 3: Uruchom test i sprawdź, że nie przechodzi**

Run: `python -m pytest tests/test_poland_order_split.py::test_podglad_podzialu_zwraca_pozycje_i_kwoty -v`
Expected: FAIL — status 404 (endpoint nie istnieje)

- [ ] **Step 4: Dodaj endpoint**

W `modules/products/routes.py`, po funkcji `delete_poland_order` (po linii 3737):

```python
@products_bp.route('/api/poland-orders/<int:id>/split-preview', methods=['GET'])
@login_required
@role_required('admin')
def poland_order_split_preview(id):
    """Dane do okna podziału partii: pozycje z ilościami i bieżące kwoty ewidencyjne."""
    from decimal import Decimal
    from sqlalchemy.orm import joinedload

    partia = PolandOrder.query.get_or_404(id)
    items = (
        PolandOrderItem.query
        .options(joinedload(PolandOrderItem.product))
        .filter_by(poland_order_id=partia.id)
        .order_by(PolandOrderItem.id)
        .all()
    )

    pozycje = []
    for item in items:
        product = item.product
        cena = (Decimal(str(product.purchase_price_pln or product.purchase_price or 0))
                if product else Decimal('0'))
        pozycje.append({
            'id': item.id,
            'nazwa': product.name if product else '(produkt usunięty)',
            'rozmiar': item.selected_size,
            'ilosc': item.quantity,
            'wartosc_zakupu': float(cena * item.quantity),
        })

    return jsonify({
        'success': True,
        'numer': partia.order_number,
        'status': partia.status,
        'shipping_cost': float(partia.shipping_cost or 0),
        'customs_cost': float(partia.customs_cost or 0),
        'pozycje': pozycje,
    })
```

- [ ] **Step 5: Uruchom test i sprawdź, że przechodzi**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: PASS — oba testy

- [ ] **Step 6: Commit**

```bash
git add modules/products/routes.py tests/test_poland_order_split.py
git commit -m "feat(polska): endpoint podgladu podzialu partii"
```

---

### Task 3: Endpoint podziału — ścieżka szczęśliwa

**Files:**
- Modify: `modules/products/routes.py` (funkcja pomocnicza + endpoint zaraz po `poland_order_split_preview`)
- Test: `tests/test_poland_order_split.py`

**Interfaces:**
- Consumes: `_przelicz_sumy_partii` (Task 1), `generate_proxy_order_number()`, `generate_poland_order_number()`, `generate_proxy_to_poland_number()`
- Produces: `POST /admin/products/api/poland-orders/<int:id>/split`, body
  `{'item_ids': [int], 'shipping_cost_stara': str, 'shipping_cost_nowa': str,
  'customs_cost_stara': str, 'customs_cost_nowa': str}`,
  odpowiedź `{'success': True, 'nowy_numer': str, 'nowa_partia_id': int, 'message': str}`.
  Dodatkowo `_kwota_z_okna(surowa, nazwa_pola) -> Decimal` podnoszące `ValueError` z polskim komunikatem.

- [ ] **Step 1: Napisz testy, które mają nie przejść**

```python
def test_podzial_przenosi_zaznaczone_pozycje(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem

    admin = make_user(role='admin', email='admin-split2@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    p3 = make_product(purchase_price_pln=Decimal('5.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6), (p3.id, 2)], numer='PL/S3',
                                     shipping=Decimal('100.00'), customs=Decimal('40.00'))
    id_partii = partia.id
    id_do_wydzielenia = [pozycje[1].id, pozycje[2].id]

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': id_do_wydzielenia,
        'shipping_cost_stara': '60.00',
        'shipping_cost_nowa': '40.00',
        'customs_cost_stara': '25.00',
        'customs_cost_nowa': '15.00',
    })

    assert odpowiedz.status_code == 200
    dane = odpowiedz.get_json()
    assert dane['success'] is True

    stara = db.session.get(PolandOrder, id_partii)
    nowa = db.session.get(PolandOrder, dane['nowa_partia_id'])

    assert {i.id for i in stara.items} == {pozycje[0].id}
    assert {i.id for i in nowa.items} == set(id_do_wydzielenia)
    assert nowa.order_number == dane['nowy_numer']
    assert nowa.order_number.startswith('PL/')
    assert nowa.proxy_order_id != stara.proxy_order_id


def test_podzial_dziedziczy_status_date_i_terminy(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-split3@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    data_zalozenia = datetime(2026, 7, 11, 18, 55, 0)
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S4',
                                     created_at=data_zalozenia, status='urzad_celny')
    partia.payment_deadline = datetime(2026, 7, 20, 23, 59, 0)
    partia.customs_payment_deadline = datetime(2026, 7, 25, 23, 59, 0)
    partia.tracking_number = 'ABC123'
    partia.notes = 'notatka oryginalu'
    db.session.commit()

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '0', 'shipping_cost_nowa': '0',
        'customs_cost_stara': '0', 'customs_cost_nowa': '0',
    })

    nowa = db.session.get(PolandOrder, odpowiedz.get_json()['nowa_partia_id'])
    assert nowa.status == 'urzad_celny'
    assert nowa.created_at == data_zalozenia
    assert nowa.payment_deadline == datetime(2026, 7, 20, 23, 59, 0)
    assert nowa.customs_payment_deadline == datetime(2026, 7, 25, 23, 59, 0)
    assert not nowa.tracking_number
    assert not nowa.notes
    assert nowa.is_archived is False


def test_podzial_zapisuje_kwoty_i_przelicza_sumy(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-split4@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/S5',
                                     shipping=Decimal('100.00'), customs=Decimal('40.00'))
    id_partii = partia.id

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '70.00',
        'shipping_cost_nowa': '30.00',
        'customs_cost_stara': '25.00',
        'customs_cost_nowa': '15.00',
    })

    stara = db.session.get(PolandOrder, id_partii)
    nowa = db.session.get(PolandOrder, odpowiedz.get_json()['nowa_partia_id'])

    assert stara.shipping_cost == Decimal('70.00')
    assert nowa.shipping_cost == Decimal('30.00')
    assert stara.customs_cost == Decimal('25.00')
    assert nowa.customs_cost == Decimal('15.00')
    # stara: 4 x 25 = 100 zakupu + 70 + 25;  nowa: 6 x 10 = 60 zakupu + 30 + 15
    assert stara.total_amount == Decimal('195.00')
    assert nowa.total_amount == Decimal('105.00')
```

- [ ] **Step 2: Uruchom testy i sprawdź, że nie przechodzą**

Run: `python -m pytest tests/test_poland_order_split.py -v -k podzial`
Expected: FAIL — wszystkie trzy, status 404

- [ ] **Step 3: Dodaj parser kwot**

W `modules/products/routes.py`, bezpośrednio przed endpointem podglądu z Taska 2:

```python
def _kwota_z_okna(surowa, nazwa_pola):
    """Kwota z formularza → Decimal(2 miejsca). Podnosi ValueError z polskim komunikatem."""
    from decimal import Decimal, InvalidOperation

    if surowa in (None, ''):
        return Decimal('0.00')
    try:
        wartosc = Decimal(str(surowa))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'Nieprawidłowa kwota: {nazwa_pola}.')
    if wartosc < 0:
        raise ValueError(f'Nieprawidłowa kwota: {nazwa_pola}.')
    return wartosc.quantize(Decimal('0.01'))
```

- [ ] **Step 4: Dodaj endpoint podziału**

Zaraz po `poland_order_split_preview`:

```python
@products_bp.route('/api/poland-orders/<int:id>/split', methods=['POST'])
@login_required
@role_required('admin')
def split_poland_order(id):
    """Wydziela wskazane pozycje partii do nowej partii z własnym rodzicem (ProxyOrder).

    Świadomie NIE woła przeliczników kosztów klientów ani powiadomień: stawki za
    sztukę, kwoty cła i przypisania sztuk (PolandOrderItemOrder) jadą razem z
    pozycją, więc u klientów nic się nie zmienia.
    """
    from decimal import Decimal

    try:
        partia = PolandOrder.query.get_or_404(id)

        data = request.get_json() or {}
        item_ids = data.get('item_ids') or []

        wszystkie = list(partia.items)
        id_w_partii = {it.id for it in wszystkie}
        zaznaczone_id = {int(i) for i in item_ids}

        wysylka_stara = _kwota_z_okna(data.get('shipping_cost_stara'), 'wysyłka starej partii')
        wysylka_nowa = _kwota_z_okna(data.get('shipping_cost_nowa'), 'wysyłka nowej partii')
        clo_stare = _kwota_z_okna(data.get('customs_cost_stara'), 'cło starej partii')
        clo_nowe = _kwota_z_okna(data.get('customs_cost_nowa'), 'cło nowej partii')

        rodzic = partia.proxy_order
        nowy_rodzic = ProxyOrder(
            order_number=generate_proxy_order_number(),
            order_type=rodzic.order_type,
            supplier_id=rodzic.supplier_id,
            status=rodzic.status,
            currency=rodzic.currency,
            notes=f'Wydzielone z {rodzic.order_number} przy podziale partii {partia.order_number}',
        )
        db.session.add(nowy_rodzic)
        db.session.flush()

        nowy_numer = (generate_proxy_to_poland_number()
                      if partia.order_number.startswith('PRX/PL/')
                      else generate_poland_order_number())

        nowa_partia = PolandOrder(
            order_number=nowy_numer,
            proxy_order_id=nowy_rodzic.id,
            status=partia.status,
            payment_deadline=partia.payment_deadline,
            customs_payment_deadline=partia.customs_payment_deadline,
            shipping_cost=wysylka_nowa,
            customs_cost=clo_nowe,
        )
        # Kolejka FIFO (_allocate_product_shipping_fifo) idzie po created_at — nowa
        # partia MUSI stanąć w miejscu oryginału, inaczej najbliższe przeliczenie
        # przetasuje sztuki między partiami i zmieni klientom kwoty.
        nowa_partia.created_at = partia.created_at
        db.session.add(nowa_partia)
        db.session.flush()

        przeniesione = []
        for item in wszystkie:
            if item.id not in zaznaczone_id:
                continue
            proxy_item = item.proxy_order_item
            if proxy_item is not None:
                proxy_item.proxy_order_id = nowy_rodzic.id
            item.poland_order_id = nowa_partia.id
            przeniesione.append({
                'poland_order_item_id': item.id,
                'product_id': item.product_id,
                'quantity': item.quantity,
            })

        partia.shipping_cost = wysylka_stara
        partia.customs_cost = clo_stare

        db.session.flush()
        db.session.refresh(partia)
        db.session.refresh(nowa_partia)

        _przelicz_sumy_partii(partia)
        _przelicz_sumy_partii(nowa_partia)

        # Sumy na rodzicach — ten sam układ co przy zakładaniu partii:
        # zadeklarowana = suma pozycji, total = kwota wpisana dla przesyłki.
        for rodzic_partii, partia_rodzica in ((rodzic, partia), (nowy_rodzic, nowa_partia)):
            zadeklarowana = sum(
                (Decimal(str(it.shipping_cost or 0)) for it in partia_rodzica.items),
                Decimal('0'),
            )
            faktyczna = Decimal(str(partia_rodzica.shipping_cost or 0))
            rodzic_partii.shipping_cost_declared = zadeklarowana
            rodzic_partii.shipping_cost_total = faktyczna
            rodzic_partii.shipping_cost_difference = faktyczna - zadeklarowana

        db.session.commit()

        log_activity(
            user=current_user,
            action='poland_order_split',
            entity_type='poland_order',
            entity_id=partia.id,
            old_value={'order_number': partia.order_number,
                       'shipping_cost': float(wysylka_stara),
                       'customs_cost': float(clo_stare)},
            new_value={'order_number': nowa_partia.order_number,
                       'poland_order_id': nowa_partia.id,
                       'shipping_cost': float(wysylka_nowa),
                       'customs_cost': float(clo_nowe),
                       'pozycje': przeniesione},
        )

        return jsonify({
            'success': True,
            'nowy_numer': nowa_partia.order_number,
            'nowa_partia_id': nowa_partia.id,
            'message': (f'Utworzono partię {nowa_partia.order_number} z {len(przeniesione)} '
                        f'pozycjami wydzielonymi z {partia.order_number}'),
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error splitting Poland order: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
```

- [ ] **Step 5: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: PASS — wszystkie

- [ ] **Step 6: Commit**

```bash
git add modules/products/routes.py tests/test_poland_order_split.py
git commit -m "feat(polska): podzial partii na dwie — sciezka szczesliwa"
```

---

### Task 4: Walidacje i uprawnienia

**Files:**
- Modify: `modules/products/routes.py` (`split_poland_order` z Taska 3)
- Test: `tests/test_poland_order_split.py`

**Interfaces:**
- Consumes: `split_poland_order` (Task 3)
- Produces: kody odpowiedzi 400/409/403 z komunikatami z tabeli w specyfikacji

- [ ] **Step 1: Napisz testy, które mają nie przejść**

```python
@pytest.mark.parametrize('ladunek, kod, fragment', [
    ({'item_ids': []}, 400, 'przynajmniej jedną pozycję'),
    ({'item_ids': 'wszystkie'}, 400, 'Nieprawidłowa lista pozycji'),
])
def test_podzial_odrzuca_bledne_zaznaczenie(db, client, login, make_user, make_product,
                                            ladunek, kod, fragment):
    admin = make_user(role='admin', email=f'admin-w-{kod}-{fragment[:5]}@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, _ = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W1')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json=ladunek)

    assert odpowiedz.status_code == kod
    assert fragment in odpowiedz.get_json()['error']


def test_podzial_nie_pozwala_wydzielic_wszystkiego(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-w2@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W2')
    id_partii = partia.id

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_partii}/split', json={
        'item_ids': [p.id for p in pozycje],
    })

    assert odpowiedz.status_code == 400
    assert 'musi zostać przynajmniej jedna pozycja' in odpowiedz.get_json()['error']
    assert len(list(db.session.get(PolandOrder, id_partii).items)) == 2
    assert PolandOrder.query.count() == 1


def test_podzial_odrzuca_obca_pozycje(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder

    admin = make_user(role='admin', email='admin-w3@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W3')
    obca, obce_pozycje = _zbuduj_partie(db, [(p1.id, 1)], numer='PL/W3B')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id, obce_pozycje[0].id],
    })

    assert odpowiedz.status_code == 409
    assert 'nie są już w tej partii' in odpowiedz.get_json()['error']
    assert PolandOrder.query.count() == 2


def test_podzial_odrzuca_partie_anulowana(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-w4@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W4',
                                     status='anulowane')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
    })

    assert odpowiedz.status_code == 400
    assert 'anulowanej partii' in odpowiedz.get_json()['error']


def test_podzial_odrzuca_ujemna_kwote(db, client, login, make_user, make_product):
    admin = make_user(role='admin', email='admin-w5@example.com')
    login(admin)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer='PL/W5')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
        'shipping_cost_nowa': '-5',
    })

    assert odpowiedz.status_code == 400
    assert 'Nieprawidłowa kwota' in odpowiedz.get_json()['error']


@pytest.mark.parametrize('rola', ['mod', 'client'])
def test_podzial_tylko_dla_admina(db, client, login, make_user, make_product, rola):
    from modules.products.models import PolandOrder

    uzytkownik = make_user(role=rola, email=f'{rola}-split@example.com')
    login(uzytkownik)
    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 4), (p2.id, 6)], numer=f'PL/W6{rola}')

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[0].id],
    })

    assert odpowiedz.status_code in (302, 403)
    assert PolandOrder.query.count() == 1
```

- [ ] **Step 2: Uruchom testy i sprawdź, które nie przechodzą**

Run: `python -m pytest tests/test_poland_order_split.py -v -k "odrzuca or wszystkiego or admina"`
Expected: FAIL — walidacje zwracają 500 zamiast 400/409 (wyjątek łapie ogólny `except`)

- [ ] **Step 3: Dodaj walidacje w `split_poland_order`**

Wstaw bezpośrednio po `partia = PolandOrder.query.get_or_404(id)`:

```python
        if partia.status == 'anulowane':
            return jsonify({'success': False,
                            'error': 'Nie można dzielić anulowanej partii.'}), 400
```

Zastąp blok od `item_ids = data.get('item_ids') or []` do linii z `zaznaczone_id = {int(i) for i in item_ids}`:

```python
        item_ids = data.get('item_ids') or []
        if not item_ids:
            return jsonify({'success': False,
                            'error': 'Zaznacz przynajmniej jedną pozycję do wydzielenia.'}), 400

        wszystkie = list(partia.items)
        id_w_partii = {it.id for it in wszystkie}
        try:
            zaznaczone_id = {int(i) for i in item_ids}
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Nieprawidłowa lista pozycji.'}), 400

        if not zaznaczone_id <= id_w_partii:
            return jsonify({'success': False,
                            'error': 'Te pozycje nie są już w tej partii — odśwież stronę.'}), 409

        if zaznaczone_id == id_w_partii:
            return jsonify({'success': False,
                            'error': 'W partii musi zostać przynajmniej jedna pozycja.'}), 400
```

Owiń parsowanie kwot:

```python
        try:
            wysylka_stara = _kwota_z_okna(data.get('shipping_cost_stara'), 'wysyłka starej partii')
            wysylka_nowa = _kwota_z_okna(data.get('shipping_cost_nowa'), 'wysyłka nowej partii')
            clo_stare = _kwota_z_okna(data.get('customs_cost_stara'), 'cło starej partii')
            clo_nowe = _kwota_z_okna(data.get('customs_cost_nowa'), 'cło nowej partii')
        except ValueError as blad:
            return jsonify({'success': False, 'error': str(blad)}), 400
```

Uwaga: `item_ids: 'wszystkie'` (napis) przechodzi przez `if not item_ids`, a rozbija się dopiero na `int(i)` — dlatego `try/except` wokół konwersji jest konieczny, nie ozdobny.

- [ ] **Step 4: Uruchom cały plik testowy**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: PASS — wszystkie

- [ ] **Step 5: Commit**

```bash
git add modules/products/routes.py tests/test_poland_order_split.py
git commit -m "feat(polska): walidacje i uprawnienia podzialu partii"
```

---

### Task 5: Testy gwarancji — pieniądze, powiadomienia, kolejka, terminy

Sedno projektu: dowód, że podział jest dla klientów niewidoczny. Same testy, bez zmian w kodzie produkcyjnym — jeśli któryś nie przejdzie, wraca się do Taska 3.

**Files:**
- Test: `tests/test_poland_order_split.py`

**Interfaces:**
- Consumes: endpoint z Tasków 3–4, `_zbuduj_partie` (Task 2), `_distribute_proxy_shipping_to_client_orders`, `get_products_to_order`, `delete_poland_order`

- [ ] **Step 1: Dopisz budowniczego zamówienia klienta**

```python
def _zamowienie_klienta(db, make_user, make_order, product_id, ilosc, created_at, cena=130):
    """Zamówienie klienta z jedną pozycją (exclusive — offer_page_id ustawione)."""
    from modules.orders.models import OrderItem

    uzytkownik = make_user()
    zamowienie = make_order(uzytkownik, offer_page_id=1, created_at=created_at)
    db.session.add(OrderItem(order_id=zamowienie.id, product_id=product_id, quantity=ilosc,
                             price=Decimal(str(cena)), total=Decimal(str(cena)) * ilosc))
    db.session.commit()
    return zamowienie
```

- [ ] **Step 2: Napisz test kwot u klientów i braku powiadomień**

```python
def test_podzial_nie_zmienia_kwot_klientow_i_nie_wysyla_powiadomien(
        db, client, login, make_user, make_order, make_product, monkeypatch):
    from modules.orders.models import Order
    from modules.products import routes as trasy

    admin = make_user(role='admin', email='admin-g1@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    baza = datetime(2026, 6, 1, 10, 0, 0)
    z1 = _zamowienie_klienta(db, make_user, make_order, p1.id, 2, baza)
    z2 = _zamowienie_klienta(db, make_user, make_order, p2.id, 3, baza + timedelta(minutes=1))

    partia, pozycje = _zbuduj_partie(db, [(p1.id, 2), (p2.id, 3)], numer='PL/G1',
                                     created_at=baza, shipping=Decimal('100.00'),
                                     stawka_za_szt=Decimal('20.00'))

    trasy._distribute_proxy_shipping_to_client_orders({p1.id: Decimal('40'), p2.id: Decimal('60')})
    db.session.commit()

    przed = {z1.id: db.session.get(Order, z1.id).proxy_shipping_cost,
             z2.id: db.session.get(Order, z2.id).proxy_shipping_cost}
    assert przed[z1.id] > 0 and przed[z2.id] > 0

    wyslane = []
    monkeypatch.setattr(trasy, '_notify_distributed_costs',
                        lambda *a, **k: wyslane.append(a))

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '40.00', 'shipping_cost_nowa': '60.00',
        'customs_cost_stara': '0', 'customs_cost_nowa': '0',
    })
    assert odpowiedz.status_code == 200

    po = {z1.id: db.session.get(Order, z1.id).proxy_shipping_cost,
          z2.id: db.session.get(Order, z2.id).proxy_shipping_cost}
    assert po == przed
    assert wyslane == []
```

- [ ] **Step 3: Napisz test kolejki FIFO**

```python
def test_podzial_nie_rusza_kolejki_fifo(db, client, login, make_user, make_order, make_product):
    from modules.orders.models import Order
    from modules.products import routes as trasy

    admin = make_user(role='admin', email='admin-g2@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    baza = datetime(2026, 6, 1, 10, 0, 0)
    z1 = _zamowienie_klienta(db, make_user, make_order, p1.id, 2, baza)
    z2 = _zamowienie_klienta(db, make_user, make_order, p2.id, 3, baza + timedelta(minutes=1))

    partia, pozycje = _zbuduj_partie(db, [(p1.id, 2), (p2.id, 3)], numer='PL/G2',
                                     created_at=baza, shipping=Decimal('100.00'),
                                     stawka_za_szt=Decimal('20.00'))
    trasy._distribute_proxy_shipping_to_client_orders({p1.id: Decimal('40'), p2.id: Decimal('60')})
    db.session.commit()
    przed = {z1.id: db.session.get(Order, z1.id).proxy_shipping_cost,
             z2.id: db.session.get(Order, z2.id).proxy_shipping_cost}

    client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
        'shipping_cost_stara': '40.00', 'shipping_cost_nowa': '60.00',
    })

    # Wymuszone przeliczenie PO podziale — to ono ujawniłoby przestawioną kolejkę.
    trasy._distribute_proxy_shipping_to_client_orders({p1.id: Decimal('40'), p2.id: Decimal('60')})
    db.session.commit()

    po = {z1.id: db.session.get(Order, z1.id).proxy_shipping_cost,
          z2.id: db.session.get(Order, z2.id).proxy_shipping_cost}
    assert po == przed
```

- [ ] **Step 4: Napisz test terminów, przypisań i listy „Do zamówienia"**

```python
def test_podzial_zachowuje_terminy_i_przypisania_sztuk(
        db, client, login, make_user, make_order, make_product):
    from modules.orders.models import Order
    from modules.products.models import PolandOrderItemOrder

    admin = make_user(role='admin', email='admin-g3@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    baza = datetime(2026, 6, 1, 10, 0, 0)
    z1 = _zamowienie_klienta(db, make_user, make_order, p1.id, 2, baza)
    z2 = _zamowienie_klienta(db, make_user, make_order, p2.id, 3, baza + timedelta(minutes=1))

    partia, pozycje = _zbuduj_partie(db, [(p1.id, 2), (p2.id, 3)], numer='PL/G3', created_at=baza)
    partia.payment_deadline = datetime(2026, 6, 20, 23, 59, 0)
    partia.customs_payment_deadline = datetime(2026, 6, 25, 23, 59, 0)
    db.session.add(PolandOrderItemOrder(poland_order_item_id=pozycje[0].id, order_id=z1.id, quantity=2))
    db.session.add(PolandOrderItemOrder(poland_order_item_id=pozycje[1].id, order_id=z2.id, quantity=3))
    db.session.commit()

    termin_e2 = db.session.get(Order, z2.id).get_shipping_kr_deadline()
    termin_e3 = db.session.get(Order, z2.id).get_customs_vat_deadline()

    client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
    })

    klient = db.session.get(Order, z2.id)
    assert klient.get_shipping_kr_deadline() == termin_e2
    assert klient.get_customs_vat_deadline() == termin_e3

    przypisania = PolandOrderItemOrder.query.filter_by(order_id=z2.id).all()
    assert len(przypisania) == 1
    assert przypisania[0].poland_order_item_id == pozycje[1].id
    assert przypisania[0].quantity == 3


def test_podzial_nie_zmienia_listy_do_zamowienia(
        db, client, login, make_user, make_order, make_product):
    from modules.products.routes import get_products_to_order

    admin = make_user(role='admin', email='admin-g4@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    baza = datetime(2026, 6, 1, 10, 0, 0)
    _zamowienie_klienta(db, make_user, make_order, p1.id, 4, baza)
    _zamowienie_klienta(db, make_user, make_order, p2.id, 6, baza + timedelta(minutes=1))

    partia, pozycje = _zbuduj_partie(db, [(p1.id, 2), (p2.id, 3)], numer='PL/G4', created_at=baza)
    przed = sorted((w['product'].id, w['to_order']) for w in get_products_to_order())

    client.post(f'/admin/products/api/poland-orders/{partia.id}/split', json={
        'item_ids': [pozycje[1].id],
    })

    po = sorted((w['product'].id, w['to_order']) for w in get_products_to_order())
    assert po == przed
```

- [ ] **Step 5: Napisz test niezależności partii przy usuwaniu**

```python
def test_usuniecie_jednej_partii_nie_rusza_drugiej(db, client, login, make_user, make_product):
    from modules.products.models import PolandOrder, PolandOrderItem

    admin = make_user(role='admin', email='admin-g5@example.com')
    login(admin)

    p1 = make_product(purchase_price_pln=Decimal('25.00'))
    p2 = make_product(purchase_price_pln=Decimal('10.00'))
    partia, pozycje = _zbuduj_partie(db, [(p1.id, 2), (p2.id, 3)], numer='PL/G5')
    id_starej = partia.id
    zostajaca_pozycja = pozycje[0].id

    odpowiedz = client.post(f'/admin/products/api/poland-orders/{id_starej}/split', json={
        'item_ids': [pozycje[1].id],
    })
    id_nowej = odpowiedz.get_json()['nowa_partia_id']

    usuniecie = client.delete(f'/admin/products/poland-orders/{id_nowej}/delete')
    assert usuniecie.status_code == 200

    stara = db.session.get(PolandOrder, id_starej)
    assert stara is not None
    assert {i.id for i in stara.items} == {zostajaca_pozycja}
    assert db.session.get(PolandOrder, id_nowej) is None
    assert PolandOrderItem.query.filter_by(poland_order_id=id_nowej).count() == 0
```

- [ ] **Step 6: Uruchom cały plik**

Run: `python -m pytest tests/test_poland_order_split.py -v`
Expected: PASS — wszystkie

- [ ] **Step 7: Commit**

```bash
git add tests/test_poland_order_split.py
git commit -m "test(polska): gwarancje podzialu — kwoty, maile, kolejka, terminy"
```

---

### Task 6: Przycisk i okno podziału

**Files:**
- Modify: `templates/admin/warehouse/stock_orders.html` (kolumna akcji wiersza Polska, linie 429–439; nowe okno na końcu bloku okien, po `#orderToPolandModal`)
- Modify: `static/css/components/modals.css` (dopisz na końcu pliku)

**Interfaces:**
- Consumes: `openSplitPolandOrderModal(orderId)` i `closeSplitPolandOrderModal()` (Task 7 — na tym etapie jeszcze nie istnieją, przycisk zadziała po Tasku 7)
- Produces: identyfikatory, na których opiera się JS: `#splitPolandOrderModal`, `#splitModalTitle`, `#splitItemsContainer`, `#splitCounter`, `#splitShippingStara`, `#splitShippingNowa`, `#splitCustomsStara`, `#splitCustomsNowa`, `#splitSumaInfo`, `#splitConfirmBtn`

- [ ] **Step 1: Dodaj przycisk w kolumnie akcji**

W `templates/admin/warehouse/stock_orders.html`, wewnątrz `<td>` z przyciskiem usuwania (linie 429–439), **przed** blokiem `{% if current_user.role == 'admin' %}` z koszem:

```html
                                        {% if current_user.role == 'admin' and order.status != 'anulowane' %}
                                        <button class="btn btn-sm btn-secondary" title="Podziel partię" onclick="openSplitPolandOrderModal({{ order.id }})">
                                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                                <circle cx="6" cy="6" r="3"></circle>
                                                <circle cx="6" cy="18" r="3"></circle>
                                                <line x1="20" y1="4" x2="8.12" y2="15.88"></line>
                                                <line x1="14.47" y1="14.48" x2="20" y2="20"></line>
                                                <line x1="8.12" y1="8.12" x2="12" y2="12"></line>
                                            </svg>
                                        </button>
                                        {% endif %}
```

- [ ] **Step 2: Dodaj okno**

Na końcu sekcji okien w tym samym pliku, po zamknięciu `<div id="orderToPolandModal">`:

```html
<!-- Modal: Podział partii -->
<div id="splitPolandOrderModal" class="modal-overlay">
    <div class="modal modal-lg">
        <div class="modal-header">
            <h2 class="modal-title" id="splitModalTitle">Podział partii</h2>
            <button class="modal-close" onclick="closeSplitPolandOrderModal()">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
        <div class="modal-body">
            <p class="split-hint">Zaznacz pozycje, które mają trafić do nowej partii. Kwoty u klientów nie zmienią się i nie pójdą żadne maile.</p>

            <div id="splitCounter" class="split-counter">Zostaje: — · Do wydzielenia: —</div>

            <div id="splitItemsContainer" class="split-items-container">
                <div class="loading-spinner">Ładowanie danych...</div>
            </div>

            <div class="split-costs">
                <div class="split-costs-column">
                    <h3 class="split-costs-title">Zostaje w tej partii</h3>
                    <label for="splitShippingStara">Wysyłka (PLN)</label>
                    <input type="number" id="splitShippingStara" class="form-control" min="0" step="0.01" oninput="splitOznaczRecznaEdycje()">
                    <label for="splitCustomsStara">Cło/VAT (PLN)</label>
                    <input type="number" id="splitCustomsStara" class="form-control" min="0" step="0.01" oninput="splitOznaczRecznaEdycje()">
                </div>
                <div class="split-costs-column">
                    <h3 class="split-costs-title">Nowa partia</h3>
                    <label for="splitShippingNowa">Wysyłka (PLN)</label>
                    <input type="number" id="splitShippingNowa" class="form-control" min="0" step="0.01" oninput="splitOznaczRecznaEdycje()">
                    <label for="splitCustomsNowa">Cło/VAT (PLN)</label>
                    <input type="number" id="splitCustomsNowa" class="form-control" min="0" step="0.01" oninput="splitOznaczRecznaEdycje()">
                </div>
            </div>

            <p class="split-costs-note">Podpowiedź wyliczona po sztukach — wpisz prawdziwe koszty, jeśli je znasz. To Twoja ewidencja, klientom nic się z tego nie nalicza.</p>
            <p id="splitSumaInfo" class="split-suma-info" hidden></p>
        </div>
        <div class="modal-footer">
            <button type="button" class="btn btn-secondary" onclick="closeSplitPolandOrderModal()">Anuluj</button>
            <button type="button" class="btn btn-primary" id="splitConfirmBtn" onclick="submitSplitPolandOrder()" disabled>Podziel</button>
        </div>
    </div>
</div>
```

- [ ] **Step 3: Dodaj style**

Na końcu `static/css/components/modals.css`:

```css
/* ==========================================================================
   Okno podziału partii (zakładka Polska)
   ========================================================================== */

.split-hint {
    margin: 0 0 12px;
    font-size: 13px;
    color: #6b7280;
}

.split-counter {
    padding: 10px 12px;
    margin-bottom: 12px;
    border-radius: 8px;
    background: #f3f4f6;
    font-size: 13px;
    font-weight: 600;
    color: #374151;
}

.split-items-container {
    max-height: 320px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
}

.split-item-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid #f3f4f6;
    min-height: 44px;
}

.split-item-row:last-child {
    border-bottom: none;
}

.split-item-name {
    flex: 1;
    font-size: 13px;
    color: #111827;
}

.split-item-qty {
    font-size: 13px;
    font-weight: 600;
    color: #6b7280;
    white-space: nowrap;
}

.split-costs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-top: 16px;
}

.split-costs-column label {
    display: block;
    margin: 10px 0 4px;
    font-size: 12px;
    color: #6b7280;
}

.split-costs-title {
    margin: 0;
    font-size: 13px;
    font-weight: 700;
    color: #111827;
}

.split-costs-note {
    margin: 12px 0 0;
    font-size: 12px;
    color: #6b7280;
}

.split-suma-info {
    margin: 8px 0 0;
    padding: 8px 10px;
    border-radius: 6px;
    background: #fef3c7;
    font-size: 12px;
    color: #92400e;
}

@media (max-width: 640px) {
    .split-costs {
        grid-template-columns: 1fr;
    }
}

[data-theme="dark"] .split-hint,
[data-theme="dark"] .split-costs-note,
[data-theme="dark"] .split-costs-column label {
    color: #9ca3af;
}

[data-theme="dark"] .split-counter {
    background: #374151;
    color: #e5e7eb;
}

[data-theme="dark"] .split-items-container {
    border-color: #4b5563;
}

[data-theme="dark"] .split-item-row {
    border-bottom-color: #374151;
}

[data-theme="dark"] .split-item-name,
[data-theme="dark"] .split-costs-title {
    color: #f3f4f6;
}

[data-theme="dark"] .split-item-qty {
    color: #9ca3af;
}

[data-theme="dark"] .split-suma-info {
    background: #78350f;
    color: #fde68a;
}
```

- [ ] **Step 4: Sprawdź, że szablon się renderuje**

Run:
```bash
python -c "
from app import create_app
app = create_app('testing')
with app.test_request_context():
    from jinja2 import Environment
    src = app.jinja_env.loader.get_source(app.jinja_env, 'admin/warehouse/stock_orders.html')[0]
    app.jinja_env.parse(src)
    print('szablon OK')
"
```
Expected: `szablon OK` (bez `TemplateSyntaxError`)

- [ ] **Step 5: Commit**

```bash
git add templates/admin/warehouse/stock_orders.html static/css/components/modals.css
git commit -m "feat(polska): przycisk i okno podzialu partii"
```

---

### Task 7: Obsługa okna w JS

**Files:**
- Modify: `static/js/pages/admin/stock-orders.js` (dopisz przed `function deleteOrder(orderId)`, czyli przed linią 1756)

**Interfaces:**
- Consumes: endpointy z Tasków 2–4, `getCsrfToken()` (linia 61), `handleFetchResponse()` (linia 77), `escapeHtml()` (linia ~92), `window.showToast`, identyfikatory z Taska 6
- Produces: `openSplitPolandOrderModal(orderId)`, `closeSplitPolandOrderModal()`, `splitOznaczRecznaEdycje()`, `submitSplitPolandOrder()` — wszystkie globalne, wołane z `onclick` w szablonie

- [ ] **Step 1: Dodaj stan i otwieranie okna**

```javascript
// ============================================
// Podział partii Polska
// ============================================

const splitState = {
    orderId: null,
    numer: '',
    pozycje: [],           // [{id, nazwa, rozmiar, ilosc, wartosc_zakupu}]
    zaznaczone: new Set(), // id pozycji idących do nowej partii
    wysylkaRazem: 0,
    cloRazem: 0,
    recznaEdycja: false,   // po ręcznej zmianie kwoty przestajemy nadpisywać propozycję
};

function openSplitPolandOrderModal(orderId) {
    const modal = document.getElementById('splitPolandOrderModal');
    const container = document.getElementById('splitItemsContainer');

    splitState.orderId = orderId;
    splitState.pozycje = [];
    splitState.zaznaczone = new Set();
    splitState.recznaEdycja = false;

    container.innerHTML = '<div class="loading-spinner">Ładowanie danych...</div>';
    document.getElementById('splitConfirmBtn').disabled = true;
    document.getElementById('splitSumaInfo').hidden = true;
    modal.classList.add('active');

    fetch(`/admin/products/api/poland-orders/${orderId}/split-preview`)
        .then(handleFetchResponse)
        .then(data => {
            if (!data || !data.success) return;
            splitState.numer = data.numer;
            splitState.pozycje = data.pozycje;
            splitState.wysylkaRazem = data.shipping_cost;
            splitState.cloRazem = data.customs_cost;
            document.getElementById('splitModalTitle').textContent = `Podział partii ${data.numer}`;
            renderSplitItems();
            splitPrzeliczPropozycje();
        })
        .catch(error => {
            console.error('Split preview error:', error);
            container.innerHTML = '<div class="split-hint">Nie udało się wczytać pozycji.</div>';
        });
}

function closeSplitPolandOrderModal() {
    const modal = document.getElementById('splitPolandOrderModal');
    if (modal && modal.classList.contains('active')) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active', 'closing');
        }, 200);
    }
}
```

- [ ] **Step 2: Dodaj renderowanie listy i licznik**

```javascript
function renderSplitItems() {
    const container = document.getElementById('splitItemsContainer');
    if (!splitState.pozycje.length) {
        container.innerHTML = '<div class="split-hint">Ta partia nie ma pozycji.</div>';
        return;
    }

    container.innerHTML = splitState.pozycje.map(poz => {
        const rozmiar = poz.rozmiar ? ` (${escapeHtml(poz.rozmiar)})` : '';
        return `
            <label class="split-item-row">
                <input type="checkbox" value="${poz.id}" onchange="splitPrzelacz(${poz.id}, this.checked)">
                <span class="split-item-name">${escapeHtml(poz.nazwa)}${rozmiar}</span>
                <span class="split-item-qty">${poz.ilosc} szt.</span>
            </label>
        `;
    }).join('');
}

function splitPrzelacz(itemId, zaznaczony) {
    if (zaznaczony) {
        splitState.zaznaczone.add(itemId);
    } else {
        splitState.zaznaczone.delete(itemId);
    }
    splitAktualizujLicznik();
    splitPrzeliczPropozycje();
}

function splitAktualizujLicznik() {
    const idzie = splitState.pozycje.filter(p => splitState.zaznaczone.has(p.id));
    const zostaje = splitState.pozycje.filter(p => !splitState.zaznaczone.has(p.id));
    const sztuk = lista => lista.reduce((suma, p) => suma + p.ilosc, 0);

    document.getElementById('splitCounter').textContent =
        `Zostaje w ${splitState.numer}: ${zostaje.length} poz., ${sztuk(zostaje)} szt. · ` +
        `Do nowej partii: ${idzie.length} poz., ${sztuk(idzie)} szt.`;

    // Musi zostać przynajmniej jedna pozycja i przynajmniej jedna musi wyjść.
    document.getElementById('splitConfirmBtn').disabled =
        idzie.length === 0 || zostaje.length === 0;
}
```

- [ ] **Step 3: Dodaj propozycję podziału kwot i ostrzeżenie o sumie**

```javascript
function splitPrzeliczPropozycje() {
    if (splitState.recznaEdycja) {
        splitSprawdzSume();
        return;
    }

    const sztukRazem = splitState.pozycje.reduce((suma, p) => suma + p.ilosc, 0);
    const sztukNowa = splitState.pozycje
        .filter(p => splitState.zaznaczone.has(p.id))
        .reduce((suma, p) => suma + p.ilosc, 0);
    const udzial = sztukRazem > 0 ? sztukNowa / sztukRazem : 0;

    const podziel = (razem) => {
        const nowa = Math.round(razem * udzial * 100) / 100;
        return [Math.round((razem - nowa) * 100) / 100, nowa];
    };

    const [wysylkaStara, wysylkaNowa] = podziel(splitState.wysylkaRazem);
    const [cloStare, cloNowe] = podziel(splitState.cloRazem);

    document.getElementById('splitShippingStara').value = wysylkaStara.toFixed(2);
    document.getElementById('splitShippingNowa').value = wysylkaNowa.toFixed(2);
    document.getElementById('splitCustomsStara').value = cloStare.toFixed(2);
    document.getElementById('splitCustomsNowa').value = cloNowe.toFixed(2);

    splitSprawdzSume();
}

function splitOznaczRecznaEdycje() {
    splitState.recznaEdycja = true;
    splitSprawdzSume();
}

function splitSprawdzSume() {
    const licz = id => parseFloat(document.getElementById(id).value || '0') || 0;
    const info = document.getElementById('splitSumaInfo');

    const wysylkaPo = licz('splitShippingStara') + licz('splitShippingNowa');
    const cloPo = licz('splitCustomsStara') + licz('splitCustomsNowa');

    const komunikaty = [];
    if (Math.abs(wysylkaPo - splitState.wysylkaRazem) >= 0.01) {
        komunikaty.push(`Wysyłka: suma obu partii to ${wysylkaPo.toFixed(2)} zł, przed podziałem było ${splitState.wysylkaRazem.toFixed(2)} zł.`);
    }
    if (Math.abs(cloPo - splitState.cloRazem) >= 0.01) {
        komunikaty.push(`Cło/VAT: suma obu partii to ${cloPo.toFixed(2)} zł, przed podziałem było ${splitState.cloRazem.toFixed(2)} zł.`);
    }

    info.textContent = komunikaty.join(' ');
    info.hidden = komunikaty.length === 0;
}
```

- [ ] **Step 4: Dodaj wysyłkę formularza**

```javascript
function submitSplitPolandOrder() {
    const idzie = splitState.pozycje.filter(p => splitState.zaznaczone.has(p.id));
    if (!idzie.length) return;

    const sztuk = idzie.reduce((suma, p) => suma + p.ilosc, 0);
    const pytanie = `Wydzielić ${idzie.length} poz. (${sztuk} szt.) z ${splitState.numer} do nowej partii?\n\n`
        + 'Kwoty u klientów nie zmienią się i nie pójdą żadne maile.';
    if (!confirm(pytanie)) return;

    const przycisk = document.getElementById('splitConfirmBtn');
    przycisk.disabled = true;

    fetch(`/admin/products/api/poland-orders/${splitState.orderId}/split`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({
            item_ids: idzie.map(p => p.id),
            shipping_cost_stara: document.getElementById('splitShippingStara').value || '0',
            shipping_cost_nowa: document.getElementById('splitShippingNowa').value || '0',
            customs_cost_stara: document.getElementById('splitCustomsStara').value || '0',
            customs_cost_nowa: document.getElementById('splitCustomsNowa').value || '0',
        }),
    })
        .then(response => response.json().then(data => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
            if (ok && data.success) {
                if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
                setTimeout(() => { window.location.reload(); }, 500);
                return;
            }
            przycisk.disabled = false;
            if (typeof window.showToast === 'function') {
                window.showToast(data.error || 'Nie udało się podzielić partii', 'error');
            }
        })
        .catch(error => {
            console.error('Split error:', error);
            przycisk.disabled = false;
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd podczas dzielenia partii', 'error');
            }
        });
}
```

Uwaga: tu **nie** używamy `handleFetchResponse` — on zamienia każdy status 400 na „sesja wygasła" i przeładowuje stronę, przez co komunikaty walidacyjne z Taska 4 (400/409) nigdy by nie dotarły do użytkowniczki.

- [ ] **Step 5: Sprawdź składnię pliku**

Run: `node --check static/js/pages/admin/stock-orders.js`
Expected: brak wyjścia (kod 0)

- [ ] **Step 6: Commit**

```bash
git add static/js/pages/admin/stock-orders.js
git commit -m "feat(polska): obsluga okna podzialu partii"
```

---

### Task 8: Weryfikacja końcowa

**Files:**
- Brak zmian — wyłącznie uruchomienie kontroli

- [ ] **Step 1: Pełna suita testów**

Run: `python -m pytest -q`
Expected: PASS — bez nowych błędów względem stanu sprzed gałęzi

- [ ] **Step 2: Kontrola składni JS i szablonu**

Run:
```bash
node --check static/js/pages/admin/stock-orders.js && python -c "
from app import create_app
app = create_app('testing')
src = app.jinja_env.loader.get_source(app.jinja_env, 'admin/warehouse/stock_orders.html')[0]
app.jinja_env.parse(src)
print('szablon OK')
"
```
Expected: `szablon OK`

- [ ] **Step 3: Sprawdź, że nie wywołujemy zakazanych funkcji**

Run:
```bash
sed -n '/def split_poland_order/,/^@products_bp.route/p' modules/products/routes.py | grep -c "_distribute_\|_notify_distributed_costs\|_update_client_orders_on"
```
Expected: `0`

- [ ] **Step 4: Przegląd ręczny przez właścicielkę**

Weryfikacja ekranów za logowaniem zostaje po stronie Karoliny — bez hasła nie da się przeklikać panelu admina. Do sprawdzenia: wygląd okna w trybie jasnym i ciemnym, działanie licznika, propozycja kwot, komunikat przy niezgodnej sumie.

- [ ] **Step 5: Zapytaj o zgodę na merge do `main` i push**

Push = wdrożenie na produkcję. Nigdy bez wyraźnej zgody, i nie w godzinach szczytu zamówień.
