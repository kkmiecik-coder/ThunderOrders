# Ukrywanie pozycji z ilością 0 w widokach magazynowych — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pozycje zamówienia z ilością 0 (wyzerowane przy domykaniu oferty) przestają być pokazywane w karcie WMS, w sesji kompletacji i w widoku klienta „moje wysyłki".

**Architecture:** Jedna właściwość `Order.shippable_items` w modelu jest jedynym źródłem prawdy o tym, „co realnie jedzie". Trzy widoki przechodzą na nią zamiast na `order.items`. Żaden wiersz w bazie nie jest kasowany ani modyfikowany — zmiana jest wyłącznie prezentacyjna.

**Tech Stack:** Python 3.10+, Flask, SQLAlchemy, Jinja2, pytest. Testy uruchamiane przez `python -m pytest`.

## Global Constraints

- Specyfikacja: `docs/superpowers/specs/2026-09-08-wms-ukrywanie-zerowych-pozycji-design.md`
- Gałąź robocza: `fix/wms-ukrywanie-zerowych-pozycji` (założona od `main`). NIE pushować — właścicielka daje zgodę na każdy push osobno.
- Kryterium filtrowania: `quantity > 0`. NIE filtrujemy po `is_set_fulfilled`.
- `templates/admin/orders/detail.html` pozostaje NIETKNIĘTY — sekcja „poza setem" ma tam zostać widoczna.
- Żadnych zmian w `utils/offer_closure.py`, w sumach, cenach ani w `Order.items_count`.
- Komentarze i docstringi po polsku, zgodnie z konwencją repozytorium.
- Commity: polski conventional commit, stopka `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Testy renderujące szablon przez `client.get(...)` nie wymagają `test_request_context` — kontekst daje sam request testowy.

---

### Task 1: Właściwość `Order.shippable_items`

**Files:**
- Modify: `modules/orders/models.py` (klasa `Order`, tuż za `sorted_items`, linia ~624)
- Test: `tests/test_wms_zerowe_pozycje.py` (nowy plik)

**Interfaces:**
- Produces: `Order.shippable_items` → `list[OrderItem]` — pozycje z `quantity > 0`, w kolejności z `Order.sorted_items`. Zadania 2–4 korzystają wyłącznie z tej nazwy.

- [ ] **Step 1: Napisz test, który ma nie przejść**

Utwórz `tests/test_wms_zerowe_pozycje.py`:

```python
"""Wyzerowane pozycje nie zaśmiecają widoków magazynowych.

Domykanie strony sprzedaży nie kasuje produktu, który nie zmieścił się w
komplecie — zeruje mu ilość, cenę i total (utils/offer_closure.py:190).
Wiersz zostaje, bo klient ma w szczegółach zamówienia widzieć, co przepadło.
Widoki magazynowe pokazywały go jednak na równi z żywym towarem („0x Yunho"),
a licznik produktów liczył wiersze zamiast sztuk — obsługa czytała z karty
więcej rzeczy, niż paczka realnie zawiera.
"""

from decimal import Decimal

import pytest


def _pozycja(db, order, nazwa, ilosc, is_set_fulfilled=None):
    """Pozycja custom — bez Product, bo liczy się tylko ilość i nazwa."""
    from modules.orders.models import OrderItem

    cena = Decimal('10.00') if ilosc else Decimal('0.00')
    item = OrderItem(
        order_id=order.id,
        custom_name=nazwa,
        is_custom=True,
        quantity=ilosc,
        price=cena,
        total=cena * ilosc,
        is_set_fulfilled=is_set_fulfilled,
        fulfilled_quantity=0 if is_set_fulfilled is False else None,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_shippable_items_pomija_wyzerowana_pozycje(db, make_user, make_order):
    order = make_order(user=make_user())
    zywa = _pozycja(db, order, 'Mingi', 1)
    _pozycja(db, order, 'Yunho', 0, is_set_fulfilled=False)

    db.session.expire_all()
    assert [i.id for i in order.shippable_items] == [zywa.id]


def test_shippable_items_zachowuje_kolejnosc_sorted_items(db, make_user, make_order):
    """Zamówienie bez zer wygląda dokładnie tak jak dotąd — ta sama kolejność."""
    order = make_order(user=make_user())
    poza_setem = _pozycja(db, order, 'Poza setem', 2, is_set_fulfilled=False)
    zwykla = _pozycja(db, order, 'Zwykła', 1)
    w_secie = _pozycja(db, order, 'W secie', 3, is_set_fulfilled=True)

    db.session.expire_all()
    # sorted_items: None → True → False
    assert [i.id for i in order.shippable_items] == [zwykla.id, w_secie.id, poza_setem.id]


def test_shippable_items_puste_gdy_same_zera(db, make_user, make_order):
    order = make_order(user=make_user())
    _pozycja(db, order, 'Nic nie weszło', 0, is_set_fulfilled=False)

    db.session.expire_all()
    assert order.shippable_items == []
```

- [ ] **Step 2: Uruchom test i upewnij się, że nie przechodzi**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: FAIL — `AttributeError: 'Order' object has no attribute 'shippable_items'`

- [ ] **Step 3: Dodaj właściwość**

W `modules/orders/models.py`, w klasie `Order`, bezpośrednio po `sorted_items` (kończy się na `return sorted(self.items, key=sort_key)`, linia ~624):

```python
    @property
    def shippable_items(self):
        """Pozycje, które realnie jadą — bez wyzerowanych przy domykaniu oferty.

        Domykanie strony sprzedaży nie kasuje produktu, który nie zmieścił się
        w komplecie: zeruje mu ilość, cenę i total, zostawiając wiersz jako ślad
        (utils/offer_closure.py:190 i :237). Ten sam mechanizm zeruje gratisy
        w zamówieniach, którym nic nie weszło (utils/offer_closure.py:470).
        Dla klienta ten ślad jest potrzebny — w szczegółach zamówienia widzi,
        co zamawiał i co przepadło — ale magazynowi mówi o towarze, którego nie
        ma czego zdjąć z półki.

        Filtrujemy po samej ilości, a nie po `is_set_fulfilled`: jeśli sztuk
        jest zero, nie ma czego pakować, niezależnie od tego, skąd to zero się
        wzięło. Kolejność bierzemy z `sorted_items`, żeby zamówienie bez zer
        wyglądało dokładnie tak jak dotąd.

        Ten sam wzorzec co `ShippingRequest.active_orders`: filtrujemy widok,
        danych w bazie nie ruszamy.
        """
        return [item for item in self.sorted_items if item.quantity > 0]
```

- [ ] **Step 4: Uruchom test i upewnij się, że przechodzi**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: PASS — 3 testy

- [ ] **Step 5: Commit**

```bash
git add modules/orders/models.py tests/test_wms_zerowe_pozycje.py
git commit -m "$(cat <<'MSG'
feat(zamowienia): Order.shippable_items — pozycje, ktore realnie jada

Jedna definicja "co jedzie" dla widokow magazynowych: pozycje z iloscia
wieksza od zera, w kolejnosci z sorted_items. Wyzerowane przy domykaniu
oferty zostaja w bazie nietkniete.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 2: Karta zlecenia w panelu WMS

**Files:**
- Modify: `templates/admin/orders/wms_dashboard.html` (gałąź paczki zbiorczej, linie ~300–352; gałąź zlecenia zwykłego, linie ~369–395)
- Test: `tests/test_wms_zerowe_pozycje.py` (dopisanie testów)

**Interfaces:**
- Consumes: `Order.shippable_items` z Task 1.

- [ ] **Step 1: Napisz testy, które mają nie przejść**

Dopisz na końcu `tests/test_wms_zerowe_pozycje.py`:

```python
def _zlecenie(db, make_user, make_order, ile_zamowien=1, status='czeka_na_wycene'):
    """Zlecenie wysyłki widoczne na /admin/orders/wms (nie zbiorcze, nie anulowane)."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    user = make_user()
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status=status,
    )
    db.session.add(sr)
    db.session.flush()

    zamowienia = []
    for _ in range(ile_zamowien):
        o = make_order(user=user)
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        zamowienia.append(o)
    db.session.commit()
    return sr, zamowienia


def _zaloguj_admina(login, make_user):
    login(make_user(role='admin', email='admin-wms@example.com'))


def test_karta_wms_nie_pokazuje_wyzerowanej_pozycji(
        db, client, login, make_user, make_order):
    sr, (order,) = _zlecenie(db, make_user, make_order)
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert 'Mingi zywy' in html
    assert 'Yunho wyzerowany' not in html


def test_karta_wms_licznik_liczy_tylko_zywe_pozycje(
        db, client, login, make_user, make_order):
    """Dwa wiersze, jeden zerowy → karta ma mowic „1 produkt", nie „2 produkty"."""
    sr, (order,) = _zlecenie(db, make_user, make_order)
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert '1 produkt<' in html
    assert '2 produkty' not in html


def test_zamowienie_z_samymi_zerami_znika_z_karty(
        db, client, login, make_user, make_order):
    sr, (zywe, martwe) = _zlecenie(db, make_user, make_order, ile_zamowien=2)
    _pozycja(db, zywe, 'Towar', 1)
    _pozycja(db, martwe, 'Nic nie weszlo', 0, is_set_fulfilled=False)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert zywe.order_number in html
    assert martwe.order_number not in html


def test_licznik_pokaz_wiecej_pomija_ukryte_zamowienia(
        db, client, login, make_user, make_order):
    """6 zamowien, 2 z samymi zerami → widocznych 4, wiec ukryte jest 1."""
    sr, zamowienia = _zlecenie(db, make_user, make_order, ile_zamowien=6)
    for i, o in enumerate(zamowienia):
        if i < 2:
            _pozycja(db, o, f'Nic nie weszlo {i}', 0, is_set_fulfilled=False)
        else:
            _pozycja(db, o, f'Towar {i}', 1)
    _zaloguj_admina(login, make_user)

    html = client.get('/admin/orders/wms').get_data(as_text=True)

    assert 'data-hidden-count="1"' in html
    assert 'Pokaż więcej (1)' in html
```

- [ ] **Step 2: Uruchom testy i zobacz, które padają**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: 3 pierwsze testy z Task 1 PASS; cztery nowe FAIL (zerowa pozycja w HTML, licznik „2 produkty", numer martwego zamówienia w HTML, `data-hidden-count="3"` zamiast `"1"`)

- [ ] **Step 3: Popraw gałąź paczki zbiorczej**

W `templates/admin/orders/wms_dashboard.html` znajdź pętlę uczestników (zaczyna się od `{% for uczestnik in sr.consolidation_participants %}`, linia ~305). Zastąp fragment od tej linii do `{% endfor %}` zamykającego pętlę zamówień uczestnika:

```jinja
                                {% for uczestnik in sr.consolidation_participants %}
                                {# Zamowienia z samymi wyzerowanymi pozycjami sa niewidoczne, wiec
                                   uczestnik, ktoremu nic nie zostalo, nie dostaje pustego naglowka.
                                   Filtr liczony raz do zmiennej — ns.i i licznik „Pokaz wiecej"
                                   musza widziec dokladnie te sama liste, co petla nizej. #}
                                {% set widoczne_zamowienia = uczestnik.orders|selectattr('shippable_items')|list %}
                                {% if widoczne_zamowienia %}
                                {% set grupa_od = ns.i %}
                                <div class="sr-order-group{% if grupa_od >= 3 %} sr-order-extra{% endif %}"{% if grupa_od >= 3 %} style="display: none;"{% endif %}>
```

Nagłówek grupy (`sr-order-group-head` wraz z avatarem, nazwiskiem, `sr-group-status` i znacznikiem „adresat") zostaje bez zmian.

Następnie pętla zamówień uczestnika — zastąp `{% for order in uczestnik.orders %}` i użycia `order.items`:

```jinja
                                    {% for order in widoczne_zamowienia %}
                                    {% set ns.i = ns.i + 1 %}
                                    {% set n = order.shippable_items|length %}
                                    <div class="sr-order-compact{% if ns.i > 3 and grupa_od < 3 %} sr-order-extra{% endif %}"{% if ns.i > 3 and grupa_od < 3 %} style="display: none;"{% endif %}>
                                        <svg class="sr-order-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                                        <a href="{{ url_for('orders.admin_detail', order_id=order.id) }}" class="order-badge-link" onclick="event.stopPropagation();">{{ order.order_number }}</a>
                                        <span class="sr-order-count">· {{ n }} {% if n == 1 %}produkt{% elif n % 10 in [2, 3, 4] and n % 100 not in [12, 13, 14] %}produkty{% else %}produktów{% endif %}</span>
                                        {% if n > 0 %}
                                        <button type="button" class="sr-order-toggle" onclick="event.stopPropagation(); toggleOrderProducts(this);">Pokaż</button>
                                        <div class="order-products-hidden" style="display: none;">
                                            {% for item in order.shippable_items %}
                                            <div class="order-product-item">
                                                <span class="product-qty">{{ item.quantity }}x</span>
                                                <span class="product-name">{{ item.product_name }}{% if item.selected_size %} <span class="size-badge">{{ item.selected_size }}</span>{% endif %}</span>
                                            </div>
                                            {% endfor %}
                                        </div>
                                        {% endif %}
                                    </div>
                                    {% endfor %}
                                </div>
                                {% endif %}
                                {% endfor %}
```

Uwaga: `{% endif %}` domykający `{% if widoczne_zamowienia %}` stoi ZA `</div>` grupy i PRZED `{% endfor %}` uczestników.

- [ ] **Step 4: Popraw gałąź zlecenia zwykłego**

W tym samym pliku, w gałęzi `{% else %}` (bez konsolidacji, linia ~369), zastąp pętlę zamówień oraz warunek przycisku:

```jinja
                                {% else %}
                                {# Filtr liczony raz: petla i licznik „Pokaz wiecej" musza widziec
                                   te sama liste, inaczej przycisk obiecuje wiecej, niz da sie rozwinac. #}
                                {% set widoczne_zamowienia = sr.orders|selectattr('shippable_items')|list %}
                                {% for order in widoczne_zamowienia %}
                                {% set n = order.shippable_items|length %}
                                <div class="sr-order-compact{% if loop.index > 3 %} sr-order-extra{% endif %}"{% if loop.index > 3 %} style="display: none;"{% endif %}>
                                    <svg class="sr-order-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                                    <a href="{{ url_for('orders.admin_detail', order_id=order.id) }}" class="order-badge-link" onclick="event.stopPropagation();">{{ order.order_number }}</a>
                                    <span class="sr-order-count">· {{ n }} {% if n == 1 %}produkt{% elif n % 10 in [2, 3, 4] and n % 100 not in [12, 13, 14] %}produkty{% else %}produktów{% endif %}</span>
                                    {% if n > 0 %}
                                    <button type="button" class="sr-order-toggle" onclick="event.stopPropagation(); toggleOrderProducts(this);">Pokaż</button>
                                    <div class="order-products-hidden" style="display: none;">
                                        {% for item in order.shippable_items %}
                                        <div class="order-product-item">
                                            <span class="product-qty">{{ item.quantity }}x</span>
                                            <span class="product-name">{{ item.product_name }}{% if item.selected_size %} <span class="size-badge">{{ item.selected_size }}</span>{% endif %}</span>
                                        </div>
                                        {% endfor %}
                                    </div>
                                    {% endif %}
                                </div>
                                {% endfor %}
                                {% if widoczne_zamowienia|length > 3 %}
                                {# Bez konsolidacji element = zamówienie 1:1, ale ten sam atrybut co w gałęzi
                                   zbiorczej — JS czyta go jednolicie, niezależnie od trybu karty. #}
                                <button type="button" class="sr-orders-toggle" data-expanded="false" data-hidden-count="{{ widoczne_zamowienia|length - 3 }}" onclick="event.stopPropagation(); toggleExtraOrders(this);">Pokaż więcej ({{ widoczne_zamowienia|length - 3 }})</button>
                                {% endif %}
                                {% endif %}
```

- [ ] **Step 5: Uruchom testy i upewnij się, że przechodzą**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: PASS — 7 testów

- [ ] **Step 6: Sprawdź, że nic innego się nie wywróciło**

Run: `python -m pytest tests/test_anulowanie_zlecenia.py tests/test_uprawnienia_przyciskow_admin.py tests/test_bramka_platnosci_wysylki.py -q`
Expected: PASS, bez nowych błędów

- [ ] **Step 7: Commit**

```bash
git add templates/admin/orders/wms_dashboard.html tests/test_wms_zerowe_pozycje.py
git commit -m "$(cat <<'MSG'
fix(wms): karta zlecenia nie pokazuje juz pozycji z iloscia 0

Wyzerowane przy domykaniu oferty znikaja z listy, licznik produktow liczy
zywe pozycje, a zamowienie z samymi zerami nie zajmuje miejsca w karcie.
Licznik "Pokaz wiecej" liczy po tej samej liscie, co petla.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 3: Sesja kompletacji w telefonie

**Files:**
- Modify: `modules/orders/wms.py` (`_build_session_data`, linie 134 i 153–154; oraz `all_picked` i sumy postępu, linie ~739–751)
- Test: `tests/test_wms_zerowe_pozycje.py` (dopisanie testu)

**Interfaces:**
- Consumes: `Order.shippable_items` z Task 1.

- [ ] **Step 1: Napisz test, który ma nie przejść**

Dopisz na końcu `tests/test_wms_zerowe_pozycje.py`:

```python
def test_sesja_kompletacji_nie_dostaje_wyzerowanych_pozycji(
        db, make_user, make_order):
    """Pozycja 0x wchodzila do sesji i od razu liczyla sie jako zebrana —
    pakujaca widziala wiersz, ktorego nie ma czego zdjac z polki."""
    from modules.orders.wms import _build_session_data
    from modules.orders.wms_models import WmsSession, WmsSessionOrder

    user = make_user(role='admin', email='magazyn@example.com')
    order = make_order(user=user)
    _pozycja(db, order, 'Mingi zywy', 2)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)

    sesja = WmsSession(session_token='tok-test-1', user_id=user.id, status='active')
    db.session.add(sesja)
    db.session.flush()
    db.session.add(WmsSessionOrder(session_id=sesja.id, order_id=order.id))
    db.session.commit()

    dane = _build_session_data(sesja)

    pozycje = dane['orders'][0]['items']
    assert [p['product_name'] for p in pozycje] == ['Mingi zywy']
    assert dane['orders'][0]['total_quantity'] == 2
    assert dane['orders'][0]['picked_percentage'] == 0
```

- [ ] **Step 2: Uruchom test i upewnij się, że nie przechodzi**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py::test_sesja_kompletacji_nie_dostaje_wyzerowanych_pozycji -v`
Expected: FAIL — lista zawiera dwie pozycje, druga to `Yunho wyzerowany`

- [ ] **Step 3: Przełącz `_build_session_data` na `shippable_items`**

W `modules/orders/wms.py`, w funkcji `_build_session_data`, zamień pętlę i sumy:

```python
        items_data = []
        # Wyzerowane pozycje (nie zmiescily sie w komplecie przy domykaniu
        # oferty) nie maja czego zdjac z polki, a wchodzac do sesji od razu
        # liczyly sie jako zebrane — patrz Order.shippable_items.
        for item in order.shippable_items:
```

oraz kilka linii niżej:

```python
        # Quantity-based progress
        total_qty = sum(i.quantity for i in order.shippable_items)
        picked_qty = sum(i.picked_quantity or 0 for i in order.shippable_items)
```

- [ ] **Step 4: Uzgodnij postęp kompletacji z tą samą listą**

W tym samym pliku, w miejscu przeliczania postępu po zebraniu pozycji (linie ~739–751), zamień trzy użycia `order.items`:

```python
            all_picked = all(
                (i.picked_quantity or 0) >= i.quantity for i in order.shippable_items
            )
```

```python
        total_qty = sum(i.quantity for i in order.shippable_items)
        picked_qty = sum(i.picked_quantity or 0 for i in order.shippable_items)
```

Uzasadnienie: pozycja z ilością 0 spełnia `0 >= 0` i wnosi 0 do obu sum, więc wynik liczbowo się nie zmienia — chodzi o to, żeby postęp liczył się po dokładnie tej samej liście, którą widzi pakująca.

- [ ] **Step 5: Uruchom testy i upewnij się, że przechodzą**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: PASS — 8 testów

- [ ] **Step 6: Sprawdź testy sesji WMS**

Run: `python -m pytest tests/ -q -k "wms"`
Expected: PASS, bez nowych błędów

- [ ] **Step 7: Commit**

```bash
git add modules/orders/wms.py tests/test_wms_zerowe_pozycje.py
git commit -m "$(cat <<'MSG'
fix(wms): sesja kompletacji pomija pozycje z iloscia 0

Wyzerowana pozycja wchodzila do sesji i od razu liczyla sie jako zebrana,
wiec pakujaca widziala wiersz bez towaru. Postep liczy sie teraz po tej
samej liscie, ktora widac na ekranie.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

### Task 4: Widok klienta „moje wysyłki"

**Files:**
- Modify: `templates/client/shipping/requests_list.html` (linie ~50–75)
- Test: `tests/test_wms_zerowe_pozycje.py` (dopisanie testu)

**Interfaces:**
- Consumes: `Order.shippable_items` z Task 1.

- [ ] **Step 1: Napisz test, który ma nie przejść**

Dopisz na końcu `tests/test_wms_zerowe_pozycje.py`:

```python
def test_klient_nie_widzi_wyzerowanej_pozycji_na_liscie_wysylek(
        db, client, login, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder

    user = make_user(email='klient-wysylki@example.com')
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id,
        status='czeka_na_wycene',
    )
    db.session.add(sr)
    db.session.flush()
    order = make_order(user=user)
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=order.id))
    db.session.commit()
    _pozycja(db, order, 'Mingi zywy', 1)
    _pozycja(db, order, 'Yunho wyzerowany', 0, is_set_fulfilled=False)
    login(user)

    html = client.get('/client/shipping/requests').get_data(as_text=True)

    assert 'Mingi zywy' in html
    assert 'Yunho wyzerowany' not in html
```

- [ ] **Step 2: Uruchom test i upewnij się, że nie przechodzi**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py::test_klient_nie_widzi_wyzerowanej_pozycji_na_liscie_wysylek -v`
Expected: FAIL — `'Yunho wyzerowany' not in html` nie zachodzi

- [ ] **Step 3: Popraw szablon klienta**

W `templates/client/shipping/requests_list.html` zastąp blok listy zamówień (od `{% for order in req.display_orders %}` do zamykającego `{% endfor %}`, linie ~50–76):

```jinja
                        {# Zamowienia, z ktorych nic nie jedzie (same wyzerowane pozycje),
                           nie pokazuja sie wcale — patrz Order.shippable_items. #}
                        {% for order in req.display_orders if order.shippable_items %}
                        <div class="card-order-block">
                            <a href="{{ url_for('orders.client_detail', order_id=order.id) }}" class="order-badge">
                                {{ order.order_number }}
                            </a>
                            <div class="card-order-products">
                                {% set pozycje = order.shippable_items %}
                                {% for item in pozycje[:2] %}
                                <div class="card-product-item">
                                    <span class="card-product-qty">{{ item.quantity }}x</span>
                                    <span class="card-product-name">{{ item.product_name }}{% if item.selected_size %} <span class="card-size-badge">{{ item.selected_size }}</span>{% endif %}</span>
                                </div>
                                {% endfor %}
                                {% if pozycje|length > 2 %}
                                <div class="card-order-products-hidden" style="display: none;">
                                    {% for item in pozycje[2:] %}
                                    <div class="card-product-item">
                                        <span class="card-product-qty">{{ item.quantity }}x</span>
                                        <span class="card-product-name">{{ item.product_name }}{% if item.selected_size %} <span class="card-size-badge">{{ item.selected_size }}</span>{% endif %}</span>
                                    </div>
                                    {% endfor %}
                                </div>
                                <button type="button" class="card-order-products-toggle" onclick="toggleOrderProducts(this);">
                                    +{{ pozycje|length - 2 }} więcej...
                                </button>
                                {% endif %}
                            </div>
                        </div>
                        {% endfor %}
```

- [ ] **Step 4: Uruchom testy i upewnij się, że przechodzą**

Run: `python -m pytest tests/test_wms_zerowe_pozycje.py -v`
Expected: PASS — 9 testów

- [ ] **Step 5: Uruchom pełną suitę**

Run: `python -m pytest tests/ -q`
Expected: PASS, bez nowych błędów względem stanu sprzed zmian

- [ ] **Step 6: Commit**

```bash
git add templates/client/shipping/requests_list.html tests/test_wms_zerowe_pozycje.py
git commit -m "$(cat <<'MSG'
fix(wysylki): klient nie widzi juz pozycji z iloscia 0 na liscie wysylek

Ten sam filtr co w panelu WMS — na liscie zlecen klient widzi wylacznie to,
co realnie jedzie. Szczegoly zamowienia bez zmian: tam sekcja "poza setem"
ma zostac widoczna.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
)"
```

---

## Po wdrożeniu

Zmiana dotyka wyłącznie ekranów za logowaniem, więc przeklikanie zostaje po stronie właścicielki. Do sprawdzenia na żywo:

1. Panel WMS → karta zlecenia z zamówieniem z domkniętej oferty: brak wierszy „0x", licznik zgadza się z liczbą realnych produktów.
2. Karta paczki zbiorczej: uczestnik, któremu nic nie weszło, nie pokazuje pustego nagłówka.
3. Zlecenie z ponad trzema zamówieniami: „Pokaż więcej (N)" rozwija dokładnie N pozycji.
4. Sesja WMS w telefonie: lista do zebrania bez wierszy 0x, pasek postępu zachowuje się jak dotąd.
5. Konto klienta → „Zlecenia wysyłki": bez wierszy 0x; w szczegółach zamówienia sekcja „poza setem" nadal widoczna.

Push na `main` (czyli wdrożenie) dopiero po jej wyraźnej zgodzie.
