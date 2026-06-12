# Mobile API — Etap E5 (Moje zamówienia + dashboard klienta) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Domknięcie warstwy ODCZYTU mobilnego API — ekran „Moje zamówienia" + szczegóły zamówienia
(pozycje / sety / bonusy / statusy / **etapy płatności E1–E4**) + dashboard klienta. Trzy endpointy
ze specu sekcja 5:

```
GET  /orders          ?status=&type=&page=&per_page=   → lista zamówień usera (wszystkie typy)
GET  /orders/<id>                                      → szczegóły: pozycje, sety, bonusy, etapy płatności
GET  /dashboard                                        → statystyki klienta (ekran główny apki)
```

E5 to **czysty ODCZYT** — zero mutacji, zero idempotency, **spodziewane ZERO migracji** (head pozostaje
`c72aad290158`). Pełny moduł płatności (upload dowodów) to **E6** — E5 tylko CZYTA stan etapów.

**Architecture:** Trzy odkrycia kształtują plan:
1. **Logika etapów płatności JUŻ JEST scentralizowana jako `@property` na modelu `Order`**
   (`modules/orders/models.py:780–962`): `product_payment_status` / `stage_2_status` / `stage_3_status`
   / `stage_4_status` (każdy zwraca `'none'|'pending'|'approved'|'rejected'`, E2 dodatkowo `None` gdy
   nie dotyczy), `can_upload_*`, `get_*_deadline()`, oraz kwoty (`effective_total`,
   `proxy_shipping_total`, `customs_vat_total`, `shipping_cost`). **Mobilny serializer czyta te
   properties wprost — ZERO refaktoru warstwy płatności, ZERO duplikacji logiki.** (Agent znalazł
   3-krotną duplikację *agregacji ikony* w `payment_icon_state` / `client/payment_confirmations.py`
   / templates — to NIE jest to, czego potrzebuje mobile, i NIE tykamy tego w E5.)
2. **Lista / szczegół zamówień klienta to cienkie trasy** (`modules/orders/routes.py::client_list`
   l. 1591, `client_detail` l. 1678) — proste `filter_by(user_id=...)` + paginacja + `get_or_404`
   + `abort(403)`. Logika nietrywialna jest w properties modelu. Mobile **nie potrzebuje współdzielonego
   serwisu listy/detalu** (zapytanie banalne, properties już są jednym źródłem prawdy) — serializery
   piszemy lokalnie w module mobilnym.
3. **Dashboard klienta to logika INLINE w trasie** (`modules/client/routes.py:90–238`) — 4 liczniki
   zamówień + należność (`to_pay`) + ostatnie zamówienia + wykres 30 dni. Tu jest jedyne realne
   rozgałęzienie architektoniczne (ekstrakcja serwisu vs lokalny helper mobilny) — patrz **D3**.

**Tech Stack:** Flask, flask-jwt-extended (JWT, bez sesji/CSRF), SQLAlchemy, Flask-Migrate (Alembic —
**ZERO migracji w E5**), pytest (sqlite in-memory). Nowe trasy dopisujemy do
`modules/api_mobile/orders_routes.py` (NOWY plik), zarejestrowanego w `__init__.py`. Koperty, kwoty
w **groszach (int)**, obrazki jako **absolutne URL-e**, paginacja `json_page` — spójne z E1–E4.

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Etapy płatności — model `Order` (`modules/orders/models.py`) — SERCE E5
Etapy E1–E4 NIE są iterowane z generycznej listy — są **zakodowane jako osobne properties na `Order`**.
Mobile buduje listę etapów decydując o ich obecności wg `order_type` i `order.payment_stages`:

| Etap | `payment_stage` (string) | Obecny gdy | Kwota (źródło) | Status property | `can_upload` | Deadline |
|------|--------------------------|------------|----------------|-----------------|--------------|----------|
| **E1** | `'product'` | **zawsze** | `effective_total` (l. 584) | `product_payment_status` (l. 792) | `can_upload_product_payment` (l. 800) | brak (E1 nie ma deadline) |
| **E2** | `'korean_shipping'` | **`payment_stages == 4`** | `proxy_shipping_total` (l. 617) | `stage_2_status` (l. 853) | `can_upload_stage_2` (l. 911) | `get_shipping_kr_deadline()` (l. 941) |
| **E3** | `'customs_vat'` | **`order_type != 'on_hand'`** | `customs_vat_total` (l. 623) | `stage_3_status` (l. 878) | `can_upload_stage_3` (l. 922) | `get_customs_vat_deadline()` (l. 949) |
| **E4** | `'domestic_shipping'` | **zawsze** | `shipping_cost` (kolumna, l. 179) | `stage_4_status` (l. 901) | `can_upload_stage_4` (l. 933) | `get_shipping_pl_deadline()` (l. 957) |

- `stage_2_status` (l. 855) zwraca **`None`** gdy `payment_stages != 4` (etap nie istnieje); inaczej
  `'none'` (brak rekordu) lub `conf.status`. `stage_3_status` / `stage_4_status` / `product_payment_status`
  zwracają `'none'` przy braku rekordu, inaczej `conf.status` (`'pending'|'approved'|'rejected'`).
- **Liczba etapów wynika z kombinacji** (zgodne ze specem sekcja 6):
  - **on_hand** → E1 + E4 (= 2 etapy; E3 odpada przez `order_type != 'on_hand'`, E2 odpada bo
    `payment_stages != 4`).
  - **exclusive / pre_order, `payment_stages == 3`** → E1 + E3 + E4 (= 3 etapy).
  - **exclusive / pre_order, `payment_stages == 4`** → E1 + E2 + E3 + E4 (= 4 etapy).
- **`stage_amounts` (kwoty per etap)** — autorytatywne mapowanie z uploadu
  (`modules/client/payment_confirmations.py:351–358`): `product→effective_total`,
  `korean_shipping→proxy_shipping_total`, `customs_vat→customs_vat_total`,
  `domestic_shipping→Decimal(shipping_cost)`. **Brak procentów / zaliczek** — każdy etap to PEŁNA kwota
  odrębnej pozycji kosztowej, nie ułamek wartości produktu.
- **Deadline'y NIE są na `PaymentConfirmation`** — to metody `Order.get_*_deadline()` sięgające do
  `PolandOrder.payment_deadline` (E2), `PolandOrder.customs_payment_deadline` (E3),
  `ShippingRequest.payment_deadline` (E4). Zwracają `datetime` lub `None`. E1 nie ma deadline.
- **`total_to_pay`** (l. 358–380) = E1 + (E2 gdy `payment_stages==4`) + (E3 gdy `≠on_hand`) + E4.
  **`remaining_to_pay`** (l. 382–394) = `total_to_pay − paid_amount` (podłoga 0). `paid_amount`
  akumuluje sumę WSZYSTKICH zatwierdzonych etapów. (Uwaga: `grand_total`/`remaining_amount` obejmują
  tylko E1+E4 — NIE używamy ich do pełnej należności.)

### Model `PaymentConfirmation` (`modules/orders/models.py:1479–1586`)
- `id`, `order_id` (FK NOT NULL), `payment_method_id` (FK NULL), `payment_stage`
  **String(50) NOT NULL** ∈ `{'product','korean_shipping','customs_vat','domestic_shipping'}` (l. 1518),
  `amount` Numeric(10,2) NOT NULL (l. 1525), `proof_file` String(255) NULL (l. 1526),
  `uploaded_at` DateTime NULL, `status` **String(20) NOT NULL default `'pending'`** ∈
  `{'pending','approved','rejected'}` (l. 1530), `rejection_reason` Text NULL (l. 1536),
  `created_at`/`updated_at`. **Brak kolumny `deadline`.**
- Relacja na Order: `payment_confirmations` **`lazy='dynamic'`** (l. 240) — to QUERY, nie lista.
  Properties etapów filtrują je per `payment_stage`. Properties `is_pending/is_approved/is_rejected`,
  `has_proof`, `proof_url`, `stage_display_name` (mapa PL, l. 1574–1583).

### Model `Order` — pola do serializacji (`modules/orders/models.py`)
- `id` (l. 159), `order_number` String(20) format `PO/00000001` (l. 160), `order_type`
  **String(50) FK→`order_types.slug`** default `'on_hand'` (l. 161) — wartości `'on_hand'`/`'exclusive'`/
  `'pre_order'`, **NIE ma `order_type_id`**; `user_id` FK NOT NULL (l. 163), `status` **String(50)
  FK→`order_statuses.slug`** default `'nowe'` (l. 172).
- **Status I order_type to FK do tabel lookup** (pamięć projektu była nieścisła — to NIE luźny string;
  kolumna trzyma slug, relacja daje `name`/`badge_color`). Tabela `order_statuses` (`OrderStatus`,
  l. 61) jest **zarządzana z bazy przez admina** — NIE zakładaj sztywnej listy slugów; czytaj
  `status_display_name` / `status_badge_color` (mają fallback: name→slug, color→`#6B7280`, więc działa
  nawet gdy `status_rel is None` — kluczowe dla testów bez seedowania `OrderStatus`).
- Kwoty: `total_amount` Numeric NOT NULL default 0.00 (E1, l. 177), `paid_amount` NOT NULL default 0.00
  (l. 178), `shipping_cost` NOT NULL default 0.00 (E4, l. 179), `proxy_shipping_cost` default 0.00
  (E2, l. 180), `customs_vat_sale_cost` default 0.00 (E3, l. 181). `payment_stages` Integer **NULL**
  (l. 190; wartości 2/3/4). `offer_page_id` FK NULL, `offer_page_name` String(200) NULL (l. 189,
  snapshot), `custom_name` String(50) NULL (l. 216, alias klienta), `notes` Text NULL (l. 219).
  `created_at` default `get_local_now` (l. 232).
- **`get_local_now()` (l. 29–59) zwraca naive datetime w czasie polskim (Europe/Warsaw), bez tzinfo.**
  Serializacja `.isoformat()` → bez offsetu (parytet z webem — web też operuje na tym czasie).
- Properties gotowe do użycia: `customer_name` (l. 248), `status_display_name` (l. 264),
  `status_badge_color` (l. 257), `type_display_name` (l. 278; dla `exclusive` → `"Exclusive - {nazwa}"`),
  `items_count` (suma quantity, l. 301), `effective_total` (l. 584), `effective_grand_total`
  (= effective_total + shipping, l. 607), `total_to_pay`/`remaining_to_pay`. **Brak `to_dict()`.**
- `effective_total` (l. 584–604) iteruje `self.items`: pomija `is_set_fulfilled is False`, liczy
  proporcjonalnie `fulfilled_quantity < quantity`, inaczej pełne `item.total`. **Zamówienie BEZ pozycji
  → `effective_total == 0`** (w testach trzeba dodać `OrderItem` dla niezerowej wartości).

### Model `OrderItem` (`modules/orders/models.py:973–1097`)
- `id`, `order_id` FK NOT NULL, `product_id` FK **nullable** (NULL dla custom / pełnych setów, l. 982),
  `custom_name` String(255) (l. 985), `is_custom` Bool (l. 987), `is_full_set` Bool default False
  (l. 988), `selected_size` String(50) NULL (l. 991), `quantity` Int NOT NULL (l. 994), `price`
  Numeric NOT NULL (cena jednostkowa, l. 995), `total` Numeric NOT NULL (= price×quantity, l. 996),
  `is_bonus` Bool **NOT NULL default False** (gratis, l. 1020), `bonus_source_section_id` FK NULL
  (l. 1021). Pola setów: `is_set_fulfilled` Bool **nullable** (NULL=nie dotyczy, True=zmieścił się,
  False=przepadł, l. 1009), `set_section_id` FK NULL (l. 1010), `set_number` Int NULL (numer setu 1-based,
  l. 1011), `fulfilled_quantity` Int NULL (l. 1017).
- **Rozróżnianie typów pozycji:** bonus = `is_bonus == True`; pełny set = `is_full_set == True`
  (zwykle `product_id is None`); pozycja w secie = `set_section_id` + `set_number` + status
  `is_set_fulfilled`; zwykła pozycja = `is_bonus=False, is_full_set=False, is_set_fulfilled=None`.
- **Properties bezpieczne na usunięty produkt** (`item.product` może być `None`): `product_name`
  (l. 1038, `custom_name`→`product.name`→`'Unknown Product'`), `product_name_with_size` (l. 1045),
  `product_sku` (l. 1053), **`product_image_url`** (l. 1065–1076; zwraca gotowy URL z prefiksem
  `/static/...`, placeholder dla custom/set i dla usuniętego produktu — **NIGDY None**). Mobile dokleja
  `request.url_root` (URL absolutny) zamiast surowego `item.product.primary_image`.

### Webowe trasy klienta (parytet — `modules/orders/routes.py`)
- **Lista `client_list` (l. 1591–1675, `@login_required`):** baza `Order.query.filter_by(
  user_id=current_user.id)`. Filtry: `status` (pojedynczy, l. 1599/1616–1617) / `statuses` (CSV,
  l. 1600/1611–1615), `date_from`/`date_to`, `search` (order_number/custom_name), `payment_status`
  (paid/unpaid/partial). **BRAK filtra po `order_type`** → zwraca WSZYSTKIE typy. **Nieznany status
  → po prostu `Order.status == status` → puste wyniki (BEZ walidacji/400).** Sort `created_at.desc()`,
  `per_page = 20` (stały). Mobilny `?type=` to NOWY filtr bez webowego odpowiednika (patrz D1).
- **Szczegół `client_detail` (l. 1678–1690, `@login_required`):** `order = Order.query.get_or_404(
  order_id)` → **404 gdy nie istnieje**; `if order.user_id != current_user.id: abort(403)` →
  **403 dla cudzego zamówienia**. **Mobile zmienia 403→404** (brak wycieku istnienia — patrz Korekta 4).
- **Serializacja webowa do skopiowania** — `get_recent_orders` (l. 347–358, `/api/recent-orders`):
  `{id, order_number, customer_name, status, status_display_name, status_badge_color,
  effective_grand_total (float), detail_url}`. Mobilny brief = ten kształt + `order_type`,
  `items_count`, `offer_page_name`, kwoty w **groszach**.

### Webowy dashboard klienta (`modules/client/routes.py:90–238`, `@login_required`)
Logika INLINE w trasie `dashboard()` (brak serwisu). Metryki widoczne klientowi (kafelki w
`templates/client/dashboard.html`) i zapytania:
- `orders.all` = `Order.query.filter_by(user_id).count()` (l. 101).
- `orders.in_progress` = status ∈ `('nowe','oczekujace','w_realizacji','spakowane','wyslane')` (l. 102–104).
- `orders.delivered` = `status='dostarczone'` (l. 105).
- `orders.awaiting_shipping` = status ∈ `allowed_statuses` (z `Settings['shipping_request_allowed_statuses']`,
  fallback `['dostarczone_gom']`) AND NOT EXISTS w `ShippingRequestOrder` (l. 149–155).
- `payment.paid` = `SUM(paid_amount)` (l. 108–110). `payment.to_pay` = suma `o.remaining_to_pay` po
  kandydatach (filtr `paid_amount < total+shipping+proxy+customs`), **wykluczając `exclusive` z
  niezamkniętą stroną** (`o.order_type=='exclusive' and o.offer_page and not o.offer_page.is_fully_closed`)
  (l. 116–130). To jedyna nietrywialna agregacja — rdzeń liczy property `remaining_to_pay` (jedno
  źródło prawdy).
- `recent_orders` = ostatnie 15 (`created_at.desc().limit(15)`), web tnie na `visible[:5]`/`buffer[5:10]`
  + `total`/`remaining` (l. 158–169). Mobile zwraca `visible[:5]` zserializowane + `total`.
- `chart_data` = zamówienia/dzień ostatnie 30 dni, puste dni zerami → `{labels:[...], values:[...]}`
  (l. 173–194).
- **Poza zakresem czysto-zamówieniowego /dashboard:** `offer_pages` (flagi widoczności stron sprzedaży,
  NIE per-user, l. 197–214 — apka ma własne `/api/offer-pages`), `contest_widget` (widget konkursu),
  `show_tour` (onboarding). „Witacz personalny" to czysty HTML (`first_name`); „Spotify/cytat dnia"
  NIE są zaimplementowane na tym ekranie (tylko pomysły). Patrz **D2** (zakres metryk).

### Testy / fixtury / środowisko / migracje
- **Baseline: `258 passed`** (`source venv/bin/activate && python -m pytest`, zweryfikowane
  `--collect-only` 2026-06-12; pełny suite ~2.5 min). TYLKO `python -m pytest` (gołe `pytest` pada na
  `No module named 'app'`).
- **Głowa migracji: `c72aad290158` (zweryfikowane `flask db heads`).** E5 = czysty odczyt → **ZERO
  migracji.** (Gdyby implementacja wymusiła zmianę modelu — STOP i migracja Flask-Migrate; nie spodziewane.)
- **conftest (`tests/conftest.py`)**: `make_user(role='client', email=None, **kwargs)` — **NIE ustawia
  hasła** (helper `_auth` robi `u.set_password('Haslo123!')`); `make_product(name=None,
  sale_price=99.00, quantity=10, **kwargs)`; **`make_order(user, status='nowe', total_amount=100.00,
  created_at=None, **kwargs)`** — przyjmuje OBIEKT `user` (nie id); `order_number` hardcoded
  `PO/{n:08d}` (NIE przez `generate_order_number` → **nie wymaga seedowania `OrderType`**); **NIE
  tworzy `OrderItem` ani `PaymentConfirmation`** (tworzymy je inline w testach przez helpery).
  `**kwargs` pozwala `order_type=...`, `payment_stages=...`, `shipping_cost=...`,
  `proxy_shipping_cost=...`, `customs_vat_sale_cost=...`, `offer_page_name=...`.
- **Brak jakichkolwiek testów odczytu zamówień / `PaymentConfirmation` / dashboardu** — E5 to greenfield
  testowy (pierwsze pokrycie). Helper `_auth(client, db, make_user) → (headers, user)` kopiowany per plik
  (kanon w `tests/test_mobile_api_offers.py:11`). Wzorzec paginacji w `tests/test_mobile_api_shop.py:119`
  (asercja `body['pagination'] == {'page','per_page','total','has_next'}`).
- `/docs` w `.gitignore` → commit planu przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem + E1–E4 — zatwierdzane wraz z planem)

1. **Kwoty w groszach (int).** Web zwraca PLN (float) — mobile wszędzie **grosze** (`to_grosze`):
   `total`, `total_amount`, koszty wysyłki, kwoty etapów, `paid_amount`, `remaining_to_pay`,
   `payment.paid`/`payment.to_pay`. Parytet z E1–E4.
2. **Obrazki pozycji jako absolutne URL-e.** `item.product_image_url` (zawiera `/static/...`) →
   `request.url_root.rstrip('/') + product_image_url`. Placeholder dla custom/set/usuniętego produktu
   (property nigdy nie zwraca None).
3. **Lista zwraca wszystkie typy zamówień** (parytet z webem, który nie filtruje po typie). Filtr
   `?type=` to NOWE rozszerzenie mobilne (patrz D1). Sort `created_at.desc()`, paginacja `json_page`,
   `per_page` domyślnie 20, max 50.
4. **Szczegół cudzego zamówienia → `404 order_not_found` (NIE 403).** Web robi `abort(403)` (wyciek
   istnienia: 403 ≠ 404). Mobile **maskuje istnienie**: nieistniejące ORAZ nienależące do usera →
   identyczne `404 order_not_found`. To celowe wzmocnienie bezpieczeństwa kontraktu API (zgodne z
   wymaganiem zadania „cudze id → 404, bez wycieku istnienia").
5. **Etapy płatności = lista zbudowana z properties modelu.** `GET /orders/<id>` zwraca
   `payment_stages: [{stage, stage_index, name, amount (grosze), status, can_upload, deadline (ISO|null),
   has_proof, rejection_reason}]` — tylko etapy OBECNE dla danego zamówienia (on_hand: 2; exclusive/
   preorder: 3 lub 4). Apka buduje z tego ekran płatności (E6 doda upload). E5 **tylko CZYTA**.
6. **Nazwy etapów — jeden kanon w mobilnym serializerze.** Kod webowy ma 3 rozbieżne mapy nazw
   (`PaymentConfirmation.stage_display_name`, `PAYMENT_STAGE_LABELS`, `stage_N_name`). Mobile używa
   stabilnej mapy `_STAGE_LABELS` (oparta na `PaymentConfirmation.stage_display_name`, najautorytatywniej
   na modelu): `product→'Płatność za produkt'`, `korean_shipping→'Wysyłka z Korei'`,
   `customs_vat→'Cło i VAT'`, `domestic_shipping→'Wysyłka krajowa'`. Plus `stage_index` (`'E1'..'E4'`)
   dla stabilnego porządku w apce.
7. **`/dashboard` odwzorowuje kafelki zamówieniowe weba** (NIE wymyśla metryk): `orders{all,
   in_progress,delivered,awaiting_shipping}`, `payment{paid,to_pay}` (grosze), `recent_orders`
   (zserializowane brief), `chart` (30 dni). Widgety nie-zamówieniowe (offer_pages/contest/tour) poza
   zakresem (D2).

---

## Decyzje — ROZSTRZYGNIĘTE przez Konrada 2026-06-13 (wszystkie wg rekomendacji)

> **D1:** nieznany `?type=` → 400 invalid_input (status pass-through jak web). **D2:** dashboard
> pełny jak web (liczniki, paid/to_pay, 5 ostatnich, wykres 30 dni). **D3:** wariant (a) —
> ekstrakcja dashboard_service + refaktor weba bez zmiany zachowania (parity-testy).

## Decyzje do podjęcia przez Konrada (prawdziwe rozgałęzienia — NIE rozstrzygam arbitralnie)

> **Rozstrzygnąć PRZED implementacją:** D1 → Task 1, D2 → Task 4, D3 → Task 4 (architektura).
> Poniższe taski zapisano wg rekomendacji; przy innym wyborze dopisz oznaczone warianty.

- **D1 — Walidacja filtra `?type=` (i `?status=`) na liście.**
  - **`status`:** parytet z webem — pass-through, **nieznany status → puste wyniki** (web nie waliduje;
    `order_statuses` jest dynamiczne/zarządzane przez admina, więc twarda lista byłaby krucha).
    **Rekomendacja: pass-through (bez 400).** (Brak realnego rozgałęzienia — przyjęte jak web.)
  - **`type`:** zamknięty zbiór `{on_hand, exclusive, pre_order}`, NOWY parametr bez webowego
    precedensu. (a) **waliduj → `400 invalid_input`** dla nieznanej wartości (łapie literówki klienta
    wcześnie, mały zamknięty zbiór) — **rekomendowane**; (b) pass-through (nieznany typ → puste wyniki,
    spójnie ze `status`). **Rekomendacja: (a)** — czytelny kontrakt dla zamkniętego enuma.
- **D2 — Zakres metryk `/dashboard`.** (a) **Pełny zestaw zamówieniowy** (proponowane): `orders` (4
  liczniki) + `payment{paid,to_pay}` + `recent_orders` (5) + `chart` (30 dni) — pełny parytet z
  kafelkami i wykresem weba; (b) minimalny: tylko `orders` (4 liczniki) + `recent_orders` (bez
  `payment.to_pay` i wykresu — pomija najcięższą agregację). **Rekomendacja: (a)** — apka ma ten sam
  ekran główny co web; koszt niski (logika `remaining_to_pay` już w property). offer_pages/contest/tour
  **poza zakresem w obu wariantach** (osobne widgety/endpointy).
- **D3 — Architektura `/dashboard`: serwis współdzielony vs lokalny helper mobilny.**
  - **(a) Ekstrakcja `modules/client/dashboard_service.py::get_client_dashboard_stats(user)`**
    (wzorzec E1–E2: logika z trasy → serwis), web `dashboard()` refaktorowany by ją wołać (bez zmiany
    zachowania), mobile woła ten sam serwis. **Zalety:** jedno źródło prawdy agregacji, pierwszy test
    parytetu dla (dziś nietestowanego) dashboardu weba. **Wada:** dotyka produkcyjnej trasy weba
    (mechaniczny refaktor, ale przy zamrożeniu wdrożeń to ryzyko do zaakceptowania).
  - **(b) Lokalny helper mobilny `_dashboard_stats(user)`** w `orders_routes.py` (duplikuje ~5 zapytań
    agregujących). **Zalety:** ZERO dotknięcia produkcyjnego weba (spójne z „E5 = czysty odczyt" +
    zamrożenie wdrożeń); rdzeń liczy i tak property `remaining_to_pay` (logika biznesowa nie jest
    duplikowana, tylko zapytania-liczniki). **Wada:** dwie kopie zapytań-liczników (ryzyko kosmetycznego
    rozjazdu liczb przy przyszłych zmianach).
  - **Rekomendacja: (a)** dla spójności z ustalonym wzorcem E1–E2 i parytetu (jedno źródło prawdy +
    test). Wybierz **(b)** jeśli przy zamrożeniu wdrożeń wolisz NIE ruszać produkcyjnej trasy weba w
    czysto-odczytowym etapie. **Taski zapisano wg (a); wariant (b) oznaczony „[D3=(b)]".**

---

## File Structure

- `modules/api_mobile/orders_routes.py` — **NOWY**: `GET /orders`, `GET /orders/<id>`, `GET /dashboard`
  + serializery (`_serialize_order_brief`, `_serialize_order_detail`, `_serialize_order_item`,
  `_serialize_payment_stages`). Tasks 1–4.
- `modules/api_mobile/__init__.py` — Task 1: dopisać `from . import orders_routes` (po `offers_routes`).
- `modules/client/dashboard_service.py` — **NOWY [D3=(a)]** (Task 4): `get_client_dashboard_stats(user)`.
- `modules/client/routes.py` — **[D3=(a)]** (Task 4): refaktor `dashboard()` by wołać serwis (bez zmiany
  zachowania). **[D3=(b)]: pominąć — bez dotknięcia weba.**
- `tests/test_mobile_api_orders.py` — **NOWY** (Tasks 1–4): testy tras E5 (`_auth` + helpery
  `_add_item`/`_add_payment` skopiowane lokalnie).
- `tests/test_client_dashboard_service.py` — **NOWY [D3=(a)]** (Task 4): testy serwisu dashboardu.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 5: korekty kontraktu E5.

---

### Task 1: `GET /orders` — lista zamówień (brief serializer + filtry status/type + paginacja)

**Files:** Create `modules/api_mobile/orders_routes.py`; modify `modules/api_mobile/__init__.py`;
Create `tests/test_mobile_api_orders.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_orders.py`:
```python
"""Testy E5: mobilne API odczytu zamówień + dashboard.

Helper _auth skopiowany z tests/test_mobile_api_offers.py.
make_order (conftest) NIE tworzy OrderItem ani PaymentConfirmation — robią to helpery niżej.
"""
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _add_item(db, order, product=None, quantity=1, price=Decimal('10.00'),
              is_bonus=False, is_full_set=False, **kwargs):
    from modules.orders.models import OrderItem
    it = OrderItem(order_id=order.id, product_id=product.id if product else None,
                   quantity=quantity, price=price, total=price * quantity,
                   is_bonus=is_bonus, is_full_set=is_full_set, **kwargs)
    db.session.add(it); db.session.commit()
    return it


def _add_payment(db, order, stage, status='pending', amount=Decimal('20.00'),
                 proof_file='proof.jpg'):
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=amount, status=status, proof_file=proof_file)
    db.session.add(pc); db.session.commit()
    return pc


def test_orders_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/orders').status_code == 401


def test_orders_lists_only_owner(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    make_order(u, total_amount=100.00)
    make_order(u, total_amount=50.00)
    make_order(other, total_amount=999.00)            # cudze — nie powinno wyciec
    r = client.get('/api/mobile/v1/orders', headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body['pagination']['total'] == 2
    assert len(body['data']) == 2


def test_orders_brief_shape_and_grosze(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=50.00, order_type='pre_order',
                   offer_page_name='Drop PO', shipping_cost=Decimal('0.00'))
    p = make_product(sale_price=Decimal('50.00'))
    _add_item(db, o, product=p, quantity=1, price=Decimal('50.00'))
    r = client.get('/api/mobile/v1/orders', headers=h)
    obj = r.get_json()['data'][0]
    assert set(obj) >= {'id', 'order_number', 'order_type', 'status',
                        'status_display_name', 'status_badge_color', 'total',
                        'items_count', 'created_at', 'offer_page_name'}
    assert obj['order_type'] == 'pre_order'
    assert obj['total'] == 5000                       # effective_grand_total grosze (item 50 + ship 0)
    assert obj['items_count'] == 1
    assert obj['offer_page_name'] == 'Drop PO'


def test_orders_filter_by_type(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, order_type='on_hand')
    make_order(u, order_type='pre_order')
    make_order(u, order_type='pre_order')
    r = client.get('/api/mobile/v1/orders?type=pre_order', headers=h)
    body = r.get_json()
    assert body['pagination']['total'] == 2
    assert all(o['order_type'] == 'pre_order' for o in body['data'])


def test_orders_filter_by_status(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, status='nowe')
    make_order(u, status='dostarczone')
    r = client.get('/api/mobile/v1/orders?status=dostarczone', headers=h)
    body = r.get_json()
    assert body['pagination']['total'] == 1
    assert body['data'][0]['status'] == 'dostarczone'


def test_orders_invalid_type_400(client, db, make_user):
    # D1(a): nieznany type → 400 invalid_input. [D1(b): usuń ten test, oczekuj 200 + total 0]
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/orders?type=banana', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'invalid_input'


def test_orders_pagination(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    for _ in range(3):
        make_order(u)
    r = client.get('/api/mobile/v1/orders?per_page=2&page=1', headers=h)
    assert r.get_json()['pagination'] == {'page': 1, 'per_page': 2, 'total': 3, 'has_next': True}
    r2 = client.get('/api/mobile/v1/orders?per_page=2&page=2', headers=h)
    assert r2.get_json()['pagination']['has_next'] is False
```
> Run: `python -m pytest tests/test_mobile_api_orders.py -v` → FAIL (404/no route).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/orders_routes.py` (NOWY):
```python
"""Trasy odczytu zamówień klienta + dashboard dla mobilnego API (E5)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from modules.orders.models import Order
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze
from .validators import parse_int, ValidationError

ALLOWED_ORDER_TYPES = ('on_hand', 'exclusive', 'pre_order')


def _abs_image(path):
    """item.product_image_url zawiera już '/static/...' — dokleja origin (URL absolutny)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_order_brief(order):
    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_type': order.order_type,
        'status': order.status,
        'status_display_name': order.status_display_name,
        'status_badge_color': order.status_badge_color,
        'total': to_grosze(order.effective_grand_total),     # parytet z webową listą
        'items_count': order.items_count,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'offer_page_name': order.offer_page_name,
    }


@api_mobile_bp.route('/orders', methods=['GET'])
@jwt_required()
def orders_list():
    user_id = int(get_jwt_identity())
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page', default=20, min_value=1), 50)

    query = Order.query.filter_by(user_id=user_id)

    status = (request.args.get('status') or '').strip()
    if status:                                            # pass-through (parytet web; nieznany → pusto)
        query = query.filter(Order.status == status)

    order_type = (request.args.get('type') or '').strip()
    if order_type:                                        # D1(a): zamknięty enum → walidacja
        if order_type not in ALLOWED_ORDER_TYPES:
            raise ValidationError(f'Nieznany typ zamówienia: {order_type}.')
        query = query.filter(Order.order_type == order_type)

    query = query.order_by(Order.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return json_page(
        [_serialize_order_brief(o) for o in pagination.items],
        page=pagination.page, per_page=pagination.per_page,
        total=pagination.total, has_next=pagination.has_next,
    )
```
> `ValidationError` jest mapowany globalnie na `400 invalid_input` (errorhandler w `__init__.py`).
> **[D1(b)]:** usuń blok walidacji typu — `if order_type and order_type in ALLOWED_ORDER_TYPES:` (nieznany → pusto).

- [ ] **Step 3: Rejestracja** — `modules/api_mobile/__init__.py`, po `from . import offers_routes`:
  `from . import orders_routes  # noqa: E402,F401`.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_orders.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): lista zamówień klienta (GET /orders)"`

---

### Task 2: `GET /orders/<id>` — szczegóły (pozycje / sety / bonusy + ownership 404)

**Files:** Modify `modules/api_mobile/orders_routes.py`, `tests/test_mobile_api_orders.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_orders.py`:
```python
def test_order_detail_requires_jwt(client, db, make_user, make_order):
    u = make_user()
    o = make_order(u)
    assert client.get(f'/api/mobile/v1/orders/{o.id}').status_code == 401


def test_order_detail_not_found_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/orders/999999', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'order_not_found'


def test_order_detail_other_user_404(client, db, make_user, make_order):
    # Korekta 4: cudze zamówienie → 404 (NIE 403) — bez wycieku istnienia.
    h, u = _auth(client, db, make_user)
    other = make_user()
    o = make_order(other, total_amount=100.00)
    r = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h)
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'order_not_found'


def test_order_detail_items_sets_bonuses(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=60.00, order_type='pre_order', payment_stages=3)
    p1 = make_product(name='Bluza', sale_price=Decimal('50.00'))
    gift = make_product(name='Gratis', sale_price=Decimal('0.00'))
    _add_item(db, o, product=p1, quantity=1, price=Decimal('50.00'))
    _add_item(db, o, product=gift, quantity=1, price=Decimal('0.00'), is_bonus=True)
    _add_item(db, o, product=None, quantity=1, price=Decimal('10.00'),
              is_full_set=True, custom_name='Set niespodzianka', set_number=1)
    r = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['id'] == o.id
    assert d['order_type'] == 'pre_order'
    assert 'status_display_name' in d and 'remaining_to_pay' in d
    assert len(d['items']) == 3
    bluza = next(i for i in d['items'] if i['name'] == 'Bluza')
    assert bluza['price'] == 5000 and bluza['total'] == 5000     # grosze
    assert bluza['is_bonus'] is False and bluza['is_full_set'] is False
    assert bluza['image_url'].startswith('http')                 # absolutny URL
    bonus = next(i for i in d['items'] if i['is_bonus'])
    assert bonus['name'] == 'Gratis'
    full_set = next(i for i in d['items'] if i['is_full_set'])
    assert full_set['name'] == 'Set niespodzianka' and full_set['set_number'] == 1


def test_order_detail_financial_summary_grosze(client, db, make_user, make_order, make_product):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('15.00'))
    p = make_product(sale_price=Decimal('100.00'))
    _add_item(db, o, product=p, quantity=1, price=Decimal('100.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert d['total_amount'] == 10000          # E1, grosze
    assert d['shipping_cost'] == 1500          # E4
    assert d['total_to_pay'] == 11500          # on_hand: E1 100 + E4 15
    assert d['paid_amount'] == 0
    assert d['remaining_to_pay'] == 11500
```

- [ ] **Step 2: Implementacja** — dopisz do `modules/api_mobile/orders_routes.py`:
```python
def _serialize_order_item(item):
    return {
        'id': item.id,
        'product_id': item.product_id,
        'name': item.product_name,
        'sku': item.product_sku,
        'image_url': _abs_image(item.product_image_url),
        'selected_size': item.selected_size,
        'quantity': item.quantity,
        'price': to_grosze(item.price),
        'total': to_grosze(item.total),
        'is_bonus': bool(item.is_bonus),
        'is_full_set': bool(item.is_full_set),
        'set_number': item.set_number,
        'is_set_fulfilled': item.is_set_fulfilled,        # True / False / None
        'fulfilled_quantity': item.fulfilled_quantity,
    }


def _serialize_order_detail(order):
    return {
        'id': order.id,
        'order_number': order.order_number,
        'order_type': order.order_type,
        'order_type_display': order.type_display_name,
        'status': order.status,
        'status_display_name': order.status_display_name,
        'status_badge_color': order.status_badge_color,
        'created_at': order.created_at.isoformat() if order.created_at else None,
        'offer_page_name': order.offer_page_name,
        'custom_name': order.custom_name,
        'notes': order.notes,
        'payment_stages_count': order.payment_stages,
        # Finanse (grosze)
        'total_amount': to_grosze(order.total_amount),
        'shipping_cost': to_grosze(order.shipping_cost),
        'proxy_shipping_cost': to_grosze(order.proxy_shipping_cost),
        'customs_vat_cost': to_grosze(order.customs_vat_sale_cost),
        'total_to_pay': to_grosze(order.total_to_pay),
        'paid_amount': to_grosze(order.paid_amount),
        'remaining_to_pay': to_grosze(order.remaining_to_pay),
        'items': [_serialize_order_item(i) for i in order.sorted_items],
        'payment_stages': _serialize_payment_stages(order),   # Task 3
    }


def _get_owned_order_or_404(order_id):
    """Zamówienie usera z JWT albo None — cudze/nieistniejące traktujemy identycznie (bez wycieku)."""
    order = Order.query.get(order_id)
    if order is None or order.user_id != int(get_jwt_identity()):
        return None
    return order


@api_mobile_bp.route('/orders/<int:order_id>', methods=['GET'])
@jwt_required()
def order_detail(order_id):
    order = _get_owned_order_or_404(order_id)
    if order is None:
        return json_err('order_not_found', 'Zamówienie nie istnieje.', 404)
    return json_ok(_serialize_order_detail(order))
```
> **W Task 2 dodaj tymczasowy stub** `def _serialize_payment_stages(order): return []` żeby detal
> przeszedł GREEN bez etapów; Task 3 zastępuje go pełną implementacją (testy etapów dochodzą w Task 3).
> `order.sorted_items` (l. 559) sortuje pozycje (poza-setem na końcu) — parytet z webem.

- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_orders.py -v` (testy z Task 1+2 zielone;
  `payment_stages` chwilowo `[]`).
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): szczegóły zamówienia (pozycje, sety, bonusy)"`

---

### Task 3: `GET /orders/<id>` — etapy płatności E1–E4 (SERCE E5)

**Files:** Modify `modules/api_mobile/orders_routes.py`, `tests/test_mobile_api_orders.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_orders.py`:
```python
def test_payment_stages_preorder_4(client, db, make_user, make_order):
    """Pre-order 4-etapowy: E1+E2+E3+E4 ze statusami i kwotami."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=100.00, order_type='pre_order', payment_stages=4,
                   proxy_shipping_cost=Decimal('30.00'),
                   customs_vat_sale_cost=Decimal('20.00'),
                   shipping_cost=Decimal('15.00'))
    _add_payment(db, o, 'product', status='approved')
    _add_payment(db, o, 'korean_shipping', status='pending')
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    by = {s['stage']: s for s in d['payment_stages']}
    assert set(by) == {'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'}
    assert [s['stage_index'] for s in d['payment_stages']] == ['E1', 'E2', 'E3', 'E4']
    assert by['product']['status'] == 'approved'
    assert by['korean_shipping']['status'] == 'pending'
    assert by['customs_vat']['status'] == 'none'         # brak rekordu
    assert by['korean_shipping']['amount'] == 3000        # grosze
    assert by['domestic_shipping']['amount'] == 1500
    assert by['product']['has_proof'] is True             # _add_payment ma proof_file


def test_payment_stages_onhand_2(client, db, make_user, make_order):
    """On-hand: TYLKO 2 etapy E1+E4 (brak E2/E3)."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=80.00, order_type='on_hand', shipping_cost=Decimal('15.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert {s['stage'] for s in d['payment_stages']} == {'product', 'domestic_shipping'}
    assert [s['stage_index'] for s in d['payment_stages']] == ['E1', 'E4']


def test_payment_stages_exclusive_3(client, db, make_user, make_order):
    """Exclusive 3-etapowy: E1+E3+E4 (brak E2 bo payment_stages != 4)."""
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=80.00, order_type='exclusive', payment_stages=3,
                   customs_vat_sale_cost=Decimal('20.00'), shipping_cost=Decimal('10.00'))
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    assert {s['stage'] for s in d['payment_stages']} == {'product', 'customs_vat', 'domestic_shipping'}
    assert by_customs := next(s for s in d['payment_stages'] if s['stage'] == 'customs_vat')
    assert by_customs['amount'] == 2000                   # grosze
    assert by_customs['status'] == 'none'
    # każdy etap ma komplet pól kontraktu
    for s in d['payment_stages']:
        assert set(s) >= {'stage', 'stage_index', 'name', 'amount', 'status',
                          'can_upload', 'deadline', 'has_proof', 'rejection_reason'}


def test_payment_stage_rejected_reason(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, total_amount=50.00, order_type='on_hand', shipping_cost=Decimal('10.00'))
    pc = _add_payment(db, o, 'domestic_shipping', status='rejected')
    pc.rejection_reason = 'Nieczytelny dowód'
    db.session.commit()
    d = client.get(f'/api/mobile/v1/orders/{o.id}', headers=h).get_json()['data']
    e4 = next(s for s in d['payment_stages'] if s['stage'] == 'domestic_shipping')
    assert e4['status'] == 'rejected'
    assert e4['rejection_reason'] == 'Nieczytelny dowód'
```

- [ ] **Step 2: Implementacja** — zastąp stub `_serialize_payment_stages` w
  `modules/api_mobile/orders_routes.py`:
```python
_STAGE_LABELS = {
    'product': 'Płatność za produkt',
    'korean_shipping': 'Wysyłka z Korei',
    'customs_vat': 'Cło i VAT',
    'domestic_shipping': 'Wysyłka krajowa',
}


def _stage_entry(stage, stage_index, name, amount, status, can_upload, deadline, conf):
    return {
        'stage': stage,
        'stage_index': stage_index,
        'name': name,
        'amount': to_grosze(amount),
        'status': status,                                 # 'none'|'pending'|'approved'|'rejected'
        'can_upload': bool(can_upload),
        'deadline': deadline.isoformat() if deadline else None,
        'has_proof': bool(conf.has_proof) if conf else False,
        'rejection_reason': conf.rejection_reason if conf else None,
    }


def _serialize_payment_stages(order):
    """Lista etapów OBECNYCH dla zamówienia (czyta properties Order — jedno źródło prawdy).

    on_hand: E1+E4 (2). exclusive/pre_order: E1(+E2 gdy payment_stages==4)+E3+E4 (3 lub 4).
    """
    stages = []
    # E1 — zawsze
    stages.append(_stage_entry(
        'product', 'E1', _STAGE_LABELS['product'], order.effective_total,
        order.product_payment_status, order.can_upload_product_payment,
        None, order.product_payment_confirmation))
    # E2 — tylko 4-etapowe
    if order.payment_stages == 4:
        stages.append(_stage_entry(
            'korean_shipping', 'E2', _STAGE_LABELS['korean_shipping'], order.proxy_shipping_total,
            order.stage_2_status, order.can_upload_stage_2,
            order.get_shipping_kr_deadline(), order.stage_2_confirmation))
    # E3 — nie dotyczy on_hand
    if order.order_type != 'on_hand':
        stages.append(_stage_entry(
            'customs_vat', 'E3', _STAGE_LABELS['customs_vat'], order.customs_vat_total,
            order.stage_3_status, order.can_upload_stage_3,
            order.get_customs_vat_deadline(), order.stage_3_confirmation))
    # E4 — zawsze
    stages.append(_stage_entry(
        'domestic_shipping', 'E4', _STAGE_LABELS['domestic_shipping'], order.shipping_cost,
        order.stage_4_status, order.can_upload_stage_4,
        order.get_shipping_pl_deadline(), order.stage_4_confirmation))
    return stages
```
> Etapy obecne wynikają z `order_type` + `payment_stages` (parytet z webem — patrz Zweryfikowane
> fakty / tabela). `stage_index` (`'E1'..'E4'`) daje apce stabilny porządek niezależnie od liczby etapów.

- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_orders.py -v`.
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): etapy płatności E1-E4 w szczegółach zamówienia"`

---

### Task 4: `GET /dashboard` — statystyki klienta [D2 zakres, D3 architektura]

**Files [D3=(a)]:** Create `modules/client/dashboard_service.py`; modify `modules/client/routes.py`,
`modules/api_mobile/orders_routes.py`; Create `tests/test_client_dashboard_service.py`; modify
`tests/test_mobile_api_orders.py`.
**Files [D3=(b)]:** modify `modules/api_mobile/orders_routes.py`, `tests/test_mobile_api_orders.py`
(bez dotykania `modules/client/`).

- [ ] **Step 1: Testy serwisu (RED) [D3=(a)]** — `tests/test_client_dashboard_service.py`:
```python
from decimal import Decimal


def test_dashboard_stats_counts(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    u = make_user()
    make_order(u, status='nowe')
    make_order(u, status='oczekujace')
    make_order(u, status='dostarczone')
    make_user()  # inny user bez zamówień
    stats = get_client_dashboard_stats(u)
    assert stats['orders']['all'] == 3
    assert stats['orders']['in_progress'] == 2          # nowe + oczekujace
    assert stats['orders']['delivered'] == 1
    assert len(stats['recent_orders']['visible']) == 3
    assert 'labels' in stats['chart_data'] and 'values' in stats['chart_data']


def test_dashboard_stats_to_pay(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    u = make_user()
    make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('20.00'))
    stats = get_client_dashboard_stats(u)
    # on_hand total_to_pay = 100 + 20 = 120; paid 0
    assert stats['payment']['to_pay'] == Decimal('120.00')
    assert stats['payment']['paid'] == Decimal('0.00')


def test_dashboard_stats_isolated_per_user(db, make_user, make_order):
    from modules.client.dashboard_service import get_client_dashboard_stats
    a, b = make_user(), make_user()
    make_order(a); make_order(b); make_order(b)
    assert get_client_dashboard_stats(a)['orders']['all'] == 1
    assert get_client_dashboard_stats(b)['orders']['all'] == 2
```

- [ ] **Step 2: Serwis [D3=(a)]** — `modules/client/dashboard_service.py` (NOWY): przenieś sekcje 1–5
  z `modules/client/routes.py::dashboard()` (l. 97–194), zamieniając `current_user` → parametr `user`.
  Zwraca surowe dane (Order obj + Decimale + liczby):
```python
"""Statystyki zamówieniowe dashboardu klienta — współdzielone przez web i mobilne API (E5)."""

import json
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy import func as sql_func

from extensions import db
from modules.orders.models import Order
from modules.shipping.models import ShippingRequestOrder   # ścieżkę potwierdzić przy implementacji
from models import Settings                                 # ścieżkę potwierdzić (jak w client/routes.py)


def get_client_dashboard_stats(user):
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)

    orders_all = Order.query.filter_by(user_id=user.id).count()
    orders_in_progress = Order.query.filter_by(user_id=user.id).filter(
        Order.status.in_(['nowe', 'oczekujace', 'w_realizacji', 'spakowane', 'wyslane'])
    ).count()
    orders_delivered = Order.query.filter_by(user_id=user.id).filter_by(status='dostarczone').count()

    paid_total = db.session.query(
        sql_func.coalesce(sql_func.sum(Order.paid_amount), 0)
    ).filter_by(user_id=user.id).scalar() or Decimal('0.00')

    to_pay_orders = Order.query.filter_by(user_id=user.id).filter(
        Order.paid_amount < (
            Order.total_amount + Order.shipping_cost
            + sql_func.coalesce(Order.proxy_shipping_cost, 0)
            + sql_func.coalesce(Order.customs_vat_sale_cost, 0)
        )
    ).all()
    to_pay_total = sum(
        (o.remaining_to_pay for o in to_pay_orders
         if not (o.order_type == 'exclusive' and o.offer_page and not o.offer_page.is_fully_closed)),
        Decimal('0.00'),
    )

    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    allowed_statuses = ['dostarczone_gom']
    if setting and setting.value:
        try:
            allowed_statuses = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed_statuses = ['dostarczone_gom']
    in_shipping_request = db.session.query(ShippingRequestOrder.order_id).filter(
        ShippingRequestOrder.order_id == Order.id).exists()
    orders_awaiting_shipping = Order.query.filter(and_(
        Order.user_id == user.id, Order.status.in_(allowed_statuses), ~in_shipping_request)).count()

    recent_all = Order.query.filter_by(user_id=user.id).order_by(
        Order.created_at.desc()).limit(15).all()
    total_orders = Order.query.filter_by(user_id=user.id).count()

    orders_by_day = db.session.query(
        sql_func.date(Order.created_at).label('d'), sql_func.count(Order.id)
    ).filter(Order.user_id == user.id,
             sql_func.date(Order.created_at) >= thirty_days_ago
    ).group_by(sql_func.date(Order.created_at)).all()
    all_dates = [(thirty_days_ago + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(31)]
    by_date = {str(r[0]): r[1] for r in orders_by_day}

    return {
        'orders': {'all': orders_all, 'in_progress': orders_in_progress,
                   'delivered': orders_delivered, 'awaiting_shipping': orders_awaiting_shipping},
        'payment': {'paid': paid_total, 'to_pay': to_pay_total},
        'recent_orders': {'visible': recent_all[:5], 'buffer': recent_all[5:10],
                          'total': total_orders, 'remaining': max(0, total_orders - 5)},
        'chart_data': {'labels': all_dates, 'values': [by_date.get(d, 0) for d in all_dates]},
    }
```
> **UWAGA implementacyjna:** dokładne ścieżki importów (`ShippingRequestOrder`, `Settings`, `and_`,
> `sql_func`) skopiuj z nagłówka/treści `modules/client/routes.py` (tam już działają) — powyżej to
> wzorzec, nie pewnik ścieżek. Refaktor `dashboard()`: zastąp l. 97–194 wywołaniem
> `stats = get_client_dashboard_stats(current_user._get_current_object())` i zbuduj dotychczasowe
> kwargs template z `stats` (web nadal `float(...)` na payment, przekazuje obiekty `recent_orders`).
> Sekcje 6 (offer_pages), contest_widget, show_tour **zostają w trasie** (nie-zamówieniowe).
> **[D3=(b)]:** pomiń serwis i refaktor weba — przenieś powyższą logikę do `_dashboard_stats(user)`
> w `orders_routes.py`; usuń `tests/test_client_dashboard_service.py`, zachowaj testy mobilne (Step 4).

- [ ] **Step 3: Endpoint mobilny** — dopisz do `modules/api_mobile/orders_routes.py`:
```python
@api_mobile_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def client_dashboard():
    from modules.auth.models import User
    from modules.client.dashboard_service import get_client_dashboard_stats   # [D3=(b): _dashboard_stats]
    user = User.query.get(int(get_jwt_identity()))
    if user is None:
        return json_err('user_not_found', 'Nie znaleziono użytkownika.', 404)
    stats = get_client_dashboard_stats(user)
    return json_ok({
        'orders': stats['orders'],
        'payment': {
            'paid': to_grosze(stats['payment']['paid']),
            'to_pay': to_grosze(stats['payment']['to_pay']),
        },
        'recent_orders': [_serialize_order_brief(o) for o in stats['recent_orders']['visible']],
        'recent_orders_total': stats['recent_orders']['total'],
        'chart': stats['chart_data'],
    })
```

- [ ] **Step 4: Testy mobilne (RED→GREEN)** — dopisz do `tests/test_mobile_api_orders.py`:
```python
def test_dashboard_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/dashboard').status_code == 401


def test_dashboard_counts_and_recent(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, status='nowe')
    make_order(u, status='oczekujace')
    make_order(u, status='dostarczone')
    make_user()  # cudzy bez zamówień
    d = client.get('/api/mobile/v1/dashboard', headers=h).get_json()['data']
    assert d['orders'] == {'all': 3, 'in_progress': 2, 'delivered': 1, 'awaiting_shipping': 0}
    assert d['recent_orders_total'] == 3
    assert 'order_number' in d['recent_orders'][0] and 'total' in d['recent_orders'][0]
    assert len(d['chart']['labels']) == 31


def test_dashboard_to_pay_grosze(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    make_order(u, total_amount=100.00, order_type='on_hand', shipping_cost=Decimal('20.00'))
    d = client.get('/api/mobile/v1/dashboard', headers=h).get_json()['data']
    assert d['payment']['to_pay'] == 12000          # grosze (120 PLN)
    assert d['payment']['paid'] == 0
```

- [ ] **Step 5: GREEN** — `python -m pytest tests/test_mobile_api_orders.py tests/test_client_dashboard_service.py -v`.
- [ ] **Step 6: Commit** — `git commit -m "feat(mobile-api): dashboard klienta (GET /dashboard)"`
  (przy D3=(a) obejmuje serwis + refaktor weba).

---

### Task 5: Pełna regresja + aktualizacja specu + DoD

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** `python -m pytest tests/test_mobile_api_orders.py tests/test_client_dashboard_service.py -v`
  oraz pełne `python -m pytest` — oczekiwane **258 + ~22–24 nowych**, zero failów (web dashboard
  refaktorowany behawioralnie bez zmian — przy D3=(a)).
- [ ] **Step 2:** Spec — sekcja „Moje zamówienia + dashboard": dopisz notę korekt E5: (a) ścieżki
  `GET /orders`, `GET /orders/<id>`, `GET /dashboard`; (b) kwoty w groszach, obrazki absolutne;
  (c) lista zwraca wszystkie typy + filtry `status` (pass-through) / `type` (D1); (d) szczegół: pozycje/
  sety/bonusy + finanse + **etapy płatności E1–E4 budowane z properties Order** (obecność wg
  `order_type`+`payment_stages`: on_hand 2, exclusive/preorder 3 lub 4); kształt etapu `{stage,
  stage_index, name, amount, status, can_upload, deadline, has_proof, rejection_reason}`; (e) cudze/
  nieistniejące zamówienie → `404 order_not_found` (vs web 403); (f) `/dashboard` = kafelki
  zamówieniowe weba (D2); architektura serwisu (D3); (g) E5 to ODCZYT — upload dowodów to E6.
- [ ] **Step 3:** Commit (`git add -f docs/...`) — `git commit -m "docs(mobile-api): korekty kontraktu
  E5 (zamówienia + dashboard)"`

---

## Definition of Done (E5)

- [ ] **GET /orders:** za JWT, tylko zamówienia usera, wszystkie typy, filtry `status` (pass-through) +
  `type` (D1), paginacja `json_page` (default 20, max 50), brief w groszach (`effective_grand_total`),
  `order_type`/`status`/`status_display_name`/`offer_page_name`/`items_count`/`created_at`.
- [ ] **GET /orders/<id>:** za JWT, **cudze/nieistniejące → 404 `order_not_found`** (bez wycieku
  istnienia); pozycje (sety `is_full_set`/`set_number`, bonusy `is_bonus`, `selected_size`, ceny grosze,
  obrazki absolutne, bezpieczne na usunięty produkt); finanse w groszach (`total_amount`, koszty,
  `total_to_pay`, `paid_amount`, `remaining_to_pay`).
- [ ] **Etapy płatności (SERCE):** lista zbudowana z properties `Order` — obecność etapów wg
  `order_type`+`payment_stages` (on_hand: E1+E4; exclusive/preorder: E1(+E2)+E3+E4); każdy etap =
  `{stage, stage_index, name, amount (grosze), status (none/pending/approved/rejected), can_upload,
  deadline (ISO|null), has_proof, rejection_reason}`. ZERO duplikacji logiki (czytamy model).
- [ ] **GET /dashboard:** za JWT, metryki = kafelki zamówieniowe weba (D2): `orders` (4 liczniki),
  `payment{paid,to_pay}` (grosze), `recent_orders` (5, brief), `chart` (30 dni). Architektura wg D3.
- [ ] Wszystkie endpointy za JWT, kwoty w groszach, obrazki absolutne, paginacja `json_page`.
- [ ] **ZERO migracji** (head pozostaje `c72aad290158`); gdyby wymuszona zmiana modelu — migracja
  Flask-Migrate (nie spodziewane).
- [ ] Spec zaktualizowany o korekty kontraktu E5.
- [ ] Decyzje **D1–D3** rozstrzygnięte z Konradem PRZED implementacją odnośnych tasków (D1→Task 1,
  D2+D3→Task 4).
- [ ] [D3=(a)] Web `dashboard()` refaktorowany do serwisu BEZ zmiany zachowania (pełna regresja zielona;
  serwis pokryty testami).
- [ ] Pełny `python -m pytest` zielony. **NIE pushować** — wdrożenia WSTRZYMANE decyzją Konrada.

## Szacunek liczby testów

- GET /orders (Task 1): ~7 (requires_jwt, only_owner, brief_shape+grosze, filter_type, filter_status,
  invalid_type_400 [D1a], pagination).
- GET /orders/<id> szczegóły (Task 2): ~5 (requires_jwt, not_found_404, other_user_404,
  items_sets_bonuses, financial_summary).
- Etapy płatności (Task 3): ~4 (preorder_4, onhand_2, exclusive_3, rejected_reason).
- /dashboard (Task 4): serwis ~3 [D3=(a)] + mobile ~3 (requires_jwt, counts_and_recent, to_pay_grosze).
- **Razem: ~22–24 nowych testów.** Baseline po E5: **~280–282 passed** (start 258).
  [D3=(b): bez 3 testów serwisu → ~19–21 nowych.]

## Kolejność i bezpieczeństwo

Najpierw lista (Task 1, zero ryzyka — nowy odczyt), potem szczegół bez etapów (Task 2, ownership 404),
potem etapy płatności na bazie sprawdzonego detalu (Task 3 — serce, czyta stabilne properties modelu),
na końcu dashboard (Task 4 — jedyne ewentualne dotknięcie weba przy D3=(a), chronione testem serwisu +
pełną regresją). Każdy task: RED→GREEN→commit, pełna regresja przed mergem. Decyzje D1–D3 PRZED kodem.
**Bez push — produkcja nietknięta; E5 to czysty odczyt, zero migracji.**
