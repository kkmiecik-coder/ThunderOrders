# Zlecenie wysyłki: cennik + typ opakowania + uwagi — design

**Data:** 2026-07-20
**Taski ClickUp:** [869e674tp](https://app.clickup.com/t/869e674tp) (ceny wysyłki, high), [869e674xk](https://app.clickup.com/t/869e674xk) (wybór karton/koperta, high), [869e674je](https://app.clickup.com/t/869e674je) (dodatkowe uwagi, urgent) — lista „WMS i wysyłki".
**Zakres:** backend + frontend, strona admina i klienta (web). Flutter/API mobilne — tylko parytet backendu, UI poza zakresem.

## 1. Cel i kontekst

Trzy taski dotyczą tej samej funkcji — **zlecenia wysyłki** (`ShippingRequest`, numery `WYS/000001`). Dziś:

- Klient tworzy zlecenie 2-krokowym wizardem: wybiera zamówienia + adres. Nie podaje ceny, opakowania ani uwag.
- Zlecenie startuje w statusie `czeka_na_wycene`. Admin obsługuje je w modalu WMS (`PUT /admin/orders/shipping-requests/<id>`): wpisuje koszt **ręcznie**, ustawia status/kurier/tracking/gabaryt.
- Model `ShippingRequest` ma już: `total_shipping_cost`, `parcel_size` (A/B/C, tylko admin), `admin_notes` (notatka admina, bez inputu w UI).
- Brak w modelu: typ opakowania (karton/koperta), uwagi klienta.

Cennik z taska tp to funkcja `cena = f(gabaryt, karton/koperta)`:

| Gabaryt | Karton | Koperta |
|---|---|---|
| Mini | — | 12,99 |
| A | 19,49 | 17,99 |
| B | 21,49 | — |
| C | 23,49 | — |

## 2. Decyzje (zatwierdzone przez Konrada)

1. **Model procesu: hybryda.** Klient wskazuje sugerowane opakowanie przy tworzeniu; ostateczny gabaryt + cenę ustala admin przy obsłudze.
2. **Źródło cennika: baza `PackagingMaterial` (WMS).** Zamiast osobnego cennika rozszerzamy istniejącą tabelę materiałów o `sale_price` + `size_category`. Materiał ma już `type` (karton/koperta), więc jeden wiersz materiału = pełny wiersz cennika. Wybór materiału przez admina podstawia jednocześnie cenę + gabaryt + typ. Spina taski tp i xk w jedno źródło prawdy; ceny edytowalne w panelu bez deployu.
3. **Pola klienta przy tworzeniu:** (a) dodatkowe uwagi [je], (b) sugerowany typ opakowania karton/koperta [kliencka część xk], (c) podgląd cennika (info „wysyłka od X zł").
4. **Sugerowane opakowanie klienta = tylko karton vs koperta** (bez rozdzielania na koperty bąbelkowe/foliopaki itd.).
5. **Magazyn nietknięty.** Wybór materiału na zleceniu służy wyłącznie do ceny/gabarytu/typu. Stan magazynowy zmienia się jak dziś — dopiero przy pakowaniu zamówienia (`wms_pack_order` odejmuje 1). Unika podwójnego odejmowania.

### Decyzje techniczne (delegowane, wzięte na siebie)
- Powiązanie materiału ze zleceniem: **FK `packaging_material_id` na `ShippingRequest` + snapshot ceny** do istniejącego `total_shipping_cost` (cena historyczna nie „ucieka" po edycji materiału).
- `parcel_size` poszerzone `String(1)` → `String(10)` (żeby zmieścić `mini`).
- Cennik dla klienta liczony server-side i przekazany do kontekstu szablonu (bez osobnego endpointu).
- Nazwy pól: `sale_price`, `size_category`, `packaging_material_id`, `client_package_preference`, `client_notes`.

## 3. Zmiany modelu

### `PackagingMaterial` — `modules/orders/wms_models.py`
- `sale_price` — `Numeric(8,2)`, nullable — cena sprzedaży wysyłki (osobno od `cost` = koszt zakupu materiału).
- `size_category` — `String(10)`, nullable — gabaryt: `mini`/`A`/`B`/`C`.
- Nowa stała klasowa `SIZE_CHOICES = {'mini':'Mini', 'A':'Gabaryt A', 'B':'Gabaryt B', 'C':'Gabaryt C'}`.
- Property `size_display` — czytelna nazwa gabarytu z `SIZE_CHOICES` (albo `None`).

### `ShippingRequest` — `modules/orders/models.py`
- `packaging_material_id` — `Integer`, FK → `packaging_materials.id`, nullable + relacja `packaging_material` — materiał wybrany przez admina (źródło ceny/gabarytu/typu).
- `client_package_preference` — `String(30)`, nullable — sugestia klienta: `karton`/`koperta` [xk].
- `client_notes` — `Text`, nullable — uwagi klienta [je].
- `parcel_size` — poszerzenie do `String(10)`.
- Bez zmian: `total_shipping_cost` (tu snapshot ceny), `admin_notes` (notatka admina, osobno od `client_notes`).

## 4. Migracje

Repo ma obecnie **3 rozgałęzione heady** migracji (brak jednego wspólnego heada):
`f5fe71f921ef`, `830b9d3167ad`, `b1c2d3e4f5a6`.

1. `flask db heads` → potwierdź stan.
2. `flask db merge` trzech headów (precedens w repo: `9556407dc0e2`, `26764a10e8c2`).
3. **Jedna** migracja z `down_revision` = wynik merge, dodająca:
   - `packaging_materials.sale_price` (`Numeric(8,2)`, nullable)
   - `packaging_materials.size_category` (`String(10)`, nullable)
   - `shipping_requests.packaging_material_id` (`Integer`, nullable) + FK `fk_shipping_requests_packaging_material_id`
   - `shipping_requests.client_package_preference` (`String(30)`, nullable)
   - `shipping_requests.client_notes` (`Text`, nullable)
   - ALTER `shipping_requests.parcel_size` → `String(10)`
4. `flask db upgrade` — test lokalnie (XAMPP). Uwaga na wzorce MariaDB przy FK (nazwane FK, brak dropu indeksu podtrzymującego FK).
5. Commit migracji razem z kodem.

## 5. Backend

### Admin — CRUD materiałów opakowaniowych (`modules/orders/wms.py`)
Obsługa `sale_price` + `size_category` w 4 miejscach:
- `packaging_material_get` (~1471–1494) — serializacja nowych pól.
- `packaging_materials_list_api` (~1497–1519) — serializacja.
- `packaging_material_create` (~1522–1562) — odczyt z payloadu, walidacja `size_category` vs `SIZE_CHOICES`.
- `packaging_material_update` (~1565–1601) — jw.

### Admin — obsługa zlecenia (`modules/orders/routes.py`)
- `admin_update_shipping_request` (PUT, ~3746): przyjmuje `packaging_material_id`. Gdy podany i materiał istnieje:
  - `total_shipping_cost = material.sale_price` — o ile admin nie nadpisał kosztu ręcznie w tym samym żądaniu (ręczna wartość ma priorytet).
  - `parcel_size = material.size_category`.
  - Bez zmian stanu magazynowego.
  - Zachowana istniejąca auto-zmiana statusu `czeka_na_wycene → czeka_na_oplacenie` po ustaleniu kosztu.
- `admin_get_shipping_request` (~3662): serializuje `packaging_material_id` (+ nazwa/typ/gabaryt/cena materiału), `client_package_preference`, `client_notes`.

### Klient — tworzenie zlecenia (`modules/client/shipping_service.py`)
- `validate_and_create_request` (~139–199): odczytuje i zapisuje `client_package_preference` (walidacja: `karton`/`koperta`/puste) + `client_notes` (trim, limit długości). Zmiana w serwisie automatycznie obejmuje endpoint web (`modules/client/shipping.py` create ~224) i **API mobilne** (`modules/api_mobile/shipping_routes.py` create ~157) — parytet za darmo; oba pola opcjonalne (wstecznie kompatybilne).

### Cennik dla klienta
- Helper (w `shipping_service.py` lub `wms_utils.py`) budujący cennik z aktywnych materiałów z ustawionym `sale_price`: minimalna cena („wysyłka od X zł") + lista `{size_display, type_display, sale_price}`. Przekazany do kontekstu `shipping_requests_list` (`modules/client/shipping.py`) i wyrenderowany w modalu.

## 6. Frontend

### Klient
- `templates/client/shipping/requests_list.html` — w wizardzie tworzenia: radio „Sugerowane opakowanie: Karton / Koperta", textarea „Dodatkowe uwagi", box informacyjny z cennikiem.
- `static/js/pages/client/shipping-requests.js` — zebranie `client_package_preference` + `client_notes` i wysłanie w POST create.
- `static/css/pages/client/shipping-requests.css` — style nowych elementów (light + dark mode).

### Admin — materiały opakowaniowe
- `templates/admin/orders/wms_dashboard.html` (modal `#material-modal`) — input ceny sprzedaży + `<select>` gabarytu (Mini/A/B/C); kolumny listy (desktop + mobile) pokazują cenę sprzedaży i gabaryt.
- `static/js/pages/admin/wms-dashboard.js` — rozszerzenie payloadu create/update i wypełniania modala przy edycji.
- `static/css/pages/admin/wms-dashboard.css` — ewentualne dostrojenie kolumn (light + dark).

### Admin — modal zlecenia
- `templates/admin/orders/_shipping_request_modal.html` — `<select>` materiału opakowaniowego (etykiety: typ + gabaryt + cena); po wyborze JS auto-wypełnia koszt i gabaryt (`srParcelSize` rozszerzony o „Mini"). Wyświetlenie sugestii klienta (`client_package_preference`) i uwag klienta (`client_notes`) jako **read-only do wglądu** (uwagi wpisuje wyłącznie klient przy tworzeniu zlecenia; admin ich nie edytuje). `admin_notes` pozostaje bez zmian (poza zakresem).
- `static/js/pages/admin/shipping-requests.js` — obsługa selecta materiału (auto-fill kosztu/gabarytu), wysłanie `packaging_material_id` w PUT.
- `static/css/pages/admin/shipping-requests-list.css` — style nowych elementów (light + dark).

## 7. Testy (`python -m pytest`)
- Model: defaulty i zapis `sale_price`/`size_category` na `PackagingMaterial`; nowe pola `ShippingRequest`.
- Serwis: tworzenie zlecenia z `client_package_preference` + `client_notes` zapisuje wartości; walidacja preferencji (odrzucenie wartości spoza karton/koperta).
- Admin update: `packaging_material_id` → `total_shipping_cost` z `sale_price` i `parcel_size` z `size_category`; ręczne nadpisanie kosztu ma priorytet; brak zmian stanu magazynowego.
- Helper cennika: poprawna cena minimalna i lista pozycji z materiałów.

## 8. Poza zakresem
- Flutter UI (tylko backend przyjmuje pola).
- Zmiany w przepływie pakowania zamówień / stanie magazynowym.
- Automatyczne dobieranie gabarytu/materiału (pozostaje decyzja admina; istniejące `suggest_packaging` bez zmian).
