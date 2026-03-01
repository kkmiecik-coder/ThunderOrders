# WMS (Warehouse Management System) - Plan Implementacji

**Data utworzenia:** 2026-02-28
**Status:** Do zatwierdzenia
**Autor:** Konrad + Claude

---

## Spis treści

1. [Podsumowanie decyzji projektowych](#podsumowanie-decyzji-projektowych)
2. [Architektura i przepływ danych](#architektura-i-przepływ-danych)
3. [Architektura WebSocket](#architektura-websocket)
4. [Faza 1: Infrastruktura WMS + Desktop Picking](#faza-1-infrastruktura-wms--desktop-picking)
5. [Faza 2: WebSocket + QR Parowanie + Mobile](#faza-2-websocket--qr-parowanie--mobile)
6. [Faza 3: Materiały pakowania + Algorytm sugestii](#faza-3-materiały-pakowania--algorytm-sugestii)
7. [Faza 4: Zdjęcie paczki + Email do klienta](#faza-4-zdjęcie-paczki--email-do-klienta)
8. [Faza 5: Integracja z wysyłkami + Dashboard](#faza-5-integracja-z-wysyłkami--dashboard)
9. [Zmiany produkcyjne (VPS)](#zmiany-produkcyjne-vps)
10. [Punkty integracji między fazami](#punkty-integracji-między-fazami)

---

## Podsumowanie decyzji projektowych

| Decyzja | Wybór |
|---|---|
| Przepływ statusów zamówienia | `dostarczone_gom` → `spakowane` (usunąć status `do_pakowania`) |
| Punkt wejścia do WMS | Głównie z listy Zleceń Wysyłki + opcjonalnie z listy zamówień |
| Multi-SR w sesji | Tak — wiele Zleceń Wysyłki w jednej sesji WMS |
| Wiele aktywnych sesji | Dozwolone, z lockiem 10 min na zamówienia |
| Po spakowaniu | Status Zlecenia Wysyłki → "Do wysłania" |
| Materiały pakowania - stock | Auto-dedukcja po użyciu |
| Skanowanie barcode | Nie w v1, tylko QR do parowania telefon-komputer |
| Real-time | WebSocket via flask-socketio + eventlet |
| Wymiary produktów | Już w bazie (`length`, `width`, `height`, `weight` na `Product`) |
| QR code | `qrcode[pil]` już w requirements.txt |

---

## Architektura i przepływ danych

### Główny flow WMS

```
[Admin: Lista Zleceń Wysyłki]
        |
        | Zaznacza 1+ SR → klika "Zabierz do WMS"
        | (alternatywnie: z listy zamówień → zaznacza zamówienia)
        v
[POST /admin/orders/wms/create-session]
        |
        | Walidacja: zamówienia mają status dostarczone_gom
        | Walidacja: zamówienia nie są zablokowane (lock < 10 min)
        | Tworzy WmsSession + WmsSessionOrder + WmsSessionShippingRequest
        | Ustawia lock (wms_locked_at) na zamówieniach
        v
[GET /admin/orders/wms/<session_id>]  ← Desktop
        |
        | Wyświetla QR code z URL: /wms/mobile/<session_token>
        v
[Telefon skanuje QR] → [GET /wms/mobile/<session_token>]
        |
        | WebSocket: join_session → oba urządzenia w jednym "pokoju"
        | Desktop przechodzi w tryb podglądu (monitoring)
        | Telefon staje się pickerem
        v
[FAZA ZBIERANIA - per zamówienie]
        |
        | Telefon: picker tapuje produkty → zmienia wms_status
        | WebSocket event → Desktop aktualizuje progress w real-time
        | Gdy wszystkie itemy zebrane → zamówienie oznaczone jako zebrane
        v
[FAZA PAKOWANIA - per zamówienie]
        |
        | System sugeruje materiał pakowania (algorytm bin-packing)
        | Picker wybiera/potwierdza opakowanie
        | Opcjonalnie: robi zdjęcie spakowanej paczki
        | Potwierdza pakowanie → Order.status → "spakowane"
        | PackagingMaterial.quantity_in_stock -= 1
        v
[POST-PACKING]
        |
        | Gdy WSZYSTKIE zamówienia z danego SR spakowane:
        |   → ShippingRequest.status → "Do wysłania"
        |   → Opcjonalnie: email z foto do klienta
        v
[Sesja zakończona]
        |
        | WmsSession.status → "completed"
        | Podsumowanie sesji na desktopie
```

### Mechanizm lockowania zamówień

```
Zamówienie wchodzi do sesji WMS:
  → Order.wms_locked_at = NOW()
  → Order.wms_session_id = session.id

Nowa sesja próbuje wziąć to samo zamówienie:
  → Sprawdza Order.wms_locked_at
  → Jeśli NULL lub starszy niż 10 minut → dozwolone (stara sesja uznana za porzuconą)
  → Jeśli < 10 minut → odrzucone z komunikatem "Zamówienie jest w trakcie pakowania"

Sesja zakończona lub anulowana:
  → Order.wms_locked_at = NULL
  → Order.wms_session_id = NULL
```

---

## Architektura WebSocket

### Pokoje (rooms)

Każda sesja WMS to jeden pokój: `wms_{session_id}`

Członkowie pokoju:
- Desktop (1 klient)
- Mobile/telefon (1 klient)

### Eventy: Mobile → Server

| Event | Dane | Opis |
|---|---|---|
| `join_session` | `{session_id, role: "mobile", token}` | Telefon dołącza do sesji |
| `update_item_status` | `{order_item_id, new_status_slug}` | Zmiana statusu WMS itemu |
| `mark_order_packed` | `{order_id, packaging_material_id, weight}` | Potwierdzenie pakowania |

### Eventy: Desktop → Server

| Event | Dane | Opis |
|---|---|---|
| `join_session` | `{session_id, role: "desktop"}` | Desktop dołącza do sesji |

### Eventy: Server → Pokój (broadcast)

| Event | Dane | Opis |
|---|---|---|
| `phone_connected` | `{connected_at}` | Telefon połączony |
| `phone_disconnected` | `{}` | Telefon rozłączony |
| `item_status_updated` | `{order_id, item_id, new_status, picker, picked_at, order_progress}` | Item zebrany/zmieniony |
| `order_picked` | `{order_id, picked_at}` | Wszystkie itemy zebrane |
| `order_packed` | `{order_id, packaging, weight, has_photo}` | Zamówienie spakowane |
| `session_progress` | `{total_orders, picked, packed}` | Ogólny progress sesji |
| `error` | `{message}` | Błąd |

### Upload zdjęcia

Zdjęcie paczki przesyłane przez HTTP POST (nie WebSocket — zbyt duże dane binarne). Po uploadzie serwer emituje event `packing_photo_uploaded` do pokoju.

---

## Faza 1: Infrastruktura WMS + Desktop Picking

### Cel
Zbudować fundamenty WMS: modele bazodanowe, routing, i działający interfejs desktop do zbierania produktów. Bez WebSocket, bez mobile, bez QR. Admin zbiera produkty bezpośrednio na desktopie klikając przyciski.

### Rezultat po Fazie 1
Admin zaznacza zamówienia (z listy zamówień lub z listy SR), klika "Zabierz do WMS", ląduje na stronie WMS z listą produktów do zebrania. Klika aby zmienić status WMS każdego itemu. Progress bary się aktualizują. Po zebraniu wszystkiego — zamówienia oznaczone jako spakowane.

### Krok 1.1: Modele bazodanowe

**Nowy plik:** `modules/orders/wms_models.py`

**Model `WmsSession`:**
- `id` — PK
- `session_token` — String(64), unique, indexed — token do parowania mobilnego
- `user_id` — FK do users.id — kto utworzył sesję
- `status` — String(20), default 'active' — wartości: active, paused, completed, cancelled
- `phone_connected` — Boolean, default False
- `phone_connected_at` — DateTime, nullable
- `desktop_connected_at` — DateTime, nullable
- `current_order_index` — Integer, default 0 — które zamówienie jest aktualnie obrabiane
- `created_at` — DateTime
- `completed_at` — DateTime, nullable
- `notes` — Text, nullable
- Relacja do `WmsSessionOrder` (one-to-many, cascade delete)
- Relacja do `WmsSessionShippingRequest` (one-to-many, cascade delete)
- Computed properties: `is_active`, `orders_count`, `picked_orders_count`, `packed_orders_count`, `progress_percentage`

**Model `WmsSessionOrder`:**
- `id` — PK
- `session_id` — FK do wms_sessions.id
- `order_id` — FK do orders.id
- `sort_order` — Integer — kolejność zbierania
- `picking_started_at` — DateTime, nullable
- `picking_completed_at` — DateTime, nullable
- `packing_completed_at` — DateTime, nullable

**Model `WmsSessionShippingRequest`:**
- `id` — PK
- `session_id` — FK do wms_sessions.id
- `shipping_request_id` — FK do shipping_requests.id
- Pozwala śledzić, które SR weszły do sesji (do aktualizacji statusu SR po spakowaniu)

**Nowe pola na modelu `Order`:**
- `wms_locked_at` — DateTime, nullable — timestamp locka WMS
- `wms_session_id` — Integer, nullable — FK do wms_sessions.id (aktywna sesja)
- `packed_at` — DateTime, nullable
- `packed_by` — Integer, FK do users.id, nullable
- `packing_photo` — String(500), nullable — ścieżka do zdjęcia
- `total_package_weight` — Numeric(8,2), nullable — waga paczki w kg

> **Uwaga:** Pole `packaging_material_id` (FK do PackagingMaterial) dodane w Fazie 3.

### Krok 1.2: Migracja bazy danych

- `flask db migrate -m "Add WMS session tables and packing fields to Order"`
- Tworzy tabele: `wms_sessions`, `wms_session_orders`, `wms_session_shipping_requests`
- Dodaje kolumny do `orders`: `wms_locked_at`, `wms_session_id`, `packed_at`, `packed_by`, `packing_photo`, `total_package_weight`

### Krok 1.3: Routing WMS

**Nowy plik:** `modules/orders/wms.py`

Zaimportować w `modules/orders/__init__.py` (po imporcie routes).

**Route'y do zaimplementowania:**

1. **`POST /admin/orders/wms/create-session`** — tworzy sesję WMS
   - Przyjmuje: `order_ids` i/lub `shipping_request_ids`
   - Walidacja: zamówienia mają status `dostarczone_gom`
   - Walidacja: zamówienia nie są zablokowane (`wms_locked_at` NULL lub > 10 min)
   - Tworzy `WmsSession` z tokenem (`secrets.token_urlsafe(32)`)
   - Tworzy `WmsSessionOrder` dla każdego zamówienia
   - Tworzy `WmsSessionShippingRequest` dla każdego SR (jeśli wejście z SR)
   - Ustawia lock: `Order.wms_locked_at = now()`, `Order.wms_session_id = session.id`
   - Redirect do strony WMS

2. **`GET /admin/orders/wms/<int:session_id>`** — strona desktop WMS
   - Renderuje stronę z wszystkimi zamówieniami i ich itemami
   - Tryb picking (Faza 1) — admin klika bezpośrednio

3. **`POST /admin/orders/wms/update-item-status`** — zmiana statusu itemu
   - Przyjmuje: `order_item_id`, `new_status_slug`
   - Walidacja: item należy do zamówienia w aktywnej sesji
   - Aktualizuje: `OrderItem.wms_status`, `picked_at`, `picked_by`
   - Zwraca JSON z nowym stanem i progressem zamówienia

4. **`GET /admin/orders/wms/<int:session_id>/data`** — JSON z pełnym stanem sesji
   - Do odświeżania strony / initial load

5. **`POST /admin/orders/wms/<int:session_id>/pack-order`** — oznacz zamówienie jako spakowane
   - Ustawia `Order.status` → `spakowane`, `packed_at`, `packed_by`
   - Sprawdza czy wszystkie zamówienia z danego SR są spakowane → jeśli tak, zmienia SR status
   - Zdejmuje lock z zamówienia

6. **`POST /admin/orders/wms/<int:session_id>/complete`** — zakończ sesję
   - `WmsSession.status` → `completed`, `completed_at = now()`
   - Zdejmuje locki ze wszystkich zamówień

7. **`POST /admin/orders/wms/<int:session_id>/cancel`** — anuluj sesję
   - Zdejmuje locki, przywraca statusy jeśli trzeba

### Krok 1.4: Aktualizacja przycisku "Zabierz do WMS"

**Plik:** `static/js/pages/admin/orders-list.js` (linia 227-232)

Obecnie `handleGoToWMS()` nawiguje do `GET /admin/orders/wms?order_ids=...` — zmienić na:
- POST do `/admin/orders/wms/create-session` z order_ids
- Walidacja po stronie klienta: czy zaznaczono zamówienia
- Obsługa błędów (toast z komunikatem jeśli zamówienia mają zły status lub są zablokowane)
- Po sukcesie: redirect do URL sesji

**Plik:** `templates/admin/orders/detail.html` (linia ~923)

Zmienić `alert('Funkcja WMS w budowie')` na faktyczne tworzenie sesji WMS dla tego zamówienia.

### Krok 1.5: Przycisk WMS na liście Zleceń Wysyłki

**Plik:** `templates/admin/orders/shipping_requests_list.html`

Dodać przycisk "Zabierz do WMS" (pojedynczy SR) oraz bulk action "Zabierz do WMS" (zaznaczone SRy).

**Plik:** `static/js/pages/admin/shipping-requests.js` (lub odpowiedni plik JS)

Handler: zbiera `shipping_request_ids`, POST do `/admin/orders/wms/create-session`, redirect do sesji.

### Krok 1.6: Strona desktop WMS — szablon HTML

**Nowy plik:** `templates/admin/orders/wms.html` (extends `admin/base_admin.html`)

**Layout:**

**Nagłówek sesji:**
- Info: numer sesji, czas utworzenia, kto utworzył, ile zamówień
- Ogólny progress bar (X z Y zamówień zebranych/spakowanych)
- Przełącznik trybu: "Tryb zbierania" / "Tryb podglądu" (podgląd jako placeholder w Fazie 1)
- Przyciski: "Zakończ sesję", "Anuluj sesję"

**Główna treść — Tryb zbierania:**

- **Lewy panel (70%):** Aktualne zamówienie
  - Numer zamówienia, nazwa klienta, typ zamówienia
  - Numer Zlecenia Wysyłki (jeśli dotyczy)
  - Lista itemów jako karty:
    - Miniatura produktu
    - Nazwa produktu, SKU
    - Ilość (quantity)
    - Aktualny status WMS (kolorowy badge)
    - Przyciski/dropdown do zmiany statusu WMS
    - Po zmianie na status "zebrany" → znacznik ✓ + timestamp
  - Progress bar zamówienia (X z Y itemów zebranych)
  - Przycisk "Oznacz jako spakowane" (aktywny gdy wszystko zebrane)

- **Prawy panel (30%):** Kolejka zamówień
  - Lista wszystkich zamówień w sesji
  - Każde: numer, ilość itemów, progress %, indicator statusu
  - Aktualne zamówienie podświetlone
  - Klik przełącza między zamówieniami
  - Grupowanie po SR (jeśli sesja z wielu SR)

### Krok 1.7: CSS WMS

**Nowy plik:** `static/css/pages/admin/wms.css`

Style dla obu trybów (light + dark mode). Kluczowe komponenty:
- `.wms-page` — kontener główny
- `.wms-header` — nagłówek z info sesji
- `.wms-progress-bar` — progress bary
- `.wms-picking-area` — lewy panel
- `.wms-order-queue` — prawy panel
- `.wms-item-card` — karta produktu
- `.wms-item-status-badge` — badge statusu
- `.wms-order-card` — karta zamówienia w kolejce
- `.wms-mode-toggle` — przełącznik trybu

### Krok 1.8: JavaScript WMS desktop

**Nowy plik:** `static/js/pages/admin/wms.js`

Funkcje:
- `initWmsPage()` — inicjalizacja strony
- `loadSessionData(sessionId)` — pobranie stanu sesji z API
- `selectOrder(orderId)` — przełączenie na inne zamówienie
- `updateItemStatus(orderItemId, newStatusSlug)` — AJAX zmiana statusu, aktualizacja DOM
- `updateProgressBars()` — przeliczenie i aktualizacja progress barów
- `packOrder(orderId)` — oznaczenie zamówienia jako spakowane
- `completeSession()` — zakończenie sesji
- Użycie istniejących: `window.Toast.show()`, `getCsrfToken()`

### Krok 1.9: Link WMS w sidebarze

**Plik:** `templates/components/sidebar_admin.html`

Dodać pozycję "WMS" w kategorii "Zamówienia" — link do listy sesji WMS lub do aktywnej sesji.

### Krok 1.10: Usunięcie statusu "do_pakowania"

Usunąć status zamówienia `do_pakowania` z bazy (lub oznaczyć jako nieaktywny). Upewnić się, że żadne zamówienia nie mają tego statusu aktualnie.

### Testowanie po Fazie 1

- [ ] Zaznacz 3+ zamówienia ze statusem `dostarczone_gom` → "Zabierz do WMS" → sesja utworzona
- [ ] Strona WMS pokazuje zamówienia i ich produkty
- [ ] Kliknięcie zmienia status WMS itemu → progress bar się aktualizuje
- [ ] Zamówienia z innym statusem niż `dostarczone_gom` → odrzucone
- [ ] Zamówienie z lockiem < 10 min → odrzucone z komunikatem
- [ ] "Oznacz jako spakowane" → status zamówienia → `spakowane`
- [ ] "Zakończ sesję" → sesja completed, locki zdjęte
- [ ] Wejście z listy SR → wszystkie zamówienia z SR wchodzą do sesji
- [ ] Dark mode działa poprawnie na całej stronie WMS
- [ ] Po spakowaniu wszystkich zamówień z SR → status SR zmieniony

---

## Faza 2: WebSocket + QR Parowanie + Mobile

### Cel
Dodać komunikację real-time między desktopem a telefonem. Desktop generuje QR code, telefon skanuje i staje się pickerem. Desktop przechodzi w tryb podglądu. Zmiany statusów na telefonie pojawiają się na desktopie natychmiast.

### Zależności
- Faza 1 musi być ukończona

### Krok 2.1: Dependencje

**Plik:** `requirements.txt` — dodać:
- `flask-socketio==5.3.6`
- `eventlet==0.36.1`

### Krok 2.2: Inicjalizacja SocketIO

**Plik:** `extensions.py`
- Dodać instancję `socketio = SocketIO()`

**Plik:** `app.py`
- W `create_app()`: `socketio.init_app(app, async_mode='eventlet', cors_allowed_origins=...)`
- W `if __name__ == '__main__'`: zmienić `app.run()` na `socketio.run(app, host='0.0.0.0', port=5001, debug=True)`

### Krok 2.3: Event handlery WebSocket

**Nowy plik:** `modules/orders/wms_events.py`

Rejestruje handlery SocketIO:

**`@socketio.on('join_session')`:**
- Desktop: walidacja użytkownika (sesja cookie), join room `wms_{session_id}`
- Mobile: walidacja tokenu sesji, join room, ustawienie `phone_connected = True`, emit `phone_connected`

**`@socketio.on('update_item_status')`:**
- Walidacja itemu w sesji
- Aktualizacja DB (ta sama logika co HTTP route z Fazy 1)
- Emit `item_status_updated` do pokoju
- Jeśli zamówienie w pełni zebrane → emit `order_picked`

**`@socketio.on('mark_order_packed')`:**
- Aktualizacja pól pakowania na Order
- Zmiana statusu → `spakowane`
- Emit `order_packed` do pokoju

**`@socketio.on('disconnect')`:**
- Sprawdzenie roli (mobile/desktop)
- Mobile disconnect → `phone_connected = False`, emit `phone_disconnected`

Import w `app.py` po inicjalizacji socketio.

### Krok 2.4: Generowanie QR code

**Plik:** `modules/orders/wms.py`

Nowy route `GET /admin/orders/wms/<int:session_id>/qr`:
- Generuje QR code z URL: `https://{domain}/wms/mobile/{session_token}`
- Zwraca jako base64 data URI w JSON
- Wzorzec: istniejący `collection_qr_session_create` w `modules/client/collection.py` (linia 541-591)

**Plik:** Szablon desktop WMS — wyświetlanie QR w overlaju gdy telefon nie jest połączony.

### Krok 2.5: Strona mobilna WMS

**Nowy plik:** `templates/admin/orders/wms_mobile.html`

Samodzielna strona (NIE extends `base_admin.html`) — standalone mobile layout. Bez autentykacji (dostęp tokenem).

**Layout mobilny:**
- Nagłówek: info o sesji, indicator połączenia (zielona kropka)
- Karta aktualnego zamówienia: numer, klient, progress
- Lista itemów: duże karty touch-friendly:
  - Miniatura produktu
  - Nazwa, ilość
  - Status WMS (badge)
  - Duże przyciski do zmiany statusu (tap targets min. 48px)
- Dolna nawigacja: "Poprzednie" / "Następne zamówienie"
- Sekcja pakowania (po zebraniu wszystkiego):
  - Przycisk "Oznacz jako spakowane"

### Krok 2.6: Route mobilny

**Plik:** `modules/orders/wms.py`

`GET /wms/mobile/<session_token>`:
- Wyszukanie `WmsSession` po tokenie
- Walidacja: sesja aktywna
- Renderowanie `wms_mobile.html`
- CSRF exempt (dodać do listy wyłączeń)

### Krok 2.7: CSS mobilny

**Nowy plik:** `static/css/pages/admin/wms-mobile.css`

Mobile-first:
- Touch targets min. 48px
- Full-width elementy
- Duże kolorowe przyciski statusów
- Wsparcie dla light + dark mode (prefers-color-scheme lub osobny toggle)

### Krok 2.8: JavaScript mobilny

**Nowy plik:** `static/js/pages/admin/wms-mobile.js`

Funkcje:
- `initMobileWms(sessionToken)` — połączenie WebSocket, join session
- `onItemStatusTap(orderItemId, newStatus)` — emit `update_item_status`
- `navigateOrder(direction)` — przejście do następnego/poprzedniego zamówienia
- `handlePackingSubmit(orderId)` — emit `mark_order_packed`
- Zarządzanie połączeniem (reconnect, offline indicator)
- Wibracja na zmianę statusu (`navigator.vibrate(50)`)

### Krok 2.9: Aktualizacja desktop JS dla WebSocket

**Plik:** `static/js/pages/admin/wms.js`

Rozszerzenie o klienta SocketIO:
- Połączenie WebSocket przy ładowaniu strony
- Emit `join_session` z role "desktop"
- Nasłuchiwanie eventów i aktualizacja DOM w real-time
- Pokazywanie/ukrywanie QR overlay na podstawie statusu połączenia telefonu
- Automatyczne przełączenie w "Tryb podglądu" gdy telefon się połączy
- Obsługa `phone_disconnected` — prompt do ponownego skanowania

### Testowanie po Fazie 2

- [ ] Desktop WMS — widoczny QR code
- [ ] Skanowanie QR telefonem → strona mobilna WMS się otwiera
- [ ] Desktop: indicator "Telefon połączony", QR znika
- [ ] Zmiana statusu na telefonie → desktop aktualizuje się natychmiast (bez odświeżania)
- [ ] Progress bary na desktopie reagują na zmiany z telefonu
- [ ] Rozłączenie telefonu → desktop: "Telefon rozłączony"
- [ ] Ponowne skanowanie QR → sesja wznowiona
- [ ] Nawigacja między zamówieniami na telefonie
- [ ] Reconnect WebSocket po chwilowej utracie sieci

---

## Faza 3: Strona WMS Pakowanie + Materiały pakowania + Algorytm sugestii

### Cel
Stworzyć dedykowaną stronę **WMS Pakowanie** (`/admin/orders/wms`) z dwoma zakładkami:
1. **Sesje pakowania** — lista sesji WMS (aktywne, zakończone, anulowane) z przyciskiem "Nowa sesja" i podstawowymi statystykami
2. **Materiały** — mini-magazyn materiałów pakowania (kartony, koperty, foliopaki) z wymiarami, stanem magazynowym i kosztami

Dodatkowo: algorytm sugestii pakowania zintegrowany z sesją WMS.

Sidebar link "WMS Pakowanie" (już istnieje jako placeholder) zostanie zaktualizowany, żeby wskazywał na nową stronę.

### Zależności
- Faza 1 musi być ukończona
- Faza 2 zalecana (mobile UI) ale nie wymagana

### Krok 3.1: Model PackagingMaterial

**Plik:** `modules/orders/wms_models.py`

**Model `PackagingMaterial`:**
- `id` — PK
- `name` — String(100) — np. "Karton 30x20x15", "Koperta bąbelkowa M"
- `type` — String(30) — wartości: `karton`, `koperta_babelkowa`, `koperta`, `foliopak`, `inne`
- `inner_length` — Numeric(8,2), nullable — wymiary wewnętrzne w cm
- `inner_width` — Numeric(8,2), nullable
- `inner_height` — Numeric(8,2), nullable
- `max_weight` — Numeric(8,2), nullable — maks. waga w kg
- `own_weight` — Numeric(8,2), nullable — waga opakowania w kg
- `quantity_in_stock` — Integer, default 0
- `low_stock_threshold` — Integer, default 5 — próg alertu niskiego stanu
- `cost` — Numeric(8,2), nullable — koszt jednostkowy
- `is_active` — Boolean, default True
- `sort_order` — Integer, default 0
- `created_at`, `updated_at` — DateTime

### Krok 3.2: FK na modelu Order

**Plik:** `modules/orders/models.py`

Dodać:
- `packaging_material_id` — Integer, FK do packaging_materials.id, nullable
- Relacja: `packaging_material` (PackagingMaterial)

### Krok 3.3: Migracja

`flask db migrate -m "Add packaging_materials table and FK on orders"`

### Krok 3.4: Strona WMS Pakowanie — zakładki + lista sesji

**Route:** `GET /admin/orders/wms` — strona lądowania WMS z dwoma zakładkami.

**Plik:** `modules/orders/wms.py` — nowy route `wms_dashboard`:
- Pobiera sesje WMS (aktywne na górze, potem zakończone/anulowane, sortowane po dacie)
- Pobiera materiały pakowania (dla zakładki Materiały)
- Pobiera podstawowe statystyki: dzisiejsze sesje, spakowane zamówienia, aktywna sesja

**Nowy plik:** `templates/admin/orders/wms_dashboard.html`

Extends `admin/base_admin.html` (standardowa strona adminowa z sidebarem).

Layout: wzorzec 2-kolumnowy z zakładkami po lewej (analogicznie do `/admin/orders/settings`):

**Zakładka 1 — Sesje pakowania (`tab-sessions`):**
- **Karta "Aktywne sesje"** (jeśli istnieją):
  - Numer sesji, kto utworzył, data, liczba zamówień, progress bar
  - Przycisk "Wznów sesję" → link do `/admin/orders/wms/<session_id>`
- **Przycisk "Nowa sesja"** → redirect do listy zamówień z filtrem statusu `dostarczone_gom`
- **Karta "Historia sesji"**:
  - Lista ostatnich zakończonych/anulowanych sesji
  - Każda: numer, status badge, liczba zamówień, spakowane/total, czas trwania, data
  - Kliknięcie → link do sesji (widok read-only)
- **Statystyki dzienne** (prosta karta na górze):
  - Dziś spakowano X zamówień
  - Aktywnych sesji: N
  - Ostatnia sesja: kiedy

**Zakładka 2 — Materiały (`tab-materials`):**
- Karta z listą materiałów pakowania (drag & drop do reorderingu)
- Przycisk "Dodaj materiał"
- Każdy wiersz: nazwa, typ (badge), wymiary (L×W×H), waga max, stan magazynowy (z alertem low stock), koszt, aktywny/nieaktywny, przyciski edytuj/usuń
- Modal dodawania/edycji materiału (wzorzec: `.modal-overlay` + `.modal-content`)

**Nowy plik:** `static/css/pages/admin/wms-dashboard.css` — style zakładek, kart sesji, listy materiałów + dark mode.

**Nowy plik:** `static/js/pages/admin/wms-dashboard.js` — tab switching, CRUD materiałów, drag & drop reorder.

### Krok 3.5: Sidebar — aktualizacja linku WMS Pakowanie

**Plik:** `templates/components/sidebar_admin.html`

Link "WMS Pakowanie" (już istnieje ~linia 50) — zmienić `href` z `orders.admin_list` na `orders.wms_dashboard`. Poprawić active state detection.

### Krok 3.6: CRUD materiałów pakowania — route'y API

**Plik:** `modules/orders/wms.py` — nowe route'y:
- `POST /admin/orders/packaging-materials/create` — dodaj materiał
- `GET /api/orders/packaging-materials/<id>` — dane materiału (JSON, dla modala edycji)
- `POST /admin/orders/packaging-materials/<id>/update` — aktualizuj materiał
- `DELETE /admin/orders/packaging-materials/<id>` — usuń materiał
- `POST /admin/orders/packaging-materials/reorder` — zmiana kolejności (drag & drop)
- `GET /api/orders/packaging-materials` — lista aktywnych (JSON, dla dropdown w WMS)

### Krok 3.7: Algorytm sugestii pakowania

**Nowy plik:** `modules/orders/wms_utils.py`

**Funkcja `suggest_packaging(order_items) -> list[dict]`:**

1. **Zbierz wymiary produktów** — dla każdego OrderItem pobierz Product.length/width/height/weight. Pomnóż wagę przez quantity. Oznacz produkty bez wymiarów jako "nieznane".

2. **Oblicz potrzebną objętość** — suma objętości wszystkich itemów × współczynnik 1.3 (30% zapas na materiał ochronny i nieregularne kształty).

3. **Oblicz łączną wagę** — suma wag produktów × quantity.

4. **Filtruj opakowania** — dla każdego aktywnego PackagingMaterial sprawdź:
   - Objętość wewnętrzna >= potrzebna objętość
   - max_weight >= łączna waga (jeśli ustawione)
   - Najdłuższy wymiar produktu mieści się w najdłuższym wymiarze opakowania (z uwzględnieniem rotacji)
   - quantity_in_stock > 0

5. **Optymalizacja jednego produktu** — jeśli zamówienie ma 1 item (qty 1), szukaj najmniejszego opakowania gdzie 3 wymiary produktu mieszczą się w 3 wymiarach opakowania (z rotacją).

6. **Rankowanie** — sortuj pasujące opakowania po: najmniejsza objętość (best fit), najniższy koszt. Zwróć top 3 sugestie.

7. **Format zwrotny:** lista z materiałem, fit_score (0-1), powodem, i ostrzeżeniami (np. "Produkt X nie ma wymiarów").

8. **Edge cases:**
   - Brak wymiarów → zwróć wszystkie materiały z ostrzeżeniem
   - Nic nie pasuje → pusta lista z komunikatem
   - Mix znanych/nieznanych → oblicz na podstawie znanych, ostrzeż o nieznanych

### Krok 3.8: Integracja sugestii w UI sesji WMS

**Route:** `GET /api/orders/wms/suggest-packaging/<int:order_id>` — wywołuje `suggest_packaging()`, zwraca JSON.

**Desktop i Mobile UI:** Po zebraniu wszystkich itemów zamówienia, sekcja pakowania:
- Top 3 sugerowane opakowania z fit score
- Dropdown z pełną listą aktywnych materiałów (ręczny wybór)
- Pole wagi (pre-filled: obliczona waga produktów + waga opakowania)
- Przycisk "Potwierdź pakowanie"
- Auto-dedukcja: `PackagingMaterial.quantity_in_stock -= 1`
- Alert jeśli stan materiału spadnie poniżej `low_stock_threshold`

### Testowanie po Fazie 3

- [ ] Strona `/admin/orders/wms` otwiera się z dwoma zakładkami
- [ ] Sidebar link "WMS Pakowanie" prowadzi do nowej strony
- [ ] Zakładka "Sesje pakowania" — widać aktywne i historyczne sesje
- [ ] Przycisk "Wznów sesję" → otwiera sesję WMS
- [ ] Przycisk "Nowa sesja" → przekierowuje do listy zamówień
- [ ] Zakładka "Materiały" — CRUD materiałów pakowania działa
- [ ] Drag & drop reorder materiałów
- [ ] Modal dodawania/edycji materiału z wymiarami, wagą, kosztem
- [ ] W sesji WMS po zebraniu produktów → pojawiają się sugestie pakowania
- [ ] Sugestie poprawnie rankują (najmniejsze pasujące opakowanie pierwsze)
- [ ] Ręczny wybór z listy działa
- [ ] Po potwierdzeniu pakowania: quantity_in_stock zmniejszony o 1
- [ ] Alert przy niskim stanie materiału
- [ ] Zamówienia z produktami bez wymiarów → ostrzeżenie

---

## Faza 4: Zdjęcie paczki + Email do klienta

### Cel
Umożliwić zrobienie zdjęcia spakowanej paczki telefonem. Zdjęcie zapisane, powiązane z zamówieniem, opcjonalnie wysłane emailem do klienta.

### Zależności
- Faza 2 musi być ukończona (interfejs mobilny)
- Faza 3 zalecana (flow pakowania)

### Krok 4.1: Capture zdjęcia na telefonie

**Plik:** `static/js/pages/admin/wms-mobile.js`

Dodać funkcjonalność kamery:
- `<input type="file" accept="image/*" capture="environment">` — najbardziej kompatybilne rozwiązanie
- Po wybraniu zdjęcia: kompresja/resize klient-side (Canvas API, max 1200px, JPEG 0.7) — zmniejszenie rozmiaru uploadu
- Podgląd zrobionego zdjęcia
- Przycisk "Wyślij zdjęcie"

### Krok 4.2: Route uploadu zdjęcia

**Plik:** `modules/orders/wms.py`

`POST /wms/mobile/upload-packing-photo`:
- Przyjmuje: `session_token`, `order_id`, plik obrazu (multipart)
- Walidacja tokenu sesji i zamówienia
- Zapis do `static/uploads/packing_photos/{order_id}_{timestamp}.jpg`
- Aktualizacja `Order.packing_photo` — ścieżka do pliku
- Emit WebSocket `packing_photo_uploaded` do pokoju (powiadomienie desktopa)
- CSRF exempt

### Krok 4.3: Wyświetlanie zdjęcia na desktopie

**Plik:** Szablon desktop WMS + JS

Po otrzymaniu eventu `packing_photo_uploaded`:
- Miniatura zdjęcia na karcie zamówienia
- Kliknięcie → modal z pełnym rozmiarem

### Krok 4.4: Email ze zdjęciem do klienta

**Plik:** `utils/email_manager.py` (lub odpowiedni plik email)

Nowa metoda: `EmailManager.notify_packing_photo(order, photo_path)`
- Pobiera email klienta z `order.customer_email`
- Renderuje szablon email z numerem zamówienia i zdjęciem inline
- Wysyła asynchronicznie (istniejący wzorzec)

**Nowy plik:** `templates/emails/packing_photo.html`

Szablon email:
- Logo ThunderOrders
- "Twoje zamówienie [numer] zostało spakowane!"
- Zdjęcie paczki inline
- Opcjonalnie: informacja o wysyłce

### Krok 4.5: Trigger emaila z UI WMS

W flow pakowania (po uploadzie zdjęcia i oznaczeniu jako spakowane):
- Checkbox: "Wyślij zdjęcie pakowania do klienta" (default: zaznaczony)
- Jeśli zaznaczony → wywołanie endpointu emailowego
- Route: `POST /admin/orders/wms/send-packing-email` z `order_id`

### Testowanie po Fazie 4

- [ ] Na telefonie, po zebraniu itemów → przycisk kamery widoczny
- [ ] Zrobienie zdjęcia → podgląd na telefonie
- [ ] Upload → zdjęcie pojawia się na desktopie WMS
- [ ] Zdjęcie zapisane na dysku w poprawnej ścieżce
- [ ] Checkbox "Wyślij do klienta" → klient dostaje email z embedded zdjęciem
- [ ] Detal zamówienia (poza WMS) też pokazuje zdjęcie pakowania
- [ ] Zdjęcie działa z obiema kamerami telefonu (preferowana tylna)

---

## Faza 5: Integracja z wysyłkami + Polish UX

### Cel
Połączyć zakończenie pakowania WMS z systemem Zleceń Wysyłki. Rozbudować tryb podglądu. Dodać historię WMS w detalu zamówienia. Dopracować UX.

**Uwaga:** Dashboard WMS (lista sesji) i sidebar zostały już zaimplementowane w Fazie 3.

### Zależności
- Wszystkie poprzednie fazy ukończone

### Krok 5.1: Flow po spakowaniu — integracja z ShippingRequest

Gdy zamówienie jest spakowane w WMS:
- Sprawdź czy zamówienie należy do ShippingRequest
- Jeśli TAK i WSZYSTKIE zamówienia z tego SR są spakowane → zmień `ShippingRequest.status` na "Do wysłania"
- Jeśli nie wszystkie → zmień tylko status zamówienia na `spakowane`, SR czeka na resztę

**Nowy status SR "Do wysłania":**
- Dodać do `ShippingRequestStatus` jeśli nie istnieje
- Slug: `do_wyslania`
- Nazwa: "Do wysłania"
- Kolor badge: np. pomarańczowy
- Możliwe że będzie to status `is_initial=False` — admin dalej przetwarza (dodaje tracking, kuriera)

**Plik:** `modules/orders/wms.py` — logika w `pack-order` route (rozszerzenie z Fazy 1)

### Krok 5.2: Aktualizacja shipping_request_allowed_statuses

Aktualnie `shipping_request_allowed_statuses` defaults to `['dostarczone_gom']`. Po WMS zamówienia mają status `spakowane`.

Upewnić się że `spakowane` jest dodane do dozwolonych statusów — albo automatycznie przy pierwszym uruchomieniu WMS, albo jako krok konfiguracji w dokumentacji.

### Krok 5.3: Rozbudowa trybu podglądu (Preview mode) na desktopie

**Plik:** Szablon desktop WMS + JS

"Tryb podglądu" (przełączany z nagłówka, bazowa wersja z Fazy 2) rozbudować o:
- Grid wszystkich zamówień w sesji jako karty (zamiast queue + items)
- Każda karta: numer zamówienia, klient, animowany progress bar, status pakowania, miniatura zdjęcia
- Real-time aktualizacje via WebSocket (już działa z Fazy 2)
- Statystyki sesji: łączne itemy, zebrane, spakowane, czas elapsed

### Krok 5.4: Historia WMS w detalu zamówienia

**Plik:** `templates/admin/orders/detail.html`

Nowa sekcja "Historia WMS":
- Czy zamówienie było procesowane przez WMS
- Która sesja, kiedy, przez kogo
- Szczegóły pakowania: materiał, waga, zdjęcie
- Timeline: picked_at, packed_at, shipping_requested_at

### Krok 5.5: Polish UX

Elementy do dopracowania:
- Stany ładowania i skeleton screens
- Obsługa błędów (utrata sieci, concurrent edits)
- Animacje zmian statusu (progress bary, checkmarki)
- Dźwięki na telefonie (opcjonalnie: beep na pick, chime na complete)
- Timeout sesji (auto-pause po nieaktywności)
- Dialogi potwierdzenia (anulowanie sesji, usunięcie zamówienia z sesji)
- Skróty klawiszowe na desktopie (strzałki do nawigacji zamówień)

### Testowanie po Fazie 5

- [ ] Pełny flow end-to-end: wybierz SR → WMS → zbierz → pakuj → SR status "Do wysłania"
- [ ] Po spakowaniu wszystkich zamówień z SR → status SR się zmienia
- [ ] Tryb podglądu — rozbudowany grid z kartami zamówień
- [ ] Detal zamówienia — historia WMS widoczna
- [ ] Obsługa edge cases (timeout, disconnect, concurrent)

---

## Zmiany produkcyjne (VPS)

### Faza 1: Standardowy deploy
- `git pull` + `flask db upgrade` + `sudo systemctl restart thunderorders`
- Brak zmian w infrastrukturze

### Faza 2: WebSocket wymaga zmian WSGI

**1. Gunicorn — zmiana worker class:**

Obecne (domyślne): `gunicorn app:create_app()`

Nowe: `gunicorn --worker-class eventlet --workers 1 app:create_app()`

- `--worker-class eventlet` → obsługa WebSocket
- `--workers 1` → eventlet zarządza concurrency via green threads (zalecane)

**2. Aktualizacja `gunicorn_config.py` na serwerze:**
- `worker_class = 'eventlet'`
- `workers = 1`
- `timeout = 120` (zwiększony dla WebSocket)

**3. Nginx — dodać obsługę WebSocket:**

Dodać do bloku `server`:
```
location /socket.io/ {
    proxy_pass http://127.0.0.1:8000/socket.io/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}
```

**4. Systemd service — aktualizacja komendy Gunicorn**

**5. Instalacja pakietów na serwerze:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Faza 3: Standardowy deploy
- Migracja DB + restart

### Faza 4: Katalog uploadów
- Utworzyć na serwerze: `mkdir -p /var/www/ThunderOrders/static/uploads/packing_photos`
- Upewnić się o uprawnieniach zapisu

### Faza 5: Standardowy deploy

---

## Punkty integracji między fazami

### Faza 1 → Faza 2
- HTTP route `update-item-status` z Fazy 1 pozostaje jako fallback (gdy WebSocket niedostępny)
- Faza 2 dodaje WebSocket jako główny kanał, ale zachowuje HTTP routes
- Desktop JS z Fazy 1 rozszerzony w Fazie 2 o klienta WebSocket

### Faza 1 → Faza 3
- Faza 1 tworzy `packed_at`, `packed_by`, `total_package_weight` na Order
- Faza 3 dodaje `packaging_material_id` FK i model `PackagingMaterial`
- Flow "oznacz jako spakowane" z Fazy 1 rozszerzony w Fazie 3 o wybór opakowania

### Faza 2 → Faza 4
- Mobile UI z Fazy 2 rozszerzony w Fazie 4 o funkcję kamery
- Upload zdjęcia przez HTTP POST, potem emit WebSocket event

### Faza 3 → Faza 5
- Dane pakowania (materiał, waga) z Fazy 3 → wykorzystywane w Fazie 5 przy tworzeniu/aktualizacji SR
- Waga paczki → przydatna do wyceny wysyłki

### Faza 4 → Faza 5
- Zdjęcie pakowania z Fazy 4 → widoczne w historii WMS w detalu zamówienia (Faza 5)
- Szablon email z Fazy 4 → rozszerzony o info o wysyłce w Fazie 5

---

## Nowe pliki — podsumowanie

| Plik | Faza | Opis |
|---|---|---|
| `modules/orders/wms_models.py` | 1 | Modele WmsSession, WmsSessionOrder, WmsSessionShippingRequest, PackagingMaterial |
| `modules/orders/wms.py` | 1 | Route'y HTTP dla WMS |
| `modules/orders/wms_events.py` | 2 | Event handlery WebSocket |
| `modules/orders/wms_utils.py` | 3 | Algorytm sugestii pakowania |
| `templates/admin/orders/wms.html` | 1 | Strona desktop sesji WMS |
| `templates/admin/orders/wms_mobile.html` | 2 | Strona mobilna WMS |
| `templates/admin/orders/wms_mobile_error.html` | 2 | Strona błędu mobilnego WMS |
| `templates/admin/orders/wms_dashboard.html` | 3 | Strona WMS Pakowanie (zakładki: sesje + materiały) |
| `templates/emails/packing_photo.html` | 4 | Szablon email ze zdjęciem |
| `static/js/pages/admin/wms.js` | 1 | JavaScript desktop sesji WMS |
| `static/js/pages/admin/wms-mobile.js` | 2 | JavaScript mobile WMS |
| `static/js/pages/admin/wms-dashboard.js` | 3 | JavaScript strony WMS Pakowanie (tabs, CRUD materiałów) |
| `static/css/pages/admin/wms.css` | 1 | Style desktop sesji WMS |
| `static/css/pages/admin/wms-mobile.css` | 2 | Style mobile WMS |
| `static/css/pages/admin/wms-mobile-error.css` | 2 | Style strony błędu mobilnego |
| `static/css/pages/admin/wms-dashboard.css` | 3 | Style strony WMS Pakowanie |

## Modyfikowane pliki — podsumowanie

| Plik | Faza | Zmiana |
|---|---|---|
| `modules/orders/models.py` | 1, 3 | Nowe pola na Order (packing, lock, packaging_material_id) |
| `modules/orders/__init__.py` | 1 | Import wms.py |
| `static/js/pages/admin/orders-list.js` | 1 | Fix "Zabierz do WMS" button |
| `templates/admin/orders/detail.html` | 1, 5 | Fix WMS button, dodanie historii WMS |
| `templates/admin/orders/shipping_requests_list.html` | 1 | Przycisk WMS na SR |
| `templates/components/sidebar_admin.html` | 3 | Link "WMS Pakowanie" → `orders.wms_dashboard` |
| `extensions.py` | 2 | Instancja SocketIO |
| `app.py` | 2 | Init SocketIO, socketio.run() |
| `requirements.txt` | 2 | flask-socketio, eventlet, simple-websocket |
| `utils/email_manager.py` | 4 | Metoda notify_packing_photo |

---

## Migracje bazy danych

| Faza | Migracja |
|---|---|
| 1 | Tabele: `wms_sessions`, `wms_session_orders`, `wms_session_shipping_requests`. Kolumny na `orders`: `wms_locked_at`, `wms_session_id`, `packed_at`, `packed_by`, `packing_photo`, `total_package_weight` |
| 3 | Tabela: `packaging_materials`. Kolumna na `orders`: `packaging_material_id` (FK) |
| 5 | Ewentualne: nowy `ShippingRequestStatus` "Do wysłania" (dane, nie schemat) |
