# Mobile API — Etap E4 (Pre-order: validate-cart + place-order-preorder) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Domknięcie trzeciego (ostatniego) flow składania zamówień mobilnego API — **pre-order**.
Dwa endpointy ze specu sekcja 5: `POST /offers/<token>/validate-cart` (walidacja pozycji koszyka,
który żyje w apce jak `localStorage` w webie) oraz `POST /offers/<token>/place-order-preorder`
(złożenie `Order(pre_order)` + bonusy, **objęte `Idempotency-Key`** — trzecia mutacja składająca
zamówienie). Pre-order **NIE ma rezerwacji** (brak `session_id`, brak `SELECT FOR UPDATE`, brak
limitów dostępności) — backend tylko waliduje produkty i składa zamówienie z koszyka przekazanego
w żądaniu.

**Architecture:** Logika składania pre-order JUŻ JEST wyciągnięta do warstwy serwisowej —
`place_preorder_order` w `modules/offers/place_order.py` (analogicznie do `place_offer_order` z E3).
Trasa webowa `modules/offers/routes.py::place_order` (l. 704) to cienki wrapper, który dla
`page_type == 'preorder'` woła ten serwis. **Główny refaktor E4 to ta sama zmiana co w E3 Task 3:**
`place_preorder_order` sięga po `flask_login.current_user` bezpośrednio (4 miejsca) — trzeba przekazać
użytkownika jawnym parametrem `user`, by mobile (JWT, bez sesji Flask-Login) mógł użyć tej samej
funkcji. Przy okazji domykamy jedną asymetrię hardeningu: w `place_preorder_order` **commit (l. 911)
nie jest owinięty** w try/except (w przeciwieństwie do `place_offer_order`), co przy błędzie bazy
rzuca nieobsłużony wyjątek → 500 → **zaklinowany klucz idempotency** (wiersz `processing` zostaje).
Wszystkie cztery bloki POST-commit (log_activity / email+push / Socket.IO / achievements) są już
owinięte try/except — patrz Zweryfikowane fakty. Endpointy mobilne dopisujemy do istniejącego
`modules/api_mobile/offers_routes.py` (E3). Bramki strony, koperty błędów, kwoty w groszach i
`@idempotent` — **spójne z E3**.

**Tech Stack:** Flask, flask-jwt-extended, SQLAlchemy, Flask-Migrate (Alembic — w E4 **prawdopodobnie
ZERO migracji**, patrz fakty), pytest (sqlite in-memory).

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Serwis `place_preorder_order` (`modules/offers/place_order.py`, l. 759–998)
- Sygnatura: `place_preorder_order(page, cart_items, order_note=None)` (l. 759). `cart_items` =
  `[{'product_id': int, 'quantity': int, 'selected_size'?: str}, ...]`.
- Walidacja wejścia (l. 774–781): pusty `cart_items` → `(False, {'error': 'empty_cart', 'message':
  'Koszyk jest pusty'})`; filtruje pozycje z `product_id` i `quantity > 0`; jeśli po filtrze pusto →
  ponownie `empty_cart`.
- `generate_order_number('pre_order')` (l. 785) → prefix **`PO`** (`OrderType.slug='pre_order'`,
  `modules/orders/utils.py:21`; **testy MUSZĄ zaseedować `OrderType(slug='pre_order', prefix='PO')`**).
  Błąd → `(False, {'error': 'order_number_failed', 'message': str(e)})`.
- `Order(order_type='pre_order', user_id=current_user.id, status='nowe', offer_page_id=page.id,
  offer_page_name=page.name, payment_stages=page.payment_stages, notes=order_note, total_amount)`
  (l. 790–800). **`current_user.id` na l. 793 — REFAKTOR.**
- Pozycje (l. 809–838): per `cart_item` pobiera `Product.query.get(product_id)` (None → `continue`,
  pozycja po cichu pominięta); **walidacja rozmiaru** (l. 814–821): `if product.sizes and not
  item_data.get('selected_size'): db.session.rollback(); return False, {'error': 'size_required',
  'message': ..., 'product_name': product.name}`. Cena: `product.sale_price if product.sale_price
  else product.price` (l. 824; `sale_price` jest NOT NULL → praktycznie zawsze `sale_price`).
  `total_items_count += quantity` (NIE liczy bonusów).
- **Bonusy** (l. 840–907): iteruje sekcje `section_type='bonus'` (`OfferSection`), bierze pierwszą
  aktywną `OfferSetBonus`. Trzy `trigger_type`: `buy_products` (po `OfferBonusRequiredProduct`,
  ratio `bought // min_quantity`), `price_threshold` (po `total_amount`), `quantity_threshold`
  (po `total_items_count`). `repeatable` skaluje liczbę, inaczej max 1. Limit globalny
  `max_available` (suma wcześniej przyznanych, bez anulowanych). **Brak `SELECT FOR UPDATE`**
  (pre-order nie ma anti-overselling — to świadomie, bonusy pre-order liczone „miękko").
- `order.total_amount = total_amount; db.session.commit()` (l. 910–911). **`commit` NIE owinięty
  try/except** (asymetria vs `place_offer_order`, który łapie `OperationalError`/deadlock i zwraca
  `database_error`). **HARDENING E4: owinąć** — patrz Task 1.
- **POST-commit (l. 913–989) — WSZYSTKIE 4 bloki JUŻ owinięte `try/except`** (nie wywołają 500 ani
  nie zaklinują klucza idempotency):
  - l. 914–923: `log_activity(user=current_user, ...)` → `except Exception: pass`. **`current_user`
    l. 916 — REFAKTOR.**
  - l. 926–934: `EmailManager`/`PushManager` `notify_order_confirmation` + `notify_admin_new_order`
    → `except Exception: pass`.
  - l. 937–977: Socket.IO `emit_new_order` + `emit_stats_update` (`get_live_summary`) →
    `except Exception: pass`. **`current_user.first_name/last_name/email` l. 956 — REFAKTOR.**
  - l. 980–989: `AchievementService().check_event(current_user, ...)` → `except Exception: pass`.
    **`current_user` l. 982 — REFAKTOR.**
  > Różnica vs `place_offer_order`: tam bloki POST-commit logują z tracebackiem
  > (`current_app.logger.exception(...)`), tu są **ciche** (`except Exception: pass`). To gap
  > obserwowalności, NIE ryzyko 500. Wyrównanie do logowania — opcjonalne (Task 1, sub-step opcjonalny).
- **`current_user` użyte w 4 miejscach: l. 793, 916, 956, 982.** Wszystkie → przekazany `user`.
- **`bind_user` NIE dotyczy pre-order** — nie ma rezerwacji do związania z userem (koszyk przychodzi
  w body). W E3 `bind_user` filtrował `OfferReservation.user_id`; tu nie ma czego filtrować.
- Sukces (l. 992–998): `{'order_id', 'order_number', 'total_amount' (float), 'items_count',
  'items' (GA, build_ga_items)}` — identyczny kształt jak `place_offer_order`. **Brak double-submit
  guard** (w przeciwieństwie do `place_offer_order`, l. 218–236, który zwraca `already_placed`) —
  patrz Decyzja **D3**.

### Trasa webowa pre-order (`modules/offers/routes.py`)
- **Składanie:** `place_order` (l. 704, `@csrf.exempt`, limit 15/min per user): login→`page_not_found`
  404→`if not page.is_active → 403 page_not_active`→rozgałęzienie. Dla `page_type == 'preorder'`
  (l. 727–733): `cart_items = data.get('cart_items', [])`; pusto → `400 empty_cart`; woła
  `place_preorder_order(page=page, cart_items=cart_items, order_note=order_note)`. **NIE sprawdza
  jawnie `draft`** (draft i tak nie jest `is_active` → wpada w 403). **NIE sprawdza `page_type`
  wprost** (rozgałęzia if/else — pre-order i exclusive w jednej trasie).
- **„validate-cart" webowe = trasa `/restore`** (l. 622–646, `@csrf.exempt`, limit 30/min). Dla
  `page_type == 'preorder'` (l. 632–646): iteruje `cart_items`, dla każdego
  `Product.query.get(product_id)`; jeśli `product and product.is_active` → dokłada
  `{'product_id', 'name', 'price': float(sale_price or price), 'quantity'}`. **Pozycje nieaktywne /
  nieistniejące po cichu odpada** (brak raportu). **Brak bramki `is_active`/`draft`** — tylko
  `page_not_found` 404. Zwraca `{'success': True, 'cart_items': valid_items}`.
  > Wniosek kontraktowy: `quantity` w odpowiedzi = ilość ZAMAWIANA (z koszyka), nie stan magazynowy.
  > `price` webowo w PLN (float) — mobile zwróci w **groszach (int)**, parytet z E1–E3.

### Wzorce mobilne z E3 (do reużycia — `modules/api_mobile/offers_routes.py`)
- `offer_place_order` (l. 296–348, exclusive): `@jwt_required` + `@limiter.limit("15 per minute")` +
  `@idempotent('offer_place_order')`. Bramka: `page_not_found` 404 → **`if page.page_type ==
  'preorder': wrong_page_type 400`** (E4 to ODWROTNOŚĆ: odrzucamy `exclusive`) → `draft` 404 →
  `not is_active` 403 `page_not_active`. `user = User.query.get(int(get_jwt_identity()))`,
  `user is None → user_not_found 404`. Mapuje błędy serwisu na status (`_PLACE_ORDER_ERR_STATUS`),
  kwoty `to_grosze`, sukces 201 (lub 200 z `already_placed`). **Strip `items` GA z odpowiedzi.**
- `_brief(p)` (l. 79–91): `{id, name, slug (shop_service.slugify), sku, price (to_grosze), quantity
  (stock!), image_url (absolute_static_url(primary_image.path_compressed)), sizes ([s.name])}`.
  **UWAGA:** `_brief['quantity']` to STAN MAGAZYNOWY — dla validate-cart potrzebujemy ilości
  ZAMAWIANEJ, więc NIE reużywamy `_brief` wprost (patrz Task 2).
- `@idempotent('...')` (`modules/api_mobile/idempotency.py`): claim-first, nagłówek opcjonalny,
  TTL 48h, MUSI być POD `@jwt_required()`. Brak nagłówka = zachowanie jak dziś. Replay zwraca
  oryginalną odpowiedź z zapisanym `status_code`. Trasa musi zwracać `(Response, status)` (json_ok/
  json_err to robią).
- Helpery (`helpers.py`): `json_ok(data, status=200)`, `json_err(code, message, status)`,
  `to_grosze(amount)`, `absolute_static_url(path)`. `validators.py`: `parse_int(...)` (+errorhandler
  `ValidationError`→400 `invalid_input`).

### Order / OrderType / Product
- `generate_order_number('pre_order')` wymaga `OrderType(slug='pre_order', prefix='PO')`
  (`modules/orders/utils.py`). Prefiks zamówień: `PO/00000001`.
- `Product` (`modules/products/models.py`): `sale_price` Numeric(10,2) **NOT NULL** (l. 204),
  `is_active` Boolean default True (l. 218), `sizes` m2m przez `product_sizes` (l. 232),
  `primary_image`. `OfferSection.section_type='bonus'`, `OfferSetBonus` (pola: `section_id`,
  `trigger_type`, `threshold_value`, `bonus_product_id`, `bonus_quantity`, `max_available`,
  `when_exhausted`, `count_full_set`, `repeatable`, `is_active`, `sort_order`).
- `OfferPage.page_type` enum **exclusive/preorder**; `is_active` (`status == 'active'`),
  `status == 'draft'` niepubliczny.

### Testy / środowisko / migracje
- **Baseline: `235 passed`** (`source venv/bin/activate && python -m pytest -q`, zweryfikowane
  2026-06-12). TYLKO `python -m pytest` (gołe `pytest` pada na `No module named 'app'`).
- **Brak testów `place_preorder_order`** — E4 dodaje pierwsze pokrycie (regresja dla refaktoru `user`).
- Helpery testowe w `tests/test_mobile_api_offers.py`: `_auth(client, db, make_user) → (headers,
  user)` (loguje przez `/auth/login`), `_make_page(db, status, page_type='exclusive',
  payment_stages=4)` (tworzy `OfferPage`, `created_by=1`), `_ex_order_type(db)` (wzorzec do
  skopiowania jako `_po_order_type`). conftest: `make_user`, `make_product(name=None,
  sale_price=99.00, quantity=10, **kwargs)`, `client`, `db`.
- **Migracje head: `c72aad290158` (zweryfikowane `flask db heads`). E4 NIE wprowadza nowych modeli/
  kolumn — `mobile_idempotency_keys` (E3) już istnieje. ZERO migracji w E4.** (Gdyby implementacja
  wymusiła zmianę modelu — STOP i migracja Flask-Migrate; nie spodziewane.)
- **Notyfikacje w teście:** baseline 235 obejmuje `test_place_order_happy_path` (exclusive), które
  woła te same `EmailManager.notify_order_confirmation` / `PushManager` / Socket.IO co pre-order —
  i przechodzi. Pre-order korzysta z tych samych zaślepionych/owiniętych ścieżek → **monkeypatch
  niepotrzebny** (gdyby happy-path pre-order wywalił się na poczcie — dodaj `monkeypatch`, ale to
  mało prawdopodobne).
- `/docs` w `.gitignore` → commit planu i specu przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem + E3 — zatwierdzane wraz z planem)

1. **Ścieżki mobilne** (spec sekcja 5): `POST /offers/<token>/validate-cart`,
   `POST /offers/<token>/place-order-preorder`. Brak konfliktu routingu z E3 (`reserve`/`release`/
   `extend`/`place-order` — różne literalne sufiksy; `place-order` ≠ `place-order-preorder`).
2. **Kwoty w groszach (int).** Web `/restore` zwraca `price` w PLN (float) — mobile `validate-cart`
   zwraca **grosze** (parytet z E1–E3). `place-order-preorder`: `total` w groszach.
3. **`page_type` jako dyskryminator (ODWROTNOŚĆ E3).** Oba endpointy E4 są **preorder-only**: dla
   `page_type != 'preorder'` (czyli `exclusive`) → `400 wrong_page_type` (E3 place-order odrzucał
   `preorder` tym samym kodem). Symetria kontraktu.
4. **Bramka strony — parytet z E3.** `draft` → `404 page_not_found` (niepubliczny, jak detail/reserve/
   place-order). `place-order-preorder`: dodatkowo `not is_active → 403 page_not_active` (parytet z
   webowym `place_order` i mobilnym exclusive). `validate-cart`: **bez bramki `is_active`** — patrz D1.
5. **`validate-cart` raportuje odrzucone pozycje** (rozszerzenie względem webowego `/restore`, które
   odpada po cichu) — patrz Decyzja **D2**. Pole `quantity` = ilość ZAMAWIANA (parytet z webem).
6. **`Idempotency-Key`** obejmuje `POST /offers/<token>/place-order-preorder` (trzecia mutacja
   składająca zamówienie, po `checkout` E2 i `place-order` E3). Mechanizm bez zmian (claim-first,
   opcjonalny, TTL 48h).
7. **Odpowiedź `place-order-preorder`** = `{order_id, order_number (PO/...), total (grosze),
   items_count}` — bez `items` GA, bez `session['last_order_data']` (web-only), parytet z mobilnym
   exclusive.

---

## Decyzje — ROZSTRZYGNIĘTE przez Konrada 2026-06-12 (wszystkie wg rekomendacji)

> **D1:** validate-cart BEZ bramki is_active (parytet z web /restore). **D2:** odpowiedź
> `cart_items` + `removed[{product_id, reason}]`. **D3:** dedup wyłącznie przez opcjonalny
> Idempotency-Key (parytet z webem — wiele pre-orderów na stronę legalne; bez guardu).

## Decyzje do podjęcia przez Konrada (prawdziwe rozgałęzienia — NIE rozstrzygam arbitralnie)

- **D1 — Bramka `is_active` dla `validate-cart`.** `validate-cart` to operacja walidacyjna (read-only,
  zero mutacji). (a) **BEZ bramki `is_active`** (proponowane): waliduje koszyk niezależnie od statusu
  strony (parytet z webowym `/restore`, które nie bramkuje; pozwala apce wstępnie sprawdzić koszyk
  zanim strona przejdzie w `active`); odrzuca tylko `draft` (404) i `exclusive` (`wrong_page_type`).
  (b) bramka `is_active → 403` (walidacja tylko na żywej stronie — spójność z `place-order-preorder`,
  ale apka nie zwaliduje koszyka na `upcoming`/`closed`). **Rekomendacja: (a).**
- **D2 — Odpowiedź `validate-cart` na pozycje nieprawidłowe.** Web `/restore` odpada nieaktywne/
  nieistniejące po cichu (zwraca tylko poprawne). (a) **zwróć `cart_items` (poprawne, wzbogacone) +
  `removed: [{product_id, reason: 'not_found'|'inactive'}]`** (proponowane — apka wie, które pozycje
  usunąć z lokalnego koszyka i czemu); (b) ściśle jak web — tylko `cart_items` (poprawne), apka sama
  diffuje swój koszyk. **Rekomendacja: (a)** (lepszy UX synchronizacji koszyka, niski koszt).
- **D3 — Dedup `place-order-preorder` BEZ nagłówka `Idempotency-Key` (najważniejsza).**
  `place_preorder_order` **nie ma** double-submit guard (web pozwala na wiele pre-orderów na tę samą
  stronę). Mobilny exclusive (E3) zwraca `already_placed` bez klucza dzięki guardowi serwisu —
  pre-order tej symetrii nie ma.
  - **(a) tylko `Idempotency-Key`** (proponowane, bez zmian serwisu): apka wysyła klucz dla
    bezpiecznego retry; brak klucza = zachowanie jak web (powtórny POST tworzy DRUGIE zamówienie).
    Parytet z webem, najprościej, nie blokuje świadomego drugiego pre-orderu. Replay z kluczem →
    to samo zamówienie (objęte `@idempotent`).
  - **(b) mobilny guard (param `dedup_user_page=True` tylko z trasy mobilnej, wzorem `bind_user` z
    E3)**: przed utworzeniem zamówienia szuka istniejącego nieanulowanego `Order(pre_order)` dla
    `user+page` → zwraca `already_placed` (200). Daje symetrię z exclusive bez zmiany weba (domyślnie
    off). **Wada:** blokuje świadomy drugi pre-order z apki (rozjazd mobile vs web).
  - **(c) globalny guard** (zmienia zachowanie produkcyjnego weba — **NIE rekomendowane**, blokuje
    legalne wielokrotne pre-ordery).
  - **Rekomendacja: (a)** — `Idempotency-Key` to właściwy mechanizm dedup (już w kontrakcie),
    zachowuje parytet z webem i nie blokuje wielu pre-orderów. (b) tylko jeśli Konrad chce twardej
    symetrii „jedno zamówienie pre-order na stronę z apki".

> **Te decyzje wpływają na Task 1 (D3 → ewentualny param serwisu), Task 2 (D1/D2 → kształt odpowiedzi)
> i Task 3 (D3 → ewentualny `already_placed`). Rozstrzygnąć PRZED implementacją odnośnych tasków.**
> Poniższe taski zapisano wg rekomendacji (D1=a, D2=a, D3=a); jeśli Konrad wybierze inaczej —
> dopisz wskazane warianty (oznaczone „[D3=(b)]" itd.).

---

## File Structure

- `modules/offers/place_order.py` — Task 1: `place_preorder_order(..., user=None)`, zamiana
  `current_user` (l. 793/916/956/982), owinięcie `commit` (hardening). [D3=(b): param `dedup_user_page`].
- `modules/offers/routes.py` — Task 1: web `place_order` (l. 733) przekazuje
  `user=current_user._get_current_object()`.
- `modules/api_mobile/offers_routes.py` — Task 2 (`validate-cart`) + Task 3 (`place-order-preorder`).
- `tests/test_offers_preorder_service.py` — NOWY (Task 1): testy serwisu (pierwsze pokrycie).
- `tests/test_mobile_api_preorder.py` — NOWY (Task 2–3): testy tras mobilnych E4 (kopia `_auth`/
  helperów seedujących z `test_mobile_api_offers.py`).
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 4: korekty kontraktu E4.

---

### Task 1: Refaktor `place_preorder_order(user=...)` + hardening commit + parytet web + testy serwisu

**Files:** Modify `modules/offers/place_order.py`, `modules/offers/routes.py`;
Create `tests/test_offers_preorder_service.py`

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_offers_preorder_service.py`. Wołają serwis WPROST
  (bez HTTP), przekazując `user`:
```python
from decimal import Decimal


def _po_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='pre_order').first()
    if not ot:
        ot = OrderType(slug='pre_order', name='Pre-order', prefix='PO')
        db.session.add(ot); db.session.commit()
    return ot


def _preorder_page(db, payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Preorder Drop', token=OfferPage.generate_token(), status='active',
                  page_type='preorder', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def test_place_preorder_happy_path(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()  # created_by=1 istnieje
    page = _preorder_page(db, payment_stages=3)
    prod = make_product(sale_price=Decimal('50.00'))
    cart = [{'product_id': prod.id, 'quantity': 2}]

    ok, result = place_preorder_order(page=page, cart_items=cart, order_note='hej', user=user)

    assert ok is True
    order = Order.query.get(result['order_id'])
    assert order.order_type == 'pre_order'
    assert order.user_id == user.id
    assert order.payment_stages == 3
    assert order.status == 'nowe'
    assert order.order_number.startswith('PO/')
    assert float(order.total_amount) == 100.0
    assert result['items_count'] == 2
    assert OrderItem.query.filter_by(order_id=order.id).count() == 1


def test_place_preorder_empty_cart(db, make_user):
    from modules.offers.place_order import place_preorder_order
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    ok, result = place_preorder_order(page=page, cart_items=[], user=user)
    assert ok is False
    assert result['error'] == 'empty_cart'


def test_place_preorder_size_required(db, make_user, make_product):
    from modules.offers.place_order import place_preorder_order
    from modules.products.models import Size
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    size = Size(name='M'); db.session.add(size); db.session.commit()
    prod.sizes.append(size); db.session.commit()
    cart = [{'product_id': prod.id, 'quantity': 1}]  # brak selected_size
    ok, result = place_preorder_order(page=page, cart_items=cart, user=user)
    assert ok is False
    assert result['error'] == 'size_required'
    assert result['product_name'] == prod.name


def test_place_preorder_bonus_quantity_threshold(db, make_user, make_product):
    """Sekcja 'bonus' + trigger quantity_threshold: kup >=2 szt → +1 gratis (is_bonus)."""
    from modules.offers.place_order import place_preorder_order
    from modules.offers.models import OfferSection, OfferSetBonus
    from modules.orders.models import Order, OrderItem
    _po_order_type(db)
    user = make_user(); make_user()
    page = _preorder_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    gift = make_product(sale_price=Decimal('5.00'))
    sec = OfferSection(offer_page_id=page.id, section_type='bonus', sort_order=0)
    db.session.add(sec); db.session.commit()
    bonus = OfferSetBonus(section_id=sec.id, trigger_type='quantity_threshold',
                          threshold_value=Decimal('2'), bonus_product_id=gift.id,
                          bonus_quantity=1, repeatable=False, is_active=True,
                          when_exhausted='hide')
    db.session.add(bonus); db.session.commit()
    cart = [{'product_id': prod.id, 'quantity': 2}]

    ok, result = place_preorder_order(page=page, cart_items=cart, user=user)

    assert ok is True
    order = Order.query.get(result['order_id'])
    bonus_items = OrderItem.query.filter_by(order_id=order.id, is_bonus=True).all()
    assert len(bonus_items) == 1
    assert bonus_items[0].product_id == gift.id
    assert bonus_items[0].quantity == 1
    assert result['items_count'] == 2  # bonus nie wlicza się do items_count
```
> **UWAGA:** Pola `OfferSetBonus` (`when_exhausted`, `max_available` nullable) zweryfikuj przy RED —
> jeśli `when_exhausted` ma NOT NULL bez defaultu, ustaw `'hide'` (jak wyżej); jeśli test bonusu jest
> kruchy, można go pominąć (pozostają 3 testy serwisu — happy/empty/size). Run:
> `python -m pytest tests/test_offers_preorder_service.py -v` → FAIL (`place_preorder_order` nie
> przyjmuje `user`).

- [ ] **Step 2: Refaktor `place_preorder_order`** (`modules/offers/place_order.py`):
  - Sygnatura: `def place_preorder_order(page, cart_items, order_note=None, user=None):`.
  - Na początku funkcji (po docstringu / przed walidacją koszyka):
    `if user is None: from flask_login import current_user as _cu; user = _cu._get_current_object()`
    (backward-compat dla ścieżek bez `user`).
  - Zamień WSZYSTKIE `current_user` → `user`: l. 793 (`user_id=user.id`), l. 916
    (`log_activity(user=user, ...)`), l. 956 (`f'{user.first_name} {user.last_name}'.strip() or
    user.email` — w bloku Socket.IO), l. 982 (`AchievementService().check_event(user, ...)`).
  - **HARDENING — owiń commit** (l. 910–911), symetria z `place_offer_order` (l. 604–614); chroni
    przed zaklinowaniem klucza idempotency przy błędzie bazy:
```python
    # 6. Update total
    order.total_amount = total_amount
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return False, {'error': 'database_error', 'message': str(e)}
```
  - **[Opcjonalnie — gap obserwowalności]** wyrównaj 4 bloki POST-commit z `except Exception: pass`
    do logowania jak w `place_offer_order` (`current_app.logger.exception(...)`). Nie zmienia
    zachowania, poprawia diagnostykę. **Niewymagane do GREEN.**
  - **[D3=(b) tylko jeśli Konrad wybierze guard]** dodaj param `dedup_user_page=False` i — gdy `True` —
    przed `generate_order_number` sprawdź istniejące zamówienie:
    ```python
    if dedup_user_page:
        existing = Order.query.filter_by(order_type='pre_order', offer_page_id=page.id,
                                         user_id=user.id).order_by(Order.created_at.desc()).first()
        if existing and existing.status != 'anulowane':
            return True, {'order_id': existing.id, 'order_number': existing.order_number,
                          'total_amount': float(existing.total_amount),
                          'items_count': len([i for i in existing.items if not i.is_bonus]),
                          'already_placed': True}
    ```
  - **NIE dotykaj** `place_offer_order` (E3, gotowe).
- [ ] **Step 3: Parytet web** — `modules/offers/routes.py::place_order` (l. 733) zmień na:
  `success, result = place_preorder_order(page=page, cart_items=cart_items, order_note=order_note,
  user=current_user._get_current_object())`.
- [ ] **Step 4: GREEN + regresja** — `python -m pytest tests/test_offers_preorder_service.py -v`
  oraz `python -m pytest -q` (235 + nowe, zero failów; web pre-order nietknięty behawioralnie).
- [ ] **Step 5: Commit** — `git commit -m "refactor(offers): place_preorder_order przyjmuje user
  (parytet web+mobile) + hardening commit + testy serwisu"`

---

### Task 2: Mobile — `POST /offers/<token>/validate-cart`

**Files:** Modify `modules/api_mobile/offers_routes.py`; Create `tests/test_mobile_api_preorder.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_preorder.py` (kopia `_auth`; helpery
  `_preorder_page`/`_exclusive_page`):
```python
"""Testy E4: mobilne API pre-order (validate-cart + place-order-preorder).

Helper _auth skopiowany z tests/test_mobile_api_offers.py.
"""


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _preorder_page(db, status='active', payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name=f'PO {status}', token=OfferPage.generate_token(), status=status,
                  page_type='preorder', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _exclusive_page(db, status='active'):
    from modules.offers.models import OfferPage
    p = OfferPage(name=f'EX {status}', token=OfferPage.generate_token(), status=status,
                  page_type='exclusive', payment_stages=4, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def test_validate_cart_requires_token(client, db, make_user):
    page = _preorder_page(db)
    assert client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart',
                       json={'cart_items': []}).status_code == 401


def test_validate_cart_filters_invalid_and_grosze(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    page = _preorder_page(db)
    active = make_product(sale_price='50.00')
    inactive = make_product(sale_price='30.00'); inactive.is_active = False; db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': [
                        {'product_id': active.id, 'quantity': 2},
                        {'product_id': inactive.id, 'quantity': 1},
                        {'product_id': 999999, 'quantity': 1},
                    ]})
    assert r.status_code == 200
    d = r.get_json()['data']
    assert [i['product_id'] for i in d['cart_items']] == [active.id]
    assert d['cart_items'][0]['price'] == 5000      # grosze
    assert d['cart_items'][0]['quantity'] == 2      # ilość zamawiana
    # D2(a): odrzucone raportowane
    removed = {x['product_id']: x['reason'] for x in d['removed']}
    assert removed.get(inactive.id) == 'inactive'
    assert removed.get(999999) == 'not_found'


def test_validate_cart_wrong_page_type(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _exclusive_page(db)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'wrong_page_type'


def test_validate_cart_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _preorder_page(db, status='draft')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/validate-cart', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'
```
> Jeśli **D1=(b)** (bramka is_active) — dopisz `test_validate_cart_inactive_page_403`. Jeśli
> **D2=(b)** (bez `removed`) — usuń asercje `removed` i pole z implementacji.

- [ ] **Step 2: Implementacja** — w `modules/api_mobile/offers_routes.py` (NIE reużywamy `_brief` —
  inne znaczenie `quantity`):
```python
@api_mobile_bp.route('/offers/<token>/validate-cart', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_validate_cart(token):
    """Walidacja koszyka pre-order (koszyk żyje w apce jak localStorage w webie).

    Pre-order-only (wrong_page_type dla exclusive). Sprawdza istnienie i aktywność produktów;
    zwraca poprawne pozycje (cena→grosze) + listę odrzuconych. Bez bramki is_active (D1a) —
    parytet z webowym /restore; odrzuca tylko draft (404). Zero mutacji → bez idempotency.
    """
    from modules.products.models import Product
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type != 'preorder':
        return json_err('wrong_page_type',
                        'Walidacja koszyka dotyczy tylko stron pre-order.', 400)
    if page.status == 'draft':                  # niepubliczny — parytet z detail/place-order
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    items = body.get('cart_items') or []
    valid, removed = [], []
    for it in items:
        pid = it.get('product_id')
        qty = it.get('quantity', 1)
        product = Product.query.get(pid) if pid else None
        if product and product.is_active:
            img = product.primary_image
            entry = {
                'product_id': product.id,
                'name': product.name,
                'sku': product.sku,
                'price': to_grosze(product.sale_price),     # grosze
                'quantity': qty,                            # ilość zamawiana (parytet z webem)
                'image_url': absolute_static_url(img.path_compressed) if img else None,
                'sizes': [s.name for s in product.sizes],
            }
            if it.get('selected_size') is not None:
                entry['selected_size'] = it.get('selected_size')
            valid.append(entry)
        else:
            removed.append({'product_id': pid,
                            'reason': 'not_found' if product is None else 'inactive'})
    return json_ok({'cart_items': valid, 'removed': removed})
```
> Trasa dopisana do `offers_routes.py` (ten sam moduł co E3 — `absolute_static_url`/`to_grosze`/
> `json_*` już zaimportowane). `from . import offers_routes` w `__init__.py` już jest (E3).
- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_preorder.py -v`.
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): walidacja koszyka pre-order (validate-cart)"`

---

### Task 3: Mobile — `POST /offers/<token>/place-order-preorder` (+ @idempotent)

**Files:** Modify `modules/api_mobile/offers_routes.py`; Test `tests/test_mobile_api_preorder.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_preorder.py`:
```python
def _po_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='pre_order').first()
    if not ot:
        ot = OrderType(slug='pre_order', name='Pre-order', prefix='PO')
        db.session.add(ot); db.session.commit()
    return ot


def test_place_preorder_requires_token(client, db, make_user):
    page = _preorder_page(db)
    assert client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder',
                       json={'cart_items': []}).status_code == 401


def test_place_preorder_happy_path(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active', payment_stages=3)
    prod = make_product(sale_price='50.00')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': prod.id, 'quantity': 2}],
                          'order_note': 'proszę szybko'})
    assert r.status_code == 201
    d = r.get_json()['data']
    assert d['order_number'].startswith('PO/')
    assert d['total'] == 10000          # grosze
    assert d['items_count'] == 2


def test_place_preorder_wrong_page_type_400(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _exclusive_page(db, status='active')   # exclusive aktywny → wrong_page_type (przed is_active)
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'wrong_page_type'


def test_place_preorder_page_not_active_403(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='ended')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'page_not_active'


def test_place_preorder_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _preorder_page(db, status='draft')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': [{'product_id': 1, 'quantity': 1}]})
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'page_not_found'


def test_place_preorder_empty_cart_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=h,
                    json={'cart_items': []})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'empty_cart'


def test_place_preorder_idempotent_replay(client, db, make_user, make_product):
    # Bez guardu pre-order (D3a) drugi POST bez klucza tworzyłby drugie zamówienie —
    # dlatego dedup testujemy przez Idempotency-Key.
    h, _ = _auth(client, db, make_user)
    _po_order_type(db)
    page = _preorder_page(db, status='active')
    prod = make_product(sale_price='50.00')
    hk = {**h, 'Idempotency-Key': 'po-idem-123'}
    body = {'cart_items': [{'product_id': prod.id, 'quantity': 1}]}
    r1 = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=hk, json=body)
    assert r1.status_code == 201
    oid1 = r1.get_json()['data']['order_id']
    r2 = client.post(f'/api/mobile/v1/offers/{page.token}/place-order-preorder', headers=hk, json=body)
    assert r2.status_code == 201
    assert r2.get_json()['data']['order_id'] == oid1
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='pre_order').count() == 1
```
> **[D3=(b)]** dopisz `test_place_preorder_already_placed_without_key` (dwa POST-y bez klucza →
> drugi 200 z `already_placed: true`, jedno zamówienie w bazie) i przekaż `dedup_user_page=True`
> z trasy.

- [ ] **Step 2: Implementacja** — w `modules/api_mobile/offers_routes.py` (idempotency POD
  `@jwt_required`; bramki = ODWROTNOŚĆ E3; kwoty→grosze; bez `items` GA):
```python
from modules.auth.models import User          # już zaimportowane w E3
from .idempotency import idempotent            # już zaimportowane w E3

_PREORDER_ERR_STATUS = {
    'empty_cart': 400,
    'size_required': 400,
    'order_number_failed': 500,
    'database_error': 500,
    'server_error': 500,
}


@api_mobile_bp.route('/offers/<token>/place-order-preorder', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('offer_place_order_preorder')
def offer_place_order_preorder(token):
    """Złożenie zamówienia pre-order (koszyk z body, brak rezerwacji).

    Bramka (parytet/odwrotność E3): page_not_found 404 → exclusive → wrong_page_type 400 →
    draft 404 → not is_active → 403 page_not_active. Idempotency-Key (opcjonalny) gwarantuje
    jednokrotne złożenie. Serwis sam emituje Socket.IO i wysyła maile/push (apka webowa +
    dashboard LIVE muszą zobaczyć zamówienie z telefonu).
    """
    from modules.offers.place_order import place_preorder_order
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type != 'preorder':
        return json_err('wrong_page_type',
                        'Ta strona obsługiwana jest osobnym endpointem (exclusive).', 400)
    if page.status == 'draft':                  # niepubliczny — parytet z detail/place-order
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if not page.is_active:
        return json_err('page_not_active', 'Sprzedaż nie jest aktywna.', 403)
    body = request.get_json(silent=True) or {}
    cart_items = body.get('cart_items') or []
    if not cart_items:
        return json_err('empty_cart', 'Koszyk jest pusty.', 400)
    order_note = body.get('order_note')
    user = User.query.get(int(get_jwt_identity()))
    if user is None:                            # spójnie z konwencją /auth/me
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    ok, result = place_preorder_order(page=page, cart_items=cart_items,
                                      order_note=order_note, user=user)  # [D3=(b): dedup_user_page=True]
    if not ok:
        code = result.get('error', 'place_order_failed')
        status = _PREORDER_ERR_STATUS.get(code, 400)
        details = {k: result[k] for k in ('product_name',) if k in result}
        payload = {'code': code, 'message': result.get('message', '')}
        if details:
            payload['details'] = details
        return jsonify({'success': False, 'error': payload}), status
    data = {
        'order_id': result['order_id'],
        'order_number': result['order_number'],
        'total': to_grosze(result['total_amount']),
        'items_count': result['items_count'],
    }
    if result.get('already_placed'):            # tylko gdy D3=(b)
        data['already_placed'] = True
        return json_ok(data, 200)
    return json_ok(data, 201)
```
> **UWAGA:** `place_preorder_order` sam emituje Socket.IO i wysyła maile/push (jak na webie) — to
> ZAMIERZONE (apka webowa i admin LIVE muszą zobaczyć zamówienie z telefonu). W testach te ścieżki
> są owinięte try/except w serwisie i przechodzą (baseline 235 z exclusive happy-path je wykonuje).
- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_preorder.py -v`.
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): place-order pre-order (bonusy, idempotency)"`

---

### Task 4: Pełna regresja + aktualizacja specu + DoD

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** `python -m pytest tests/test_offers_preorder_service.py
  tests/test_mobile_api_preorder.py -v` oraz pełne `python -m pytest -q` — oczekiwane
  235 + ~14–16 nowych, zero failów (web pre-order/regresja nietknięte).
- [ ] **Step 2:** Spec — sekcja „Pre-order — koszyk lokalny + zamówienie": dopisz notę korekt E4:
  (a) ścieżki `validate-cart` / `place-order-preorder`; (b) kwoty w groszach (vs web PLN);
  (c) `page_type` dyskryminator — oba endpointy preorder-only, exclusive → `wrong_page_type` 400
  (odwrotność E3); (d) bramki: `draft` → 404, `place-order-preorder` `not is_active` → 403,
  `validate-cart` bez bramki is_active (D1); (e) `validate-cart` zwraca `cart_items` (grosze,
  `quantity`=zamawiana) + `removed` (D2); (f) `Idempotency-Key` obejmuje `place-order-preorder`;
  (g) decyzja D3 (dedup bez klucza). Zaznacz, że E4 domyka wszystkie trzy flow składania (on-hand
  E2, exclusive E3, pre-order E4).
- [ ] **Step 3:** Commit (`git add -f docs/...`) — `git commit -m "docs(mobile-api): korekty
  kontraktu E4 (pre-order: validate-cart, place-order-preorder)"`

---

## Definition of Done (E4)

- [ ] **Refaktor:** `place_preorder_order(user=...)` — `current_user` wyeliminowany z logiki (l. 793/
  916/956/982), web przekazuje `current_user._get_current_object()`, pełna regresja zielona BEZ
  modyfikacji istniejących testów; **pierwsze pokrycie testowe** (happy / empty_cart / size_required
  / bonus).
- [ ] **Hardening:** `commit` w `place_preorder_order` owinięty try/except → `database_error` (symetria
  z `place_offer_order`; błąd bazy nie klinuje klucza idempotency). [Opcjonalnie: wyrównanie logowania
  POST-commit — bloki już są owinięte, więc to tylko obserwowalność.]
- [ ] **validate-cart:** preorder-only (`wrong_page_type` dla exclusive), `draft` → 404, walidacja
  aktywności produktów, ceny w groszach, `quantity`=zamawiana, lista `removed` (D2), bez bramki
  is_active (D1), bez mutacji/idempotency. Za JWT, rate-limit 120/min.
- [ ] **place-order-preorder:** happy path (`PO/`, total grosze, items_count), `wrong_page_type` 400
  (exclusive), `page_not_active` 403, `draft` 404, `empty_cart` 400, idempotentny replay (jedno
  zamówienie); bonusy przez współdzielony serwis; emisje Socket.IO + maile/push zachowane (jak web).
  Za JWT, rate-limit 15/min, `@idempotent`.
- [ ] Wszystkie endpointy za JWT, kwoty w groszach, obrazki absolutne; parytet bramek z E3.
- [ ] **ZERO migracji** (head pozostaje `c72aad290158`); gdyby wymuszona zmiana modelu — migracja
  Flask-Migrate (nie spodziewane).
- [ ] Spec zaktualizowany o korekty kontraktu E4.
- [ ] Decyzje **D1–D3** rozstrzygnięte z Konradem PRZED implementacją odnośnych tasków (D3 wpływa na
  Task 1 + Task 3).
- [ ] Pełny `python -m pytest -q` zielony. **NIE pushować** — wdrożenia WSTRZYMANE decyzją Konrada.

## Szacunek liczby testów

- Serwis `place_preorder_order` (Task 1): ~3–4 (happy, empty_cart, size_required, [bonus]).
- validate-cart (Task 2): ~4 (requires_token, filters_invalid+grosze+removed, wrong_page_type, draft_404).
- place-order-preorder (Task 3): ~7 (requires_token, happy, wrong_page_type, page_not_active, draft_404,
  empty_cart, idempotent_replay) [+1 dla D3=(b)].
- **Razem: ~14–16 nowych testów.** Baseline po E4: **~249–251 passed** (start 235).

## Kolejność i bezpieczeństwo

Refaktor serwisu + hardening + parytet web najpierw (Task 1, pełna regresja chroni produkcyjny web
pre-order), potem read-walidacja `validate-cart` (Task 2, zero ryzyka — bez mutacji), na końcu
mutacja `place-order-preorder` (Task 3, na bazie sprawdzonego serwisu + `@idempotent`). Każdy task:
RED→GREEN→commit, pełna regresja przed mergem. Decyzje D1–D3 PRZED kodem (D3 zmienia Task 1 i Task 3).
**Bez push — produkcja nietknięta.**
