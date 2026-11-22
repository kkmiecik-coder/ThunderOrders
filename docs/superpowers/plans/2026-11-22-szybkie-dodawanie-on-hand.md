# Szybkie dodawanie produktów on hand — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ekran w panelu admina pod telefon: zdjęcie(a) + nazwa + cena + ilość → „Dodaj i następny” tworzy aktywny produkt on-hand widoczny od razu w sklepie; pod spodem lista rzeczy z tej rundy z szybką poprawką i ukrywaniem.

**Architecture:** Logika w nowym serwisie `modules/products/quick_add_service.py` (tworzenie atomowe produktu ze zdjęciami, poprawka, ukrycie), cienkie trasy JSON w nowym `modules/products/quick_add.py` na istniejącym `products_bp` (`/admin/products/...`). Front: osobny szablon + CSS + JS; zdjęcie zmniejszane w przeglądarce (canvas → JPEG) przed wysłaniem; lista rundy trzymana w `sessionStorage`. Bez zmian schematu bazy.

**Tech Stack:** Flask, SQLAlchemy 2, Jinja2, vanilla JS, Pillow (istniejące `utils/image_processor.process_upload`), pytest (SQLite in-memory).

**Spec:** `docs/superpowers/specs/2026-11-22-szybkie-dodawanie-on-hand-design.md`

## Global Constraints

- Gałąź `feat/szybkie-on-hand`. Bez pushowania (push = wdrożenie, tylko za wyraźną zgodą Karoliny).
- Testy: `venv/bin/python -m pytest`. Podagenci uruchamiają WYŁĄCZNIE swoje pliki testów, nigdy pełnej suity.
- Dostęp: `@login_required` + `@role_required('admin', 'mod')` (z `utils.decorators`).
- Produkt z tego ekranu: `product_type_id` = id typu o slugu `on-hand` (`modules.client.shop_service.get_on_hand_type()`), `is_active=True`, `is_gratis=False`; pola SKU, EAN, kategoria, producent, seria, dostawca, opis, cena zakupu, wymiary = `None`; `margin` przez `product.calculate_margin()` (wyjdzie `None`).
- Zdjęcia: co najmniej 1, maksymalnie `get_image_settings()['max_per_product']`; pierwsze `is_primary=True`, `sort_order` 1..n; zapis przez `process_upload(file, os.path.join(current_app.config['UPLOAD_FOLDER'], 'products'))`.
- CSS: kolory tylko ze zmiennych `static/css/core/variables.css`, każdy styl działa w `[data-theme="dark"]`, cele dotyku ≥ 44px. CSS/JS w osobnych plikach, nie inline.
- JS: `window.showToast(msg, type)`, `getCsrfToken()`, delegacja zdarzeń z `data-*` (bez danych w inline `onclick`).
- Po zmianach w `static/` podbić `CACHE_VERSION` w `static/sw.js` z `thunderorders-v46` na `thunderorders-v47` (osobny commit `chore(pwa): bump CACHE_VERSION do v47`).
- Teksty interfejsu po polsku. Commity: polskie conventional commits, stopka `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Nowe pliki w `docs/superpowers` przez `git add -f`.

## Review Focus

1. Cena wpisana z przecinkiem na polskiej klawiaturze (`"49,99"`) musi się zapisać jako 49.99, a nie dać błąd — test w Task 1.
2. Błąd przy przetwarzaniu drugiego zdjęcia nie może zostawić produktu bez zdjęć ani osieroconych plików na dysku — test w Task 1.
3. Brak typu `on-hand` w bazie → czytelny błąd, żadnego produktu bez typu — test w Task 1.
4. Poprawka/ukrycie przez trasę szybkiego dodawania nie może ruszyć produktu, który nie jest on-hand (podrobione id) — test w Task 2.
5. Nieudany zapis (np. zerwany internet, błąd 400) zostawia wpisane pola i zdjęcia w formularzu, żeby dało się ponowić — sprawdzane ręcznie przez Karolinę na telefonie (Task 3, krok weryfikacji), w kodzie: czyszczenie formularza tylko w gałęzi sukcesu.

---

### Task 1: Serwis szybkiego dodawania

**Files:**
- Create: `modules/products/quick_add_service.py`
- Test: `tests/test_quick_add_service.py`

**Interfaces:**
- Produces:
  - `class QuickAddError(ValueError)` — komunikat po polsku do pokazania w toaście.
  - `parse_price(raw: str | None) -> Decimal` — akceptuje `"49.99"`, `"49,99"`, `" 50 "`; wynik > 0, zaokrąglony do 2 miejsc; inaczej `QuickAddError('Podaj poprawną cenę')`.
  - `parse_quantity(raw: str | None) -> int` — pusty/None → 1; liczba całkowita ≥ 1; inaczej `QuickAddError('Ilość musi być liczbą od 1 wzwyż')`.
  - `create_quick_product(name: str, price_raw: str, quantity_raw: str | None, files: list[FileStorage], user) -> Product` — waliduje (nazwa po `strip()` niepusta, ≤ 255 znaków → inaczej `QuickAddError('Podaj nazwę')` / `QuickAddError('Nazwa jest za długa')`; brak plików → `QuickAddError('Dodaj co najmniej jedno zdjęcie')`; za dużo plików → `QuickAddError(f'Maksymalnie {n} zdjęć')`; brak typu on-hand → `QuickAddError('Brak typu produktu „On-hand” w ustawieniach magazynu')`), tworzy produkt i zdjęcia w jednej transakcji, commituje, loguje `log_activity(user=user, action='product_created', entity_type='product', entity_id=product.id)`. Gdy któreś zdjęcie się nie przetworzy: `db.session.rollback()`, usunięcie już zapisanych plików: `os.path.join(upload_folder, 'original', filename)` i `os.path.join(upload_folder, 'compressed', filename)` dla każdego `filename` zwróconego przez `process_upload`, `QuickAddError('Nie udało się zapisać zdjęcia — spróbuj ponownie')`.
  - `update_quick_product(product: Product, name: str, price_raw: str, quantity_raw: str | None) -> Product` — te same walidacje nazwy/ceny/ilości, commit.
  - `hide_quick_product(product: Product) -> Product` — `is_active=False`, commit.
  - `is_quick_editable(product: Product) -> bool` — True tylko gdy produkt ma typ o slugu `on-hand`.
  - `serialize_quick_product(product: Product) -> dict` — `{'id', 'name', 'sale_price': '49.99' (str), 'quantity', 'is_active', 'thumb_url'}`; `thumb_url` = `url_for('static', filename=<path_compressed głównego zdjęcia>)` albo `None`.

- [ ] **Step 1: Napisz testy (failing)**

Fixture w pliku: `on_hand_type` (dodaje `ProductType(name='On-hand', slug='on-hand')`), `upload_dir` (monkeypatch `app.config['UPLOAD_FOLDER']` na `tmp_path`; pliki lądują w `tmp_path/products/original|compressed`), helper `_jpeg(name='a.jpg')` tworzący `FileStorage` z małym JPEG z Pillow. Testy w `app.test_request_context()` (potrzebne `url_for`).

```python
def test_parse_price_accepts_comma_and_dot():
    assert parse_price('49,99') == Decimal('49.99')
    assert parse_price(' 50 ') == Decimal('50.00')
    for bad in ['', None, 'abc', '0', '-5']:
        with pytest.raises(QuickAddError): parse_price(bad)

def test_parse_quantity_defaults_to_one():
    assert parse_quantity('') == 1 and parse_quantity(None) == 1 and parse_quantity('3') == 3
    for bad in ['0', '-1', '1.5', 'x']:
        with pytest.raises(QuickAddError): parse_quantity(bad)

def test_create_makes_active_on_hand_product_visible_in_shop(...):
    p = create_quick_product('Album X', '49,99', '2', [_jpeg('a.jpg'), _jpeg('b.jpg')], admin)
    assert p.product_type_id == on_hand_type.id and p.is_active and p.quantity == 2
    assert p.sale_price == Decimal('49.99') and p.sku is None and p.margin is None
    imgs = sorted(p.images, key=lambda i: i.sort_order)
    assert [i.sort_order for i in imgs] == [1, 2] and imgs[0].is_primary and not imgs[1].is_primary
    assert build_products_query(on_hand_type).filter(Product.id == p.id).count() == 1

def test_create_requires_name_price_and_photo(...):   # każdy z trzech braków → QuickAddError, Product.query.count() == 0

def test_create_rejects_more_photos_than_limit(...):  # Settings warehouse_image_max_per_product=2, 3 pliki → QuickAddError, 0 produktów

def test_create_without_on_hand_type_fails_cleanly(...):  # bez fixture on_hand_type → QuickAddError, 0 produktów

def test_failed_second_photo_rolls_back_and_removes_files(...):
    # monkeypatch process_upload: 1. wywołanie = prawdziwe, 2. = raise ValueError
    # → QuickAddError; Product.query.count() == 0; ProductImage.query.count() == 0;
    #   katalogi original/ i compressed/ w upload_dir puste

def test_update_changes_fields_and_validates(...):    # '59,00', '5' → zapisane; pusta nazwa → QuickAddError i stara nazwa zostaje

def test_hide_sets_inactive_and_drops_from_shop(...):

def test_is_quick_editable_only_for_on_hand(...):     # produkt bez typu → False
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `venv/bin/python -m pytest tests/test_quick_add_service.py -v`
Expected: FAIL (`ModuleNotFoundError: modules.products.quick_add_service`)

- [ ] **Step 3: Zaimplementuj `modules/products/quick_add_service.py`** wg Interfaces. Ceny przez `Decimal(raw.strip().replace(',', '.'))` w `try/except InvalidOperation`, `quantize(Decimal('0.01'))`. Produkt: `db.session.add` + `flush()` (żeby mieć id), potem zdjęcia w pętli; pliki zapisane w tej pętli zbierane do listy do ewentualnego sprzątania.

- [ ] **Step 4: Uruchom — ma przejść**

Run: `venv/bin/python -m pytest tests/test_quick_add_service.py -v`
Expected: wszystkie PASS

- [ ] **Step 5: Commit**

```bash
git add modules/products/quick_add_service.py tests/test_quick_add_service.py
git commit -m "feat(magazyn): serwis szybkiego dodawania produktów on hand"
```

---

### Task 2: Trasy JSON

**Files:**
- Create: `modules/products/quick_add.py`
- Modify: `modules/products/__init__.py` (dopisać `from modules.products import quick_add` pod importem `routes`)
- Test: `tests/test_quick_add_routes.py`

**Interfaces:**
- Consumes: wszystko z Task 1.
- Produces (endpointy na `products_bp`, prefiks `/admin/products`):
  - `GET /quick-add` → `products.quick_add` — renderuje `admin/warehouse/quick_add.html` (szablon z Task 3; w tym tasku wystarczy minimalny plik z `{% extends "admin/base_admin.html" %}`, Task 3 go rozbuduje).
  - `POST /quick-add` → `products.quick_add_create` — multipart: `name`, `sale_price`, `quantity`, `images` (wiele). 200 `{'success': True, 'product': serialize_quick_product(p)}`; `QuickAddError` → 400 `{'success': False, 'error': str(e)}`.
  - `POST /quick-add/<int:product_id>/update` → `products.quick_add_update` — JSON `{name, sale_price, quantity}`; 200 jak wyżej; 400 przy `QuickAddError`; 404 gdy brak produktu albo `not is_quick_editable(p)`.
  - `POST /quick-add/<int:product_id>/hide` → `products.quick_add_hide` — 200 `{'success': True, 'product': ...}`; 404 jak wyżej.

- [ ] **Step 1: Napisz testy (failing)** — z fixture `client`, `login`, `make_user`, `make_product`; fixture `on_hand_type` i `upload_dir` jak w Task 1 (skopiować do pliku).

```python
def test_client_role_gets_no_access(...):        # role='client' → GET /admin/products/quick-add i POST: status != 200, 0 produktów
def test_mod_can_open_page(...):                 # role='mod' → GET 200
def test_create_returns_product_json(...):       # POST multipart z 1 JPEG → 200, json['product']['name'] == 'Album', ['quantity'] == 1 (pole puste), thumb_url zaczyna się od '/static/uploads/products/'
def test_create_validation_error_is_400(...):    # bez zdjęcia → 400, json['error'] == 'Dodaj co najmniej jedno zdjęcie'
def test_update_and_hide_work_for_on_hand(...):  # update → 200 i nowa cena; hide → 200, is_active False
def test_update_and_hide_404_for_non_on_hand(...):  # make_product() bez typu → oba 404, produkt bez zmian
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `venv/bin/python -m pytest tests/test_quick_add_routes.py -v`
Expected: FAIL (404 na `/admin/products/quick-add`)

- [ ] **Step 3: Zaimplementuj `modules/products/quick_add.py`** i import w `__init__.py`. Pliki z `request.files.getlist('images')`, pomijając puste (`f and f.filename`).

- [ ] **Step 4: Uruchom — ma przejść**

Run: `venv/bin/python -m pytest tests/test_quick_add_routes.py tests/test_quick_add_service.py -v`
Expected: wszystkie PASS

- [ ] **Step 5: Commit**

```bash
git add modules/products/quick_add.py modules/products/__init__.py templates/admin/warehouse/quick_add.html tests/test_quick_add_routes.py
git commit -m "feat(magazyn): trasy szybkiego dodawania on hand"
```

---

### Task 3: Ekran na telefon + wejścia z menu

**Files:**
- Modify: `templates/admin/warehouse/quick_add.html`
- Create: `static/css/pages/admin/quick-add.css`, `static/js/pages/admin/quick-add.js`
- Modify: `templates/components/sidebar_admin.html` (sekcja „Magazyn”: nowa pozycja „Szybkie dodawanie” po „Lista produktów”; dopisać `'products.quick_add'` do listy endpointów podświetlających nagłówek), `templates/components/bottom_bar_admin.html` (to samo w arkuszu Magazyn i w liście endpointów przycisku), `templates/admin/warehouse/products_list.html` (przycisk „Szybkie dodawanie” w `.toolbar-left`, link do `products.quick_add`)
- Modify: `static/sw.js` (`CACHE_VERSION` → `thunderorders-v47`)
- Test: `tests/test_quick_add_routes.py` (dopisać test renderu)

**Interfaces:**
- Consumes: endpointy z Task 2, `serialize_quick_product` jako kształt danych listy.
- Produces: szablon z elementami o id: `qa-form`, `qa-photos` (`<input type="file" accept="image/*" multiple>` — bez `capture`, żeby telefon dał wybór aparat/galeria), `qa-previews`, `qa-name`, `qa-price` (`inputmode="decimal"`), `qa-quantity` (`type="number" min="1" value="1" inputmode="numeric"`), `qa-submit` („Dodaj i następny”), `qa-list` (lista rundy), `qa-list-empty`.

Zachowanie JS (decyzje, które implementer ma odwzorować):
- Wybrane zdjęcia od razu zmniejszane: `createImageBitmap` (z fallbackiem `Image` + `URL.createObjectURL`) → canvas, dłuższy bok max 1600 px → `canvas.toBlob(..., 'image/jpeg', 0.85)` → plik `zdjecie-<n>.jpg`. Błąd odczytu → `showToast('Nie udało się odczytać zdjęcia', 'error')`, zdjęcie pominięte. Miniatury w `qa-previews` z przyciskiem usunięcia; kolejne wybory dopisują się (do limitu z `data-max-photos` na formularzu, wartość z `get_image_settings()['max_per_product']` podana z trasy GET).
- Wysyłka `FormData` przez `fetch` z nagłówkiem `X-CSRFToken: getCsrfToken()`, przycisk zablokowany z tekstem „Zapisuję…” w trakcie.
- Sukces: produkt na górę listy rundy, zapis listy do `sessionStorage['quickAddRound']` (try/catch), `showToast('Dodano: <nazwa>', 'success')`, wyczyszczenie zdjęć/nazwy/ceny, ilość z powrotem na 1, fokus na przycisk zdjęcia.
- Błąd (400/500/brak sieci): `showToast(error || 'Nie udało się zapisać — sprawdź internet i spróbuj ponownie', 'error')`, NIC nie jest czyszczone.
- Lista rundy: karta z miniaturą, nazwą, ceną „49,99 zł”, „szt. 2”; przyciski „Popraw” (rozwija pola nazwa/cena/ilość + „Zapisz”) i „Ukryj” (`confirm('Ukryć ten produkt ze sklepu?')`) — delegacja zdarzeń po `data-id`. Ukryty element zostaje na liście z etykietą „Ukryty”.

- [ ] **Step 1: Dopisz test renderu (failing)**

```python
def test_quick_add_page_renders_form(...):   # admin, GET → 200; w HTML: 'id="qa-photos"', 'accept="image/*"', 'Dodaj i następny', 'quick-add.js', 'data-max-photos="10"'
```

- [ ] **Step 2: Uruchom — ma nie przejść**

Run: `venv/bin/python -m pytest tests/test_quick_add_routes.py::test_quick_add_page_renders_form -v`
Expected: FAIL (brak elementów w minimalnym szablonie)

- [ ] **Step 3: Zbuduj szablon, CSS i JS** wg powyższego. Układ jednokolumnowy, przyciski na całą szerokość, min. 44px; na desktopie wyśrodkowana kolumna ~480px.

- [ ] **Step 4: Dodaj wejścia z menu i przycisk na liście produktów.**

- [ ] **Step 5: Sprawdź**

Run: `venv/bin/python -m pytest tests/test_quick_add_routes.py tests/test_quick_add_service.py -v && node --check static/js/pages/admin/quick-add.js`
Expected: wszystkie PASS, `node --check` bez błędów

- [ ] **Step 6: Commit (dwa)**

```bash
git add templates/admin/warehouse/quick_add.html static/css/pages/admin/quick-add.css static/js/pages/admin/quick-add.js templates/components/sidebar_admin.html templates/components/bottom_bar_admin.html templates/admin/warehouse/products_list.html tests/test_quick_add_routes.py
git commit -m "feat(magazyn): ekran szybkiego dodawania on hand na telefon"
git add static/sw.js
git commit -m "chore(pwa): bump CACHE_VERSION do v47"
```

---

### Na koniec (kontroler)

- [ ] Pełna suita w tle: `venv/bin/python -m pytest` — wynik zgłosić Karolinie wprost (także ewentualne niezwiązane porażki).
- [ ] Powiedzieć Karolinie wprost: ekranu za logowaniem nie przeklikam sama — przeklikanie na telefonie (zdjęcie z aparatu, z galerii, zdjęcie z iPhone'a, wyłączony internet przy zapisie, poprawka, ukrycie, czy rzecz widać w sklepie) zostaje po jej stronie, lokalnie przed scaleniem do main.
