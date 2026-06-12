# Mobile API — Etap E2 (Koszyk + checkout on-hand) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Koszyk i składanie zamówienia on-hand w mobilnym API: `GET/POST/PATCH/DELETE /shop/cart*`,
`GET /shop/checkout/summary`, `POST /shop/checkout` — przez warstwę serwisową współdzieloną z webem
(zero duplikacji logiki, zwłaszcza atomowej walidacji stocku). Plus trzy follow-upy z recenzji E1.

**Architecture:** Nowy serwis `modules/client/cart_service.py` — logika koszyka i checkoutu wyciągnięta
1:1 z `modules/client/shop.py` (wzorzec `shop_service.py` z E1). Serwis zwraca **kody maszynowe +
dokładne obecne komunikaty PL**; web mapuje wynik na swoje dotychczasowe odpowiedzi (zero zmiany
zachowania), mobile na kopertę `{success, data/error}`. Zero migracji — `CartItem` istnieje.

**Tech Stack:** Flask, flask-jwt-extended, SQLAlchemy (`with_for_update`), pytest.

---

## Zweryfikowane fakty (z badania kodu — nie odkrywaj ponownie)

- `CartItem` (modules/products/models.py:453): `user_id`, `product_id`, `quantity`, `created_at`,
  `updated_at`; UNIQUE(`user_id`,`product_id`). **NIE MA kolumny `selected_size`** — rozmiar
  pochodzi z produktu (`product.sizes[0].name`) i jest zapisywany dopiero na `OrderItem` przy checkout.
- Webowe trasy koszyka: `modules/client/shop.py` l. 278–436 (`api_cart`, `api_cart_add`,
  `api_cart_update`, `api_cart_remove`, `api_cart_count`, helper `_get_cart_count` l. 265).
- Webowy checkout: `shop.py` l. 439–646 (`_get_initial_shipping_status`, `checkout`, `checkout_place`).
  Mechanika `checkout_place`: (1) koszyk niepusty, (2) walidacja stocku WSZYSTKICH pozycji bez locka →
  `400 {stock_errors: [...]}`, (3) walidacja adresu gdy `create_shipping`, (4) `Order(order_type='on_hand',
  status='nowe', payment_stages=2)` + `db.session.flush()`, (5) **re-walidacja z
  `Product.query.with_for_update().get(...)` per pozycja → 409 przy wyścigu**, `OrderItem` z
  `selected_size=product.sizes[0].name`, `product.quantity -= qty`, interakcja `purchase`,
  (6) opcjonalny `ShippingRequest` + `ShippingRequestOrder`, (7) czyszczenie koszyka + commit,
  (8) `log_activity(action='order_created', ...)`. **Checkout NIE wysyła maila** — jedyne efekty
  uboczne to log_activity + interakcje + dane GA zwracane frontendowi (GA odpala frontend webowy —
  mobile NIE zwraca pól GA).
- Importy dostępne w shop.py (l. 1–27): `generate_order_number` z `modules.orders.utils`;
  `Order, OrderItem, ShippingRequest, ShippingRequestOrder, ShippingRequestStatus` z
  `modules.orders.models`; `Settings, ShippingAddress` z `modules.auth.models`;
  `log_activity` z `utils.activity_logger`; `Decimal` z `decimal`.
- `ShippingAddress` (modules/auth/models.py:762): `address_type` ('home'|'pickup_point'), `name`,
  pola home: `shipping_name/address/postal_code/city/voivodeship/country`, pola pickup:
  `pickup_courier/point_id/address/postal_code/city`, `is_active`.
- Helpery mobilne (modules/api_mobile/helpers.py): `json_ok`, `json_err`, `json_page`, `to_grosze`,
  `absolute_static_url`. Trasy E1 w `modules/api_mobile/shop_routes.py` (wzorce `@jwt_required()`,
  `int(get_jwt_identity())`).
- Konwencje testów: `tests/test_mobile_api_shop.py` — helpery `_auth(client, db, make_user)`
  (zwraca nagłówki Bearer) i `_onhand_type(db)` (ProductType on-hand). Nowy plik:
  `tests/test_mobile_api_cart.py` — skopiuj te helpery lokalnie (są małe).
- Fixtura `make_product(name=None, sale_price=99.00, quantity=10, **kwargs)` (conftest.py:52) —
  product_type przekazuje się przez kwargs; sprawdź w testach E1, czy jako obiekt czy `product_type_id`.
- Interakcja `view` w `product_detail`: inline `ProductInteraction(...)` + `db.session.add` +
  `db.session.commit()` (shop.py, ~9 linii w bloku „Record view interaction") — Task 3 podmienia
  na `shop_service.record_interaction`, commit zostaje w trasie, jeśli serwis nie commituje.
- Baseline testów po E1: **169 passed** (`source venv/bin/activate && python -m pytest -q`).
  W tym repo działa TYLKO `python -m pytest` (gołe `pytest` pada).
- `/docs` jest w .gitignore — commit dokumentów wymaga `git add -f`.

## Korekty kontraktu względem specu (parytet z webem — zatwierdzone z planem)

1. **`POST /cart/items` BEZ `selected_size`** — CartItem nie przechowuje rozmiaru; produkty on-hand
   mają efektywnie jeden rozmiar, API zwraca go w pozycjach koszyka jako `size` (read-only).
2. **`POST /checkout` body: `{create_shipping, address_id}`** — bez `delivery_method`/`payment_method`
   (web ich nie ma; płatności to etapy E1–E4 obsługiwane w E6, dostawa = opcjonalny ShippingRequest).
3. **Rozszerzenie koperty błędu o `details`** (opcjonalne pole): `error: {code, message, details?}` —
   potrzebne dla `stock_errors` przy checkout. Spec aktualizowany w Task 10.

---

## File Structure

- `modules/api_mobile/validators.py` — NOWY: `ValidationError`, `parse_int`.
- `modules/api_mobile/helpers.py` — bez zmian (reużycie).
- `modules/api_mobile/shop_routes.py` — Task 1 (walidacja parametrów), Task 2 (serializer kursu).
- `modules/api_mobile/cart_routes.py` — NOWY: trasy koszyka + checkout (mobile).
- `modules/api_mobile/__init__.py` — import `cart_routes`.
- `modules/client/cart_service.py` — NOWY: serwis koszyka + checkoutu (współdzielony).
- `modules/client/shop.py` — refaktor tras koszyka/checkoutu na serwis (Task 6) + follow-up Task 3.
- `tests/test_mobile_api_cart.py` — NOWY: testy E2.
- `tests/test_mobile_api_shop.py` — testy Task 1–2.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 10.

---

### Task 1: Walidator parametrów wejścia (follow-up E1)

**Files:** Create `modules/api_mobile/validators.py`; Modify `modules/api_mobile/shop_routes.py`; Test `tests/test_mobile_api_shop.py`

- [ ] **Step 1: Test (RED)** — append do `tests/test_mobile_api_shop.py`:
```python
def test_shop_products_invalid_price_param_returns_400(client, db, make_user):
    h = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/shop/products?price_min=abc', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_shop_products_invalid_page_returns_400(client, db, make_user):
    h = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/shop/products?page=x', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'
```
Run: `source venv/bin/activate && python -m pytest tests/test_mobile_api_shop.py -k invalid -v` → FAIL (obecnie ciche ignorowanie).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/validators.py`:
```python
"""Walidacja parametrów wejścia mobilnego API (query stringi i body JSON)."""


class ValidationError(ValueError):
    """Niepoprawny parametr wejścia — mapowany na 400 invalid_input."""


def parse_int(value, field, required=False, default=None, min_value=None, max_value=None):
    """str/num -> int z zakresem; None/'' -> default (lub błąd gdy required)."""
    if value is None or value == '':
        if required:
            raise ValidationError(f'Pole {field} jest wymagane.')
        return default
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValidationError(f'Pole {field} musi być liczbą całkowitą.')
    if min_value is not None and result < min_value:
        raise ValidationError(f'Pole {field} musi być >= {min_value}.')
    if max_value is not None and result > max_value:
        raise ValidationError(f'Pole {field} musi być <= {max_value}.')
    return result
```
W `modules/api_mobile/__init__.py` (po definicji blueprintu, przed importami tras) errorhandler:
```python
from .validators import ValidationError  # noqa: E402

@api_mobile_bp.errorhandler(ValidationError)
def _validation_error(e):
    from .helpers import json_err
    return json_err('invalid_input', str(e), 400)
```
W `shop_routes.py` (lista produktów): zamień obecne parsowanie `page/per_page/price_min/price_max`
na `parse_int(...)` (page: default 1 min 1; per_page: default i cap jak dotychczas; price_min/max:
default None, min_value 0). Zachowaj dotychczasowy cap per_page.

- [ ] **Step 3: GREEN + regresja pliku** — `python -m pytest tests/test_mobile_api_shop.py -v` (wszystkie, także stare).
- [ ] **Step 4: Commit** — `git add modules/api_mobile/validators.py modules/api_mobile/__init__.py modules/api_mobile/shop_routes.py tests/test_mobile_api_shop.py && git commit -m "feat(mobile-api): walidator parametrów wejścia (400 invalid_input)"`

---

### Task 2: Serializer /exchange-rate (follow-up E1)

**Files:** Modify `modules/api_mobile/shop_routes.py`; Test `tests/test_mobile_api_shop.py`

- [ ] **Step 1: Test (RED)** — kontrakt przypięty do dokładnego zbioru kluczy:
```python
def test_exchange_rate_pinned_contract(client, db, make_user, monkeypatch):
    import utils.currency as uc
    h = _auth(client, db, make_user)
    # UWAGA: shop_routes importuje get_exchange_rate WEWNĄTRZ funkcji trasy (l. ~123),
    # więc patch musi celować w moduł źródłowy utils.currency.
    monkeypatch.setattr(uc, 'get_exchange_rate', lambda c: {
        'currency': 'USD', 'rate': 3.7, 'date': '2026-06-12',
        'cached': True, 'cached_at': 'x', 'EXTRA_INTERNAL': 'leak'})
    r = client.get('/api/mobile/v1/exchange-rate?currency=USD', headers=h)
    assert r.status_code == 200
    assert sorted(r.get_json()['data'].keys()) == ['cached', 'cached_at', 'currency', 'date', 'rate']
```
(Dostosuj patch-target do faktycznego stylu importu w shop_routes — sprawdź, czy jest `from utils.currency import get_exchange_rate`.)
Run → FAIL (`EXTRA_INTERNAL` przecieka).

- [ ] **Step 2: Implementacja** — w trasie exchange-rate jawny serializer:
```python
    return json_ok({
        'currency': rate_data['currency'],
        'rate': rate_data['rate'],
        'date': rate_data.get('date'),
        'cached': rate_data.get('cached', False),
        'cached_at': rate_data.get('cached_at'),
    })
```
- [ ] **Step 3: GREEN** + **Step 4: Commit** `fix(mobile-api): przypięty kontrakt /exchange-rate (jawny serializer)`

---

### Task 3: Web product_detail → shop_service.record_interaction (follow-up E1)

**Files:** Modify `modules/client/shop.py`

- [ ] **Step 1:** Znajdź w `product_detail` (shop.py ~l. 120–162) inline tworzenie `ProductInteraction`
  typu `view` i zamień na `shop_service.record_interaction(current_user.id, product.id, 'view')`
  (zweryfikuj sygnaturę w shop_service.py:196 — czy commituje, czy commit zostaje w trasie; zachowaj
  obecne zachowanie commitów 1:1).
- [ ] **Step 2: Pełna regresja** — `python -m pytest -q` → 169+4 z Task 1–2 (wszystkie green).
- [ ] **Step 3: Commit** `refactor(shop): product_detail używa shop_service.record_interaction`

---

### Task 4: Serwis koszyka — `modules/client/cart_service.py` (TDD na serwisie)

**Files:** Create `modules/client/cart_service.py`; Test `tests/test_mobile_api_cart.py` (sekcja serwisowa)

Serwis przenosi logikę 1:1 z shop.py (l. 265–436) — **ciała funkcji to dosłowne przeniesienia**,
zmienia się tylko `current_user.id` → parametr `user_id` i zwracane wartości:

```python
"""Serwis koszyka i checkoutu on-hand — wspólny dla weba i mobilnego API."""
from collections import namedtuple

CartResult = namedtuple('CartResult', 'ok code message status extras')
# ok=True: code/message None, extras np. {'cart_count': n}
# ok=False: code maszynowy, message = DOKŁADNY dotychczasowy komunikat PL weba, status HTTP

def get_cart_count(user_id): ...          # przeniesione _get_cart_count (shop.py:265)
def build_cart_data(user_id): ...         # przeniesiona pętla z api_cart (shop.py:281-303):
                                          # zwraca (cart_data: list[dict], total: float, count: int)
                                          # dict DOKŁADNIE jak dziś (price float, image_url '/static/...')
def add_to_cart(user_id, product_id, quantity): ...   # z api_cart_add (309-367) -> CartResult
def update_cart_item(user_id, item_id, quantity): ... # z api_cart_update (370-405) -> CartResult
def remove_cart_item(user_id, item_id): ...           # z api_cart_remove (408-424) -> CartResult
```

Kody błędów (code → status → message verbatim z weba):
`missing_product_id→400`, `product_not_found→404`, `not_on_hand→400`, `out_of_stock→400`,
`exceeds_stock→400` (extras={'available': n}), `invalid_quantity→400`, `missing_item_id→400`,
`item_not_found→404`. Commity sesji zostają w serwisie (jak dziś w trasach).

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_mobile_api_cart.py`: utwórz plik z helperami
  `_auth`/`_onhand_type` (kopiuj z test_mobile_api_shop.py) + testy serwisu wprost (bez HTTP):
  add nowy produkt → ok + wpis w bazie + interakcja cart_add; add ponowny → scala ilość;
  add ponad stock → `exceeds_stock` z available; update na 0 → usuwa; update ponad stock → błąd;
  remove cudzego item_id → `item_not_found`; build_cart_data → struktura dict jak webowa
  (klucze: id, product_id, name, price, quantity, available, image_url, is_available, slug, size).
  Run → FAIL (ModuleNotFoundError).
- [ ] **Step 2: Implementacja serwisu** (przeniesienie 1:1 wg powyższej specyfikacji).
- [ ] **Step 3: GREEN** + **Step 4: Commit** `feat(shop): serwis koszyka on-hand (wspólny web+mobile)`

---

### Task 5: Serwis checkoutu — `place_order_on_hand` (TDD na serwisie)

**Files:** Modify `modules/client/cart_service.py`; Test `tests/test_mobile_api_cart.py`

```python
CheckoutResult = namedtuple('CheckoutResult', 'ok code message status order stock_errors extras')

def get_initial_shipping_status(): ...    # przeniesione _get_initial_shipping_status (shop.py:439-454)
def place_order_on_hand(user_id, create_shipping=False, address_id=None): ...
```
Przeniesienie checkout_place (l. 477–646) 1:1, z różnicami:
- `current_user.id` → `user_id`; `current_user` w log_activity → załaduj `User.query.get(user_id)`.
- ZWRACA CheckoutResult zamiast jsonify: sukces → `order` + extras
  `{'order_number', 'total_amount' (float jak dziś), 'items_count', 'ga_items', 'shipping_request_number'}`;
  błędy → kody: `cart_empty→400`, `stock_errors→400` (lista jak dziś), `address_required→400`,
  `address_not_found→400`, `stock_conflict→409` (komunikat „...został właśnie wyprzedany..."),
  `checkout_error→500` (z istniejącym logiem wyjątku).
- `url_for('shop.order_success', ...)` ZOSTAJE w trasie webowej (prezentacja).

- [ ] **Step 1: Testy serwisu (RED):** happy path (Order on_hand/nowe/payment_stages=2, OrderItem
  z selected_size z produktu, stock zmniejszony, koszyk wyczyszczony, interakcja purchase);
  pusty koszyk → cart_empty; stock za mały → stock_errors z available; create_shipping bez
  address_id → address_required; z poprawnym adresem → ShippingRequest + ShippingRequestOrder
  powstają, extras['shipping_request_number'] niepusty.
- [ ] **Step 2: Implementacja** + **Step 3: GREEN** + **Step 4: Commit**
  `feat(shop): serwis checkoutu on-hand (atomowa walidacja stocku, wspólny web+mobile)`

---

### Task 6: Refaktor weba na serwis (zero zmiany zachowania) + pełna regresja

**Files:** Modify `modules/client/shop.py`

- [ ] **Step 1:** Przepnij `api_cart`, `api_cart_add`, `api_cart_update`, `api_cart_remove`,
  `api_cart_count`, `checkout_place` na cart_service; trasy tylko mapują CartResult/CheckoutResult
  na DOKŁADNIE dotychczasowe odpowiedzi jsonify (te same klucze, statusy, komunikaty — w tym
  `stock_errors`, `available`, `redirect_url`). Usuń przeniesione funkcje pomocnicze z shop.py.
- [ ] **Step 2: Pełna regresja** — `python -m pytest -q` (zero failów; testy webowego sklepu
  i checkoutu muszą przejść bez modyfikacji samych testów).
- [ ] **Step 3: Commit** `refactor(shop): koszyk i checkout web na cart_service (bez zmiany zachowania)`

---

### Task 7: Mobile — koszyk (GET/POST/PATCH/DELETE)

**Files:** Create `modules/api_mobile/cart_routes.py`; Modify `modules/api_mobile/__init__.py`; Test `tests/test_mobile_api_cart.py`

- [ ] **Step 1: Testy HTTP (RED):**
```python
def test_cart_requires_token(client):
    assert client.get('/api/mobile/v1/shop/cart').status_code == 401


def test_cart_flow_add_get_update_delete(client, db, make_user, make_product):
    h = _auth(client, db, make_user)
    p = make_product(product_type=_onhand_type(db), quantity=5, sale_price=Decimal('99.00'))
    r = client.post('/api/mobile/v1/shop/cart/items', headers=h,
                    json={'product_id': p.id, 'quantity': 2})
    assert r.status_code == 201 and r.get_json()['data']['cart_count'] == 2
    r = client.get('/api/mobile/v1/shop/cart', headers=h)
    data = r.get_json()['data']
    assert data['count'] == 2 and data['total'] == 19800          # grosze
    item = data['items'][0]
    assert item['price'] == 9900                                   # grosze
    assert item['image_url'] is None or item['image_url'].startswith('http')
    item_id = item['id']
    r = client.patch(f'/api/mobile/v1/shop/cart/items/{item_id}', headers=h, json={'quantity': 1})
    assert r.status_code == 200 and r.get_json()['data']['cart_count'] == 1
    r = client.delete(f'/api/mobile/v1/shop/cart/items/{item_id}', headers=h)
    assert r.status_code == 200
    assert client.get('/api/mobile/v1/shop/cart', headers=h).get_json()['data']['count'] == 0


def test_cart_add_exceeds_stock(client, db, make_user, make_product):
    h = _auth(client, db, make_user)
    p = make_product(product_type=_onhand_type(db), quantity=1, sale_price=Decimal('10.00'))
    r = client.post('/api/mobile/v1/shop/cart/items', headers=h,
                    json={'product_id': p.id, 'quantity': 5})
    assert r.status_code == 400
    body = r.get_json()
    assert body['error']['code'] == 'exceeds_stock'
    assert body['error']['details']['available'] == 1


def test_cart_item_of_other_user_not_found(client, db, make_user, make_product):
    ...  # user A dodaje, user B PATCH/DELETE na item A -> 404 item_not_found
```
(Dostosuj `make_product` do faktycznej sygnatury fixtury — sprawdź conftest.)
- [ ] **Step 2: Implementacja** — `modules/api_mobile/cart_routes.py`:
```python
"""Trasy koszyka i checkoutu on-hand dla mobilnego API."""
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import request
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze, absolute_static_url
from .validators import parse_int
from modules.client import cart_service


def _err(result):
    details = result.extras or None
    payload = {'code': result.code, 'message': result.message}
    if details:
        payload['details'] = details
    from flask import jsonify
    return jsonify({'success': False, 'error': payload}), result.status


def _serialize_item(d):
    return {**d, 'price': to_grosze(d['price']),
            'image_url': absolute_static_url(d['image_url'].removeprefix('/static/')) if d['image_url'] else None}
```
- `GET /shop/cart` → `build_cart_data` → items zserializowane + `total` (grosze) + `count`.
- `POST /shop/cart/items` → `parse_int(product_id, required=True)`, `parse_int(quantity, default=1, min_value=1)`
  → `add_to_cart` → 201 `{'cart_count': n}` / `_err`.
- `PATCH /shop/cart/items/<int:item_id>` → `parse_int(quantity, required=True)` → `update_cart_item`
  (quantity<=0 usuwa — parytet z webem) → `{'cart_count': n}`.
- `DELETE /shop/cart/items/<int:item_id>` → `remove_cart_item` → `{'cart_count': n}`.
- Rate limit `@limiter.limit("60 per minute")` na mutacjach koszyka.
- W `modules/api_mobile/__init__.py`: `from . import cart_routes  # noqa: E402,F401`.
- [ ] **Step 3: GREEN** + **Step 4: Commit** `feat(mobile-api): koszyk on-hand (GET/POST/PATCH/DELETE)`

---

### Task 8: Mobile — GET /shop/checkout/summary

**Files:** Modify `modules/api_mobile/cart_routes.py`; Test `tests/test_mobile_api_cart.py`

- [ ] **Step 1: Test (RED):** summary zwraca `items` (jak GET cart), `total` (grosze), `count`
  oraz `addresses[]` — serializacja ShippingAddress: `{id, address_type, name, shipping_name,
  shipping_address, shipping_postal_code, shipping_city, shipping_voivodeship, shipping_country,
  pickup_courier, pickup_point_id, pickup_address, pickup_postal_code, pickup_city}` tylko
  `is_active=True` bieżącego usera. Pusty koszyk → 200 z pustymi items (decyzja: summary nie
  wymusza niepustego koszyka; blokuje dopiero POST /checkout — parytet logiki webowej, gdzie
  redirect robi strona, nie API).
- [ ] **Step 2: Implementacja** + **Step 3: GREEN** + **Step 4: Commit**
  `feat(mobile-api): podsumowanie checkoutu (koszyk + adresy)`

---

### Task 9: Mobile — POST /shop/checkout

**Files:** Modify `modules/api_mobile/cart_routes.py`; Test `tests/test_mobile_api_cart.py`

- [ ] **Step 1: Testy (RED):**
  - happy path bez wysyłki → 201, `data` = `{order_id, order_number, total (GROSZE), items_count,
    shipping_request_number: None}`; po nim koszyk pusty, stock produktu zmniejszony;
  - happy path z `create_shipping=True` + adres usera → `shipping_request_number` niepusty;
  - pusty koszyk → 400 `cart_empty`;
  - stock za mały → 400 `stock_errors` z `details` (lista pozycji jak web);
  - `create_shipping` bez `address_id` → 400 `address_required`.
- [ ] **Step 2: Implementacja:**
```python
@api_mobile_bp.route('/shop/checkout', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")
def checkout_place_mobile():
    p = request.get_json(silent=True) or {}
    create_shipping = bool(p.get('create_shipping', False))
    address_id = parse_int(p.get('address_id'), 'address_id', required=False)
    result = cart_service.place_order_on_hand(int(get_jwt_identity()),
                                              create_shipping=create_shipping,
                                              address_id=address_id)
    if not result.ok:
        if result.code == 'stock_errors':
            return _err(result._replace(extras={'stock_errors': result.stock_errors}))
        return _err(result)
    return json_ok({
        'order_id': result.order.id,
        'order_number': result.extras['order_number'],
        'total': to_grosze(result.extras['total_amount']),
        'items_count': result.extras['items_count'],
        'shipping_request_number': result.extras['shipping_request_number'],
    }, 201)
```
(BEZ `ga_items` w odpowiedzi mobilnej i BEZ `redirect_url` — to webowe.)
- [ ] **Step 3: GREEN** + **Step 4: Commit** `feat(mobile-api): checkout on-hand (atomowa walidacja stocku)`

---

### Task 10: Pełna regresja + aktualizacja specu

- [ ] **Step 1:** `python -m pytest tests/test_mobile_api_cart.py -v` (komplet E2) oraz pełne
  `python -m pytest -q` — oczekiwane ~169 + ~28-32 nowych, zero failów.
- [ ] **Step 2:** Spec (`docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`), sekcja
  Sklep on-hand: nota korekt E2 — (a) cart/items bez `selected_size` (rozmiar w odpowiedzi z produktu),
  (b) checkout body `{create_shipping, address_id}`, (c) `error.details` (opcjonalne) w kopercie błędu,
  (d) kwoty w groszach.
- [ ] **Step 3:** Commit `docs(mobile-api): korekty kontraktu E2 (koszyk bez selected_size, checkout body)` (pamiętaj `git add -f docs/...`).

---

## Definition of Done (E2)

- [ ] Follow-upy E1: walidator (400 invalid_input), przypięty kontrakt /exchange-rate, record_interaction w web detail.
- [ ] `modules/client/cart_service.py` — koszyk + checkout wyciągnięte z weba; web zrefaktorowany bez zmiany zachowania (pełna regresja green bez modyfikacji istniejących testów).
- [ ] Endpointy mobilne: GET/POST/PATCH/DELETE koszyka, GET checkout/summary, POST checkout — wszystkie za JWT, z rate-limitami, kwoty w groszach, obrazki absolutne, pokryte testami (w tym: cudzy item 404, exceeds_stock z details, stock_errors, parytet atomowej walidacji).
- [ ] Spec zaktualizowany o korekty kontraktu. Zero migracji. Pełny `python -m pytest -q` green.
- [ ] NIE pushować — wdrożenie decyzją Konrada.
