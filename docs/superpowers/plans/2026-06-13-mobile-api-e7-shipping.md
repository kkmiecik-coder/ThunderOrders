# Mobile API — Etap E7 (Wysyłka: adresy dostawy CRUD + zlecenia wysyłki) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Domknięcie warstwy WYSYŁKI mobilnego API — zarządzanie adresami dostawy (CRUD z soft-delete
i domyślnym adresem) oraz zlecenia wysyłki (lista, zamówienia gotowe do wysyłki, tworzenie, anulowanie).
Osiem endpointów (kontrakt ze specu sekcja 5, ścieżki pod prefiksem `/shipping/` — patrz Korekta 1):

```
GET    /shipping/addresses                          → moje adresy dostawy
POST   /shipping/addresses        { ... }           → dodaj
PATCH  /shipping/addresses/<id>/default             → ustaw domyślny
DELETE /shipping/addresses/<id>                     → usuń (soft, is_active=False)
GET    /shipping/requests                            → moje zlecenia wysyłki
GET    /shipping/requests/available-orders           → zamówienia gotowe do wysyłki
POST   /shipping/requests   { order_ids, address_id }→ utwórz zlecenie
POST   /shipping/requests/<id>/cancel                → anuluj (usuwa, gdy status początkowy)
```

E2 (checkout on-hand) zwracał już adresy w `GET /shop/checkout/summary` i tworzył `ShippingRequest`
przez `cart_service.place_order_on_hand(create_shipping, address_id)`. E7 dodaje **pełne zarządzanie**
adresami i zleceniami jako osobny kanał — pierwszy w tym API z PATCH-em i logicznym soft-delete.

**Architecture:** Trzy odkrycia kształtują plan:
1. **Cała logika wysyłki webowej jest INLINE w trasach** (`modules/client/shipping.py`, 8 tras,
   521 linii) — **ZERO serwisu, ZERO testów webowych** (zweryfikowane grep). To dokładnie sytuacja,
   którą wzorzec E2/E5/E6 rozwiązuje przez **ekstrakcję wspólnego serwisu + refaktor weba (bez zmiany
   zachowania) + parytet/smoke testy**. Logika tworzenia zlecenia jest nietrywialna (rozwiązywanie
   statusu początkowego z `Settings`, snapshot 11 pól adresu, mapowanie `delivery_method` z kuriera,
   notify email+push, log per zamówienie) — lokalna replika w mobile (~80 linii) byłaby rozjazdem.
   **Decyzja: PEŁNA EKSTRAKCJA** `modules/client/shipping_service.py` (adresy + zlecenia) + refaktor
   6 mutujących/odczytujących tras weba; fixtura `login` z conftest daje pierwsze smoke-testy weba.
2. **Model `ShippingRequest` KOPIUJE 11 pól adresu w momencie tworzenia (snapshot)** — `address_type`,
   5 pól `shipping_*`, 5 pól `pickup_*` (models.py:1296–1308). Dzięki temu **soft-delete adresu NIE
   psuje istniejących zleceń** (zlecenie nie trzyma FK do `ShippingAddress`, tylko junction do `Order`).
   To zdejmuje pytanie „czy adres używany w zleceniu można usunąć" — można zawsze (parytet web).
3. **`ShippingRequestOrder` (junction) jest naturalnym strażnikiem unikalności** — zamówienie już
   wpięte w jakiekolwiek zlecenie znika z „available-orders" i jest odrzucane przy tworzeniu nowego.
   To quasi-jedyność (bez UNIQUE constraint, więc nie transakcyjna) — patrz Decyzja D2 o `@idempotent`.

**Tech Stack:** Flask, flask-jwt-extended (JWT, bez sesji/CSRF), SQLAlchemy, Flask-Migrate (Alembic —
**ZERO migracji w E7**, head pozostaje `c72aad290158` — wszystkie modele istnieją), pytest (sqlite
in-memory), Flask-Limiter. Nowe pliki: `modules/api_mobile/shipping_routes.py`,
`modules/client/shipping_service.py`. Koperty `{success,data}`/`{success,error{code,message,details?}}`,
kwoty w **groszach (int)**, obrazy jako **absolutne URL-e**, daty **ISO** — spójne z E0–E6.

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Webowe trasy wysyłki (`modules/client/shipping.py`, prefix blueprintu `/client`) — WZORZEC DO EKSTRAKCJI
Pełne URL-e webowe: `/client/shipping/addresses`, `/client/shipping/addresses/add` (POST),
`/client/shipping/addresses/<id>/set-default` (POST), `/client/shipping/addresses/<id>/delete` (POST),
`/client/shipping/requests`, `/client/shipping/requests/list` (JSON), `/client/shipping/requests/available-orders`,
`/client/shipping/requests/create` (POST), `/client/shipping/requests/<id>/cancel` (POST).

**Adresy — walidacja i mutacje (l. 42–175):**
- `address_type ∈ {'home','pickup_point'}` (inne → 400 „Nieprawidłowy typ adresu").
- **home** wymaga: `shipping_name, shipping_address, shipping_postal_code, shipping_city` (puste →
  400 „Pole {field} jest wymagane"). Opcjonalne: `shipping_voivodeship`, `shipping_country` (default `'Polska'`).
- **pickup_point** wymaga: `pickup_courier, pickup_point_id, pickup_address, pickup_postal_code, pickup_city`.
- `name` (przyjazna nazwa) — zawsze opcjonalne. **Brak walidacji formatu** kodu/miasta (parytet: też brak).
- `is_default=True` → najpierw `UPDATE ... SET is_default=False WHERE user_id=? AND is_default=True`
  + `db.session.flush()`, potem nowy adres z `is_default=True` (l. 60–65).
- Po commicie: **achievement hook** `AchievementService().check_event(current_user, 'address_added')`
  (best-effort try/except, l. 106–111) — `'address_added'` to realny event (achievements/services.py:36).
- **set-default**: `first_or_404(id, user_id, is_active=True)` → clear innych → `is_default=True` → commit.
- **delete**: `first_or_404(id, user_id, is_active=True)` → `is_active=False` (SOFT) → commit. **Bez**
  sprawdzania użycia w zleceniu (snapshot — patrz Architecture pkt 2). `is_default` zostaje na martwym
  wierszu (nieszkodliwe — filtr `is_active=True` go pomija; default NIE jest reassignowany).

**Zlecenia — available-orders (l. 254–319):**
- `allowed_statuses` z `Settings.query.filter_by(key='shipping_request_allowed_statuses').first()` →
  `json.loads(value)` z fallbackiem `['dostarczone_gom']` (przy braku/błędzie parsowania).
- Zbiór: `Order.user_id == user` AND `Order.status IN allowed_statuses` AND `NOT EXISTS` w
  `ShippingRequestOrder` (l. 278–288), sort `created_at.desc()`.
- Serializacja per order: `id, order_number, total_amount(float), created_at('%d.%m.%Y'), items_count`
  + `items[]` (tylko `quantity > 0`): `name(product_name), selected_size, image_url(product_image_url),
  quantity, price(float)`.

**Zlecenia — create (l. 322–484):**
- Walidacja: `order_ids` niepuste (else 400 „Wybierz przynajmniej jedno zamówienie"); `address_id`
  obecny (else 400 „Wybierz adres dostawy").
- Re-czyt `allowed_statuses` (jak wyżej). Weryfikacja zamówień JEDNYM zapytaniem:
  `Order.id.in_(order_ids)` AND `user_id` AND `status IN allowed` AND `NOT in ShippingRequestOrder`;
  **`len(orders) != len(order_ids)` → 400** „Niektóre zamówienia są niedostępne lub już mają zlecenie".
- Adres: `filter_by(id, user_id, is_active=True).first()`; brak → 400 „Nieprawidłowy adres dostawy".
- **Status początkowy** (l. 383–400): `Settings['shipping_request_default_status']` →
  `ShippingRequestStatus.filter_by(slug=value, is_active=True)`; fallback `is_initial=True, is_active=True`;
  fallback pierwszy `is_active=True` po `sort_order`; ostateczny fallback string `'nowe'`.
- **Tworzenie**: `ShippingRequest(request_number=generate_request_number(), user_id, status=slug,
  address_type, + SNAPSHOT 11 pól adresu)` → flush.
- **delivery_method** (l. 425–437): home → `'kurier'`; pickup wg `pickup_courier.lower()`:
  inpost/paczkomat → `'paczkomat'`, orlen → `'orlen_paczka'`, dpd → `'dpd_pickup'` (inaczej None).
- Pętla: `ShippingRequestOrder(shipping_request_id, order_id)` per order; `order.delivery_method =
  delivery_method` **tylko gdy** `delivery_method and not order.delivery_method`.
- Commit → **log_activity per order** (`action='shipping_requested', entity_type='order',
  entity_id=order.id, new_value={request_number, order_number, address_type}`) →
  **notify** (best-effort): `EmailManager.notify_shipping_request_created(shipping_request, current_user)`
  + `PushManager.notify_admin_shipping_request(shipping_request)` (oba istnieją — zweryfikowane).
- Odpowiedź: `{success, message, request_number}`.

**Zlecenia — cancel (l. 487–520):**
- `filter_by(id, user_id).first()` (BEZ `is_active` — `ShippingRequest` nie ma soft-delete); brak → 404.
- `can_cancel` False → 400 „Nie można anulować zlecenia w tym statusie".
- `can_cancel` (property, models.py:1364–1383) = `status_rel.is_initial` AND `total_shipping_cost is None`
  AND `not tracking_number`. True → `db.session.delete(shipping_request)` (cascade kasuje
  `ShippingRequestOrder` → zamówienia wracają do „available"). **Bez** notify/log. Odpowiedź `{success, message}`.

### Modele (NIE wymagają migracji — wszystkie pola istnieją)
- **`ShippingAddress`** (auth/models.py:762+): `user_id, address_type, name, pickup_*(5), shipping_*(6),
  is_default(Bool,index), is_active(Bool,index), created_at, updated_at`. Properties: `display_name`,
  `full_address`. Relacja `user.shipping_addresses`.
- **`ShippingRequest`** (orders/models.py:1277+): snapshot 11 pól + `request_number(unique),
  total_shipping_cost(Numeric), tracking_number, courier, payment_deadline`. Properties: `orders`,
  `orders_count`, `status_badge_color`, `status_display_name`, `can_cancel`, `short_address`,
  `full_address`, `calculated_shipping_cost`(Decimal|None — suma `order.shipping_cost`), `tracking_url`.
  Classmethod `generate_request_number()` → `WYS/000001`. Relacja `request_orders` (cascade delete-orphan).
- **`ShippingRequestStatus`** (orders/models.py:1248+): `slug(unique), name, badge_color, sort_order,
  is_active, is_initial`. **`ShippingRequestOrder`** (1453+): junction `shipping_request_id, order_id,
  shipping_cost`.
- **`Order`**: `delivery_method`(String, l.183), `effective_grand_total`, `total_amount`, `items`,
  `items_count`, `status_display_name`, `status_badge_color`. **`OrderItem`**: `product_name,
  selected_size, product_image_url, quantity, price`.
- **`Settings.get_value(key, default)`** istnieje, ale konwertuje wg `setting.type` — webowy kod
  parsuje `shipping_request_allowed_statuses` RĘCZNIE (`json.loads`), więc serwis przenosi parsowanie
  **verbatim** (nie zakładamy że setting ma typ `json`).

### Infrastruktura mobilnego API (REUŻYWALNA — z E0–E6)
- `helpers.py`: `json_ok(data,status)`, `json_err(code,msg,status)`, `to_grosze(amount)` (None-safe),
  `absolute_static_url(path)`, `json_page(...)`. `validators.py`: `parse_int(...)`, `ValidationError`
  (errorhandler blueprintu → `400 invalid_input`). `idempotency.py`: `@idempotent('endpoint')` (POD
  `@jwt_required()`; claim-first; nagłówek `Idempotency-Key` opcjonalny).
- Konwencje: `@api_mobile_bp.route` → `@jwt_required()` → `@limiter.limit(...)` → (`@idempotent`);
  `int(get_jwt_identity())`; ownership → 404 maskujące (`_get_owned_order_or_404` w orders_routes.py:171);
  mapa kodów→status jak `_PLACE_ORDER_ERR_STATUS` (offers_routes.py:286) + `details` w kopercie błędu.
- E2 ma już lokalny `_serialize_address(a)` w `cart_routes.py:115` (PODZBIÓR pól, bez `is_default/
  display_name/full_address/created_at`) — używany TYLKO w checkout summary; **zostaje nietknięty**
  (E7 ma własny, bogatszy serializer; zmiana E2 = niepotrzebne ryzyko parytetu).
- Rejestracja tras: `modules/api_mobile/__init__.py` importuje moduły na końcu (`from . import
  payments_routes`); E7 dokłada `from . import shipping_routes`.

### Testy / fixtury / środowisko / migracje
- **Baseline: `323 passed`** (zweryfikowane 2026-06-13, ~55 s). TYLKO `source venv/bin/activate &&
  python -m pytest`.
- **Głowa migracji: `c72aad290158`** (zweryfikowane `flask db heads`). **ZERO migracji w E7.**
- conftest: fixtury `app`(function-scoped → świeży limiter per test; serie POSTów <limit),
  `db, client, make_user(role,email,**kw)`, `make_product(name,sale_price,quantity,**kw)`,
  `make_order(user,status='nowe',total_amount,created_at,**kw)`, **`login(user)`** (sesja Flask-Login).
- **Bramka klienta**: `client_bp.before_request` blokuje `profile_completed=False` → smoke-testy
  webowych tras klienta robić `make_user(profile_completed=True)` + `login(user)`.
- `log_activity(user=, action=, entity_type=, entity_id=, new_value=)` (utils/activity_logger.py).
- `/docs` w `.gitignore` → commit planu/tych zmian przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem + E1–E6 — zatwierdzane wraz z planem)

1. **Prefiks `/shipping/`** — spec listuje bare `/addresses`, `/requests` POD nagłówkiem sekcji
   „Wysyłka — `/shipping/`". Parytet z precedensem E2 (sekcja „Sklep — `/shop/`" → realne trasy
   `/shop/checkout/...`) i webem (`/client/shipping/...`). Realne trasy: `/api/mobile/v1/shipping/addresses`
   itd. Task 6 aktualizuje spec.
2. **Kwoty w groszach (int), obrazy absolutne URL-e, daty ISO** — parytet E1–E6: `total_shipping_cost`,
   `total_amount`, `price` w groszach; `image_url` absolutny; `created_at` ISO (web: float + `%d.%m.%Y`).
3. **POST `/shipping/addresses`** — body JSON parytet z webem: `address_type` (wymagane),
   per-typ wymagane pola (patrz fakty), `name`/`is_default` opcjonalne. Złe pola → `400 invalid_input`
   (+ `details.field` przy braku pola, + `details.allowed` przy złym typie). Zwraca utworzony adres (201).
4. **PATCH `/shipping/addresses/<id>/default`** — cudzy/nieistniejący/usunięty → `404 address_not_found`
   (maskowanie istnienia; web: 404 bez kodu). Zwraca zaktualizowany adres (drobne ulepszenie vs web
   „success" — apka odświeża listę bez re-GET).
5. **DELETE `/shipping/addresses/<id>`** — soft (`is_active=False`); cudzy/nieistniejący →
   `404 address_not_found`. Zawsze dozwolone (snapshot zleceń — Architecture pkt 2). `204`/`200 {deleted:true}`.
6. **GET `/shipping/requests`** — lista zleceń (BEZ paginacji — parytet web, zbiór mały), grosze + ISO,
   `orders[]` PEŁNA (web cappował do 3 w widoku listy; apka dostaje pełnię + `orders_count`).
7. **POST `/shipping/requests`** — body `{order_ids:[int], address_id:int}`. Rozróżnienie błędów
   (czytelniej niż webowy zbiorczy komunikat, maskowanie jak E5):
   - puste `order_ids` → `400 no_orders`; brak `address_id` → `400 no_address`;
   - id cudze/nieistniejące → `404 orders_not_found` + `details.missing_order_ids` (maskowanie);
   - id moje, ale zły status / już w zleceniu → `409 orders_not_available` + `details.unavailable_order_ids`
     (to MOJE zamówienia — ujawnienie niedostępności jest OK);
   - adres cudzy/nieaktywny → `404 address_not_found` (maskowanie).
   Wszystko **all-or-nothing** (parytet web). Web skleja `orders_not_found`+`orders_not_available` w
   jeden istniejący komunikat „Niektóre zamówienia są niedostępne lub już mają zlecenie" (bez zmiany
   zachowania). Sukces → `201 {request_id, request_number}`.
8. **POST `/shipping/requests/<id>/cancel`** — cudzy/nieistniejący → `404 request_not_found`; nie
   `can_cancel` → `409 cannot_cancel`. Sukces → `200 {cancelled:true}`. Bez efektów ubocznych (parytet).
9. **Efekty uboczne tworzenia zachowane w SERWISIE** (log_activity per order + email klienta + push
   admina + achievement przy dodaniu adresu) — jeden kod dla obu kanałów; admin widzi akcje z telefonu
   (wzorzec E3/E6).

---

## Decyzje — ROZSTRZYGNIĘTE samodzielnie (delegacja: parytet web → rekomendacja → bezpieczeństwo)

- **D1 — Pełna ekstrakcja `shipping_service.py` (adresy + zlecenia) + refaktor weba.** Web ma 0 serwisu
  i 0 testów; logika tworzenia zlecenia jest nietrywialna i divergence-prone — wzorzec E2/E5/E6 nakazuje
  wspólny serwis; refaktor weba mitygowany pierwszymi smoke-testami (fixtura `login`).
- **D2 — `@idempotent` NA `POST /shipping/requests` (TAK).** Tworzy `ShippingRequest`; duplikat jest
  szkodliwy (dwa zlecenia na te same zamówienia). Junction daje quasi-jedyność, ale read-then-write
  bez UNIQUE constraint NIE jest transakcyjnie szczelny (okno wyścigu). Wszystkie pozostałe mutacje
  TWORZĄCE w tym API (checkout, place-order, place-order-preorder) mają `@idempotent` — spójność +
  bezpieczeństwo. Retry tym samym kluczem zwraca zapisaną odpowiedź; retry bez klucza po sukcesie →
  `409 orders_not_available` (zamówienia już wpięte) — apka traktuje jako „już utworzone".
- **D3 — PATCH/DELETE/cancel BEZ `@idempotent`.** Naturalnie idempotentne (set-default → ten sam stan;
  soft-delete → ten sam stan; cancel → 404 przy powtórce). Dekorator dokładałby tylko pułapkę cache'u.
- **D4 — Soft-delete adresu zawsze dozwolony, default NIE reassignowany.** Parytet web; snapshot zleceń
  znosi referencyjne ryzyko; martwy `is_default=True` nieszkodliwy (filtr `is_active`).
- **D5 — Serwis dedupuje `order_ids` (set-based), web dziedziczy łagodniejszą obsługę duplikatów.**
  Web liczył `len(orders) != len(order_ids)` → zduplikowane id (np. `[5,5]`) dawały błąd. Set-based
  klasyfikacja serwisu traktuje `[5,5]` jak `[5]` (sukces). Różnica dotyczy WYŁĄCZNIE malformowanego
  wejścia nieosiągalnego z webowego UI (distinct checkboksy); pętla iteruje deduplikowany wynik
  zapytania, więc żadnego podwójnego `ShippingRequestOrder` — bezpieczne, udokumentowane (jak świadome
  różnice wyścigowe w E6).
- **D6 — E7 ma własny bogaty serializer adresu; E2 (`cart_routes._serialize_address`) nietknięty.**
  E2 to podzbiór do checkoutu; zmiana = ryzyko parytetu bez korzyści.

> **Do Konrada: BRAK rozgałęzień produktowych.** Cały zakres E7 jest jednoznacznym parytetem z
> istniejącym webem; powyższe to drobne decyzje techniczne rozstrzygnięte regułą delegacji.

---

## File Structure

- `modules/client/shipping_service.py` — **NOWY (serce E7)**: adresy (`list_active_addresses`,
  `validate_address_payload`, `create_address`, `set_default_address`, `soft_delete_address`) +
  zlecenia (`allowed_request_statuses`, `get_available_orders`, `validate_and_create_request`,
  `cancel_request`). Tasks 1, 3.
- `modules/client/shipping.py` — Tasks 1, 3: refaktor 6 tras webowych (3 adresy + available-orders +
  create + cancel) by wołać serwis — BEZ zmiany zachowania (parsowanie/serializacja/odpowiedzi zostają
  w trasie). Trasy HTML-only (`shipping_addresses`, `shipping_requests_list`) i `requests/list` (JSON)
  mogą wołać `list_active_addresses`/proste helpery — opcjonalnie, bez zmiany kształtu.
- `modules/api_mobile/shipping_routes.py` — **NOWY**: 8 tras mobilnych + serializery. Tasks 2, 4, 5.
- `modules/api_mobile/__init__.py` — Task 2: `from . import shipping_routes`.
- `tests/test_shipping_service.py` — **NOWY** (Tasks 1, 3): testy serwisu + smoke webowych tras (`login`).
- `tests/test_mobile_api_shipping.py` — **NOWY** (Tasks 2, 4, 5): testy tras mobilnych.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 6: korekty kontraktu E7.

---

### Task 1: `shipping_service.py` — ADRESY (ekstrakcja) + refaktor webowych tras adresów

**Files:** Create `modules/client/shipping_service.py`; modify `modules/client/shipping.py`;
Create `tests/test_shipping_service.py`

> Czysty refaktor + pierwsze pokrycie: webowe trasy adresów zachowują IDENTYCZNE zachowanie
> (komunikaty, is_default-clearing, achievement, soft-delete). Mobile podłączy się w Task 2.

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_shipping_service.py`:
```python
"""Testy serwisu wysyłki (ekstrakcja z webowych tras shipping.py — parytet)."""
from decimal import Decimal


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan Kowalski',
         'shipping_address': 'Główna 1', 'shipping_postal_code': '00-001',
         'shipping_city': 'Warszawa'}
    d.update(over)
    return d


def _pickup(**over):
    d = {'address_type': 'pickup_point', 'pickup_courier': 'InPost',
         'pickup_point_id': 'WAW001', 'pickup_address': 'Kwiatowa 2',
         'pickup_postal_code': '00-002', 'pickup_city': 'Warszawa'}
    d.update(over)
    return d


def test_validate_ok_home_and_pickup(db):
    from modules.client.shipping_service import validate_address_payload
    assert validate_address_payload(_home()) == (True, None)
    assert validate_address_payload(_pickup()) == (True, None)


def test_validate_bad_type(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload({'address_type': 'office'})
    assert not ok and err['code'] == 'invalid_address_type'


def test_validate_missing_home_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_home(shipping_city=''))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'shipping_city'


def test_validate_missing_pickup_field(db):
    from modules.client.shipping_service import validate_address_payload
    ok, err = validate_address_payload(_pickup(pickup_point_id=None))
    assert not ok and err['code'] == 'missing_field' and err['field'] == 'pickup_point_id'


def test_create_address_defaults_country_and_flushes_default(db, make_user):
    from modules.client.shipping_service import create_address
    from modules.auth.models import ShippingAddress
    u = make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Kraków', is_default=True))[2]
    db.session.refresh(a1)
    assert a2.is_default is True and a1.is_default is False     # clearing innych
    assert a2.shipping_country == 'Polska'                      # default kraju


def test_set_default_clears_others_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, set_default_address
    u, other = make_user(), make_user()
    a1 = create_address(u, _home(is_default=True))[2]
    a2 = create_address(u, _home(shipping_city='Gdańsk'))[2]
    ok, err, addr = set_default_address(u.id, a2.id)
    db.session.refresh(a1)
    assert ok and addr.id == a2.id and a2.is_default and not a1.is_default
    # cudzy adres → not_found (maskowanie)
    ok2, err2, _ = set_default_address(other.id, a1.id)
    assert not ok2 and err2['code'] == 'not_found'


def test_soft_delete_marks_inactive_and_owns(db, make_user):
    from modules.client.shipping_service import create_address, soft_delete_address
    u, other = make_user(), make_user()
    a = create_address(u, _home())[2]
    ok, err = soft_delete_address(other.id, a.id)               # cudzy
    assert not ok and err['code'] == 'not_found'
    ok2, _ = soft_delete_address(u.id, a.id)
    db.session.refresh(a)
    assert ok2 and a.is_active is False
    # ponowny soft-delete nieaktywnego → not_found (filtr is_active)
    ok3, err3 = soft_delete_address(u.id, a.id)
    assert not ok3 and err3['code'] == 'not_found'


def test_list_active_sorted_default_first(db, make_user):
    from modules.client.shipping_service import create_address, list_active_addresses, soft_delete_address
    u = make_user()
    a1 = create_address(u, _home())[2]
    a2 = create_address(u, _home(shipping_city='Łódź', is_default=True))[2]
    dead = create_address(u, _home(shipping_city='Poznań'))[2]
    soft_delete_address(u.id, dead.id)
    out = list_active_addresses(u.id)
    assert [a.id for a in out] == [a2.id, a1.id]                # default first, dead pominięty
```
> Plus **smoke webowych tras adresów** (fixtura `login`, `profile_completed=True` — bramka klienta):
```python
def test_web_address_add_route_parity_smoke(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert 'address_id' in r.get_json()


def test_web_address_add_missing_field_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/shipping/addresses/add', json=_home(shipping_city=''),
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and 'shipping_city' in r.get_json()['message']  # web message BEZ zmian


def test_web_address_set_default_and_delete_parity(client, db, make_user, login):
    from modules.client.shipping_service import create_address
    u = make_user(profile_completed=True); login(u)
    a = create_address(u, _home())[2]
    assert client.post(f'/client/shipping/addresses/{a.id}/set-default',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
    assert client.post(f'/client/shipping/addresses/{a.id}/delete',
                       headers={'X-Requested-With': 'XMLHttpRequest'}).status_code == 200
```
> Run: `source venv/bin/activate && python -m pytest tests/test_shipping_service.py -v` → FAIL (brak modułu).

- [ ] **Step 2: Implementacja serwisu (adresy)** — `modules/client/shipping_service.py` (NOWY):
```python
"""Wspólny serwis wysyłki — web (trasy shipping.py) + mobilne API (E7).

Logika przeniesiona 1:1 z modules/client/shipping.py (adresy + zlecenia). Serwis NIE importuje
nic z modules.api_mobile (brak cyklu). Funkcje zwracają (ok, err[, value]) — kanał serializuje.
"""

from extensions import db
from modules.auth.models import ShippingAddress

_HOME_REQUIRED = ['shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city']
_PICKUP_REQUIRED = ['pickup_courier', 'pickup_point_id', 'pickup_address',
                    'pickup_postal_code', 'pickup_city']


def validate_address_payload(data):
    """(True, None) lub (False, {'code': ...}). Parytet web l. 52-101."""
    atype = (data or {}).get('address_type')
    if atype not in ('home', 'pickup_point'):
        return False, {'code': 'invalid_address_type'}
    required = _HOME_REQUIRED if atype == 'home' else _PICKUP_REQUIRED
    for field in required:
        if not data.get(field):
            return False, {'code': 'missing_field', 'field': field}
    return True, None


def list_active_addresses(user_id):
    """Aktywne adresy usera, default first, potem najnowsze (parytet web l. 30-33)."""
    return ShippingAddress.query.filter_by(user_id=user_id, is_active=True).order_by(
        ShippingAddress.is_default.desc(), ShippingAddress.created_at.desc()).all()


def _clear_default(user_id):
    ShippingAddress.query.filter_by(user_id=user_id, is_default=True).update(
        {'is_default': False})
    db.session.flush()


def create_address(user, data):
    """(True, None, address). Zakłada walidację (validate_address_payload). Parytet web l. 44-117."""
    is_default = bool(data.get('is_default', False))
    if is_default:
        _clear_default(user.id)
    addr = ShippingAddress(user_id=user.id, address_type=data['address_type'],
                           is_default=is_default, name=data.get('name'))
    if data['address_type'] == 'pickup_point':
        for f in _PICKUP_REQUIRED:
            setattr(addr, f, data.get(f))
    else:
        for f in _HOME_REQUIRED:
            setattr(addr, f, data.get(f))
        addr.shipping_voivodeship = data.get('shipping_voivodeship')
        addr.shipping_country = data.get('shipping_country', 'Polska')
    db.session.add(addr)
    db.session.commit()
    try:                                                       # achievement hook (parytet l. 106-111)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'address_added')
    except Exception:
        pass
    return True, None, addr


def set_default_address(user_id, address_id):
    """(ok, err, address). Cudzy/nieaktywny → not_found (maskowanie). Parytet web l. 131-145."""
    addr = ShippingAddress.query.filter_by(id=address_id, user_id=user_id, is_active=True).first()
    if not addr:
        return False, {'code': 'not_found'}, None
    _clear_default(user_id)
    addr.is_default = True
    db.session.commit()
    return True, None, addr


def soft_delete_address(user_id, address_id):
    """(ok, err). is_active=False; cudzy/nieaktywny → not_found. Parytet web l. 161-169."""
    addr = ShippingAddress.query.filter_by(id=address_id, user_id=user_id, is_active=True).first()
    if not addr:
        return False, {'code': 'not_found'}
    addr.is_active = False
    db.session.commit()
    return True, None
```

- [ ] **Step 3: Refaktor webowych tras adresów** — `modules/client/shipping.py`:
  - `shipping_address_add()`: zachowaj `request.get_json()`; `ok, err = validate_address_payload(data)`
    → mapuj na ISTNIEJĄCE komunikaty (`invalid_address_type` → „Nieprawidłowy typ adresu";
    `missing_field` → `f"Pole {err['field']} jest wymagane"`), oba `400`; potem
    `_, _, address = create_address(current_user, data)`; odpowiedź `{success, message:'Adres został
    dodany', address_id: address.id}`. Achievement przeniesiony do serwisu — USUŃ z trasy.
  - `shipping_address_set_default()`: `ok, err, _ = set_default_address(current_user.id, address_id)`;
    `not ok` → `jsonify(success=False, message='...')` z 404 (web miał `first_or_404` → 404; zachowaj
    status 404, komunikat dowolny spójny). Sukces → `{success, message:'Adres ustawiony jako domyślny'}`.
  - `shipping_address_delete()`: `ok, _ = soft_delete_address(current_user.id, address_id)`; analogicznie.
  - (Opcjonalnie) `shipping_addresses()` HTML → `addresses = list_active_addresses(current_user.id)`.
  > Zachowaj `try/except` + `db.session.rollback()` w trasach (serwis robi commit; rollback przy
  > nieoczekiwanym wyjątku zostaje). Kształt odpowiedzi/statusy BEZ ZMIAN (smoke-testy to pilnują).

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_shipping_service.py -v` + pełny suite (0 regresji).
- [ ] **Step 5: Commit** — `git commit -m "refactor(shipping): ekstrakcja serwisu adresów dostawy (web parity + testy)"`

**DoD:** serwis adresów pokryty testami; 3 webowe trasy adresów wołają serwis bez zmiany zachowania
(smoke green); pełny suite zielony. **Szacunek: +13 testów** (10 serwis + 3 smoke web).

---

### Task 2: Mobilne trasy ADRESÓW — GET/POST/PATCH default/DELETE

**Files:** Create `modules/api_mobile/shipping_routes.py`; modify `modules/api_mobile/__init__.py`;
Create `tests/test_mobile_api_shipping.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_shipping.py`:
```python
"""Testy E7: mobilne API wysyłki (adresy CRUD + zlecenia). _auth jak w orders."""
import json
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login', json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _home(**over):
    d = {'address_type': 'home', 'shipping_name': 'Jan', 'shipping_address': 'Główna 1',
         'shipping_postal_code': '00-001', 'shipping_city': 'Warszawa'}
    d.update(over); return d


def test_addresses_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/shipping/addresses').status_code == 401


def test_post_then_get_addresses(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True), headers=h)
    assert r.status_code == 201
    a = r.get_json()['data']['address']
    assert a['is_default'] is True and a['shipping_country'] == 'Polska'
    assert set(a) >= {'id', 'address_type', 'name', 'display_name', 'full_address', 'is_default',
                      'shipping_name', 'pickup_courier', 'created_at'}
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert [x['id'] for x in lst] == [a['id']]


def test_post_address_bad_type(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json={'address_type': 'office'}, headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_post_address_missing_field_details(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city=''), headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['field'] == 'shipping_city'


def test_patch_default(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a1 = client.post('/api/mobile/v1/shipping/addresses', json=_home(is_default=True),
                     headers=h).get_json()['data']['address']
    a2 = client.post('/api/mobile/v1/shipping/addresses', json=_home(shipping_city='Kraków'),
                     headers=h).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a2["id"]}/default', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['address']['is_default'] is True
    lst = client.get('/api/mobile/v1/shipping/addresses', headers=h).get_json()['data']['addresses']
    assert {x['id']: x['is_default'] for x in lst}[a1['id']] is False


def test_patch_default_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h2
                    ).get_json()['data']['address']
    r = client.patch(f'/api/mobile/v1/shipping/addresses/{a["id"]}/default', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'address_not_found'


def test_delete_soft(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 200
    assert client.get('/api/mobile/v1/shipping/addresses', headers=h
                      ).get_json()['data']['addresses'] == []
    # powtórny delete → 404
    assert client.delete(f'/api/mobile/v1/shipping/addresses/{a["id"]}', headers=h).status_code == 404
```
> Run → FAIL (brak tras).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/shipping_routes.py` (NOWY):
```python
"""Trasy wysyłki (adresy + zlecenia) dla mobilnego API (E7)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.auth.models import User
from modules.client import shipping_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err
from .validators import parse_int


def _serialize_address(a):
    return {
        'id': a.id, 'address_type': a.address_type, 'name': a.name,
        'display_name': a.display_name, 'full_address': a.full_address,
        'is_default': bool(a.is_default),
        'shipping_name': a.shipping_name, 'shipping_address': a.shipping_address,
        'shipping_postal_code': a.shipping_postal_code, 'shipping_city': a.shipping_city,
        'shipping_voivodeship': a.shipping_voivodeship, 'shipping_country': a.shipping_country,
        'pickup_courier': a.pickup_courier, 'pickup_point_id': a.pickup_point_id,
        'pickup_address': a.pickup_address, 'pickup_postal_code': a.pickup_postal_code,
        'pickup_city': a.pickup_city,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    }


@api_mobile_bp.route('/shipping/addresses', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_addresses_list():
    addrs = svc.list_active_addresses(int(get_jwt_identity()))
    return json_ok({'addresses': [_serialize_address(a) for a in addrs]})


@api_mobile_bp.route('/shipping/addresses', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_create():
    data = request.get_json(silent=True) or {}
    ok, err = svc.validate_address_payload(data)
    if not ok:
        if err['code'] == 'invalid_address_type':
            return jsonify_invalid('Nieprawidłowy typ adresu.',
                                   {'allowed': ['home', 'pickup_point']})
        return jsonify_invalid(f"Pole {err['field']} jest wymagane.", {'field': err['field']})
    user = User.query.get(int(get_jwt_identity()))
    _, _, addr = svc.create_address(user, data)
    return json_ok({'address': _serialize_address(addr)}, 201)


@api_mobile_bp.route('/shipping/addresses/<int:address_id>/default', methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_set_default(address_id):
    ok, err, addr = svc.set_default_address(int(get_jwt_identity()), address_id)
    if not ok:
        return json_err('address_not_found', 'Adres nie istnieje.', 404)
    return json_ok({'address': _serialize_address(addr)})


@api_mobile_bp.route('/shipping/addresses/<int:address_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_address_delete(address_id):
    ok, err = svc.soft_delete_address(int(get_jwt_identity()), address_id)
    if not ok:
        return json_err('address_not_found', 'Adres nie istnieje.', 404)
    return json_ok({'deleted': True})


def jsonify_invalid(message, details):
    """400 invalid_input z details (koperta błędu jak _PLACE_ORDER_ERR)."""
    from flask import jsonify
    return jsonify({'success': False, 'error': {
        'code': 'invalid_input', 'message': message, 'details': details}}), 400
```
> Uwaga implementacyjna: `jsonify_invalid` definiuj na górze modułu (przeniesiony import `jsonify`)
> lub użyj istniejącego wzorca `details` w kopercie (offers_routes l. 332-337). Wybrano lokalny helper
> dla zwięzłości — przy implementacji rozważ przeniesienie do `helpers.py` jako `json_err(code, msg,
> status, details=None)` (addytywne, bez łamania E0-E6). **Decyzja techniczna do podjęcia przy
> implementacji** — rekomendacja: rozszerzyć `helpers.json_err` o opcjonalny `details` (czystsze niż
> lokalny helper, reużywalne w Task 5).

- [ ] **Step 3: Rejestracja** — `modules/api_mobile/__init__.py`, po `from . import payments_routes`:
  `from . import shipping_routes  # noqa: E402,F401`.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_shipping.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): adresy dostawy CRUD (GET/POST/PATCH default/DELETE)"`

**DoD:** 4 trasy adresów działają; ownership maskowany 404; walidacja z `details.field`; soft-delete
weryfikowalny przez ponowny 404. **Szacunek: +8 testów.**

---

### Task 3: `shipping_service.py` — ZLECENIA (ekstrakcja) + refaktor webowych tras zleceń

**Files:** Modify `modules/client/shipping_service.py`, `modules/client/shipping.py`,
`tests/test_shipping_service.py`

- [ ] **Step 1: Testy serwisu (RED)** — dopisz do `tests/test_shipping_service.py`:
```python
def _seed_status(db, slug='czeka_na_wycene', is_initial=True):
    from modules.orders.models import ShippingRequestStatus
    s = ShippingRequestStatus(slug=slug, name='Czeka na wycenę', is_active=True,
                              is_initial=is_initial, sort_order=0)
    db.session.add(s); db.session.commit()
    return s


def _allow(db, statuses=('dostarczone_gom',)):
    from modules.auth.models import Settings
    import json as _j
    Settings.set_value('shipping_request_allowed_statuses', _j.dumps(list(statuses)), type='json')


def test_get_available_orders_filters(db, make_user, make_order):
    from modules.client.shipping_service import get_available_orders, validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    ok = make_order(u, status='dostarczone_gom')
    make_order(u, status='nowe')                               # zły status → poza
    out = get_available_orders(u.id)
    assert [o.id for o in out] == [ok.id]
    # po wpięciu w zlecenie znika z available
    validate_and_create_request(u, [ok.id], _addr(db, u).id)
    assert get_available_orders(u.id) == []


def _addr(db, user):
    from modules.client.shipping_service import create_address
    return create_address(user, {'address_type': 'home', 'shipping_name': 'J',
                                  'shipping_address': 'A 1', 'shipping_postal_code': '00-001',
                                  'shipping_city': 'W'})[2]


def test_create_request_snapshots_and_delivery_method(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    a = _addr(db, u)
    ok, err, req = validate_and_create_request(u, [o.id], a.id)
    assert ok and req.request_number.startswith('WYS/')
    assert req.shipping_city == 'W' and req.address_type == 'home'   # snapshot
    db.session.refresh(o)
    assert o.delivery_method == 'kurier'                              # home → kurier


def test_create_request_foreign_order_404(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u, other = make_user(), make_user()
    foreign = make_order(other, status='dostarczone_gom')
    ok, err, _ = validate_and_create_request(u, [foreign.id], _addr(db, u).id)
    assert not ok and err['code'] == 'orders_not_found' and foreign.id in err['missing_order_ids']


def test_create_request_wrong_status_409(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='nowe')                          # mój, ale zły status
    ok, err, _ = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert not ok and err['code'] == 'orders_not_available' and o.id in err['unavailable_order_ids']


def test_create_request_bad_address_404(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    ok, err, _ = validate_and_create_request(u, [o.id], 99999)
    assert not ok and err['code'] == 'address_not_found'


def test_create_request_empty_inputs(db, make_user):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    assert validate_and_create_request(u, [], 1)[1]['code'] == 'no_orders'
    assert validate_and_create_request(u, [5], None)[1]['code'] == 'no_address'


def test_cancel_request_initial_only(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, cancel_request
    from modules.orders.models import ShippingRequest
    _seed_status(db); _allow(db)
    u, other = make_user(), make_user()
    o = make_order(u, status='dostarczone_gom')
    _, _, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    assert cancel_request(other.id, req.id)[1]['code'] == 'not_found'      # cudzy
    ok, _ = cancel_request(u.id, req.id)
    assert ok and ShippingRequest.query.get(req.id) is None               # usunięte
    # zamówienie wraca do available
    from modules.client.shipping_service import get_available_orders
    assert [x.id for x in get_available_orders(u.id)] == [o.id]


def test_cancel_request_blocked_after_quote(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, cancel_request
    from decimal import Decimal
    _seed_status(db); _allow(db)
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    _, _, req = validate_and_create_request(u, [o.id], _addr(db, u).id)
    req.total_shipping_cost = Decimal('25.00'); db.session.commit()       # admin wycenił
    ok, err = cancel_request(u.id, req.id)
    assert not ok and err['code'] == 'cannot_cancel'
```
> Plus smoke webowych tras zleceń (`login`, `profile_completed=True`):
```python
def test_web_request_create_and_cancel_parity(client, db, make_user, make_order, login):
    from modules.client.shipping_service import create_address
    _seed_status(db); _allow(db)
    u = make_user(profile_completed=True); login(u)
    o = make_order(u, status='dostarczone_gom')
    a = create_address(u, {'address_type': 'home', 'shipping_name': 'J', 'shipping_address': 'A 1',
                           'shipping_postal_code': '00-001', 'shipping_city': 'W'})[2]
    r = client.post('/client/shipping/requests/create',
                    json={'order_ids': [o.id], 'address_id': a.id},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert r.get_json()['request_number'].startswith('WYS/')


def test_web_request_create_foreign_rejected_parity(client, db, make_user, make_order, login):
    from modules.client.shipping_service import create_address
    _seed_status(db); _allow(db)
    u, other = make_user(profile_completed=True), make_user()
    login(u)
    foreign = make_order(other, status='dostarczone_gom')
    a = create_address(u, {'address_type': 'home', 'shipping_name': 'J', 'shipping_address': 'A 1',
                           'shipping_postal_code': '00-001', 'shipping_city': 'W'})[2]
    r = client.post('/client/shipping/requests/create',
                    json={'order_ids': [foreign.id], 'address_id': a.id},
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False     # web: zbiorczy komunikat
```
> Run → FAIL.

- [ ] **Step 2: Implementacja serwisu (zlecenia)** — dopisz do `shipping_service.py`:
```python
import json

from modules.orders.models import (
    Order, ShippingRequest, ShippingRequestOrder, ShippingRequestStatus)
from modules.auth.models import Settings
from utils.activity_logger import log_activity

_SNAPSHOT_FIELDS = ('shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city',
                    'shipping_voivodeship', 'shipping_country', 'pickup_courier', 'pickup_point_id',
                    'pickup_address', 'pickup_postal_code', 'pickup_city')


def allowed_request_statuses():
    """Verbatim z web l. 262-270 (NIE Settings.get_value — typ settingu niepewny)."""
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    if setting and setting.value:
        try:
            return json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            return ['dostarczone_gom']
    return ['dostarczone_gom']


def _orders_in_request_ids(order_ids):
    rows = ShippingRequestOrder.query.filter(ShippingRequestOrder.order_id.in_(order_ids)).all()
    return {r.order_id for r in rows}


def get_available_orders(user_id):
    """Zamówienia usera w dozwolonym statusie i bez aktywnego zlecenia (parytet web l. 277-288)."""
    allowed = allowed_request_statuses()
    from sqlalchemy import and_
    in_req = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id).exists()
    return Order.query.filter(and_(Order.user_id == user_id, Order.status.in_(allowed),
                                   ~in_req)).order_by(Order.created_at.desc()).all()


def _resolve_initial_status_slug():
    """Parytet web l. 383-400."""
    setting = Settings.query.filter_by(key='shipping_request_default_status').first()
    st = None
    if setting and setting.value:
        st = ShippingRequestStatus.query.filter_by(slug=setting.value, is_active=True).first()
    if not st:
        st = ShippingRequestStatus.query.filter_by(is_initial=True, is_active=True).first()
    if not st:
        st = ShippingRequestStatus.query.filter_by(is_active=True).order_by(
            ShippingRequestStatus.sort_order).first()
    return st.slug if st else 'nowe'


def _delivery_method_for(address):
    """Parytet web l. 425-437."""
    if address.address_type == 'home':
        return 'kurier'
    if address.address_type == 'pickup_point' and address.pickup_courier:
        c = address.pickup_courier.lower()
        if 'inpost' in c or 'paczkomat' in c:
            return 'paczkomat'
        if 'orlen' in c:
            return 'orlen_paczka'
        if 'dpd' in c:
            return 'dpd_pickup'
    return None


def validate_and_create_request(user, order_ids, address_id):
    """(ok, err, request). All-or-nothing; dedupe (D5). Parytet web l. 330-479 z rozbiciem kodów."""
    if not order_ids:
        return False, {'code': 'no_orders'}, None
    if not address_id:
        return False, {'code': 'no_address'}, None
    order_ids = list(dict.fromkeys(order_ids))                 # dedupe (D5)
    allowed = allowed_request_statuses()
    owned = {o.id: o for o in Order.query.filter(
        Order.id.in_(order_ids), Order.user_id == user.id).all()}
    missing = sorted(set(order_ids) - set(owned))
    if missing:
        return False, {'code': 'orders_not_found', 'missing_order_ids': missing}, None
    in_req = _orders_in_request_ids(order_ids)
    unavailable = sorted(oid for oid in order_ids
                         if owned[oid].status not in allowed or oid in in_req)
    if unavailable:
        return False, {'code': 'orders_not_available', 'unavailable_order_ids': unavailable}, None
    address = ShippingAddress.query.filter_by(
        id=address_id, user_id=user.id, is_active=True).first()
    if not address:
        return False, {'code': 'address_not_found'}, None

    req = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                          user_id=user.id, status=_resolve_initial_status_slug(),
                          address_type=address.address_type)
    for f in _SNAPSHOT_FIELDS:
        setattr(req, f, getattr(address, f))
    db.session.add(req)
    db.session.flush()
    dm = _delivery_method_for(address)
    orders = [owned[oid] for oid in order_ids]
    for order in orders:
        db.session.add(ShippingRequestOrder(shipping_request_id=req.id, order_id=order.id))
        if dm and not order.delivery_method:
            order.delivery_method = dm
    db.session.commit()
    for order in orders:                                       # log per order (parytet l. 453-464)
        log_activity(user=user, action='shipping_requested', entity_type='order',
                     entity_id=order.id,
                     new_value={'request_number': req.request_number,
                                'order_number': order.order_number,
                                'address_type': address.address_type})
    try:                                                       # notify (parytet l. 466-473)
        from flask import current_app
        from utils.email_manager import EmailManager
        from utils.push_manager import PushManager
        EmailManager.notify_shipping_request_created(req, user)
        PushManager.notify_admin_shipping_request(req)
    except Exception as e:
        from flask import current_app
        current_app.logger.error(f'Shipping request notify failed: {e}')
    return True, None, req


def cancel_request(user_id, request_id):
    """(ok, err). Cudzy/brak → not_found; nie can_cancel → cannot_cancel. Parytet web l. 493-515."""
    req = ShippingRequest.query.filter_by(id=request_id, user_id=user_id).first()
    if not req:
        return False, {'code': 'not_found'}
    if not req.can_cancel:
        return False, {'code': 'cannot_cancel'}
    db.session.delete(req)
    db.session.commit()
    return True, None
```

- [ ] **Step 3: Refaktor webowych tras zleceń** — `modules/client/shipping.py`:
  - `shipping_requests_available_orders()`: `orders = get_available_orders(current_user.id)`; pętla
    serializacji (total_amount float, `%d.%m.%Y`, items) ZOSTAJE w trasie. USUŃ inline settings-read.
  - `shipping_requests_create()`: zachowaj `data = request.get_json()`; `ok, err, req =
    validate_and_create_request(current_user, data.get('order_ids', []), data.get('address_id'))`;
    mapuj kody na ISTNIEJĄCE komunikaty/statusy: `no_orders` → 400 „Wybierz przynajmniej jedno
    zamówienie"; `no_address` → 400 „Wybierz adres dostawy"; `orders_not_found`/`orders_not_available`
    → 400 „Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki" (sklejone — parytet);
    `address_not_found` → 400 „Nieprawidłowy adres dostawy"; sukces → `{success, message, request_number:
    req.request_number}`. USUŃ inline logikę tworzenia/notify (w serwisie).
  - `shipping_requests_cancel()`: `ok, err = cancel_request(current_user.id, request_id)`; `not_found`
    → 404 „Zlecenie nie istnieje"; `cannot_cancel` → 400 „Nie można anulować zlecenia w tym statusie";
    sukces → `{success, message}`.
  - (Opcjonalnie) `shipping_requests_list_json()` / HTML listy → bez zmian (serializacja zostaje).
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_shipping_service.py -v` + pełny suite (0 regresji).
- [ ] **Step 5: Commit** — `git commit -m "refactor(shipping): ekstrakcja serwisu zleceń wysyłki (web parity + testy)"`

**DoD:** serwis zleceń pokryty (available/create/cancel + klasyfikacja błędów); 3 webowe trasy wołają
serwis bez zmiany zachowania (smoke green); pełny suite zielony. **Szacunek: +11 testów** (9 serwis + 2 smoke).

---

### Task 4: Mobilne trasy ODCZYTU zleceń — GET /requests, GET /requests/available-orders

**Files:** Modify `modules/api_mobile/shipping_routes.py`, `tests/test_mobile_api_shipping.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_shipping.py`:
```python
def _seed_status(db, slug='czeka_na_wycene', is_initial=True):
    from modules.orders.models import ShippingRequestStatus
    s = ShippingRequestStatus(slug=slug, name='Czeka na wycenę', is_active=True,
                              is_initial=is_initial, sort_order=0, badge_color='#6B7280')
    db.session.add(s); db.session.commit(); return s


def _allow(db, statuses=('dostarczone_gom',)):
    from modules.auth.models import Settings
    Settings.set_value('shipping_request_allowed_statuses', json.dumps(list(statuses)), type='json')


def test_available_orders_shape_and_grosze(client, db, make_user, make_order, make_product):
    from modules.orders.models import OrderItem
    h, u = _auth(client, db, make_user)
    _allow(db)
    o = make_order(u, status='dostarczone_gom', total_amount=Decimal('120.00'))
    p = make_product(sale_price=Decimal('60.00'))
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=2,
                             price=Decimal('60.00'), total=Decimal('120.00')))
    db.session.commit()
    r = client.get('/api/mobile/v1/shipping/requests/available-orders', headers=h)
    assert r.status_code == 200
    orders = r.get_json()['data']['orders']
    assert orders[0]['total_amount'] == 12000                 # grosze
    assert orders[0]['items'][0]['price'] == 6000


def test_requests_list_shape(client, db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, create_address
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = create_address(u, _home())[2]
    validate_and_create_request(u, [o.id], a.id)
    r = client.get('/api/mobile/v1/shipping/requests', headers=h)
    assert r.status_code == 200
    req = r.get_json()['data']['requests'][0]
    assert req['request_number'].startswith('WYS/')
    assert req['can_cancel'] is True and req['orders'][0]['id'] == o.id
    assert set(req) >= {'id', 'request_number', 'status', 'status_display_name',
                        'status_badge_color', 'address_type', 'short_address', 'full_address',
                        'total_shipping_cost', 'tracking_number', 'tracking_url', 'can_cancel',
                        'orders_count', 'orders', 'created_at'}


def test_requests_only_own(client, db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request, create_address
    h, u = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o2 = make_order(u2, status='dostarczone_gom')
    validate_and_create_request(u2, [o2.id], create_address(u2, _home())[2].id)
    assert client.get('/api/mobile/v1/shipping/requests', headers=h
                      ).get_json()['data']['requests'] == []
```
> Run → FAIL.

- [ ] **Step 2: Implementacja** — dopisz do `shipping_routes.py`:
```python
from .helpers import to_grosze


def _abs_image(path):
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_available_order(order):
    return {
        'id': order.id, 'order_number': order.order_number,
        'total_amount': to_grosze(order.total_amount),
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'items_count': order.items_count,
        'items': [{'name': it.product_name, 'selected_size': it.selected_size,
                   'image_url': _abs_image(it.product_image_url),
                   'quantity': it.quantity, 'price': to_grosze(it.price)}
                  for it in order.items if it.quantity > 0],
    }


def _serialize_request(req):
    return {
        'id': req.id, 'request_number': req.request_number, 'status': req.status,
        'status_display_name': req.status_display_name, 'status_badge_color': req.status_badge_color,
        'address_type': req.address_type, 'short_address': req.short_address,
        'full_address': req.full_address,
        'total_shipping_cost': to_grosze(req.calculated_shipping_cost),
        'tracking_number': req.tracking_number, 'tracking_url': req.tracking_url,
        'can_cancel': req.can_cancel, 'orders_count': req.orders_count,
        'orders': [{'id': o.id, 'order_number': o.order_number} for o in req.orders],
        'created_at': req.created_at.isoformat() if req.created_at else None,
    }


@api_mobile_bp.route('/shipping/requests/available-orders', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_available_orders():
    orders = svc.get_available_orders(int(get_jwt_identity()))
    return json_ok({'orders': [_serialize_available_order(o) for o in orders]})


@api_mobile_bp.route('/shipping/requests', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def shipping_requests_list():
    from modules.orders.models import ShippingRequest
    reqs = ShippingRequest.query.filter_by(user_id=int(get_jwt_identity())).order_by(
        ShippingRequest.created_at.desc()).all()
    return json_ok({'requests': [_serialize_request(r) for r in reqs]})
```
> `total_shipping_cost` = `to_grosze(req.calculated_shipping_cost)` (property zwraca Decimal|None;
> `to_grosze(None)` → None — bezpieczne). `available-orders` musi być ZAREJESTROWANE przed
> `<int:address_id>`-owymi trasami? Nie — to inny prefiks (`/shipping/requests/...`), brak kolizji.

- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_shipping.py -v`.
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): odczyt zleceń wysyłki + zamówienia gotowe do wysyłki"`

**DoD:** 2 trasy odczytu działają; grosze/ISO/abs URL; ownership (tylko własne zlecenia). **Szacunek: +4 testy.**

---

### Task 5: Mobilne MUTACJE zleceń — POST /requests (@idempotent), POST /requests/<id>/cancel

**Files:** Modify `modules/api_mobile/shipping_routes.py`, `tests/test_mobile_api_shipping.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_shipping.py`:
```python
def test_create_request_success(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 201
    body = r.get_json()['data']
    assert body['request_number'].startswith('WYS/') and 'request_id' in body
    # po utworzeniu zamówienie znika z available
    assert client.get('/api/mobile/v1/shipping/requests/available-orders', headers=h
                      ).get_json()['data']['orders'] == []


def test_create_request_empty_orders_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [], 'address_id': 1}, headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'no_orders'


def test_create_request_foreign_order_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    _seed_status(db); _allow(db)
    foreign = make_order(other, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [foreign.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'orders_not_found'
    assert foreign.id in r.get_json()['error']['details']['missing_order_ids']


def test_create_request_wrong_status_409(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='nowe')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': a['id']}, headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'orders_not_available'


def test_create_request_bad_address_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    r = client.post('/api/mobile/v1/shipping/requests',
                    json={'order_ids': [o.id], 'address_id': 99999}, headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'address_not_found'


def test_create_request_idempotency_key_replays(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    hk = dict(h); hk['Idempotency-Key'] = 'e7-key-1'
    body = {'order_ids': [o.id], 'address_id': a['id']}
    r1 = client.post('/api/mobile/v1/shipping/requests', json=body, headers=hk)
    r2 = client.post('/api/mobile/v1/shipping/requests', json=body, headers=hk)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.get_json() == r2.get_json()                     # odtworzona odpowiedź, brak 2. zlecenia
    from modules.orders.models import ShippingRequest
    assert ShippingRequest.query.filter_by(user_id=u.id).count() == 1


def test_cancel_request(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    a = client.post('/api/mobile/v1/shipping/addresses', json=_home(), headers=h
                    ).get_json()['data']['address']
    rid = client.post('/api/mobile/v1/shipping/requests',
                      json={'order_ids': [o.id], 'address_id': a['id']}, headers=h
                      ).get_json()['data']['request_id']
    r = client.post(f'/api/mobile/v1/shipping/requests/{rid}/cancel', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['cancelled'] is True
    # powtórny cancel → 404 (już usunięte)
    assert client.post(f'/api/mobile/v1/shipping/requests/{rid}/cancel',
                       headers=h).status_code == 404


def test_cancel_request_foreign_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o2 = make_order(u2, status='dostarczone_gom')
    from modules.client.shipping_service import validate_and_create_request, create_address
    _, _, req = validate_and_create_request(u2, [o2.id], create_address(u2, _home())[2].id)
    r = client.post(f'/api/mobile/v1/shipping/requests/{req.id}/cancel', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'request_not_found'


def test_cancel_blocked_after_quote_409(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    _seed_status(db); _allow(db)
    o = make_order(u, status='dostarczone_gom')
    from modules.client.shipping_service import validate_and_create_request, create_address
    _, _, req = validate_and_create_request(u, [o.id], create_address(u, _home())[2].id)
    req.total_shipping_cost = Decimal('25.00'); db.session.commit()
    r = client.post(f'/api/mobile/v1/shipping/requests/{req.id}/cancel', headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'cannot_cancel'
```
> Run → FAIL.

- [ ] **Step 2: Implementacja** — dopisz do `shipping_routes.py`:
```python
from .idempotency import idempotent

_CREATE_REQUEST_ERR_STATUS = {
    'no_orders': 400, 'no_address': 400,
    'orders_not_found': 404, 'orders_not_available': 409, 'address_not_found': 404,
}
_CREATE_REQUEST_ERR_MSG = {
    'no_orders': 'Wybierz przynajmniej jedno zamówienie.',
    'no_address': 'Wybierz adres dostawy.',
    'orders_not_found': 'Zamówienie nie istnieje.',
    'orders_not_available': 'Niektóre zamówienia są niedostępne lub już mają zlecenie wysyłki.',
    'address_not_found': 'Adres dostawy nie istnieje.',
}
_CREATE_REQUEST_ERR_DETAILS = {
    'orders_not_found': 'missing_order_ids', 'orders_not_available': 'unavailable_order_ids',
}


@api_mobile_bp.route('/shipping/requests', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('shipping_request_create')
def shipping_request_create():
    from flask import jsonify
    p = request.get_json(silent=True) or {}
    order_ids = p.get('order_ids') or []
    if not isinstance(order_ids, list):
        return json_err('invalid_input', 'Pole order_ids musi być listą.', 400)
    try:
        order_ids = [int(x) for x in order_ids]
    except (TypeError, ValueError):
        return json_err('invalid_input', 'Pole order_ids musi zawierać liczby.', 400)
    address_id = parse_int(p.get('address_id'), 'address_id', required=False)
    user = User.query.get(int(get_jwt_identity()))
    ok, err, req = svc.validate_and_create_request(user, order_ids, address_id)
    if not ok:
        code = err['code']
        payload = {'code': code, 'message': _CREATE_REQUEST_ERR_MSG[code]}
        dkey = _CREATE_REQUEST_ERR_DETAILS.get(code)
        if dkey and dkey in err:
            payload['details'] = {dkey: err[dkey]}
        return jsonify({'success': False, 'error': payload}), _CREATE_REQUEST_ERR_STATUS[code]
    return json_ok({'request_id': req.id, 'request_number': req.request_number}, 201)


@api_mobile_bp.route('/shipping/requests/<int:request_id>/cancel', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def shipping_request_cancel(request_id):
    ok, err = svc.cancel_request(int(get_jwt_identity()), request_id)
    if not ok:
        if err['code'] == 'not_found':
            return json_err('request_not_found', 'Zlecenie nie istnieje.', 404)
        return json_err('cannot_cancel', 'Nie można anulować zlecenia w tym statusie.', 409)
    return json_ok({'cancelled': True})
```
> **Idempotency:** `@idempotent` POD `@jwt_required()` (używa get_jwt_identity). Retry tym samym
> kluczem odtwarza zapisany `201`; retry bez klucza po sukcesie → `409 orders_not_available`
> (zamówienia wpięte) — apka odświeża (D2). **Heavy-write `15/min`** jak place-order.
> `order_ids` walidowane na `list[int]` PRZED serwisem (serwis ufa typom).

- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_shipping.py -v` + pełny suite (0 regresji).
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): tworzenie (idempotent) i anulowanie zleceń wysyłki"`

**DoD:** create (idempotent) + cancel działają; rozbicie błędów (404/409) + details; idempotency
replay weryfikowany (1 zlecenie po dwóch POST). **Szacunek: +9 testów.**

---

### Task 6: Aktualizacja specu (korekty kontraktu E7) + finalny suite

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** W sekcji „Wysyłka — `/shipping/`" dopisz notkę o korektach E7 (analogicznie do
  notek E2/E5/E6): prefiks `/shipping/`; grosze/ISO/abs URL; rozbicie błędów create
  (`no_orders`/`no_address` 400, `orders_not_found` 404, `orders_not_available` 409, `address_not_found`
  404, all-or-nothing); cancel (`request_not_found` 404, `cannot_cancel` 409); `@idempotent` na POST
  `/shipping/requests`; soft-delete adresu zawsze dozwolony (snapshot). W liście etapów (l. 371) oznacz
  **E7 jako ukończone**.
- [ ] **Step 2:** Pełny suite: `source venv/bin/activate && python -m pytest -q` → oczekiwane
  **323 + ~45 = ~368 passed**, zero regresji.
- [ ] **Step 3: Commit** — `git commit -m "docs(mobile-api): korekty kontraktu E7 (wysyłka)"`

**DoD:** spec odzwierciedla zaimplementowany kontrakt E7; cały suite zielony.

---

## Podsumowanie szacunków

| Task | Zakres | Nowe testy |
|------|--------|-----------|
| 1 | Serwis adresów + refaktor web | +13 |
| 2 | Mobilne trasy adresów (CRUD) | +8 |
| 3 | Serwis zleceń + refaktor web | +11 |
| 4 | Mobilny odczyt zleceń | +4 |
| 5 | Mobilne mutacje zleceń (idempotent) | +9 |
| 6 | Spec + finalny suite | 0 |
| **Razem** | | **~45** |

**Baseline przed E7: `323 passed`. Oczekiwane po E7: ~368 passed. Migracje: ZERO (head `c72aad290158`).**
