# API mobilne ThunderOrders — projekt backendu

**Data:** 2026-06-11
**Status:** Zatwierdzony projekt (spec) — przed planem implementacji
**Repo:** ThunderOrders (backend Flask)
**Powiązany spec:** aplikacja Flutter — `thunderorders-mobile/docs/specs/2026-06-11-mobile-app-flutter-design.md`

> Ten dokument opisuje **stronę backendową** projektu: nową warstwę API mobilnego
> w aplikacji ThunderOrders. Aplikacja kliencka (Flutter) jest opisana w osobnym
> specie w repo `thunderorders-mobile`. Oba dokumenty współdzielą **kontrakt API**
> zdefiniowany tutaj (sekcja „Kontrakt API") — to jest jedyne źródło prawdy dla endpointów.

---

## 1. Cel i kontekst

Budujemy natywną aplikację mobilną (Android + iOS) będącą **widokiem klienta** ThunderOrders —
odwzorowuje 1:1 to, co dziś robi zalogowany klient na www. Aplikacja jest osobnym projektem
(Flutter, repo `thunderorders-mobile`) i konsumuje dane przez **dedykowane API mobilne**.

Backend ThunderOrders jest dziś **web-first**: logowanie przez Flask-Login (session cookie),
ochrona CSRF, route'y zwracające HTML lub JSON zaprojektowany pod konkretne ekrany webowe.
To **nie nadaje się** dla klienta mobilnego (cookie/session i CSRF źle działają z apką).
Dlatego budujemy nową, czystą, wersjonowaną warstwę API z autoryzacją tokenową (JWT).

**Zakres (pełny klient):** auth, sklep on-hand, strony ofertowe (exclusive + pre-order),
moje zamówienia, płatności wieloetapowe, wysyłka (adresy + zlecenia), kolekcja, powiadomienia push.
**Poza zakresem:** panel admina, funkcje komputer↔telefon (np. QR upload — w apce zbędne, bo telefon ma aparat natywnie).

---

## 2. Decyzje architektoniczne (zatwierdzone)

| Obszar | Decyzja |
|--------|---------|
| Warstwa API | Nowy moduł `modules/api_mobile/`, blueprint prefix **`/api/mobile/v1`** (wersjonowanie od dnia 1) |
| Autoryzacja | **JWT** (`flask-jwt-extended`): access token (~30 min) + refresh token (~30 dni) |
| Odwoływanie tokenów | **Tak** — tabela unieważnionych tokenów (realny logout, blokada skradzionego urządzenia) → migracja |
| Rejestracja | **Pełna w apce** — register + weryfikacja 6-cyfrowym kodem e-mail (reużycie istniejącej logiki) |
| OAuth | **Google Sign-In TAK** (apka wysyła Google ID token → backend weryfikuje → wydaje JWT). **Facebook NIE.** |
| Real-time | **Socket.IO w MVP** — apka dopuszczona jako klient WS (CORS + auth WS przez JWT). Polling jako fallback. |
| Push | **FCM w MVP** — Firebase Cloud Messaging: tokeny urządzeń (migracja) + wysyłka po stronie backendu |
| Wymuszanie wersji | **Lekki mechanizm w MVP** — endpoint min. wymaganej wersji apki |
| Współdzielenie logiki | **Wyciągamy logikę biznesową do serwisów** (`modules/<x>/services.py`) — web i mobile z jednego źródła |
| CSRF | Endpointy mobilne **CSRF-exempt** (CSRF bezsensowne przy JWT); ochrona = token + rate-limiting (Flask-Limiter) |
| Kolejność prac | **Poziomo** — najpierw całe API (z testami pytest), potem aplikacja Flutter |

### Zasada nadrzędna: współdzielenie logiki, nie duplikacja

API mobilne wywołuje **te same modele i tę samą logikę biznesową** co web. Tam, gdzie logika
dziś siedzi „zaszyta" w route'ach webowych (checkout on-hand, place-order exclusive/preorder,
rezerwacje), w ramach tego projektu **wyciągamy ją do warstwy serwisowej**. Bez tego mielibyśmy
dwie kopie krytycznej logiki (np. walidacji stocku) — proszenie się o bugi i rozjazd web↔mobile.

To jest celowana poprawa istniejącego kodu jako część projektu — nie refactor dla samego refactoru.

---

## 3. Architektura wysokiego poziomu

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│   ThunderOrders (to repo)   │  HTTPS  │   thunderorders-mobile        │
│   Flask backend + API mobile│ ◄─────► │   Aplikacja Flutter           │
│   modules/api_mobile/v1/    │  JSON   │   (Android + iOS, Riverpod)   │
│                             │  + JWT  │                              │
└──────────────┬──────────────┘  + WS   └──────────────────────────────┘
               │
               │ współdzieli (NIE duplikuje):
               ▼
   modele SQLAlchemy + serwisy (logika biznesowa)
   z modułów: auth, products, offers, orders, client, payments
```

Serwer WS już istnieje (gunicorn_ws + eventlet + Redis message queue) — dla apki głównie
dopuszczamy ją jako klienta (CORS origins) i dodajemy auth WS przez JWT.

---

## 4. Autoryzacja i bezpieczeństwo (JWT)

### Przepływ tokenów
- **Access token (JWT, ~30 min)** — w każdym żądaniu: `Authorization: Bearer <token>`.
- **Refresh token (~30 dni)** — wyłącznie do pobrania nowego access tokenu; apka trzyma go
  w bezpiecznym magazynie OS (Keychain iOS / Keystore Android).
- Wygasł access → apka po cichu woła `/auth/refresh` i ponawia żądanie (interceptor w apce).
- Wygasł/unieważniony refresh → apka wylogowuje użytkownika.

### Odwoływanie tokenów (migracja)
Tabela np. `mobile_token_blocklist` (jti, user_id, typ, expires_at, created_at).
- `logout` dodaje jti refresh tokenu do blocklisty.
- Możliwość „wyloguj wszędzie" (unieważnij wszystkie refreshe użytkownika).
- Sprzątanie wygasłych wpisów (lazy lub okresowo).

### Google Sign-In (wzorzec mobilny, nie webowy redirect)
1. Flutter używa natywnego Google SDK → otrzymuje **ID token** od Google.
2. Apka: `POST /auth/google { id_token }`.
3. Backend weryfikuje ID token u Google (biblioteka google-auth), dopasowuje/zakłada usera
   (pole `google_id`, `email_verified=True`), wydaje nasze JWT.

### Rejestracja + weryfikacja
Reużycie istniejącej logiki: 6-cyfrowy kod e-mail (24h ważność), blokada po nieudanych próbach,
rate-limiting. Endpointy: `register`, `verify-email`, `resend-code`.

---

## 5. Kontrakt API (źródło prawdy dla obu repo)

Wszystkie ścieżki z prefiksem **`/api/mobile/v1`**. Format odpowiedzi spójny:
`{ "success": true, "data": {...} }` lub `{ "success": false, "error": {code, message, details?} }`.

### Konwencje
- **Paginacja:** `?page=N&per_page=M` → `{ data: [...], pagination: {page, per_page, total, has_next} }`.
- **Daty:** ISO 8601 (UTC); apka formatuje lokalnie.
- **Kwoty:** w groszach (integer) — unikamy błędów float. (Potwierdzone w E1; dotyczy też parametrów wejściowych, np. `price_min`/`price_max`. Kursy walut to współczynniki — pozostają floatem.)
- **Zdjęcia:** pełne URL-e absolutne (nie ścieżki względne).
- **Auth:** wszystkie poza `health`, `login`, `register`, `verify-email`, `resend-code`, `google`,
  `refresh`, `app-version` wymagają `Bearer`.

### Auth — `/auth/`
```
POST /register          { email, password, first_name, last_name, phone }   → wysyła kod
POST /verify-email      { email, code }                  → aktywuje konto, zwraca { access, refresh, user }
POST /resend-code       { email }
POST /login             { email, password }              → { access, refresh, user }
POST /google            { id_token }                     → { access, refresh, user }
POST /refresh           (Bearer refresh)                 → { access }
POST /logout            (Bearer refresh)                 → unieważnia refresh (blocklist)
GET  /me                (Bearer)                         → { user }
```
`user = { id, email, first_name, last_name, full_name, phone, role, avatar_url, email_verified }`

> **Korekta kontraktu (E0):** `refresh` i `logout` przyjmują refresh token w nagłówku
> `Authorization: Bearer <refresh_token>` (standard flask-jwt-extended), nie w body.

### Sklep on-hand — `/shop/`
```
GET    /products        ?q=&category=&size=&price_min=&price_max=&sort=&page=&per_page=   → lista on-hand (paginacja; ceny w groszach)
GET    /products/<id>                                          → szczegóły + zdjęcia + rozmiary
GET    /filters                                                → kategorie / rozmiary / zakres cen
GET    /cart                                                   → koszyk (CartItem z bazy)
POST   /cart/items      { product_id, quantity }
PATCH  /cart/items/<id> { quantity }
DELETE /cart/items/<id>
GET    /checkout/summary                                       → podsumowanie + adresy + metody
POST   /checkout        { create_shipping, address_id }
                                                              → atomowa walidacja stocku → Order(OH)
```

> **Korekty kontraktu (E2):** pozycje koszyka nie przyjmują `selected_size` — `CartItem` nie
> przechowuje rozmiaru; produkty on-hand mają jeden rozmiar, zwracany w pozycjach koszyka jako
> `size` (read-only) i zapisywany na `OrderItem` przy checkout. Checkout nie przyjmuje
> `delivery_method`/`payment_method` (płatności = etapy E1–E4 obsługiwane osobno; dostawa =
> opcjonalny ShippingRequest przez `create_shipping` + `address_id`). Kwoty w API mobilnym
> w groszach (int). Koperta błędu może zawierać opcjonalne `details`
> (np. `stock_errors` przy checkout, `available` przy przekroczeniu stanu).

> **Korekta kontraktu (E1):** lista przyjmuje też `size`, `price_min`, `price_max` (parytet z webem; wartości dostarcza `GET /filters`). `category` to nazwa producenta (tak modeluje to webowy sklep). Szczegóły produktu zawierają dodatkowo `variants` (inne produkty z grupy wariantów).

### Strony ofertowe — wspólne — `/offers/`
```
GET  /offer-pages            ?status=live|upcoming|closed&page=   → lista (exclusive + preorder)
GET  /offer-pages/<token>                                         → pełna struktura strony:
       page_type, status, starts_at, ends_at, payment_stages, payment_deadline,
       sekcje (produkty / sety / variant_group / bonusy)
GET  /offer-pages/<token>/availability                            → snapshot dostępności (live)
```

### Exclusive — rezerwacje + zamówienie — `/offers/<token>/`
```
POST /reserve        { session_id, product_id, quantity, selected_size }   → rezerwacja (2 min TTL)
POST /extend         { session_id }                       → +1 min (jednorazowo)
POST /release        { session_id, product_id }           → zwalnia
POST /place-order    { session_id, full_set_items[], order_note }
                                                          → atomowa walidacja → Order(EX) + bonusy + release
```
> `session_id` generuje **apka** (UUID), trzyma lokalnie, pokazuje countdown 2 min.
> Bezpieczeństwo (brak oversellingu) gwarantuje baza: `SELECT FOR UPDATE` + retry na deadlock —
> niezależnie od Socket.IO. Szczegóły mechanizmu w sekcji 7.

> **Korekty kontraktu (E3):** Lista i struktura stron: mapowanie statusów `live`=active+paused
> (paused z `can_order=false`), `upcoming`=scheduled, `closed`=ended; `draft` nie jest eksponowany
> (404). Read-endpointy (`/offer-pages`, `/offer-pages/<token>`, `/availability`) wymagają Bearer
> (parytet z resztą mobile). `available`/ilości w snapshot dostępności to **sztuki** (int), nie
> grosze; ceny produktów w strukturze strony w groszach (int). `error.details` opcjonalne w kopercie
> błędu (np. `available_quantity` przy 409 z `reserve`, `available`/`product_id` przy 400 z
> `place-order`). `reserve` wymaga strony aktywnej (`403 page_not_active`); `release`/`extend`
> działają niezależnie od statusu strony. `place-order` wiąże zamówienie z użytkownikiem JWT
> (użytkownik może złożyć zamówienie tylko ze swoich rezerwacji). Wspiera nagłówek `Idempotency-Key`
> (opcjonalny, TTL 48h; dotyczy też `POST /shop/checkout`): replay zwraca oryginalną odpowiedź 201.
> Bez nagłówka — serwisowy guard wykrywa istniejące zamówienie per user+strona → 200 z
> `already_placed: true` i danymi zamówienia. `extend` przedłuża jednorazowo o +1 min.
> Pre-order (`validate-cart`, `place-order-preorder`) → E4.

### Pre-order — koszyk lokalny + zamówienie — `/offers/<token>/`
```
POST /validate-cart       { cart_items[] }                → waliduje pozycje (produkty aktywne?)
POST /place-order-preorder { cart_items[], order_note }   → Order(PO) + bonusy
```
> Koszyk pre-order żyje w apce (jak localStorage w webie). Backend tylko waliduje i składa.
> Decyzja: osobny endpoint od `place-order` (inne dane wejściowe: rezerwacje vs koszyk lokalny).

> **Korekty kontraktu (E4):** `validate-cart` nie wymaga aktywnej strony (walidacja koszyka
> możliwa przed startem i po zamknięciu oferty); odpowiedź: `cart_items` (poprawne pozycje,
> ceny w groszach) + `removed[{product_id, reason}]` (reason: `not_found` | `not_in_offer` |
> `inactive`). `place-order-preorder`: strona musi być typu preorder (400 `wrong_page_type`)
> i aktywna (403 `page_not_active`); wspiera `Idempotency-Key` (opcjonalny — wiele pre-orderów
> na stronę jest legalne, bez guardu dedup); zamawiać można wyłącznie produkty z sekcji strony
> (obce pozycje są pomijane). Kwoty w odpowiedziach w groszach (int). Błąd zapisu →
> 500 `database_error` ze stałym komunikatem (bez szczegółów bazy). Wyjątek wewnątrz tras
> z `Idempotency-Key` zwalnia klucz (retry tym samym kluczem możliwy).

### Moje zamówienia — `/orders/`
```
GET  /orders         ?status=&type=&page=&per_page=       → lista (wszystkie typy)
GET  /orders/<id>                                         → szczegóły: pozycje, sety, bonusy,
                                                            statusy, etapy płatności E1–E4
GET  /dashboard                                           → statystyki klienta (ekran główny)
```

> **Korekty kontraktu (E5):** Lista: filtr `type` walidowany (nieznany → 400 `invalid_input`),
> `status` pass-through. Cudze/nieistniejące zamówienie → 404 `order_not_found` (bez wycieku
> istnienia; web zwraca 403 — świadoma różnica). Szczegóły zawierają `payment_stages[]`
> (etapy E1–E4 wg typu zamówienia: on-hand 2, exclusive/pre-order 3 lub 4; pola: stage_index,
> stage, name, status, amount [grosze], deadline, can_upload, has_proof, rejection_reason) oraz
> `payment_stages_count` = długość tej listy. `/dashboard`: 4 liczniki zamówień,
> `payment{paid,to_pay}` (grosze), `recent_orders[]` (5), `chart{labels[],values[]}` (30 dni,
> daty ISO). Kwoty w groszach (int); daty ISO 8601.

### Płatności wieloetapowe — `/payments/`
```
GET  /payment-methods                                    → dane do przelewu (aktywne metody)
GET  /payment-confirmations  ?tab=active|archive          → moje potwierdzenia
POST /payment-confirmations  (multipart: file + items [JSON par {order_id, payment_stage}]
                              + payment_method_id?)       → BULK upload dowodu (jeden plik,
                                                            dowolne kombinacje zamówień i etapów)
GET  /payment-confirmations/proof/<filename>              → pobranie dowodu (JWT, tylko właściciel)
```
> Etapy płatności zależą od typu zamówienia (patrz sekcja 6). Apka pokazuje per zamówienie
> etapy E1–E4 ze statusem (brak/oczekuje/zatwierdzone/odrzucone), kwotą i deadline'em.

> **Korekty kontraktu (E6):** Upload jest ZBIORCZY (parytet z webem): `items` to JSON-string
> płaskich par `{order_id, payment_stage}` (duplikaty dedupowane, max 50), jeden plik dowodu
> współdzielony przez wszystkie utworzone wiersze. Walidacja all-or-nothing: cudze/nieistniejące
> zamówienie → 404 `order_not_found` + `details.missing_order_ids`; etap nieobecny dla typu
> zamówienia → 400 `stage_not_applicable` + `details.failures`; etap niedostępny (approved,
> lub pending dla E2–E4 — E1 pending wolno nadpisać) → 409 `stage_not_uploadable`. Plik:
> JPG/PNG/PDF, max 5 MB (`invalid_file`/`file_too_large`); `database_error` (500) sprząta plik.
> Odpowiedź: `confirmations[]` (amount w groszach, action created|overwritten) + `count` +
> `proof_url` (trasa JWT — webowa trasa dowodów wymaga sesji). `payment_method_id` opcjonalny
> (pass-through). BEZ nagłówka `Idempotency-Key` — jedyność per parę (nadpis pending/rejected)
> daje naturalną idempotencję. Lista: `?tab=active|archive` (walidowane), pozycje = zamówienie +
> etapy + podsumowanie kwot (grosze) + `all_approved`; bez paginacji (parytet web).

### Wysyłka — `/shipping/`
```
GET    /addresses                                        → moje adresy dostawy
POST   /addresses        { ... }                         → dodaj
PATCH  /addresses/<id>/default                           → ustaw domyślny
DELETE /addresses/<id>                                   → usuń (soft)
GET    /requests                                         → moje zlecenia wysyłki
GET    /requests/available-orders                        → zamówienia gotowe do wysyłki
POST   /requests         { order_ids, address_id, ... }  → utwórz zlecenie
POST   /requests/<id>/cancel                             → anuluj
```

### Kolekcja — `/collection/` (bez QR)
```
GET    /items            ?q=&sort=&page=&per_page=        → moja kolekcja
GET    /items/<id>                                        → szczegóły
POST   /items            (multipart: dane + zdjęcia)      → dodaj (zdjęcie z aparatu natywnie)
PATCH  /items/<id>       (multipart)                      → edytuj
DELETE /items/<id>                                        → usuń
POST   /items/<id>/images        (multipart)             → dodaj zdjęcie (max 3)
DELETE /items/<id>/images/<img_id>                        → usuń zdjęcie
PATCH  /items/<id>/images/<img_id>/primary                → ustaw główne
GET    /public/config                                     → konfiguracja publicznej strony
POST   /public/config    { show_prices, is_active }       → zmień
POST   /items/<id>/toggle-public                          → przełącz widoczność
```

### Push (FCM) — `/push/`
```
POST   /devices          { fcm_token, platform }         → rejestruje token urządzenia
DELETE /devices/<token>                                  → wyrejestrowuje (przy logout)
```

### Pomocnicze
```
GET  /health                                             → heartbeat (publiczny)
GET  /exchange-rate      ?currency=                      → kurs walut (reużycie istniejącego)
GET  /app-version                                        → { min_version, latest_version } (wymuszanie wersji)
```

---

## 6. Trzy modele sprzedaży i etapy płatności

| | on-hand | exclusive | pre-order |
|---|---|---|---|
| Gdzie | sklep (grid) | strona ofertowa | strona ofertowa |
| Koszyk | `CartItem` (baza) | **rezerwacje** (2 min TTL, fair-access) | koszyk lokalny (apka) |
| order_type / prefix | `on_hand` / OH | `exclusive` / EX | `pre_order` / PO |
| offer_page_id | NULL | page.id | page.id |
| Etapy płatności | 2 | 3 lub 4 | 3 lub 4 |
| Sety / bonusy | nie | tak | tak |

### Etapy płatności (E1–E4)
- **on-hand (2):** E1 produkt + E4 wysyłka PL.
- **exclusive/pre-order do Polski (3):** E1 produkt + E3 cło/VAT + E4 wysyłka PL.
- **exclusive/pre-order przez proxy z Korei (4):** E1 produkt + E2 wysyłka KR + E3 cło/VAT + E4 wysyłka PL.

Każdy etap = osobne `PaymentConfirmation` (status: pending/approved/rejected, kwota, dowód, deadline).
Endpoint `GET /orders/<id>` zwraca komplet etapów ze statusami, by apka zbudowała ekran płatności.

---

## 7. System rezerwacji (exclusive) — szczegóły dla API

Mechanizm istnieje i jest szczelny — apka jest po prostu kolejnym klientem tego samego API.

- **Bezpieczeństwo (anti-overselling) w bazie, nie w real-time:** każdy `reserve` i `place-order`
  robi `SELECT FOR UPDATE` na rezerwacjach + atomowe wyliczenie `available = section_max − reserved − ordered`,
  z retry na deadlock (3 próby). Overselling jest niemożliwy niezależnie od Socket.IO.
- **TTL:** 2 min od pierwszej rezerwacji w sesji; `extend` raz o +1 min.
- **session_id:** generuje apka (UUID), niezależny od user_id; jeden user może mieć wiele sesji.
- **Cleanup:** lazy (przy każdym reserve/availability) + server-side timer.
- **Model `OfferReservation`:** bez zmian — API mobilne korzysta z tej samej tabeli i logiki.

---

## 8. Real-time (Socket.IO) dla apki

- Apka łączy się z istniejącym serwerem WS, dołącza do rooma `offer_page_{id}_order`.
- Słucha: `availability_updated`, `product_available`, `page_status_changed`, `deadline_changed`, `force_disconnect`.
- **Auth WS przez JWT:** apka przekazuje access token przy połączeniu; backend weryfikuje (handshake).
- **CORS:** dodać originy apki do `SOCKETIO_CORS_ORIGINS`.
- **Fallback:** polling `GET /offers/<token>/availability` co ~5 s, gdy WS niedostępny.

---

## 9. Push (FCM) — backend

- **Migracja:** tabela `mobile_device` (user_id, fcm_token, platform, last_used_at, created_at).
- Rejestracja tokenu przez `POST /push/devices`; wyrejestrowanie przy logout.
- Wysyłka: rozszerzyć istniejący `PushManager` (dziś Web Push/VAPID) o kanał FCM —
  wspólne zdarzenia: zmiana statusu zamówienia, „produkt wrócił", przypomnienie o płatności, nowa oferta.
- Konfiguracja: klucz serwisowy Firebase w `.env`.

---

## 10. Wymuszanie wersji apki (lekkie)

- `GET /app-version` → `{ min_version, latest_version }` (wartości z configu/env).
- Apka sprawdza przy starcie; gdy wersja < `min_version` → ekran „zaktualizuj aplikację" (twardy gate),
  gdy < `latest_version` → miękka zachęta. Chroni przed psuciem się starych apek po łamiącej zmianie API.

---

## 11. Etapy realizacji (backend)

Każdy etap kończy się czymś testowalnym (pytest) i dostanie **własny plan implementacji**.

- **E0 — Fundament + Auth:** moduł `api_mobile`, JWT, blocklist (migracja), CORS, register/verify/resend/login/google/refresh/logout/me, app-version, health. → apka może się zalogować.
- **E1 — Sklep on-hand (read):** serwis produktów/filtrów; products, products/<id>, filters, exchange-rate. → katalog.
- **E2 — Koszyk + checkout on-hand:** serwis koszyka i checkoutu (wspólny z web); cart + checkout. → zamówienie OH.
- **E3 — Exclusive:** offer-pages, struktura, availability, reserve/extend/release, place-order (sety, bonusy, atomowość). → najtrudniejszy.
- **E4 — Pre-order:** validate-cart, place-order-preorder. → wszystkie trzy flow działają.
- **E5 — Zamówienia + dashboard:** orders, orders/<id> (E1–E4), dashboard.
- **E6 — Płatności:** payment-methods, lista, upload (multipart).
- **E7 — Wysyłka:** adresy (CRUD) + zlecenia.
- **E8 — Kolekcja:** items CRUD + zdjęcia + publiczna strona (bez QR).
- **E9 — Socket.IO dla apki:** auth WS przez JWT, CORS, weryfikacja eventów.
- **E10 — Push (FCM):** migracja device, rejestracja tokenów, kanał FCM w PushManagerze.

---

## 12. Otwarte do potwierdzenia przy implementacji (nie blokują projektu)

- Format kwot: grosze (int) vs string dziesiętny — decyzja w E0, spójnie w całym API. **Rozstrzygnięte w E1: grosze (int).**
- Dokładny TTL access tokenu (30/60 min) i refresh (30 dni) — kalibracja w E0.
- Czy `place-order` i `place-order-preorder` finalnie scalić w jeden endpoint z dyskryminatorem typu — do oceny w E4.
- Strategia migracji FCM vs istniejący Web Push (czy `PushManager` ma jeden wspólny interfejs dla obu kanałów) — w E10.
