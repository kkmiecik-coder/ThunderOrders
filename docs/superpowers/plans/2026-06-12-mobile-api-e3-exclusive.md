# Mobile API — Etap E3 (Exclusive: oferty, rezerwacje, place-order) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Najtrudniejszy etap roadmapy mobilnego API — strony ofertowe (lista + pełna struktura),
snapshot dostępności, **system rezerwacji** (reserve/extend/release) oraz **place-order exclusive**
(sety, bonusy, atomowa walidacja anti-overselling) na żywym, produkcyjnym sklepie. Plus dwa
follow-upy z recenzji E2: **Idempotency-Key** dla mutacji składających zamówienia (checkout E2 +
place-order E3) oraz świadome odnotowanie długu testowego dla `with_for_update`/deadlock-retry.

**Architecture:** Logika rezerwacji i składania zamówień JUŻ JEST wyciągnięta z tras webowych do
warstwy serwisowej — `modules/offers/reservation.py` (reserve/extend/release/availability/section_max)
i `modules/offers/place_order.py` (place_offer_order). Trasy webowe (`modules/offers/routes.py`) są
cienkimi wrapperami. **Główny refaktor E3 to JEDNA zmiana:** `place_offer_order` sięga po
`flask_login.current_user` bezpośrednio — trzeba przekazać użytkownika jawnym parametrem `user`, by
mobile (JWT, bez sesji Flask-Login) mógł użyć tej samej funkcji. Reszta logiki rezerwacji jest już
context-agnostic (przyjmuje `user_id`, dostęp do `request` osłonięty try/except). Endpointy mobilne to
nowy plik `modules/api_mobile/offers_routes.py` — mapują wyniki serwisów na kopertę
`{success, data/error}`, kwoty w groszach, obrazki absolutne. Read-endpointy (lista/struktura) nie
mają webowego odpowiednika JSON (web renderuje HTML) — serializery projektujemy od zera (read-only,
niskie ryzyko). **Emisje Socket.IO** z tras webowych reserve/release MUSZĄ być powtórzone w trasach
mobilnych (apka webowa musi widzieć rezerwacje złożone z telefonu).

**Tech Stack:** Flask, flask-jwt-extended, SQLAlchemy (`with_for_update` + retry na deadlock 1213),
Flask-Migrate (Alembic), pytest (sqlite in-memory).

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Modele ofert (`modules/offers/models.py`)
- **`OfferPage`** (l. 44): `name`, `description`, `token` (unique, `generate_token()` =
  `secrets.token_urlsafe(16)`, lookup `OfferPage.get_by_token(token)` l. 354), `status` enum
  `offer_page_status` = **draft/scheduled/active/paused/ended** (l. 65), `page_type` enum
  `offer_page_type` = **exclusive/preorder** (l. 73), `starts_at`/`ends_at` (naive datetime PL),
  `payment_stages` (int, default 4; 3=do Polski, 4=proxy KR), `payment_deadline`, `footer_content`,
  `preview_enabled`, `is_fully_closed`, `closed_at`. Properties: `is_active`, `is_public`
  (`status != 'draft'`), `can_order` (`status == 'active'`), `check_and_update_status()` (auto
  scheduled→active / active→ended po datach; **commituje**). `sections` (lazy='dynamic',
  order_by sort_order). Czas: `get_local_now()` (naive PL, offset DST).
- **`OfferSection`** (l. 364): `section_type` enum `offer_section_type` =
  **heading/paragraph/product/set/variant_group/bonus** (l. 381), `sort_order`, `content` (heading/
  paragraph), `product_id`+`min_quantity`+`max_quantity` (product), `set_name`+`set_image`+
  `set_max_sets`+`set_max_per_product`+`set_product_id` (set), `variant_group_id` (variant_group).
  Relacje: `product`, `set_product`, `variant_group`, `set_items` (lazy='dynamic'), `bonuses`
  (z OfferSetBonus, lazy='dynamic'). Helpery: `is_*`, `is_orderable_section`, `get_set_items_ordered()`,
  `get_set_products()`, `get_variant_group_products()`.
- **`OfferSetItem`** (l. 496): `section_id`, `product_id` XOR `variant_group_id`, `quantity_per_set`
  (default 1), `sort_order`. `get_products()` → `[product]` lub aktywne produkty z grupy. `display_name`.
- **`OfferReservation`** (l. 562): `session_id` (String 36, UUID), `offer_page_id`, `product_id`,
  `quantity`, `reserved_at`/`expires_at` (**BigInteger UNIX seconds**), `extended` (bool),
  `user_id` (nullable, SET NULL), `ip_address`, `user_agent`, `selected_size`. UNIQUE
  `(session_id, offer_page_id, product_id)` = `unique_session_page_product`. Metody `is_expired()`,
  `can_extend()`, `time_remaining()`.
- **`OfferSetBonus`** (l. 711): `section_id`, `trigger_type` enum
  **buy_products/price_threshold/quantity_threshold**, `threshold_value` (Numeric), `bonus_product_id`,
  `bonus_quantity`, `max_available`, `when_exhausted` (hide/show_exhausted), `count_full_set`,
  `repeatable`, `is_active`, `sort_order`. `required_products` → `OfferBonusRequiredProduct`
  (l. 762: `product_id`, `min_quantity`).

### Logika rezerwacji (`modules/offers/reservation.py`) — JUŻ context-agnostic
- `RESERVATION_DURATION = 120` (2 min), `EXTENSION_DURATION = 60` (1 min).
- `reserve_product(session_id, page_id, product_id, quantity, section_max=None, user_id=None,
  selected_size=None)` → `(success: bool, data: dict)`. Wrapper z **retry 3× na deadlock**
  (l. 163-179). `_reserve_product_attempt` (l. 182): w JEDNEJ transakcji cleanup→`SELECT FOR UPDATE`
  na aktywnych rezerwacjach produktu→`available = max(0, section_max − reserved − ordered)`→UPSERT→
  commit. Deadlock → zwraca None (sygnał retry). Sukces dict: `{reservation: {session_id, product_id,
  quantity, reserved_at, expires_at, first_reservation_at}, available_quantity}`. Błąd dict:
  `{error: 'insufficient_availability', message: 'Ktoś właśnie zarezerwował lub zakupił ten produkt.',
  available_quantity, check_back_at}` lub `{error: 'server_error', message}`. **Dostęp do `request`
  osłonięty try/except (l. 269-274)** — działa poza kontekstem żądania (SocketIO).
- `release_product(session_id, page_id, product_id, quantity)` → `(True, {reservation: {quantity}})`.
  Brak rezerwacji → `(True, {reservation:{quantity:0}})`. Commit w środku.
- `extend_reservation(session_id, page_id)` → `(True, {new_expires_at})` lub
  `(False, {error:'reservation_expired'|'already_extended', message})`. Cleanup przed sprawdzeniem.
- `get_availability_snapshot(page_id, section_products, session_id)` → `(products_data, session_info)`.
  `products_data[str(pid)] = {available (int; 999999=unlimited), user_reserved, total_reserved,
  total_ordered}`. `session_info = {has_reservations, can_extend, extended, [first_reserved_at,
  expires_at]}`. **available/qty to SZTUKI, NIE pieniądze — bez konwersji na grosze.**
- `get_section_max_for_product(page_id, product_id)` (l. 403) → int|None (None=unlimited). Sprawdza
  4 ścieżki: sekcja product / variant_group / set bezpośredni / set przez variant_group.
- `get_section_products_map(page_id)` (l. 473) → `{product_id: section_max}` dla całej strony.
- `cleanup_expired_reservations(page_id, auto_commit=True)` — lazy cleanup, retry 3× na deadlock.

### Logika place-order (`modules/offers/place_order.py`) — UŻYWA `current_user` (GŁÓWNY REFAKTOR)
- `place_offer_order(page, session_id, order_note=None, full_set_items=None)` (l. 127) — wrapper z
  **retry 3× na MySQL deadlock 1213** (`_is_deadlock`, `OperationalError`). `_place_offer_order_attempt`
  (l. 169): cleanup→pobierz rezerwacje sesji→**double-submit guard** (l. 202: szuka istniejącego
  Order po `offer_page_id`+`current_user.id`)→`check_product_availability` (**SELECT FOR UPDATE**,
  sort po product_id eliminuje cykle deadlock, l. 57)→`generate_order_number('exclusive')`→
  `Order(order_type='exclusive', user_id=current_user.id, status='nowe', offer_page_id, offer_page_name,
  payment_stages=page.payment_stages, total_amount)`→OrderItem per rezerwacja (z `set_number`/
  `set_section_id`/`is_full_set`/`selected_size`; **walidacja: produkt z sizes wymaga selected_size →
  `{error:'size_required'}`**)→full_set_items (max 5/order, tylko `set_product_id`)→**ewaluacja bonusów**
  (3 trigger_type, limity globalne z SELECT FOR UPDATE, odejmowanie wcześniej zdobytych przez usera)→
  usuń rezerwacje→commit→`check_and_apply_auto_increase`→`log_activity`→**maile+push**
  (`EmailManager.notify_order_confirmation/notify_admin_new_order` + push)→**emisje Socket.IO**
  (`broadcast_availability_update`, `_schedule_expiry_timer`, `emit_new_order`, `emit_stats_update`)→
  achievements. Zwraca `{order_id, order_number, total_amount (float), items_count, items (GA)}`.
- **`current_user` (flask_login) używane w**: l. 205 (double-submit), 231 (`order.user_id`), 367
  (`prev_user_orders` filter), 605/606 (`log_activity user=current_user`), 658 (customer_name do
  Socket.IO), 694 (achievement). Wszystkie → trzeba zamienić na przekazany `user`.
- **OFFER ORDERS NIE zmniejszają globalnego stocku** (`product.quantity`) — l. 320. Anti-overselling
  działa wyłącznie przez `section_max − reserved − ordered` na rezerwacjach/zamówieniach oferty.
- `place_preorder_order` (l. 718) też używa `current_user` — **to E4, NIE dotykamy teraz** (route
  webowy go woła, zostaje bez zmian).

### Trasy webowe (`modules/offers/routes.py`) — cienkie wrappery
- `reserve` (l. 380, `@csrf.exempt`, limit 120/min): `if not current_user.is_authenticated → 401
  login_required`. Liczy section_max **inline** (l. 406-456, duplikat `get_section_max_for_product`!),
  woła `reserve_product(..., user_id=current_user.id)`. Sukces → **`emit_reservations_update(page.id)` +
  `broadcast_availability_update(page.id)`** (try/except), `jsonify({success:True, **result})`.
  Błąd → `409 {success:False, **result}`.
- `release` (l. 481): jw., sukces → te same 2 emisje. Zawsze `200 {success:True, **result}`.
- `extend` (l. 595, `@csrf.exempt`, BEZ limitu): login→`extend_reservation`. **BRAK emisji Socket.IO
  w trasie webowej** (handler SocketIO `handle_extend_reservation` ROBI broadcast — rozjazd; patrz
  Decyzja D4). Sukces `200`, błąd `400`.
- `availability` (l. 518, limit 120/min, **BEZ login**): buduje section_products **inline**
  (l. 532-580, duplikat `get_section_products_map`!), woła `get_availability_snapshot`,
  `jsonify({success:True, products, session})`.
- `place_order` (l. 704, `@csrf.exempt`, limit 15/min per user): login→`page_not_found` 404→
  **`if not page.is_active → 403 page_not_active`**→rozgałęzienie preorder/exclusive. Exclusive:
  `session_id` wymagany (`400 missing_session_id`), woła `place_offer_order(page, session_id,
  order_note, full_set_items)`. Sukces → zapis `session['last_order_data']` (web-only) +
  `200 {success:True, **result}`. Błąd → `400 {success:False, **result}`.
- **Reserve/release/extend/place-order WYMAGAJĄ logowania na webie** (parytet z mobile JWT).

### Socket.IO (`modules/offers/socket_events.py`) — funkcje page_id-only, bez current_user/request
- `broadcast_availability_update(page_id)` (l. 127): emituje `availability_updated` do rooma
  `offer_page_{id}_order` + sprawdza subskrypcje powiadomień. **Nie używa current_user ani request** —
  bezpieczne z mobile.
- `emit_reservations_update(page_id)` (l. 875): emituje `reservations_update` do rooma admina.
- `_schedule_expiry_timer(page_id)` (l. 305): per-worker `threading.Timer`; używa `current_app`
  (dostępne w kontekście żądania). Bezpieczne z mobile.
- `emit_new_order` / `emit_stats_update` — wołane WEWNĄTRZ `place_offer_order`, zostają.
- Stan współdzielony przez **Redis z fallbackiem in-memory** (`redis_state.py`, `get_state()`,
  `init_state()` w app.py:164). **Mobile E3 NIE dotyka redis_state ani handlerów SocketIO** — tylko
  woła funkcje emit (best-effort, try/except). WS dla apki to E9.
- W testach: `RATELIMIT_ENABLED=False` (config.py:160), `init_state(None)` → backend in-memory,
  `socketio.emit` bez podłączonej message queue = no-op/cicho; web owija emisje try/except, mobile też.

### Wzorce mobilne (E0–E2)
- Blueprint `api_mobile_bp` prefix `/api/mobile/v1` (`modules/api_mobile/__init__.py`), errorhandler
  `ValidationError`→400 invalid_input. Trasy importowane na końcu `__init__.py`.
- Helpery (`helpers.py`): `json_ok(data, status=200)`, `json_err(code, message, status)`,
  `json_page(items, page, per_page, total, has_next)`, `to_grosze(amount)` (Decimal→int grosze,
  ROUND_HALF_UP), `absolute_static_url(path)` (względny→absolutny URL, sama dokłada `/static/`),
  `serialize_user(user)`.
- `validators.py`: `parse_int(value, field, required=False, default=None, min_value=None,
  max_value=None)` → int / `ValidationError`.
- Wzorzec trasy: `@jwt_required()` + `int(get_jwt_identity())`; mutacje `@limiter.limit(...)`.
- `cart_routes.py`: wzorzec `_err(result)` (koperta z opcjonalnym `details`), `_serialize_item`
  (price→grosze, image_url `/static/...`→absolutny). Checkout zwraca `to_grosze` kwot.
- `models.py`: `MobileTokenBlocklist` (wzorzec lazy `purge_expired`). **Migracja head obecnie:
  `c0ee01fee8b5`** (`flask db heads`).

### Order / OrderType / generate_order_number
- `generate_order_number('exclusive')` (modules/orders/utils.py:21) wymaga wiersza
  `OrderType(slug='exclusive')` → prefix `EX`. **Testy muszą zaseedować OrderType** (jak `_onhand_order_type`
  w test_mobile_api_cart.py).
- `Order` (modules/orders/models.py:152): `order_type` (FK order_types.slug), `offer_page_id`
  (SET NULL), `payment_stages`, `total_amount`, `status`. `OrderItem` (l. 973): `is_custom`,
  `is_full_set`, `is_bonus`, `selected_size`, `set_section_id`, `set_number`,
  `bonus_source_section_id`, `product_name` (property), `quantity`, `price`, `total`.

### Testy / środowisko
- **Baseline: `205 passed`** (`source venv/bin/activate && python -m pytest -q`, zweryfikowane
  2026-06-12). TYLKO `python -m pytest` (gołe `pytest` pada na `No module named 'app'`).
- **Brak istniejących testów dla reserve_product / place_offer_order / OfferReservation** — E3 dodaje
  PIERWSZE pokrycie tej krytycznej logiki (podwójna korzyść: regresja dla refaktoru `user`).
- conftest fixtury: `app` (sqlite in-memory!), `db`, `client`, `make_user(role='client', email=None,
  **kwargs)`, `make_product(name=None, sale_price=99.00, quantity=10, **kwargs)` — `product_type_id`
  przez kwargs, `make_order`, `login` (Flask-Login session).
- Helper `_auth(client, db, make_user)` → **`(headers, user)`** (tests/test_mobile_api_cart.py:15) —
  loguje przez `/auth/login`, zwraca nagłówek Bearer. Skopiuj do nowego pliku testów.
- **`with_for_update` to NO-OP w sqlite** (znany dług z E2): testy jednostkowe pokryją logikę
  rezerwacji/zamówienia, ale NIE atomowości/deadlock-retry pod współbieżnością. Patrz Decyzja D5.
- `/docs` w `.gitignore` → commit planu i specu przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem — zatwierdzane wraz z planem)

1. **Mapowanie statusów `?status=live|upcoming|closed` na enum bazy** (spec sekcja 5 vs
   `offer_page_status`): `live → active`, `upcoming → scheduled`, `closed → ended`. **`draft` NIGDY nie
   jest eksponowany** (niepubliczny). `paused` — patrz Decyzja **D1** (domyślnie proponowane: `live`
   obejmuje `active` + `paused`, bo strona wstrzymana jest „w toku", ale `can_order=false`).
   Endpoint zwraca `status` zmapowany (live/upcoming/closed) + boolean `can_order`.
2. **Ścieżki mobilne** (spójne ze specem sekcja 5): `GET /offers/offer-pages`,
   `GET /offers/offer-pages/<token>`, `GET /offers/offer-pages/<token>/availability`,
   `POST /offers/<token>/{reserve,extend,release,place-order}`. Brak konfliktu routingu (segment
   literalny `offer-pages` vs `<token>`; różne metody/ścieżki).
3. **`available`/`quantity` w odpowiedziach dostępności to SZTUKI (int), NIE grosze.** Ceny produktów
   w strukturze strony — grosze (int), spójnie z E1/E2. `999999` = bez limitu (parytet z webem).
4. **Read-endpointy wymagają Bearer** (parytet z resztą mobile, mimo że web `availability`/`order_page`
   są publiczne). `draft` → 404 na strukturze (niepubliczny).
5. **`error.details`** (opcjonalne) w kopercie błędu — dla `available_quantity` przy 409 rezerwacji
   i `available` przy `size_required`/niedostępności w place-order.
6. **Nagłówek `Idempotency-Key`** (UUID) dla `POST /shop/checkout` (E2) i
   `POST /offers/<token>/place-order` (E3) — patrz sekcja Idempotency i Decyzja **D2/D3**.
7. **`full_set_items[]`** w place-order: `[{product_id, quantity}]` (max 5/order/produkt, walidowane
   serwisem — tylko `set_product_id` strony). `order_note` opcjonalny string.

---

## Decyzje — ROZSTRZYGNIĘTE przez Konrada 2026-06-12 (wszystkie wg rekomendacji)

> **D1:** live = active + paused, z polem `can_order=false` dla paused. **D2+D3:** claim-first
> (INSERT z UNIQUE przed przetwarzaniem), nagłówek opcjonalny, TTL 48h, zakres: checkout + place-order.
> **D4:** mirror weba — extend bez emisji, tylko korekta timera. **D5:** świadomy dług —
> bez testu integracyjnego MariaDB dla FOR UPDATE.

## Decyzje do podjęcia przez Konrada (prawdziwe rozgałęzienia — NIE rozstrzygam arbitralnie)

- **D1 — `paused` w mapowaniu statusów listy.** (a) `live` = active + paused (proponowane; strona
  wstrzymana widoczna, `can_order=false`); (b) `closed` = ended + paused; (c) `paused` całkowicie
  pominięty na liście. Wpływ tylko na filtrowanie listy; struktura strony i tak zwraca surowy stan.
- **D2 — Mechanizm Idempotency-Key (obsługa wyścigu).** (a) **claim-first** (proponowane): INSERT
  wiersza-rezerwacji `(user_id, key)` z `status_code=NULL` PRZED przetwarzaniem; UNIQUE → przy
  duplikacie SELECT istniejącego: jeśli ma zapisaną odpowiedź → zwróć ją (200/201), jeśli wciąż
  `processing` → `409 idempotency_in_progress` (apka ponawia). Gwarantuje brak duplikatu nawet przy
  współbieżności. (b) **store-after-success**: przetwórz, potem zapisz; przy IntegrityError zwróć
  zapisaną. Prościej, ale przy współbieżnych żądaniach z tym samym kluczem może powstać duplikat
  (stock-locking chroni przed oversellingiem, ale nie przed dwoma zamówieniami). Rekomendacja: **(a)**.
- **D3 — Zakres i TTL Idempotency-Key.** Zakres: tylko `POST /shop/checkout` + `POST .../place-order`
  (zgodnie z follow-upem). TTL czyszczenia: 24h / 48h / 7 dni? (proponowane **48h** — pokrywa retry
  apki i ponowne wejście, lazy `purge_expired` jak w `MobileTokenBlocklist`). Klucz wymagany czy
  opcjonalny? (proponowane **opcjonalny** — brak nagłówka = zachowanie jak dziś, by nie złamać apki
  bez wsparcia; logujemy ostrzeżenie przy braku na mutacji zamówienia).
- **D4 — Emisja Socket.IO przy `extend` mobilnym.** Trasa webowa `extend` NIE emituje; handler
  SocketIO `handle_extend_reservation` emituje `broadcast_availability_update` + `_schedule_expiry_timer`.
  (a) mobile mirror trasy webowej (bez emisji; proponowane — minimalna niespodzianka, dostępność liczb
  się nie zmienia przy extend); (b) mobile jak handler SocketIO (emituje, by odświeżyć timer u innych).
  Rekomendacja: **(a)**, z `_schedule_expiry_timer` wywołanym lokalnie dla poprawności timera serwera.
- **D5 — Test integracyjny MariaDB dla `with_for_update`/deadlock-retry.** sqlite czyni
  `with_for_update` no-opem, więc atomowość/retry nie są weryfikowalne w obecnym harnessie. (a) świadomy
  dług z uzasadnieniem (proponowane — mechanizm jest produkcyjnie sprawdzony, ryzyko regresji w E3 jest
  w warstwie `user`-param, nie w samym lockingu; pokrywamy logikę funkcjonalną testami jednostkowymi);
  (b) osobny opcjonalny harness MariaDB (marker `@pytest.mark.mariadb`, pomijany domyślnie) — większy
  nakład infry. Rekomendacja: **(a)** + odnotowanie w DoD.

---

## File Structure

- `modules/api_mobile/models.py` — Task 1: dodaj `MobileIdempotencyKey`.
- `migrations/versions/<rev>_mobile_idempotency_key.py` — Task 1: migracja (head `c0ee01fee8b5`).
- `modules/api_mobile/idempotency.py` — NOWY (Task 2): helper/dekorator idempotencji.
- `modules/api_mobile/cart_routes.py` — Task 2: owinięcie `POST /shop/checkout` idempotencją.
- `modules/offers/place_order.py` — Task 3: `place_offer_order(..., user=...)`, zamiana `current_user`.
- `modules/offers/routes.py` — Task 3: web `place_order` przekazuje `user=current_user._get_current_object()`.
- `modules/api_mobile/offers_routes.py` — NOWY (Task 4-7): wszystkie trasy mobilne E3.
- `modules/api_mobile/__init__.py` — Task 4: `from . import offers_routes`.
- `tests/test_mobile_api_offers.py` — NOWY: testy E3 (read, reserve, place-order).
- `tests/test_offers_place_order_service.py` — NOWY (Task 3): testy serwisu place_offer_order.
- `tests/test_mobile_api_idempotency.py` — NOWY (Task 2): testy idempotencji.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 8: korekty kontraktu E3.

---

### Task 1: Model `MobileIdempotencyKey` + migracja (Flask-Migrate)

**Files:** Modify `modules/api_mobile/models.py`; Create `migrations/versions/<rev>_*.py`

- [ ] **Step 1:** Dodaj model do `modules/api_mobile/models.py` (wg Decyzji D2 = claim-first, kolumny
  odpowiedzi nullable do backfillu):
```python
class MobileIdempotencyKey(db.Model):
    __tablename__ = 'mobile_idempotency_keys'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    idempotency_key = db.Column(db.String(64), nullable=False)
    endpoint = db.Column(db.String(64), nullable=False)
    status_code = db.Column(db.Integer, nullable=True)      # NULL = processing (claim)
    response_body = db.Column(db.Text, nullable=True)       # JSON serializowana odpowiedź
    created_at = db.Column(db.DateTime, default=get_local_now, index=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'idempotency_key', name='uq_idem_user_key'),
    )

    @classmethod
    def purge_expired(cls, ttl_hours=48):
        """Lazy cleanup wpisów starszych niż TTL. Commit po stronie wołającego."""
        from datetime import timedelta
        cutoff = get_local_now() - timedelta(hours=ttl_hours)
        cls.query.filter(cls.created_at < cutoff).delete(synchronize_session=False)
```
- [ ] **Step 2:** Wygeneruj migrację: `source venv/bin/activate && flask db migrate -m "Mobile
  idempotency keys"`. **Zweryfikuj** wygenerowany plik w `migrations/versions/`: `down_revision =
  'c0ee01fee8b5'`, `create_table('mobile_idempotency_keys', ...)` z UNIQUE `uq_idem_user_key` +
  indeksami (`user_id`, `created_at`), `upgrade`/`downgrade` symetryczne. Popraw ręcznie jeśli Alembic
  doda śmieci (autodetekcja czasem wykrywa fałszywe zmiany enumów — usuń je).
- [ ] **Step 3:** `flask db upgrade` lokalnie (sqlite testowe tworzy tabele przez `create_all`, ale
  produkcja idzie migracją — sprawdź że upgrade przechodzi na lokalnej MariaDB XAMPP).
- [ ] **Step 4: Commit** — `git add modules/api_mobile/models.py migrations/versions/<rev>_*.py &&
  git commit -m "feat(mobile-api): tabela mobile_idempotency_keys (migracja)"`

---

### Task 2: Helper idempotencji + podłączenie do `POST /shop/checkout`

**Files:** Create `modules/api_mobile/idempotency.py`; Modify `modules/api_mobile/cart_routes.py`;
Test `tests/test_mobile_api_idempotency.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_idempotency.py` (skopiuj `_auth`, `_onhand_type`,
  `_onhand_order_type` z test_mobile_api_cart.py):
```python
def _add_to_cart(client, h, product_id, qty=1):
    return client.post('/api/mobile/v1/shop/cart/items', headers=h,
                       json={'product_id': product_id, 'quantity': qty})


def test_checkout_idempotent_replay_returns_same_order(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 2)
    key = 'idem-123e4567-e89b-12d3-a456-426614174000'
    hk = {**h, 'Idempotency-Key': key}
    r1 = client.post('/api/mobile/v1/shop/checkout', headers=hk, json={})
    assert r1.status_code == 201
    order_id_1 = r1.get_json()['data']['order_id']
    # Powtórka tym samym kluczem — koszyk już pusty, ale idempotencja zwraca pierwotną odpowiedź
    r2 = client.post('/api/mobile/v1/shop/checkout', headers=hk, json={})
    assert r2.status_code == 201
    assert r2.get_json()['data']['order_id'] == order_id_1
    # Tylko JEDNO zamówienie w bazie
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='on_hand').count() == 1


def test_checkout_without_key_works_as_before(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 1)
    r = client.post('/api/mobile/v1/shop/checkout', headers=h, json={})
    assert r.status_code == 201


def test_checkout_different_keys_two_orders(client, db, make_user, make_product):
    h, _ = _auth(client, db, make_user)
    _onhand_order_type(db)
    p = make_product(product_type_id=_onhand_type(db).id, quantity=5, sale_price='10.00')
    _add_to_cart(client, h, p.id, 1)
    client.post('/api/mobile/v1/shop/checkout', headers={**h, 'Idempotency-Key': 'k1'}, json={})
    _add_to_cart(client, h, p.id, 1)
    client.post('/api/mobile/v1/shop/checkout', headers={**h, 'Idempotency-Key': 'k2'}, json={})
    from modules.orders.models import Order
    assert Order.query.filter_by(order_type='on_hand').count() == 2
```
Run: `python -m pytest tests/test_mobile_api_idempotency.py -v` → FAIL (brak modułu/zachowania).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/idempotency.py` (wzorzec claim-first, D2a):
```python
"""Idempotency-Key dla mutacji składających zamówienia (checkout + place-order)."""
import json
from functools import wraps
from flask import request, jsonify
from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import IntegrityError
from extensions import db
from .models import MobileIdempotencyKey


def idempotent(endpoint_name):
    """Dekorator: jeśli nagłówek Idempotency-Key obecny — zapewnia jednokrotne wykonanie
    per (user_id, key). Brak nagłówka = zachowanie jak dotychczas (D3: klucz opcjonalny)."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = (request.headers.get('Idempotency-Key') or '').strip()
            if not key:
                return fn(*args, **kwargs)
            user_id = int(get_jwt_identity())
            MobileIdempotencyKey.purge_expired()  # lazy cleanup
            # Claim: spróbuj wstawić wiersz processing
            claim = MobileIdempotencyKey(user_id=user_id, idempotency_key=key,
                                         endpoint=endpoint_name)
            db.session.add(claim)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                existing = MobileIdempotencyKey.query.filter_by(
                    user_id=user_id, idempotency_key=key).first()
                if existing and existing.status_code is not None:
                    return jsonify(json.loads(existing.response_body)), existing.status_code
                # Wciąż przetwarzane przez inne żądanie
                return jsonify({'success': False, 'error': {
                    'code': 'idempotency_in_progress',
                    'message': 'Żądanie z tym kluczem jest właśnie przetwarzane.'}}), 409
            # Wykonaj właściwą logikę
            resp, status = fn(*args, **kwargs)  # trasy zwracają (response, status)
            claim.status_code = status
            claim.response_body = resp.get_data(as_text=True)
            db.session.commit()
            return resp, status
        return wrapper
    return deco
```
> **UWAGA implementacyjna:** trasy mobilne zwracają `(jsonify(...), status)` przez `json_ok`/`json_err`.
> Dekorator zakłada krotkę `(Response, int)`. `json_ok` zwraca `(Response, status)` — zgodne. Jeśli
> trasa zwróci goły `Response`, znormalizuj w dekoratorze (`if not isinstance(rv, tuple): rv = (rv, 200)`).
> Dekorator MUSI być POD `@jwt_required()` (potrzebuje `get_jwt_identity()`).

- [ ] **Step 3:** Owiń `checkout_place_mobile` w `cart_routes.py`:
```python
from .idempotency import idempotent

@api_mobile_bp.route('/shop/checkout', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")
@idempotent('shop_checkout')
def checkout_place_mobile():
    ...  # ciało bez zmian, nadal zwraca (json_ok(...)/_err(...))
```
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_idempotency.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): Idempotency-Key dla checkoutu (claim-first)"`

---

### Task 3: Refaktor `place_offer_order(user=...)` + parytet web + testy serwisu (pierwsze pokrycie)

**Files:** Modify `modules/offers/place_order.py`, `modules/offers/routes.py`;
Test `tests/test_offers_place_order_service.py`

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_offers_place_order_service.py`. Helper budujący
  aktywną stronę exclusive z sekcją produktową + rezerwacją. Testy wołają serwis WPROST (bez HTTP),
  przekazując `user`:
```python
from decimal import Decimal
import time


def _ex_order_type(db):
    from modules.orders.models import OrderType
    ot = OrderType.query.filter_by(slug='exclusive').first()
    if not ot:
        ot = OrderType(slug='exclusive', name='Exclusive', prefix='EX')
        db.session.add(ot); db.session.commit()
    return ot


def _active_page(db, payment_stages=3):
    from modules.offers.models import OfferPage
    p = OfferPage(name='Drop', token=OfferPage.generate_token(), status='active',
                  page_type='exclusive', payment_stages=payment_stages, created_by=1)
    db.session.add(p); db.session.commit()
    return p


def _product_section(db, page, product, max_quantity=10):
    from modules.offers.models import OfferSection
    s = OfferSection(offer_page_id=page.id, section_type='product',
                     product_id=product.id, max_quantity=max_quantity, sort_order=0)
    db.session.add(s); db.session.commit()
    return s


def _reserve(db, page, product, session_id, qty=1, user=None, size=None):
    from modules.offers.models import OfferReservation
    now = int(time.time())
    r = OfferReservation(session_id=session_id, offer_page_id=page.id, product_id=product.id,
                         quantity=qty, reserved_at=now, expires_at=now + 120,
                         user_id=user.id if user else None, selected_size=size)
    db.session.add(r); db.session.commit()
    return r


def test_place_offer_order_happy_path(db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    from modules.orders.models import Order, OrderItem
    _ex_order_type(db)
    user = make_user(); make_user()  # created_by=1 istnieje
    page = _active_page(db, payment_stages=3)
    prod = make_product(sale_price=Decimal('50.00'))
    _product_section(db, page, prod, max_quantity=10)
    sid = 'sess-aaaa'
    _reserve(db, page, prod, sid, qty=2, user=user)

    ok, result = place_offer_order(page=page, session_id=sid, user=user)

    assert ok is True
    order = Order.query.get(result['order_id'])
    assert order.order_type == 'exclusive'
    assert order.user_id == user.id
    assert order.payment_stages == 3
    assert order.status == 'nowe'
    assert float(order.total_amount) == 100.0
    assert OrderItem.query.filter_by(order_id=order.id).count() == 1
    # Rezerwacje usunięte
    from modules.offers.models import OfferReservation
    assert OfferReservation.query.filter_by(session_id=sid).count() == 0


def test_place_offer_order_size_required(db, make_user, make_product):
    from modules.offers.place_order import place_offer_order
    from modules.products.models import Size
    _ex_order_type(db)
    user = make_user(); make_user()
    page = _active_page(db)
    prod = make_product(sale_price=Decimal('10.00'))
    size = Size(name='M'); db.session.add(size); db.session.commit()
    prod.sizes.append(size); db.session.commit()
    _product_section(db, page, prod)
    sid = 'sess-bbbb'
    _reserve(db, page, prod, sid, qty=1, user=user, size=None)  # brak rozmiaru

    ok, result = place_offer_order(page=page, session_id=sid, user=user)
    assert ok is False
    assert result['error'] == 'size_required'


def test_place_offer_order_no_reservations(db, make_user):
    from modules.offers.place_order import place_offer_order
    _ex_order_type(db)
    user = make_user(); make_user()
    page = _active_page(db)
    ok, result = place_offer_order(page=page, session_id='empty', user=user)
    assert ok is False
    assert result['error'] == 'no_reservations'
```
Run → FAIL (`place_offer_order` nie przyjmuje `user`).

- [ ] **Step 2: Refaktor `place_offer_order`** (`modules/offers/place_order.py`):
  - Sygnatura: `def place_offer_order(page, session_id, order_note=None, full_set_items=None, user=None)`
    i `def _place_offer_order_attempt(page, session_id, order_note=None, full_set_items=None, user=None)`.
  - Na początku `_place_offer_order_attempt`: `if user is None: from flask_login import current_user as
    _cu; user = _cu._get_current_object()` (backward-compat dla ścieżek, które jeszcze nie przekazują).
  - Zamień WSZYSTKIE `current_user` → `user`: l. 205 (double-submit `user_id=user.id`), 231
    (`user_id=user.id`), 367 (`Order.user_id == user.id`), 605-606 (`log_activity(user=user, ...)`),
    658 (`f'{user.first_name} {user.last_name}'... user.email`), 694 (`AchievementService().check_event(
    user, ...)`). **Usuń** top-level `from flask_login import current_user` (l. 9) lub zostaw tylko dla
    fallbacku w środku funkcji — preferuj import lokalny w fallbacku, by funkcja nie zależała od kontekstu.
  - **NIE zmieniaj** `place_preorder_order` (E4).
- [ ] **Step 3: Parytet web** — w `modules/offers/routes.py` `place_order` (l. 741) zmień wywołanie na
  `place_offer_order(page=page, session_id=session_id, order_note=order_note,
  full_set_items=full_set_items, user=current_user._get_current_object())`.
- [ ] **Step 4: GREEN + pełna regresja** — `python -m pytest tests/test_offers_place_order_service.py -v`
  oraz `python -m pytest -q` (205 + nowe, zero failów; web place-order nietknięty behawioralnie).
- [ ] **Step 5: Commit** — `git commit -m "refactor(offers): place_offer_order przyjmuje user (parytet web+mobile) + testy serwisu"`

---

### Task 4: Mobile — `GET /offers/offer-pages` (lista + mapowanie statusów)

**Files:** Create `modules/api_mobile/offers_routes.py`; Modify `modules/api_mobile/__init__.py`;
Test `tests/test_mobile_api_offers.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_offers.py` (skopiuj `_auth`; dodaj helper
  `_make_page(db, status, page_type='exclusive')`):
```python
def test_offer_pages_requires_token(client):
    assert client.get('/api/mobile/v1/offers/offer-pages').status_code == 401


def test_offer_pages_filter_live(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'active'); _make_page(db, 'scheduled'); _make_page(db, 'ended')
    _make_page(db, 'draft')  # nigdy nie eksponowany
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    assert r.status_code == 200
    data = r.get_json()
    assert all(p['status'] == 'live' for p in data['data'])
    assert len(data['data']) == 1
    assert 'pagination' in data


def test_offer_pages_excludes_draft_always(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'draft')
    for st in ('live', 'upcoming', 'closed'):
        r = client.get(f'/api/mobile/v1/offers/offer-pages?status={st}', headers=h)
        assert all(p['status'] != 'draft' for p in r.get_json()['data'])


def test_offer_pages_includes_both_types(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_page(db, 'active', page_type='exclusive')
    _make_page(db, 'active', page_type='preorder')
    r = client.get('/api/mobile/v1/offers/offer-pages?status=live', headers=h)
    types = {p['page_type'] for p in r.get_json()['data']}
    assert types == {'exclusive', 'preorder'}
```
- [ ] **Step 2: Implementacja** — `modules/api_mobile/offers_routes.py` (mapowanie wg D1, domyślnie
  `live`=active+paused):
```python
"""Trasy stron ofertowych (exclusive + preorder read) dla mobilnego API — E3."""
from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from extensions import limiter
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze, absolute_static_url
from .validators import parse_int
from modules.offers.models import OfferPage

# Mapowanie kontrakt → enum bazy (D1: live obejmuje active + paused)
_STATUS_MAP = {'live': ('active', 'paused'), 'upcoming': ('scheduled',), 'closed': ('ended',)}


def _public_status(page):
    if page.status in ('active', 'paused'):
        return 'live'
    if page.status == 'scheduled':
        return 'upcoming'
    return 'closed'  # ended


def _serialize_page_summary(page):
    return {
        'token': page.token,
        'name': page.name,
        'page_type': page.page_type,
        'status': _public_status(page),
        'can_order': page.can_order,
        'starts_at': page.starts_at.isoformat() if page.starts_at else None,
        'ends_at': page.ends_at.isoformat() if page.ends_at else None,
        'payment_stages': page.payment_stages,
    }


@api_mobile_bp.route('/offers/offer-pages', methods=['GET'])
@jwt_required()
def offer_pages_list():
    status = (request.args.get('status') or 'live').strip().lower()
    if status not in _STATUS_MAP:
        return json_err('invalid_input', 'Nieobsługiwany status. Dozwolone: live, upcoming, closed.', 400)
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page', default=12, min_value=1), 48)

    q = OfferPage.query.filter(
        OfferPage.status.in_(_STATUS_MAP[status])   # draft nigdy nie wchodzi
    ).order_by(OfferPage.starts_at.desc().nullslast(), OfferPage.id.desc())
    pagination = q.paginate(page=page, per_page=per_page, error_out=False)
    return json_page([_serialize_page_summary(p) for p in pagination.items],
                     page=pagination.page, per_page=pagination.per_page,
                     total=pagination.total, has_next=pagination.has_next)
```
W `__init__.py`: `from . import offers_routes  # noqa: E402,F401`.
> **UWAGA:** `nullslast()` może nie działać identycznie w sqlite — jeśli test się sypie, użyj
> `order_by(OfferPage.id.desc())` jako prostszego deterministycznego sortu (parytet z webem nie jest
> tu krytyczny, listy ofert są krótkie).
- [ ] **Step 3: GREEN** + **Step 4: Commit** — `git commit -m "feat(mobile-api): lista stron ofertowych (mapowanie statusów live/upcoming/closed)"`

---

### Task 5: Mobile — `GET /offers/offer-pages/<token>` (struktura) + `GET .../availability`

**Files:** Modify `modules/api_mobile/offers_routes.py`; Test `tests/test_mobile_api_offers.py`

- [ ] **Step 1: Testy (RED):**
```python
def test_offer_page_structure_draft_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'draft')
    assert client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h).status_code == 404


def test_offer_page_structure_product_section(client, db, make_user, make_product):
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='50.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=10, sort_order=0))
    db.session.add(OfferSection(offer_page_id=page.id, section_type='heading',
                                content='Nagłówek', sort_order=1))
    db.session.commit()
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['page_type'] == 'exclusive' and d['payment_stages'] in (3, 4)
    secs = d['sections']
    prod_sec = next(s for s in secs if s['section_type'] == 'product')
    assert prod_sec['product']['price'] == 5000          # grosze
    assert prod_sec['max_quantity'] == 10
    head_sec = next(s for s in secs if s['section_type'] == 'heading')
    assert head_sec['content'] == 'Nagłówek'


def test_offer_availability_snapshot(client, db, make_user, make_product):
    from modules.offers.models import OfferSection, OfferReservation
    import time
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0))
    now = int(time.time())
    db.session.add(OfferReservation(session_id='other', offer_page_id=page.id, product_id=prod.id,
                                    quantity=2, reserved_at=now, expires_at=now + 120))
    db.session.commit()
    r = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}/availability?session_id=mine',
                   headers=h)
    assert r.status_code == 200
    pdata = r.get_json()['data']['products'][str(prod.id)]
    assert pdata['available'] == 3 and pdata['total_reserved'] == 2   # SZTUKI, nie grosze
```
- [ ] **Step 2: Implementacja** — w `offers_routes.py` serializer struktury (ceny→grosze, obrazki→
  absolutne) i endpoint availability (reużycie `get_section_products_map` + `get_availability_snapshot`):
```python
from modules.client import shop_service  # slugify


def _brief(p):
    img = p.primary_image
    return {'id': p.id, 'name': p.name, 'slug': shop_service.slugify(p.name),
            'sku': p.sku, 'price': to_grosze(p.sale_price), 'quantity': p.quantity,
            'image_url': absolute_static_url(img.path_compressed) if img else None,
            'sizes': [s.name for s in p.sizes]}


def _serialize_bonus(b):
    bp = b.bonus_product
    return {'id': b.id, 'trigger_type': b.trigger_type,
            'threshold_value': float(b.threshold_value) if b.threshold_value is not None else None,
            'bonus_product': _brief(bp) if bp else None, 'bonus_quantity': b.bonus_quantity,
            'max_available': b.max_available, 'when_exhausted': b.when_exhausted,
            'count_full_set': b.count_full_set, 'repeatable': b.repeatable,
            'required_products': [{'product_id': rp.product_id, 'min_quantity': rp.min_quantity}
                                  for rp in b.required_products]}


def _serialize_section(s):
    base = {'id': s.id, 'section_type': s.section_type, 'sort_order': s.sort_order}
    if s.section_type in ('heading', 'paragraph'):
        base['content'] = s.content
    elif s.section_type == 'product':
        base.update({'product': _brief(s.product) if s.product else None,
                     'min_quantity': s.min_quantity, 'max_quantity': s.max_quantity})
    elif s.section_type == 'variant_group':
        vg = s.variant_group
        base.update({'variant_group': {'id': vg.id, 'name': vg.name} if vg else None,
                     'max_quantity': s.max_quantity,
                     'products': [_brief(p) for p in s.get_variant_group_products() if p.is_active]})
    elif s.section_type == 'set':
        base.update({'set_name': s.set_name,
                     'set_image': absolute_static_url(s.set_image) if s.set_image else None,
                     'set_max_sets': s.set_max_sets, 'set_max_per_product': s.set_max_per_product,
                     'set_product': _brief(s.set_product) if s.set_product else None,
                     'set_items': [{'quantity_per_set': it.quantity_per_set,
                                    'products': [_brief(p) for p in it.get_products()]}
                                   for it in s.get_set_items_ordered()],
                     'bonuses': [_serialize_bonus(b) for b in s.bonuses if b.is_active]})
    elif s.section_type == 'bonus':
        base['bonuses'] = [_serialize_bonus(b) for b in s.bonuses if b.is_active]
    return base


@api_mobile_bp.route('/offers/offer-pages/<token>', methods=['GET'])
@jwt_required()
def offer_page_detail(token):
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    page.check_and_update_status()
    if page.status == 'draft':              # niepubliczny
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    return json_ok({
        **_serialize_page_summary(page),
        'description': page.description,
        'footer_content': page.footer_content,
        'payment_deadline': page.payment_deadline.isoformat() if page.payment_deadline else None,
        'sections': [_serialize_section(s) for s in page.get_sections_ordered()],
    })


@api_mobile_bp.route('/offers/offer-pages/<token>/availability', methods=['GET'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_availability(token):
    from modules.offers.reservation import get_section_products_map, get_availability_snapshot
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    session_id = request.args.get('session_id')
    section_products = get_section_products_map(page.id)
    products_data, session_info = get_availability_snapshot(page.id, section_products, session_id)
    return json_ok({'products': products_data, 'session': session_info})
```
> **UWAGA:** `get_availability_snapshot` woła `cleanup_expired_reservations` (commit) — to OK w GET tu,
> parytet z webem. `slugify` jest w `modules/client/shop_service` (użyte w E1 shop_routes). Potwierdź
> import (`shop_service.slugify`).
- [ ] **Step 3: GREEN** + **Step 4: Commit** — `git commit -m "feat(mobile-api): struktura strony ofertowej + snapshot dostępności"`

---

### Task 6: Mobile — `POST /offers/<token>/{reserve,extend,release}` (+ emisje Socket.IO)

**Files:** Modify `modules/api_mobile/offers_routes.py`; Test `tests/test_mobile_api_offers.py`

- [ ] **Step 1: Testy (RED):**
```python
def test_reserve_requires_token(client, db, make_user):
    page = _make_page(db, 'active')
    assert client.post(f'/api/mobile/v1/offers/{page.token}/reserve', json={}).status_code == 401


def test_reserve_then_availability_reflects(client, db, make_user, make_product):
    from modules.offers.models import OfferSection
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=5, sort_order=0)); db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                    json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 2})
    assert r.status_code == 200 and r.get_json()['data']['reservation']['quantity'] == 2
    a = client.get(f'/api/mobile/v1/offers/offer-pages/{page.token}/availability?session_id=mine',
                   headers=h)
    assert a.get_json()['data']['products'][str(prod.id)]['available'] == 3


def test_reserve_insufficient_409(client, db, make_user, make_product):
    from modules.offers.models import OfferSection, OfferReservation
    import time
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'active')
    prod = make_product(sale_price='10.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=1, sort_order=0))
    now = int(time.time())
    db.session.add(OfferReservation(session_id='other', offer_page_id=page.id, product_id=prod.id,
                                    quantity=1, reserved_at=now, expires_at=now + 120))
    db.session.commit()
    r = client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                    json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 1})
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'insufficient_availability'


def test_extend_once_then_already_extended(client, db, make_user, make_product):
    # reserve → extend (200) → extend ponownie (400 already_extended)
    ...


def test_release_reduces_reservation(client, db, make_user, make_product):
    # reserve qty=2 → release qty=2 → availability wraca do max
    ...
```
- [ ] **Step 2: Implementacja** — w `offers_routes.py` (mapowanie błędów rezerwacji na koperty, emisje
  Socket.IO best-effort — parytet z trasami webowymi):
```python
def _emit_safe(page_id, *, reservations=False, availability=False, schedule=False):
    try:
        from modules.offers.socket_events import (
            emit_reservations_update, broadcast_availability_update, _schedule_expiry_timer)
        if reservations:
            emit_reservations_update(page_id)
        if availability:
            broadcast_availability_update(page_id)
        if schedule:
            _schedule_expiry_timer(page_id)
    except Exception:
        pass


@api_mobile_bp.route('/offers/<token>/reserve', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_reserve(token):
    from modules.offers.reservation import reserve_product, get_section_max_for_product
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    product_id = parse_int(body.get('product_id'), 'product_id', required=True)
    quantity = parse_int(body.get('quantity'), 'quantity', default=1, min_value=1)
    selected_size = body.get('selected_size')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    user_id = int(get_jwt_identity())
    section_max = get_section_max_for_product(page.id, product_id)
    ok, result = reserve_product(session_id=session_id, page_id=page.id, product_id=product_id,
                                 quantity=quantity, section_max=section_max, user_id=user_id,
                                 selected_size=selected_size)
    if ok:
        _emit_safe(page.id, reservations=True, availability=True, schedule=True)
        return json_ok(result)
    details = {k: result[k] for k in ('available_quantity', 'check_back_at') if k in result}
    return jsonify({'success': False, 'error': {
        'code': result.get('error', 'reserve_failed'), 'message': result.get('message', ''),
        **({'details': details} if details else {})}}), 409


@api_mobile_bp.route('/offers/<token>/release', methods=['POST'])
@jwt_required()
@limiter.limit("120 per minute")
def offer_release(token):
    from modules.offers.reservation import release_product
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    product_id = parse_int(body.get('product_id'), 'product_id', required=True)
    quantity = parse_int(body.get('quantity'), 'quantity', default=1, min_value=1)
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    ok, result = release_product(session_id, page.id, product_id, quantity)
    if ok:
        _emit_safe(page.id, reservations=True, availability=True)
    return json_ok(result)


@api_mobile_bp.route('/offers/<token>/extend', methods=['POST'])
@jwt_required()
@limiter.limit("60 per minute")
def offer_extend(token):
    from modules.offers.reservation import extend_reservation
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    ok, result = extend_reservation(session_id, page.id)
    if not ok:
        return json_err(result.get('error', 'extend_failed'), result.get('message', ''), 400)
    _emit_safe(page.id, schedule=True)   # D4(a): tylko korekta timera serwera
    return json_ok(result)
```
- [ ] **Step 3: GREEN** + **Step 4: Commit** — `git commit -m "feat(mobile-api): rezerwacje exclusive (reserve/extend/release + emisje Socket.IO)"`

---

### Task 7: Mobile — `POST /offers/<token>/place-order` (exclusive, + idempotency)

**Files:** Modify `modules/api_mobile/offers_routes.py`; Test `tests/test_mobile_api_offers.py`

- [ ] **Step 1: Testy (RED):**
```python
def test_place_order_happy_path(client, db, make_user, make_product):
    from modules.offers.models import OfferSection
    h, user = _auth(client, db, make_user)
    make_user()  # created_by=1
    _ex_order_type(db)
    page = _make_page(db, 'active', payment_stages=3)
    prod = make_product(sale_price='50.00')
    db.session.add(OfferSection(offer_page_id=page.id, section_type='product',
                                product_id=prod.id, max_quantity=10, sort_order=0)); db.session.commit()
    client.post(f'/api/mobile/v1/offers/{page.token}/reserve', headers=h,
                json={'session_id': 'mine', 'product_id': prod.id, 'quantity': 2})
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order', headers=h,
                    json={'session_id': 'mine', 'order_note': 'proszę szybko'})
    assert r.status_code == 201
    d = r.get_json()['data']
    assert d['order_number'].startswith('EX/')
    assert d['total'] == 10000          # grosze
    assert d['items_count'] == 1


def test_place_order_page_not_active_403(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    page = _make_page(db, 'ended')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order', headers=h,
                    json={'session_id': 'x'})
    assert r.status_code == 403
    assert r.get_json()['error']['code'] == 'page_not_active'


def test_place_order_no_reservations_400(client, db, make_user):
    h, _ = _auth(client, db, make_user); make_user()
    _ex_order_type(db)
    page = _make_page(db, 'active')
    r = client.post(f'/api/mobile/v1/offers/{page.token}/place-order', headers=h,
                    json={'session_id': 'empty'})
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'no_reservations'


def test_place_order_idempotent_replay(client, db, make_user, make_product):
    # reserve → place-order z Idempotency-Key → powtórka tym samym kluczem zwraca to samo zamówienie
    # (po pierwszym place-order rezerwacje usunięte → bez idempotencji byłoby no_reservations)
    ...  # assert oba 201, ten sam order_id, Order.count()==1
```
- [ ] **Step 2: Implementacja** — w `offers_routes.py` (idempotency POD jwt_required; mapowanie wyniku
  serwisu na kopertę; kwoty→grosze; BEZ `items` GA, BEZ `session['last_order_data']`):
```python
from flask_jwt_extended import get_jwt_identity
from modules.auth.models import User
from .idempotency import idempotent

_PLACE_ORDER_ERR_STATUS = {
    'no_reservations': 400, 'size_required': 400, 'insufficient_availability': 409,
    'order_number_failed': 500, 'database_error': 500, 'server_error': 500,
}


@api_mobile_bp.route('/offers/<token>/place-order', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")
@idempotent('offer_place_order')
def offer_place_order(token):
    from modules.offers.place_order import place_offer_order
    page = OfferPage.get_by_token(token)
    if not page:
        return json_err('page_not_found', 'Strona ofertowa nie istnieje.', 404)
    if page.page_type == 'preorder':
        return json_err('wrong_page_type', 'Ta strona obsługiwana jest osobnym endpointem (pre-order).', 400)
    if not page.is_active:
        return json_err('page_not_active', 'Sprzedaż nie jest aktywna.', 403)
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    if not session_id:
        return json_err('invalid_input', 'Pole session_id jest wymagane.', 400)
    order_note = body.get('order_note')
    full_set_items = body.get('full_set_items', []) or []
    user = User.query.get(int(get_jwt_identity()))
    ok, result = place_offer_order(page=page, session_id=session_id, order_note=order_note,
                                   full_set_items=full_set_items, user=user)
    if not ok:
        code = result.get('error', 'place_order_failed')
        status = _PLACE_ORDER_ERR_STATUS.get(code, 400)
        details = {k: result[k] for k in ('available', 'product_name', 'product_id') if k in result}
        payload = {'code': code, 'message': result.get('message', '')}
        if details:
            payload['details'] = details
        return jsonify({'success': False, 'error': payload}), status
    return json_ok({
        'order_id': result['order_id'],
        'order_number': result['order_number'],
        'total': to_grosze(result['total_amount']),
        'items_count': result['items_count'],
    }, 201)
```
> **UWAGA:** `place_offer_order` sam emituje Socket.IO i wysyła maile/push (jak na webie) — to ZAMIERZONE
> (apka webowa i admin LIVE muszą zobaczyć zamówienie z telefonu). W testach maile/push/emisje są owinięte
> try/except w serwisie; jeśli `EmailManager`/`PushManager` próbują realnie wysyłać w teście, rozważ
> monkeypatch w teście happy-path (sprawdź zachowanie istniejących testów checkoutu E2 — checkout NIE
> wysyła maila, ale place_offer_order TAK; zweryfikuj że w `testing` configu poczta jest zaślepiona,
> inaczej dodaj `monkeypatch.setattr` na `EmailManager.notify_order_confirmation` itd.).
- [ ] **Step 3: GREEN** + **Step 4: Commit** — `git commit -m "feat(mobile-api): place-order exclusive (atomowa walidacja, sety, bonusy, idempotency)"`

---

### Task 8: Pełna regresja + aktualizacja specu + DoD

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** `python -m pytest tests/test_mobile_api_offers.py tests/test_mobile_api_idempotency.py
  tests/test_offers_place_order_service.py -v` oraz pełne `python -m pytest -q` — oczekiwane
  205 + ~30-38 nowych, zero failów (web place-order/regresja nietknięte).
- [ ] **Step 2:** Spec — sekcje „Strony ofertowe" i „Exclusive": dopisz notę korekt E3: (a) mapowanie
  `status` live/upcoming/closed→enum (D1), (b) ścieżki `offer-pages/<token>` vs `<token>/...`,
  (c) `available`/qty w sztukach (nie groszach), ceny w groszach, (d) read-endpointy za Bearer, draft→404,
  (e) `error.details`, (f) nagłówek `Idempotency-Key` (checkout + place-order, mechanizm claim-first, TTL),
  (g) `place-order` body `{session_id, full_set_items[], order_note}`. Zaznacz że pre-order place-order/
  validate-cart to E4.
- [ ] **Step 3:** Commit (`git add -f docs/...`) — `git commit -m "docs(mobile-api): korekty kontraktu E3 (statusy, idempotency, ścieżki ofert)"`

---

## Definition of Done (E3)

- [ ] **Idempotency-Key:** tabela `mobile_idempotency_keys` (migracja z głowy `c0ee01fee8b5`), helper
  claim-first, podłączony do `POST /shop/checkout` (E2) i `POST /offers/<token>/place-order` (E3);
  testy: replay zwraca to samo zamówienie (brak duplikatu), różne klucze = różne zamówienia, brak
  klucza = zachowanie jak dziś.
- [ ] **Refaktor:** `place_offer_order(user=...)` — `current_user` wyeliminowany z logiki, web
  przekazuje `current_user._get_current_object()`, pełna regresja zielona BEZ modyfikacji istniejących
  testów; **pierwsze pokrycie testowe** `place_offer_order` (happy path, size_required, no_reservations).
- [ ] **Read:** `GET /offers/offer-pages` (lista, mapowanie statusów, draft wykluczony, oba typy stron),
  `GET /offers/offer-pages/<token>` (struktura: product/set/variant_group/bonus/heading/paragraph, ceny
  w groszach, obrazki absolutne, draft→404), `GET .../availability` (sztuki, reużycie serwisu).
- [ ] **Rezerwacje:** `reserve` (409 z `details.available_quantity` przy niedostępności), `extend`
  (raz, potem `already_extended`), `release` — wszystkie z emisjami Socket.IO (apka webowa widzi
  rezerwacje z mobile).
- [ ] **Place-order exclusive:** happy path (EX/, total grosze, items_count, rezerwacje usunięte),
  `page_not_active` 403, `no_reservations` 400, `size_required` 400, idempotentny replay; sety/bonusy
  przez współdzielony serwis; emisje Socket.IO + maile/push zachowane (jak web).
- [ ] Wszystkie endpointy za JWT, mutacje z rate-limitami, kwoty w groszach, obrazki absolutne.
- [ ] Spec zaktualizowany o korekty kontraktu E3. **Dług świadomy (D5):** atomowość/deadlock-retry
  niepokryta w sqlite (`with_for_update` no-op) — udokumentowana, mechanizm produkcyjnie sprawdzony.
- [ ] Decyzje D1–D5 rozstrzygnięte z Konradem PRZED implementacją odnośnych tasków.
- [ ] Pełny `python -m pytest -q` zielony. **NIE pushować** — wdrożenie decyzją Konrada.

## Szacunek liczby testów

- Idempotency: ~3-4 (Task 2) + ~1 place-order replay (Task 7).
- Serwis place_offer_order: ~3-4 (Task 3).
- Lista ofert: ~4 (Task 4).
- Struktura + availability: ~4-5 (Task 5).
- Reserve/extend/release: ~5-6 (Task 6).
- Place-order exclusive: ~4 (Task 7).
- **Razem: ~24-28 nowych testów.** Baseline po E3: **~229-233 passed** (start 205).

## Kolejność i bezpieczeństwo (najtrudniejszy etap)

Read-only najpierw (Task 4-5, zero ryzyka dla produkcji), potem mutacje rezerwacji (Task 6, reużycie
sprawdzonej `reservation.py`, web nietknięty), na końcu place-order (Task 7) który wymaga JEDYNEGO
refaktoru web (`user`-param, Task 3) — pokrytego pełną regresją i pierwszymi testami serwisu. Idempotency
(Task 1-2) jako fundament przed place-order. Każdy task: RED→GREEN→commit, pełna regresja przed mergem.
