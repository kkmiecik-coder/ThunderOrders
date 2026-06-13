# Mobile API — Etap E8 (Kolekcja klienta: CRUD + zdjęcia + publiczna strona, BEZ QR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Mobilna warstwa „Moja Kolekcja" — CRUD itemów kolekcji (z multipart uploadem zdjęć z aparatu),
zarządzanie zdjęciami (max 3, primary) oraz konfiguracja publicznej strony kolekcji. Jedenaście
endpointów (kontrakt ze specu sekcja 5, ścieżki pod prefiksem `/collection/` — patrz Korekta 1).
**QR upload (komputer↔telefon) POZA zakresem** — telefon ma aparat natywnie (spec).

```
GET    /collection/items            ?q=&sort=&page=&per_page=   → moja kolekcja
GET    /collection/items/<id>                                   → szczegóły
POST   /collection/items            (multipart: dane + zdjęcia) → dodaj
PATCH  /collection/items/<id>       (multipart)                 → edytuj
DELETE /collection/items/<id>                                   → usuń
POST   /collection/items/<id>/images        (multipart)         → dodaj zdjęcie (max 3)
DELETE /collection/items/<id>/images/<img_id>                   → usuń zdjęcie
PATCH  /collection/items/<id>/images/<img_id>/primary           → ustaw główne
GET    /collection/public/config                                → konfiguracja publicznej strony
POST   /collection/public/config    { show_prices, is_active }  → zmień (UPSERT — D6)
POST   /collection/items/<id>/toggle-public                     → przełącz widoczność
```

**Architecture:** Cztery odkrycia kształtują plan:
1. **Cała logika kolekcji webowej jest INLINE w trasach** (`modules/client/collection.py`, 676 linii,
   13 tras) — **ZERO serwisu, ZERO testów** (zweryfikowane: brak `tests/*collection*`). Wzorzec
   E2/E5/E6/E7: **ekstrakcja wspólnego serwisu + refaktor weba (bez zmiany zachowania) + smoke testy**.
   Logika nietrywialna: limit 3 zdjęć, reassignment primary po usunięciu zdjęcia, QR temp uploads
   w `add` (web-only — serwis przyjmuje je parametrem), achievement hooki (3 eventy — zweryfikowane
   w `modules/achievements/services.py:31-33`). **Decyzja: PEŁNA EKSTRAKCJA**
   `modules/client/collection_service.py` (items + images + public).
2. **Publiczna strona kolekcji jest serwowana przez web BEZ auth** (`modules/public/routes.py:15`,
   `GET /collection/<token>`, blueprint `public` bez prefiksu) — mobilne `public/config` **tylko
   konfiguruje** (token, show_prices, is_active) i zwraca **absolutny `public_url`**, którym apka
   się dzieli (share sheet). Mobile NIE serwuje publicznej strony.
3. **Zdjęcia kolekcji są serwowane publicznym `/static`**
   (`static/uploads/collections/<user_id>/{original,compressed}/`) — w przeciwieństwie do dowodów
   wpłat z E6 NIE są chronione (są wręcz pokazywane anonimom na publicznej stronie kolekcji).
   **Parytet: mobile zwraca absolutne URL-e do `/static/...`, ŻADNEJ trasy JWT do serwowania.**
4. **Walidacja/zapis/kompresja zdjęć już współdzielona**: `utils/image_processor.py` →
   `process_collection_upload(file, user_id)` (whitelist rozszerzeń z Settings, unikalna nazwa,
   EXIF transpose, kompresja 800px/q75/dpi72, PIL `Image.open` = implicit walidacja integralności,
   cleanup przy błędzie → `ValueError`) + `delete_collection_image_files`. Mobile reużywa przez
   serwis — bez własnej repliki. Web NIE sprawdza rozmiaru pliku (tylko globalny
   `MAX_CONTENT_LENGTH` 50 MB, config.py:48) — mobile dokłada limit 10 MB per plik (D8).

**Tech Stack:** Flask, flask-jwt-extended (JWT, bez sesji/CSRF), SQLAlchemy, Flask-Migrate (Alembic —
**ZERO migracji w E8**, head pozostaje `c72aad290158` — wszystkie modele istnieją), pytest (sqlite
in-memory), Flask-Limiter, PIL. Nowe pliki: `modules/api_mobile/collection_routes.py`,
`modules/client/collection_service.py`. Koperty `{success,data}`/`{success,error{code,message,details?}}`,
kwoty w **groszach (int)**, obrazy jako **absolutne URL-e**, daty **ISO** — spójne z E0–E7.

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Modele (`modules/client/models.py` — NIE wymagają migracji, wszystkie pola istnieją)
- **`CollectionItem`** (l. 40+): `user_id(FK, index), name(String 255, NOT NULL),
  market_price(Numeric(10,2), NULL), source('manual'|'order', default 'manual'),
  order_item_id(FK NULL), product_id(FK NULL), notes(Text NULL), is_public(Bool, default True,
  NOT NULL), created_at, updated_at`. Properties: `primary_image` (pierwszy z `is_primary` albo
  pierwszy w ogóle), `image_url` (`/static/{primary.path_compressed}` → fallback zdjęcie produktu
  gdy `product_id` → placeholder `/static/img/placeholders/collection-item.svg` — plik ISTNIEJE),
  `is_from_order`, `images_count`, **`can_add_image` = `images_count < 3`** (limit 3 egzekwowany
  TYLKO aplikacyjnie, przez tę property). Relacja `images` (cascade `all, delete-orphan`,
  order_by `sort_order`).
- **`CollectionItemImage`** (l. 107+): `collection_item_id(FK CASCADE), filename, path_original,
  path_compressed, is_primary(Bool, default False), sort_order(Int, default 0), uploaded_at`.
- **`PublicCollectionConfig`** (l. 130+): `user_id(FK, UNIQUE), token(String(12), UNIQUE, index),
  show_prices(Bool, default True), is_active(Bool, default True), created_at, updated_at`.
  `generate_token()` (staticmethod): 12 znaków a-zA-Z0-9, retry-loop x10 z testem unikalności.
- **`CollectionUploadSession` + `CollectionTempUpload`** — flow QR, **POZA zakresem E8** (mobile
  ich nie dotyka; web zostaje bez zmian, serwis `create_item` przyjmuje `temp_uploads` parametrem,
  żeby webowy add zachował JEDEN commit — patrz Task 1).
- `get_local_now()` — czas PL, używany w defaultach.

### Webowe trasy kolekcji (`modules/client/collection.py`, prefix blueprintu `/client`) — WZORZEC DO EKSTRAKCJI
Pełne URL-e: `/client/collection` (GET, HTML), `/client/collection/add` (POST FormData),
`/client/collection/<id>/edit` (GET JSON + POST FormData), `/client/collection/<id>/delete` (DELETE),
`/client/collection/<id>/images` (POST), `/client/collection/<id>/images/<img_id>` (DELETE),
`/client/collection/<id>/images/<img_id>/primary` (POST), `/client/collection/public/create` (POST),
`/client/collection/public/config` (GET+POST), `/client/collection/<id>/toggle-public` (POST),
`/client/collection/public/toggle-all` (POST), trasy QR (`/qr-session`...).

**Lista (l. 14–80):** `view` (grid/list/carousel — HTML-only), `search` → `name.ilike(f'%{search}%')`,
`sort ∈ {newest(default), oldest, name_asc, price_desc}` — `price_desc` z **NULL-ami na końcu**
(`db.case((market_price.is_(None), 1), else_=0)` + `market_price.desc()`), `paginate(per_page=24)`.
Stats: `total_items` (count), `total_value` (SUM market_price, NULL-e pominięte).

**Add (l. 83–167, POST FormData):** `name` wymagane (puste → 400 „Nazwa jest wymagana");
`market_price` → `float()` **w PLN** (ValueError → 400 str(e)); `notes` (puste → None);
`source='manual'`; flush po add (item.id); `request.files.getlist('images')` — **cichy cap `[:3]`**,
pierwszy plik `is_primary=True`, `sort_order=i`; potem blok QR (`qr_session_token` → temp_uploads
→ `CollectionItemImage` per temp, gdy `item.can_add_image`, z flush w pętli); JEDEN commit;
**achievement `'collection_add'`** (best-effort try/except). Odpowiedź `{success, message, item_id}`.

**Edit (l. 170–232):** `get_or_404(item_id)` → **cudzy → 403** (mobile maskuje na 404 — D3).
GET zwraca JSON itemu z `images[]` (`{id, url: '/static/'+path_compressed, is_primary,
source: 'collection'}`) + **fallback na zdjęcia PRODUKTU** gdy item nie ma własnych a ma `product_id`
(`source: 'product'`). POST: name wymagane, market_price float, notes — **zawsze nadpisuje wszystkie
3 pola** (web wysyła komplet); commit. **Edit NIE dotyka zdjęć** (osobne endpointy).

**Delete (l. 235–262):** `delete_collection_image_files(orig, compr)` per zdjęcie (best-effort,
zwraca bool) → `db.session.delete(item)` (cascade na images) → commit.

**Add image (l. 265–321):** `not item.can_add_image` → 400 „Maksymalnie 3 zdjęcia na przedmiot";
brak pliku → 400 „Nie wybrano pliku"; `process_collection_upload` (ValueError → 400 str(e));
`is_primary = images_count == 0`, `sort_order = images_count`; **achievement `'photo_upload'`**.

**Delete image (l. 324–360):** `image.collection_item_id != item.id` → 404; usuń pliki; delete +
flush; **gdy usunięte było primary → `item.images[0].is_primary = True`** (pierwszy pozostały);
commit. **Set primary (l. 363–394):** unset wszystkich → set wskazanego → commit.

**Public create (l. 399–437):** istnieje → **409** „Publiczna strona już istnieje"; inaczej
`generate_token()`, `show_prices=True, is_active=True`; **achievement `'collection_public_toggle'`**;
zwraca `{token, url: f'/collection/{token}'}` (URL WZGLĘDNY — mobile da absolutny).
**Public config GET (l. 440–470):** brak → `{'success': False, 'exists': False}` ze **statusem 200**
(!); jest → config + **lista WSZYSTKICH itemów** z `{id, name, is_public, image_url}` (dla modala
webowego — mobile NIE dubluje, ma `GET /items` z `is_public` — D7).
**Public config POST (l. 473–503):** brak configu → **404** „Brak konfiguracji"; aktualizuje
`show_prices`/`is_active` (tylko obecne klucze, `bool()`).
**Toggle-public (l. 506–527):** `item.is_public = not item.is_public` → `{success, is_public}`.
**Toggle-all (l. 530–555):** bulk UPDATE — **web-only, POZA kontraktem mobilnym** (spec go nie
listuje; apka iteruje per item).

### Przetwarzanie zdjęć (`utils/image_processor.py` — WSPÓLNE, reużywane bez zmian)
- **`process_collection_upload(file, user_id)`** (l. 370–439): walidacja rozszerzenia
  (`allowed_file` — whitelist z Settings `warehouse_image_formats`, default `jpg,jpeg,png,webp,gif`),
  unikalna nazwa (`secrets.token_urlsafe(16)` + ext), zapis do
  `static/uploads/collections/<user_id>/original/` + EXIF transpose, kopia →
  `compressed/` + `compress_image(max_size=800, dpi=72, quality=75)`. **`Image.open` = implicit
  walidacja integralności** (nie-obraz/uszkodzony → wyjątek → cleanup obu plików → `ValueError`
  „Błąd przetwarzania obrazu: ..."). Zwraca `{filename, path_original, path_compressed}` —
  ścieżki WZGLĘDNE od `static/`. **Brak walidacji ROZMIARU** (tylko globalny `MAX_CONTENT_LENGTH`
  50 MB — config.py:48).
- **`delete_collection_image_files(path_original, path_compressed)`** (l. 442–466): best-effort
  remove obu plików, zwraca bool, nie rzuca.

### Publiczna strona (`modules/public/routes.py` — BEZ ZMIAN w E8)
- `GET /collection/<token>` (l. 15–46, blueprint `public`, **BEZ auth**): brak configu → 404;
  `is_active=False` → template `collection_inactive`; itemy `filter_by(user_id, is_public=True)`
  desc; `show_prices` steruje cenami w szablonie. Mobile linkuje
  `request.url_root + 'collection/<token>'`.

### Infrastruktura mobilnego API (REUŻYWALNA — z E0–E7)
- `helpers.py`: `json_ok(data,status)`, **`json_err(code,msg,status,details=None)`** (details już
  wbudowane — rozszerzone w E7), `to_grosze(amount)` (None-safe), `absolute_static_url(path)`
  (dokleja `/static/` SAM — dla ścieżek względnych bez prefiksu), `json_page(items,page,per_page,
  total,has_next)`. `validators.py`: `parse_int(value,field,required,default,min_value,max_value)`
  (None/'' → default), `ValidationError` (errorhandler blueprintu → `400 invalid_input`).
- `idempotency.py`: `@idempotent('endpoint')` — POD `@jwt_required()`, claim-first, nagłówek
  `Idempotency-Key` opcjonalny, **cache'uje też 4xx** (znany gotcha — akceptowane jak w checkout),
  wyjątek trasy zwalnia klucz.
- Konwencje: `@api_mobile_bp.route` → `@jwt_required()` → `@limiter.limit(...)` → (`@idempotent`);
  `int(get_jwt_identity())`; **ownership → 404 maskujące** (web 403 → mobile 404, wzorzec
  `_get_owned_order_or_404`, orders_routes.py:171); lokalne `_abs(path)` dla properties zwracających
  już `/static/...` (wzorzec `_abs_image` orders_routes.py:15 — `absolute_static_url` by zdublował
  prefix); paginacja: `parse_int` page/per_page, **cap per_page=50, default 20** (orders_routes.py:44);
  zamknięte enumy query → 400 (`ALLOWED_ORDER_TYPES`, D1(a) z E5).
- Rejestracja tras: `modules/api_mobile/__init__.py` importuje moduły na końcu (ostatni:
  `from . import shipping_routes`); E8 dokłada `from . import collection_routes`.
- Brak kolizji ścieżek: `/cart/items` vs `/collection/items` — różne prefiksy.

### Testy / fixtury / środowisko / migracje
- **Baseline: `363 passed`** (zweryfikowane 2026-06-13, ~62 s). TYLKO
  `source venv/bin/activate && python -m pytest`.
- **Głowa migracji: `c72aad290158`** (zweryfikowane `flask db heads`). **ZERO migracji w E8.**
- conftest: fixtury `app` (function-scoped → świeży limiter), `db, client,
  make_user(role,email,**kw)`, `make_product`, `make_order`, `login(user)` (sesja Flask-Login).
  **Brak fixtury kolekcji** — testy tworzą itemy serwisem/modelem.
- **Bramka klienta**: `client_bp.before_request` blokuje `profile_completed=False`
  (modules/client/__init__.py:13) → smoke webowe: `make_user(profile_completed=True)` + `login(user)`.
- **Wzorce multipart z E6** (tests/test_mobile_api_payments.py): `_tiny_png()` = BytesIO + PIL
  `Image.new('RGB',(1,1))` PNG; `client.post(..., data={...,'images': (buf,'a.png')},
  content_type='multipart/form-data')`; **autouse-fixtura sprzątająca pliki** (snapshot
  przed/po → remove różnicy). E8: sprzątamy `static/uploads/collections/` (per-user podkatalogi
  → najprościej rmtree katalogów userów utworzonych w teście).
- Achievement eventy ISTNIEJĄ: `'collection_add'`, `'photo_upload'`, `'collection_public_toggle'`
  (modules/achievements/services.py:31-33).
- `/docs` w `.gitignore` → commit planu/zmian doc przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem + E1–E7 — zatwierdzane wraz z planem)

1. **Prefiks `/collection/`** — spec listuje bare `/items` POD nagłówkiem „Kolekcja — `/collection/`".
   Parytet z precedensem E2/E7. Realne trasy: `/api/mobile/v1/collection/items` itd. Task 6 aktualizuje spec.
2. **`market_price` w GROSZACH (int) w obu kierunkach** — wejście (multipart form, string-int
   groszy, np. `"12999"` = 129,99 zł) i wyjście (`to_grosze`). Web operuje na float PLN — parsowanie
   zostaje w kanałach, serwis przyjmuje `Decimal|None`.
3. **Multipart na POST i czysty PATCH multipart** — web edytuje POST-em FormData; Flutter (dio/http)
   wysyła multipart PATCH bez problemu, Flask/Werkzeug parsuje form na PATCH normalnie. BEZ hacku
   `_method` (D2). **PATCH jest CZĘŚCIOWY**: aktualizowane tylko pola obecne w form
   (`name` obecne a puste → 400; `market_price=''` czyści cenę; `notes=''` czyści notatki) — web
   zawsze wysyła komplet pól, więc parytet zachowań przy komplecie (D4).
4. **Ownership → 404 maskujące** (`item_not_found`/`image_not_found`) — web zwraca 403 dla cudzych;
   mobile maskuje istnienie (konwencja E5/E7). Zdjęcie z innego itemu → 404 (parytet web).
5. **POST `/collection/items`**: pola form `name` (wymagane), `market_price` (grosze, opcjonalne),
   `notes` (opcjonalne), pliki `images` (0–3). **>3 plików → `400 invalid_input` +
   `details.max_images`** (web cicho ucina `[:3]`; jawny błąd = apka nie maskuje buga — D9).
   Zły format/uszkodzony plik → `400 invalid_file` (komunikat z `process_collection_upload`,
   all-or-nothing — rollback itemu). Sukces → `201` z pełnym itemem.
6. **POST `/collection/items/<id>/images`**: plik w polu `image`; brak → `400 invalid_input`;
   limit 3 osiągnięty → **`409 max_images`** (stan konfliktowy — konwencja 409 jak
   `orders_not_available` E7; web dawał 400). Sukces → `201 {image}`.
7. **GET `/collection/public/config`**: brak configu → **`200 {exists: false, config: null}`**
   (web: `success:false` + 200 — w mobilnej kopercie `success:false` oznacza błąd, a brak configu
   to poprawny stan). Jest → `{exists: true, config: {token, show_prices, is_active, public_url}}`
   z **absolutnym `public_url`**. BEZ listy itemów (web zwraca ją dla modala; apka ma
   `GET /items` z `is_public` — D7).
8. **POST `/collection/public/config` = UPSERT** — spec nie listuje odpowiednika webowego
   `/public/create`; pierwszy POST tworzy config (token + achievement, parytet create) i aplikuje
   przekazane flagi → `201 {created: true, config}`; kolejne → `200 {created: false, config}` (D6).
9. **GET `/collection/items`**: `q` → `name ilike` (parytet `search`), `sort` whitelist
   `newest|oldest|name_asc|price_desc` (nieznany → `400 invalid_input` — zamknięty enum, D1(a) E5),
   `page`/`per_page` (default 20, cap 50) + koperta `json_page`. `view` webowy pominięty (prezentacja).
10. **Brief vs detail**: lista zwraca brief (`id, name, market_price, source, is_public,
    images_count, image_url, created_at`); detail dodaje `notes, can_add_image, updated_at,
    images[]` (z **fallbackiem na zdjęcia produktu** + `source: 'collection'|'product'` —
    parytet web edit GET). Wszystkie URL-e absolutne, daty ISO.
11. **Efekty uboczne w SERWISIE** (achievementy `collection_add`/`photo_upload`/
    `collection_public_toggle`) — jeden kod dla obu kanałów (wzorzec E7 Korekta 9).
12. **`/collection/public/toggle-all` POZA zakresem mobilnym** (spec go nie listuje; web-only).

---

## Decyzje — ROZSTRZYGNIĘTE samodzielnie (delegacja: parytet web → rekomendacja → bezpieczeństwo)

- **D1 — Pełna ekstrakcja `collection_service.py` (items + images + public) + refaktor weba.**
  Web ma 0 serwisu i 0 testów; logika limitu zdjęć/primary-reassignment/achievementów jest
  divergence-prone — wzorzec E2/E5/E6/E7; refaktor mitygowany pierwszymi smoke-testami (`login` +
  `profile_completed=True`). Webowe trasy ZACHOWUJĄ swoje guardy `get_or_404` + 403 (kształt
  odpowiedzi bez zmian); serwis robi własny ownership-check (redundantny w webie, jedyny w mobile).
- **D2 — Czysty PATCH multipart (bez `_method`/POST-aliasu).** Werkzeug parsuje `request.form`/
  `request.files` dla PATCH identycznie jak dla POST; Flutter dio wspiera multipart PATCH natywnie.
  Kontrakt specu = PATCH; brak powodu na hack.
- **D3 — `@idempotent` NA `POST /collection/items` (TAK).** Duplikat itemu jest szkodliwy:
  klon na liście kolekcji + ZDUBLOWANE PLIKI na dysku (każdy retry zapisuje nowe oryginały+kompresje,
  osierocone po ręcznym usunięciu jednego z klonów). Retry multipart przy flaky mobile network jest
  realny, a wszystkie mutacje TWORZĄCE w tym API (checkout, place-order, shipping request) mają
  `@idempotent` — spójność. Replay tym samym kluczem odtwarza zapisany `201` bez ponownego zapisu
  plików. Gotcha cache'owania 4xx znany i akceptowany (klucz generowany per logiczna próba).
- **D4 — Pozostałe mutacje BEZ `@idempotent`.** PATCH item (idempotentny z natury), DELETE item/image
  (powtórka → 404), set-primary (ten sam stan), toggle-public (świadomie przełącznik — apka wysyła
  po tapnięciu, odpowiedź niesie nowy stan), public/config (upsert → ten sam stan), add-image
  (powtórka przy <3 zdjęciach tworzy duplikat zdjęcia — akceptowane: pojedynczy plik, user widzi
  i kasuje; analogia do E6 D4=a, gdzie upload też świadomie bez dekoratora).
- **D5 — Reużycie `process_collection_upload`/`delete_collection_image_files` BEZ zmian.**
  Wspólna walidacja (whitelist + integralność PIL) i kompresja (800px/q75) — zero repliki; zmiana
  pipeline'u zdjęć to ryzyko regresji weba bez korzyści.
- **D6 — POST `/collection/public/config` jako UPSERT.** Spec nie przewiduje mobilnego odpowiednika
  webowego `/public/create`; rozdzielenie create/update wymuszałoby endpoint spoza kontraktu albo
  dziwny flow w apce. Serwis ma OSOBNE prymitywy `create_public_config` (parytet create: 'exists'
  przy duplikacie, achievement) i `update_public_config` (parytet POST: 'not_found') — web używa ich
  1:1 (zachowanie bez zmian: create → 409 gdy istnieje, config POST → 404 gdy brak), mobile SKŁADA
  upsert z obu.
- **D7 — GET public/config BEZ listy itemów.** Web dokleja pełną listę itemów dla swojego modala;
  mobile ma `GET /collection/items` z polem `is_public` (paginowane) — duplikacja = drugi kontrakt
  listy do utrzymania.
- **D8 — Limit rozmiaru pliku 10 MB per zdjęcie (hardening ponad parytet).** Web nie sprawdza
  rozmiaru (tylko globalne 50 MB `MAX_CONTENT_LENGTH`); mobile sprawdza `seek/tell` przed zapisem
  (wzorzec E6) → `400 file_too_large`. 10 MB = wartość z ustawień obrazów (`warehouse_image_max_size_mb`
  default 10). Telefony robią zdjęcia 3–8 MB — limit nie przeszkadza, a chroni dysk. Web BEZ zmian.
- **D9 — >3 plików przy tworzeniu itemu → jawny 400 (web cicho ucina).** Cichy cap maskowałby bug
  apki; kontrakt jawny jest tańszy w debugowaniu. Różnica dotyczy wejścia nieosiągalnego z poprawnej
  apki (UI ogranicza wybór do 3).
- **D10 — Web `collection_edit` GET (JSON dla modala) zostaje INLINE.** To czysta serializacja
  pod webowy modal; mobile ma własny serializer detail. Ekstrakcja = zero zysku.

> **Do Konrada: BRAK rozgałęzień produktowych.** Cały zakres E8 to parytet z istniejącym webem;
> powyższe to decyzje techniczne rozstrzygnięte regułą delegacji (parytet → rekomendacja →
> bezpieczeństwo). Jedyna zmiana „widoczna" to upsert public/config (D6) — wymuszona kształtem
> kontraktu ze specu, który sam zatwierdziłeś.

---

## File Structure

- `modules/client/collection_service.py` — **NOWY (serce E8)**: items (`get_owned_item`,
  `list_items`, `create_item`, `update_item`, `delete_item`) + images (`add_image`, `delete_image`,
  `set_primary_image`) + public (`get_public_config`, `create_public_config`,
  `update_public_config`, `toggle_item_public`). Tasks 1, 3, 5.
- `modules/client/collection.py` — Tasks 1, 3, 5: refaktor tras webowych (add/edit POST/delete;
  images add/delete/primary; public create/config POST/toggle-public) by wołać serwis — BEZ zmiany
  zachowania (komunikaty/statusy/kształty zostają; trasa list i edit GET mogą zostać inline — D10).
- `modules/api_mobile/collection_routes.py` — **NOWY**: 11 tras mobilnych + serializery. Tasks 2, 4, 5.
- `modules/api_mobile/__init__.py` — Task 2: `from . import collection_routes`.
- `tests/test_collection_service.py` — **NOWY** (Tasks 1, 3, 5): testy serwisu + smoke webowych tras.
- `tests/test_mobile_api_collection.py` — **NOWY** (Tasks 2, 4, 5): testy tras mobilnych.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 6: korekty kontraktu E8.

---

### Task 1: `collection_service.py` — ITEMS (ekstrakcja) + refaktor webowych tras itemów

**Files:** Create `modules/client/collection_service.py`; modify `modules/client/collection.py`;
Create `tests/test_collection_service.py`

> Czysty refaktor + pierwsze pokrycie: webowe trasy itemów zachowują IDENTYCZNE zachowanie
> (komunikaty, statusy, QR temp_uploads w add, achievement). Mobile podłączy się w Task 2.

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_collection_service.py`:
```python
"""Testy serwisu kolekcji (ekstrakcja z webowych tras collection.py — parytet)."""
import io
import os
import shutil
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_collections(app):
    """Sprząta pliki zdjęć kolekcji utworzone w teście (per-user podkatalogi)."""
    base = os.path.join(app.root_path, 'static', 'uploads', 'collections')
    before = set(os.listdir(base)) if os.path.isdir(base) else set()
    yield
    if os.path.isdir(base):
        for d in set(os.listdir(base)) - before:
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def _png_storage(name='a.png'):
    from PIL import Image
    from werkzeug.datastructures import FileStorage
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return FileStorage(stream=buf, filename=name, content_type='image/png')


def _make_item(db, user, name='Photocard', price=None, **kw):
    from modules.client.models import CollectionItem
    item = CollectionItem(user_id=user.id, name=name, market_price=price, **kw)
    db.session.add(item); db.session.commit()
    return item


def test_create_item_minimal(db, make_user):
    from modules.client.collection_service import create_item
    u = make_user()
    ok, err, item = create_item(u, 'PC Jisoo')
    assert ok and item.id and item.source == 'manual'
    assert item.market_price is None and item.notes is None and item.is_public is True


def test_create_item_with_files_saves_and_marks_primary(db, make_user, app):
    from modules.client.collection_service import create_item
    u = make_user()
    ok, err, item = create_item(u, 'PC', market_price=Decimal('129.99'),
                                files=[_png_storage('a.png'), _png_storage('b.png')])
    assert ok and item.images_count == 2
    assert item.images[0].is_primary is True and item.images[1].is_primary is False
    assert item.images[0].sort_order == 0 and item.images[1].sort_order == 1
    for img in item.images:                                   # pliki fizycznie na dysku
        assert os.path.exists(os.path.join(app.root_path, 'static', img.path_original))
        assert os.path.exists(os.path.join(app.root_path, 'static', img.path_compressed))


def test_create_item_invalid_file_rolls_back(db, make_user):
    from modules.client.collection_service import create_item
    from modules.client.models import CollectionItem
    from werkzeug.datastructures import FileStorage
    u = make_user()
    bad = FileStorage(stream=io.BytesIO(b'not an image'), filename='evil.txt')
    ok, err, _ = create_item(u, 'PC', files=[bad])
    assert not ok and err['code'] == 'invalid_file'
    assert CollectionItem.query.filter_by(user_id=u.id).count() == 0   # all-or-nothing


def test_get_owned_item_masks_foreign(db, make_user):
    from modules.client.collection_service import get_owned_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    assert get_owned_item(u.id, item.id) is None
    assert get_owned_item(other.id, item.id).id == item.id


def test_list_items_search_and_sorts(db, make_user):
    from modules.client.collection_service import list_items
    u = make_user()
    a = _make_item(db, u, name='Album BP', price=Decimal('50'))
    b = _make_item(db, u, name='Photocard', price=None)
    c = _make_item(db, u, name='Album TXT', price=Decimal('80'))
    assert [i.id for i in list_items(u.id).items] == [c.id, b.id, a.id]       # newest
    assert [i.id for i in list_items(u.id, sort='oldest').items] == [a.id, b.id, c.id]
    assert [i.id for i in list_items(u.id, sort='name_asc').items] == [a.id, c.id, b.id]
    assert [i.id for i in list_items(u.id, sort='price_desc').items] == [c.id, a.id, b.id]  # NULL last
    assert [i.id for i in list_items(u.id, search='album').items] == [c.id, a.id]


def test_list_items_paginates_and_isolates_users(db, make_user):
    from modules.client.collection_service import list_items
    u, other = make_user(), make_user()
    for i in range(3):
        _make_item(db, u, name=f'I{i}')
    _make_item(db, other, name='Cudzy')
    page = list_items(u.id, page=1, per_page=2)
    assert page.total == 3 and len(page.items) == 2 and page.has_next is True


def test_update_item_partial_and_clears(db, make_user):
    from modules.client.collection_service import update_item
    u = make_user()
    item = _make_item(db, u, price=Decimal('10'), notes='stare')
    ok, err, it = update_item(u.id, item.id, {'name': 'Nowa', 'market_price': None})
    assert ok and it.name == 'Nowa' and it.market_price is None and it.notes == 'stare'
    ok2, err2, _ = update_item(u.id, item.id, {'name': ''})
    assert not ok2 and err2['code'] == 'name_required'


def test_update_item_foreign_not_found(db, make_user):
    from modules.client.collection_service import update_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    ok, err, _ = update_item(u.id, item.id, {'name': 'X'})
    assert not ok and err['code'] == 'not_found'


def test_delete_item_removes_files_and_row(db, make_user, app):
    from modules.client.collection_service import create_item, delete_item
    from modules.client.models import CollectionItem, CollectionItemImage
    u = make_user()
    _, _, item = create_item(u, 'PC', files=[_png_storage()])
    paths = [(i.path_original, i.path_compressed) for i in item.images]
    ok, _ = delete_item(u.id, item.id)
    assert ok and CollectionItem.query.get(item.id) is None
    assert CollectionItemImage.query.count() == 0             # cascade
    for orig, compr in paths:
        assert not os.path.exists(os.path.join(app.root_path, 'static', orig))
        assert not os.path.exists(os.path.join(app.root_path, 'static', compr))


def test_delete_item_foreign_not_found(db, make_user):
    from modules.client.collection_service import delete_item
    u, other = make_user(), make_user()
    item = _make_item(db, other)
    ok, err = delete_item(u.id, item.id)
    assert not ok and err['code'] == 'not_found'
```
> Plus **smoke webowych tras itemów** (fixtura `login`, `profile_completed=True` — bramka klienta):
```python
def test_web_collection_add_parity_smoke(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/collection/add', data={'name': 'PC', 'market_price': '12.50'},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert 'item_id' in r.get_json()


def test_web_collection_add_missing_name_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/collection/add', data={'name': ''},
                    content_type='multipart/form-data')
    assert r.status_code == 400 and 'Nazwa' in r.get_json()['message']


def test_web_collection_edit_and_delete_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    item = _make_item(db, u)
    r = client.post(f'/client/collection/{item.id}/edit',
                    data={'name': 'Po edycji', 'market_price': '', 'notes': ''},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert client.delete(f'/client/collection/{item.id}/delete').status_code == 200


def test_web_collection_foreign_403_parity(client, db, make_user, login):
    u, other = make_user(profile_completed=True), make_user()
    login(u)
    item = _make_item(db, other)
    r = client.post(f'/client/collection/{item.id}/edit', data={'name': 'X'},
                    content_type='multipart/form-data')
    assert r.status_code == 403                               # web: 403 (mobile zamaskuje 404)
```
> Run: `source venv/bin/activate && python -m pytest tests/test_collection_service.py -v` → FAIL (brak modułu).

- [ ] **Step 2: Implementacja serwisu (items)** — `modules/client/collection_service.py` (NOWY):
```python
"""Wspólny serwis kolekcji klienta — web (trasy collection.py) + mobilne API (E8).

Logika przeniesiona 1:1 z modules/client/collection.py. Serwis NIE importuje nic
z modules.api_mobile (brak cyklu). Funkcje zwracają (ok, err[, value]) — kanał serializuje.
Kwoty: serwis operuje na Decimal|None — parsowanie (float PLN w webie, grosze w mobile)
zostaje w kanałach. QR temp_uploads (web-only) wchodzą parametrem do create_item, żeby
webowy add zachował JEDEN commit.
"""

from extensions import db
from modules.client.models import CollectionItem, CollectionItemImage

MAX_IMAGES_PER_ITEM = 3
ALLOWED_SORTS = ('newest', 'oldest', 'name_asc', 'price_desc')


def get_owned_item(user_id, item_id):
    """Item usera albo None — cudze/nieistniejące traktowane identycznie (mobile maskuje 404)."""
    item = CollectionItem.query.get(item_id)
    if item is None or item.user_id != user_id:
        return None
    return item


def list_items(user_id, search=None, sort='newest', page=1, per_page=24):
    """Pagination obiekt. Parytet web collection_list (l. 36-55): ilike, 4 sorty, NULL-e
    cen na końcu przy price_desc."""
    query = CollectionItem.query.filter_by(user_id=user_id)
    if search:
        query = query.filter(CollectionItem.name.ilike(f'%{search}%'))
    if sort == 'oldest':
        query = query.order_by(CollectionItem.created_at.asc())
    elif sort == 'name_asc':
        query = query.order_by(CollectionItem.name.asc())
    elif sort == 'price_desc':
        query = query.order_by(
            db.case((CollectionItem.market_price.is_(None), 1), else_=0),
            CollectionItem.market_price.desc())
    else:  # newest (default)
        query = query.order_by(CollectionItem.created_at.desc())
    return query.paginate(page=page, per_page=per_page, error_out=False)


def create_item(user, name, market_price=None, notes=None, files=None, temp_uploads=None):
    """(ok, err, item). Item + max 3 zdjęć z `files` (FileStorage; pierwszy = primary)
    + opcjonalne rekordy QR temp_uploads (web). All-or-nothing przy błędzie pliku.
    Parytet web collection_add (l. 97-153)."""
    from utils.image_processor import process_collection_upload
    item = CollectionItem(user_id=user.id, name=name, market_price=market_price,
                          notes=notes or None, source='manual')
    db.session.add(item)
    db.session.flush()                                        # item.id
    try:
        for i, file in enumerate((files or [])[:MAX_IMAGES_PER_ITEM]):
            if file and file.filename:
                result = process_collection_upload(file, user.id)
                db.session.add(CollectionItemImage(
                    collection_item_id=item.id, filename=result['filename'],
                    path_original=result['path_original'],
                    path_compressed=result['path_compressed'],
                    is_primary=(i == 0), sort_order=i))
        for temp in (temp_uploads or []):                     # QR flow (web-only; parytet l. 132-144)
            if item.can_add_image:
                db.session.add(CollectionItemImage(
                    collection_item_id=item.id, filename=temp.filename,
                    path_original=temp.path_original,
                    path_compressed=temp.path_compressed,
                    is_primary=(item.images_count == 0),
                    sort_order=item.images_count))
                db.session.flush()
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        return False, {'code': 'invalid_file', 'message': str(e)}, None
    try:                                                      # achievement (parytet l. 149-153)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'collection_add')
    except Exception:
        pass
    return True, None, item


def update_item(user_id, item_id, fields):
    """(ok, err, item). `fields`: dict z kluczami spośród name/market_price/notes —
    obecny klucz nadpisuje (None czyści cenę/notatki; name puste → name_required).
    Web wysyła komplet pól → zachowanie identyczne; mobile robi PATCH częściowy."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    if 'name' in fields:
        if not fields['name']:
            return False, {'code': 'name_required'}, None
        item.name = fields['name']
    if 'market_price' in fields:
        item.market_price = fields['market_price']
    if 'notes' in fields:
        item.notes = fields['notes'] or None
    db.session.commit()
    return True, None, item


def delete_item(user_id, item_id):
    """(ok, err). Pliki zdjęć (best-effort) + wiersz (cascade images). Parytet web l. 246-252."""
    from utils.image_processor import delete_collection_image_files
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}
    for image in item.images:
        delete_collection_image_files(image.path_original, image.path_compressed)
    db.session.delete(item)
    db.session.commit()
    return True, None
```

- [ ] **Step 3: Refaktor webowych tras itemów** — `modules/client/collection.py`:
  - `collection_list()`: `pagination = collection_service.list_items(current_user.id,
    search=search or None, sort=sort, page=page, per_page=24)` — reszta (view, stats, template)
    BEZ zmian.
  - `collection_add()`: zachowaj parsowanie form (`name` puste → istniejące 400; `float(market_price)`
    w try/except ValueError → istniejące 400 str(e)); pobierz QR session jak dotychczas i przekaż
    `temp_uploads=qr_session.temp_uploads if qr_session else None`;
    `ok, err, item = create_item(current_user, name, market_price=..., notes=notes,
    files=request.files.getlist('images'), temp_uploads=...)`; `invalid_file` → 400
    `err['message']` (parytet: web zwracał str(e) z ValueError). Achievement przeniesiony do
    serwisu — USUŃ z trasy. Odpowiedź `{success, message: 'Przedmiot dodany do kolekcji',
    item_id: item.id}` BEZ zmian.
  - `collection_edit()` POST: ZACHOWAJ `get_or_404` + 403-guard (parytet 403!); potem
    `update_item(current_user.id, item_id, {'name': name, 'market_price': parsed, 'notes': notes})`;
    `name_required` → istniejące 400 „Nazwa jest wymagana". GET zostaje INLINE (D10).
  - `collection_delete()`: ZACHOWAJ `get_or_404` + 403-guard; potem
    `delete_item(current_user.id, item_id)`; odpowiedź BEZ zmian.
  > Zachowaj try/except + rollback w trasach (serwis commituje; rollback przy nieoczekiwanym
  > wyjątku zostaje). Kształty odpowiedzi/statusy BEZ ZMIAN (smoke-testy to pilnują).

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_collection_service.py -v` + pełny suite (0 regresji).
- [ ] **Step 5: Commit** — `git commit -m "refactor(collection): ekstrakcja serwisu itemów kolekcji (web parity + testy)"`

**DoD:** serwis itemów pokryty testami (w tym pliki na dysku + rollback all-or-nothing); webowe
trasy add/edit/delete wołają serwis bez zmiany zachowania (smoke green, w tym 403 dla cudzych);
pełny suite zielony. **Szacunek: +14 testów** (10 serwis + 4 smoke).

---

### Task 2: Mobilne trasy ITEMS — GET lista/detail, POST (@idempotent), PATCH, DELETE

**Files:** Create `modules/api_mobile/collection_routes.py`; modify `modules/api_mobile/__init__.py`;
Create `tests/test_mobile_api_collection.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_collection.py`:
```python
"""Testy E8: mobilne API kolekcji (items CRUD + zdjęcia + publiczna strona).

_auth jak w orders/payments. Multipart: BytesIO + content_type (wzorzec E6).
"""
import io
import os
import shutil
from decimal import Decimal

import pytest


@pytest.fixture(autouse=True)
def _cleanup_collections(app):
    base = os.path.join(app.root_path, 'static', 'uploads', 'collections')
    before = set(os.listdir(base)) if os.path.isdir(base) else set()
    yield
    if os.path.isdir(base):
        for d in set(os.listdir(base)) - before:
            shutil.rmtree(os.path.join(base, d), ignore_errors=True)


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    return {'Authorization': f'Bearer {r.get_json()["data"]["access_token"]}'}, u


def _tiny_png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf


def _make_item(db, user, name='Photocard', price=None, **kw):
    from modules.client.models import CollectionItem
    item = CollectionItem(user_id=user.id, name=name, market_price=price, **kw)
    db.session.add(item); db.session.commit()
    return item


# === Task 2: items CRUD ===

def test_items_requires_jwt(client, db):
    assert client.get('/api/mobile/v1/collection/items').status_code == 401


def test_items_list_pagination_grosze_and_isolation(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    _make_item(db, u, name='A', price=Decimal('129.99'))
    _make_item(db, u, name='B')
    _make_item(db, other, name='Cudzy')
    r = client.get('/api/mobile/v1/collection/items?per_page=1', headers=h)
    assert r.status_code == 200
    body = r.get_json()
    assert body['pagination'] == {'page': 1, 'per_page': 1, 'total': 2, 'has_next': True}
    row = body['data'][0]
    assert set(row) >= {'id', 'name', 'market_price', 'source', 'is_public',
                        'images_count', 'image_url', 'created_at'}
    assert row['image_url'].startswith('http')                # absolutny (placeholder)


def test_items_list_q_and_sort(client, db, make_user):
    h, u = _auth(client, db, make_user)
    a = _make_item(db, u, name='Album BP', price=Decimal('50'))
    _make_item(db, u, name='Photocard')
    c = _make_item(db, u, name='Album TXT', price=Decimal('80'))
    data = client.get('/api/mobile/v1/collection/items?q=album&sort=price_desc',
                      headers=h).get_json()['data']
    assert [r['id'] for r in data] == [c.id, a.id]
    assert data[0]['market_price'] == 8000                    # grosze


def test_items_list_bad_sort_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/collection/items?sort=cheapest', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_item_detail_shape(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u, price=Decimal('12.34'), notes='notka')
    r = client.get(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['market_price'] == 1234 and d['notes'] == 'notka'
    assert d['can_add_image'] is True and d['images'] == []


def test_item_detail_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    other = make_user()
    item = _make_item(db, other)
    r = client.get(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'item_not_found'


def test_create_item_multipart_with_images(client, db, make_user, app):
    h, u = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC Jisoo', 'market_price': '12999', 'notes': 'rzadka',
                          'images': [(_tiny_png(), 'a.png'), (_tiny_png(), 'b.png')]},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 201
    d = r.get_json()['data']
    assert d['market_price'] == 12999 and d['images_count'] == 2
    assert d['images'][0]['is_primary'] is True
    assert d['images'][0]['url'].startswith('http')
    # plik fizycznie na dysku
    from modules.client.models import CollectionItemImage
    img = CollectionItemImage.query.first()
    assert os.path.exists(os.path.join(app.root_path, 'static', img.path_compressed))


def test_create_item_missing_name_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items', data={'name': ''},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['field'] == 'name'


def test_create_item_too_many_images_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    files = [(_tiny_png(), f'{i}.png') for i in range(4)]
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'images': files},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    assert r.get_json()['error']['details']['max_images'] == 3


def test_create_item_invalid_file_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'images': [(io.BytesIO(b'nope'), 'x.txt')]},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_create_item_bad_price_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.post('/api/mobile/v1/collection/items',
                    data={'name': 'PC', 'market_price': 'abc'},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_create_item_idempotency_replay(client, db, make_user):
    from modules.client.models import CollectionItem
    h, u = _auth(client, db, make_user)
    hk = dict(h); hk['Idempotency-Key'] = 'e8-key-1'
    r1 = client.post('/api/mobile/v1/collection/items',
                     data={'name': 'PC', 'images': [(_tiny_png(), 'a.png')]},
                     content_type='multipart/form-data', headers=hk)
    r2 = client.post('/api/mobile/v1/collection/items',
                     data={'name': 'PC', 'images': [(_tiny_png(), 'a.png')]},
                     content_type='multipart/form-data', headers=hk)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.get_json() == r2.get_json()
    assert CollectionItem.query.filter_by(user_id=u.id).count() == 1   # bez duplikatu


def test_patch_item_partial(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u, name='Stara', price=Decimal('10.00'), notes='n')
    r = client.patch(f'/api/mobile/v1/collection/items/{item.id}',
                     data={'name': 'Nowa', 'market_price': ''},
                     content_type='multipart/form-data', headers=h)
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['name'] == 'Nowa' and d['market_price'] is None and d['notes'] == 'n'


def test_patch_item_foreign_404_and_empty_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    foreign = _make_item(db, other)
    r = client.patch(f'/api/mobile/v1/collection/items/{foreign.id}',
                     data={'name': 'X'}, content_type='multipart/form-data', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'item_not_found'
    mine = _make_item(db, u)
    r2 = client.patch(f'/api/mobile/v1/collection/items/{mine.id}', data={},
                      content_type='multipart/form-data', headers=h)
    assert r2.status_code == 400


def test_delete_item(client, db, make_user):
    from modules.client.models import CollectionItem
    h, u = _auth(client, db, make_user)
    item = _make_item(db, u)
    r = client.delete(f'/api/mobile/v1/collection/items/{item.id}', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['deleted'] is True
    assert CollectionItem.query.get(item.id) is None
    # powtórka / cudzy → 404
    assert client.delete(f'/api/mobile/v1/collection/items/{item.id}',
                         headers=h).status_code == 404
```
> Run → FAIL (brak tras).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/collection_routes.py` (NOWY):
```python
"""Trasy kolekcji klienta (CRUD + zdjęcia + publiczna strona) dla mobilnego API (E8)."""

from decimal import Decimal

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.auth.models import User
from modules.client import collection_service as svc
from . import api_mobile_bp
from .helpers import json_ok, json_err, json_page, to_grosze
from .validators import parse_int, ValidationError
from .idempotency import idempotent

MAX_IMAGE_SIZE = 10 * 1024 * 1024     # 10 MB per plik (D8 — hardening; web nie sprawdza)


def _abs(path):
    """Property modeli zwracają już '/static/...' — dokleja origin (URL absolutny)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_item_brief(item):
    return {
        'id': item.id,
        'name': item.name,
        'market_price': to_grosze(item.market_price),
        'source': item.source,
        'is_public': bool(item.is_public),
        'images_count': item.images_count,
        'image_url': _abs(item.image_url),                    # primary/produkt/placeholder
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_image(img, source='collection'):
    return {'id': img.id, 'url': _abs(f'/static/{img.path_compressed}'),
            'is_primary': bool(img.is_primary),
            'sort_order': img.sort_order if source == 'collection' else None,
            'source': source}


def _serialize_item_images(item):
    """Parytet web edit GET (l. 181-197): własne zdjęcia, fallback na zdjęcia produktu."""
    images = [_serialize_image(img) for img in item.images]
    if not images and item.product_id and item.product:
        images = [_serialize_image(img, source='product') for img in item.product.images]
    return images


def _serialize_item_detail(item):
    d = _serialize_item_brief(item)
    d.update({
        'notes': item.notes,
        'can_add_image': item.can_add_image,
        'images': _serialize_item_images(item),
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    })
    return d


def _market_price_from_form(form):
    """'market_price' w GROSZACH (string-int) -> Decimal PLN; ''/brak -> None (Korekta 2)."""
    grosze = parse_int(form.get('market_price'), 'market_price', min_value=0)
    if grosze is None:
        return None
    return Decimal(grosze) / 100


def _file_too_large(file):
    file.seek(0, 2); size = file.tell(); file.seek(0)
    return size > MAX_IMAGE_SIZE


@api_mobile_bp.route('/collection/items', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_items_list():
    user_id = int(get_jwt_identity())
    page = parse_int(request.args.get('page'), 'page', default=1, min_value=1)
    per_page = min(parse_int(request.args.get('per_page'), 'per_page',
                             default=20, min_value=1), 50)
    sort = (request.args.get('sort') or 'newest').strip()
    if sort not in svc.ALLOWED_SORTS:                         # zamknięty enum (D1(a) z E5)
        raise ValidationError(f'Nieznane sortowanie: {sort}.')
    q = (request.args.get('q') or '').strip() or None
    pagination = svc.list_items(user_id, search=q, sort=sort, page=page, per_page=per_page)
    return json_page([_serialize_item_brief(i) for i in pagination.items],
                     page=pagination.page, per_page=pagination.per_page,
                     total=pagination.total, has_next=pagination.has_next)


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_item_detail(item_id):
    item = svc.get_owned_item(int(get_jwt_identity()), item_id)
    if item is None:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok(_serialize_item_detail(item))


@api_mobile_bp.route('/collection/items', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")           # heavy-write (upload plików)
@idempotent('collection_item_create')     # D3: duplikat itemu + plików szkodliwy
def collection_item_create():
    name = (request.form.get('name') or '').strip()
    if not name:
        return json_err('invalid_input', 'Nazwa jest wymagana.', 400,
                        details={'field': 'name'})
    market_price = _market_price_from_form(request.form)      # ValidationError → 400
    notes = (request.form.get('notes') or '').strip()
    files = [f for f in request.files.getlist('images') if f and f.filename]
    if len(files) > svc.MAX_IMAGES_PER_ITEM:                  # D9: jawny błąd zamiast cichego capa
        return json_err('invalid_input', 'Maksymalnie 3 zdjęcia na przedmiot.', 400,
                        details={'max_images': svc.MAX_IMAGES_PER_ITEM})
    for f in files:
        if _file_too_large(f):
            return json_err('file_too_large', 'Maksymalny rozmiar zdjęcia to 10 MB.', 400)
    user = User.query.get(int(get_jwt_identity()))
    ok, err, item = svc.create_item(user, name, market_price=market_price,
                                    notes=notes, files=files)
    if not ok:
        return json_err('invalid_file', err.get('message', 'Nieprawidłowy plik.'), 400)
    return json_ok(_serialize_item_detail(item), 201)


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_update(item_id):
    """PATCH częściowy (Korekta 3): tylko pola obecne w form; zdjęcia mają osobne endpointy."""
    fields = {}
    if 'name' in request.form:
        fields['name'] = (request.form.get('name') or '').strip()
    if 'market_price' in request.form:
        fields['market_price'] = _market_price_from_form(request.form)
    if 'notes' in request.form:
        fields['notes'] = (request.form.get('notes') or '').strip()
    if not fields:
        return json_err('invalid_input', 'Brak pól do aktualizacji.', 400)
    ok, err, item = svc.update_item(int(get_jwt_identity()), item_id, fields)
    if not ok:
        if err['code'] == 'name_required':
            return json_err('invalid_input', 'Nazwa jest wymagana.', 400,
                            details={'field': 'name'})
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok(_serialize_item_detail(item))


@api_mobile_bp.route('/collection/items/<int:item_id>', methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_delete(item_id):
    ok, err = svc.delete_item(int(get_jwt_identity()), item_id)
    if not ok:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok({'deleted': True})
```
- [ ] **Step 3: Rejestracja** — `modules/api_mobile/__init__.py`, po `from . import shipping_routes`:
  `from . import collection_routes  # noqa: E402,F401`.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_collection.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): kolekcja — CRUD itemów (multipart, idempotent POST)"`

**DoD:** 5 tras itemów działa; grosze/ISO/absolutne URL-e; ownership maskowany 404; multipart POST
z plikami na dysku; idempotency replay (1 item po dwóch POST); PATCH częściowy.
**Szacunek: +15 testów.**

---

### Task 3: `collection_service.py` — IMAGES (ekstrakcja) + refaktor webowych tras zdjęć

**Files:** Modify `modules/client/collection_service.py`, `modules/client/collection.py`,
`tests/test_collection_service.py`

- [ ] **Step 1: Testy serwisu (RED)** — dopisz do `tests/test_collection_service.py`:
```python
def test_add_image_marks_first_primary_and_limits_to_3(db, make_user):
    from modules.client.collection_service import create_item, add_image
    u = make_user()
    _, _, item = create_item(u, 'PC')
    ok, _, img1 = add_image(u, item.id, _png_storage('1.png'))
    assert ok and img1.is_primary is True and img1.sort_order == 0
    add_image(u, item.id, _png_storage('2.png'))
    ok3, _, img3 = add_image(u, item.id, _png_storage('3.png'))
    assert ok3 and img3.is_primary is False and img3.sort_order == 2
    ok4, err4, _ = add_image(u, item.id, _png_storage('4.png'))
    assert not ok4 and err4['code'] == 'max_images'           # limit 3 (can_add_image)


def test_add_image_validations(db, make_user):
    from modules.client.collection_service import create_item, add_image
    from werkzeug.datastructures import FileStorage
    u, other = make_user(), make_user()
    _, _, item = create_item(u, 'PC')
    assert add_image(other, item.id, _png_storage())[1]['code'] == 'not_found'   # cudzy
    assert add_image(u, item.id, None)[1]['code'] == 'no_file'
    bad = FileStorage(stream=io.BytesIO(b'x'), filename='x.txt')
    assert add_image(u, item.id, bad)[1]['code'] == 'invalid_file'


def test_delete_image_reassigns_primary_and_removes_files(db, make_user, app):
    from modules.client.collection_service import create_item, add_image, delete_image
    u = make_user()
    _, _, item = create_item(u, 'PC')
    _, _, img1 = add_image(u, item.id, _png_storage('1.png'))     # primary
    _, _, img2 = add_image(u, item.id, _png_storage('2.png'))
    paths = (img1.path_original, img1.path_compressed)
    ok, _ = delete_image(u.id, item.id, img1.id)
    assert ok
    db.session.refresh(img2)
    assert img2.is_primary is True                            # reassignment
    assert not os.path.exists(os.path.join(app.root_path, 'static', paths[0]))
    assert not os.path.exists(os.path.join(app.root_path, 'static', paths[1]))


def test_delete_image_mismatched_item_not_found(db, make_user):
    from modules.client.collection_service import create_item, add_image, delete_image
    u = make_user()
    _, _, item_a = create_item(u, 'A')
    _, _, item_b = create_item(u, 'B')
    _, _, img = add_image(u, item_a.id, _png_storage())
    ok, err = delete_image(u.id, item_b.id, img.id)           # zdjęcie z INNEGO itemu
    assert not ok and err['code'] == 'not_found'


def test_set_primary_image(db, make_user):
    from modules.client.collection_service import create_item, add_image, set_primary_image
    u, other = make_user(), make_user()
    _, _, item = create_item(u, 'PC')
    _, _, img1 = add_image(u, item.id, _png_storage('1.png'))
    _, _, img2 = add_image(u, item.id, _png_storage('2.png'))
    ok, _, img = set_primary_image(u.id, item.id, img2.id)
    db.session.refresh(img1)
    assert ok and img.is_primary is True and img1.is_primary is False
    assert set_primary_image(other.id, item.id, img2.id)[1]['code'] == 'not_found'
```
> Plus smoke webowych tras zdjęć:
```python
def test_web_image_add_delete_primary_parity(client, db, make_user, login):
    from modules.client.collection_service import create_item, add_image
    u = make_user(profile_completed=True); login(u)
    _, _, item = create_item(u, 'PC')
    r = client.post(f'/client/collection/{item.id}/images',
                    data={'image': (_png_storage_raw(), 'a.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 200 and r.get_json()['image']['is_primary'] is True
    _, _, img2 = add_image(u, item.id, _png_storage('b.png'))
    assert client.post(
        f'/client/collection/{item.id}/images/{img2.id}/primary').status_code == 200
    assert client.delete(
        f'/client/collection/{item.id}/images/{img2.id}').status_code == 200


def test_web_image_add_over_limit_parity(client, db, make_user, login):
    from modules.client.collection_service import create_item, add_image
    u = make_user(profile_completed=True); login(u)
    _, _, item = create_item(u, 'PC')
    for i in range(3):
        add_image(u, item.id, _png_storage(f'{i}.png'))
    r = client.post(f'/client/collection/{item.id}/images',
                    data={'image': (_png_storage_raw(), 'x.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 400 and 'Maksymalnie 3' in r.get_json()['message']  # web: 400
```
> `_png_storage_raw()` = goły `BytesIO` PNG (test client sam opakowuje w FileStorage):
```python
def _png_storage_raw():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (0, 255, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf
```
> Run → FAIL.

- [ ] **Step 2: Implementacja serwisu (images)** — dopisz do `collection_service.py`:
```python
def add_image(user, item_id, file):
    """(ok, err, image). Limit 3 (can_add_image); pierwszy = primary; achievement.
    Parytet web collection_add_image (l. 272-313)."""
    from utils.image_processor import process_collection_upload
    item = get_owned_item(user.id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    if not item.can_add_image:
        return False, {'code': 'max_images'}, None
    if not file or not file.filename:
        return False, {'code': 'no_file'}, None
    try:
        result = process_collection_upload(file, user.id)
    except ValueError as e:
        return False, {'code': 'invalid_file', 'message': str(e)}, None
    image = CollectionItemImage(
        collection_item_id=item.id, filename=result['filename'],
        path_original=result['path_original'], path_compressed=result['path_compressed'],
        is_primary=(item.images_count == 0), sort_order=item.images_count)
    db.session.add(image)
    db.session.commit()
    try:                                                      # achievement (parytet l. 298-303)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'photo_upload')
    except Exception:
        pass
    return True, None, image


def _get_owned_image(user_id, item_id, image_id):
    """(item, image) — (None, None) gdy item cudzy/brak; (item, None) gdy zdjęcie nie
    należy do itemu (web: 404 — parytet l. 331-337)."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return None, None
    image = CollectionItemImage.query.get(image_id)
    if image is None or image.collection_item_id != item.id:
        return item, None
    return item, image


def delete_image(user_id, item_id, image_id):
    """(ok, err). Pliki + wiersz; primary przechodzi na pierwszy pozostały.
    Parytet web collection_delete_image (l. 339-350) — verbatim, łącznie z flush."""
    from utils.image_processor import delete_collection_image_files
    item, image = _get_owned_image(user_id, item_id, image_id)
    if item is None or image is None:
        return False, {'code': 'not_found'}
    was_primary = image.is_primary
    delete_collection_image_files(image.path_original, image.path_compressed)
    db.session.delete(image)
    db.session.flush()
    if was_primary and item.images:
        item.images[0].is_primary = True
    db.session.commit()
    return True, None


def set_primary_image(user_id, item_id, image_id):
    """(ok, err, image). Unset wszystkich → set wskazanego. Parytet web l. 377-384."""
    item, image = _get_owned_image(user_id, item_id, image_id)
    if item is None or image is None:
        return False, {'code': 'not_found'}, None
    for img in item.images:
        img.is_primary = False
    image.is_primary = True
    db.session.commit()
    return True, None, image
```

- [ ] **Step 3: Refaktor webowych tras zdjęć** — `modules/client/collection.py`:
  - `collection_add_image()`: ZACHOWAJ `get_or_404` + 403-guard; `ok, err, image =
    add_image(current_user, item_id, request.files.get('image'))`; mapuj na ISTNIEJĄCE komunikaty:
    `max_images` → 400 „Maksymalnie 3 zdjęcia na przedmiot"; `no_file` → 400 „Nie wybrano pliku";
    `invalid_file` → 400 `err['message']`. Achievement w serwisie — USUŃ z trasy. Odpowiedź
    `{success, message, image:{id, url, is_primary}}` BEZ zmian.
  - `collection_delete_image()` / `collection_set_primary_image()`: ZACHOWAJ guardy
    (`get_or_404` x2 + 403/404); wołaj `delete_image`/`set_primary_image`; odpowiedzi BEZ zmian.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_collection_service.py -v` + pełny suite.
- [ ] **Step 5: Commit** — `git commit -m "refactor(collection): ekstrakcja serwisu zdjęć kolekcji (limit 3, primary; web parity + testy)"`

**DoD:** serwis zdjęć pokryty (limit 3, primary reassignment, pliki na dysku, mismatch item/image);
3 webowe trasy wołają serwis bez zmiany zachowania; pełny suite zielony.
**Szacunek: +7 testów** (5 serwis + 2 smoke).

---

### Task 4: Mobilne trasy IMAGES — POST, DELETE, PATCH primary

**Files:** Modify `modules/api_mobile/collection_routes.py`, `tests/test_mobile_api_collection.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_collection.py`:
```python
# === Task 4: zdjęcia ===

def _make_item_with_images(db, user, n=1):
    from modules.client.collection_service import create_item, add_image
    _, _, item = create_item(user, 'PC')
    imgs = []
    for i in range(n):
        from werkzeug.datastructures import FileStorage
        from PIL import Image
        buf = io.BytesIO(); Image.new('RGB', (1, 1)).save(buf, 'PNG'); buf.seek(0)
        _, _, img = add_image(user, item.id,
                              FileStorage(stream=buf, filename=f'{i}.png'))
        imgs.append(img)
    return item, imgs


def test_add_image_201_first_primary(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (_tiny_png(), 'a.png')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 201
    img = r.get_json()['data']['image']
    assert img['is_primary'] is True and img['url'].startswith('http')


def test_add_image_max_3_409(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=3)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (_tiny_png(), 'd.png')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'max_images'


def test_add_image_no_file_400_and_foreign_404(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={}, content_type='multipart/form-data', headers=h)
    assert r.status_code == 400
    foreign_item = _make_item(db, other)
    r2 = client.post(f'/api/mobile/v1/collection/items/{foreign_item.id}/images',
                     data={'image': (_tiny_png(), 'a.png')},
                     content_type='multipart/form-data', headers=h)
    assert r2.status_code == 404 and r2.get_json()['error']['code'] == 'item_not_found'


def test_add_image_invalid_file_400(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, _ = _make_item_with_images(db, u, n=0)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/images',
                    data={'image': (io.BytesIO(b'x'), 'x.txt')},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_delete_image_reassigns_primary(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u, n=2)
    r = client.delete(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[0].id}', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['deleted'] is True
    d = client.get(f'/api/mobile/v1/collection/items/{item.id}',
                   headers=h).get_json()['data']
    assert len(d['images']) == 1 and d['images'][0]['is_primary'] is True


def test_delete_image_mismatch_404(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item_a, imgs = _make_item_with_images(db, u, n=1)
    item_b, _ = _make_item_with_images(db, u, n=0)
    r = client.delete(
        f'/api/mobile/v1/collection/items/{item_b.id}/images/{imgs[0].id}', headers=h)
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'image_not_found'


def test_set_primary_image_patch(client, db, make_user):
    h, u = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u, n=2)
    r = client.patch(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[1].id}/primary',
        headers=h)
    assert r.status_code == 200 and r.get_json()['data']['image']['is_primary'] is True
    d = client.get(f'/api/mobile/v1/collection/items/{item.id}',
                   headers=h).get_json()['data']
    flags = {i['id']: i['is_primary'] for i in d['images']}
    assert flags[imgs[1].id] is True and flags[imgs[0].id] is False


def test_set_primary_foreign_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    h2, u2 = _auth(client, db, make_user)
    item, imgs = _make_item_with_images(db, u2, n=1)
    r = client.patch(
        f'/api/mobile/v1/collection/items/{item.id}/images/{imgs[0].id}/primary',
        headers=h)
    assert r.status_code == 404
```
> Run → FAIL.

- [ ] **Step 2: Implementacja** — dopisz do `collection_routes.py`:
```python
@api_mobile_bp.route('/collection/items/<int:item_id>/images', methods=['POST'])
@jwt_required()
@limiter.limit("15 per minute")           # heavy-write (upload); D4: bez @idempotent
def collection_image_add(item_id):
    file = request.files.get('image')
    if file is None or file.filename == '':
        return json_err('invalid_input', 'Nie przesłano pliku (pole image).', 400)
    if _file_too_large(file):
        return json_err('file_too_large', 'Maksymalny rozmiar zdjęcia to 10 MB.', 400)
    user = User.query.get(int(get_jwt_identity()))
    ok, err, image = svc.add_image(user, item_id, file)
    if not ok:
        if err['code'] == 'not_found':
            return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
        if err['code'] == 'max_images':                       # Korekta 6: 409 (web: 400)
            return json_err('max_images', 'Maksymalnie 3 zdjęcia na przedmiot.', 409)
        return json_err('invalid_file', err.get('message', 'Nieprawidłowy plik.'), 400)
    return json_ok({'image': _serialize_image(image)}, 201)


@api_mobile_bp.route('/collection/items/<int:item_id>/images/<int:image_id>',
                     methods=['DELETE'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_image_delete(item_id, image_id):
    ok, err = svc.delete_image(int(get_jwt_identity()), item_id, image_id)
    if not ok:
        return json_err('image_not_found', 'Zdjęcie nie istnieje.', 404)
    return json_ok({'deleted': True})


@api_mobile_bp.route('/collection/items/<int:item_id>/images/<int:image_id>/primary',
                     methods=['PATCH'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_image_set_primary(item_id, image_id):
    ok, err, image = svc.set_primary_image(int(get_jwt_identity()), item_id, image_id)
    if not ok:
        return json_err('image_not_found', 'Zdjęcie nie istnieje.', 404)
    return json_ok({'image': _serialize_image(image)})
```
> Uwaga: maskowanie — cudzy ITEM przy add → `item_not_found`; przy delete/primary serwis zwraca
> jeden kod `not_found` (item cudzy LUB zdjęcie spoza itemu) → `image_not_found` (404; brak
> rozróżnienia = brak wycieku istnienia).

- [ ] **Step 3: GREEN** — `python -m pytest tests/test_mobile_api_collection.py -v`.
- [ ] **Step 4: Commit** — `git commit -m "feat(mobile-api): kolekcja — zdjęcia (add max 3, delete z primary-reassign, set primary)"`

**DoD:** 3 trasy zdjęć działają; limit 3 → 409; primary reassignment po delete; mismatch
item/image → 404; absolutne URL-e. **Szacunek: +8 testów.**

---

### Task 5: PUBLIC — serwis + refaktor weba + mobilne trasy (config GET/POST upsert, toggle-public)

**Files:** Modify `modules/client/collection_service.py`, `modules/client/collection.py`,
`modules/api_mobile/collection_routes.py`, `tests/test_collection_service.py`,
`tests/test_mobile_api_collection.py`

- [ ] **Step 1: Testy serwisu (RED)** — dopisz do `tests/test_collection_service.py`:
```python
def test_create_public_config_once(db, make_user):
    from modules.client.collection_service import create_public_config, get_public_config
    u = make_user()
    ok, _, config = create_public_config(u)
    assert ok and len(config.token) == 12
    assert config.show_prices is True and config.is_active is True
    ok2, err2, _ = create_public_config(u)
    assert not ok2 and err2['code'] == 'exists'               # parytet web 409
    assert get_public_config(u.id).id == config.id


def test_update_public_config(db, make_user):
    from modules.client.collection_service import create_public_config, update_public_config
    u, other = make_user(), make_user()
    create_public_config(u)
    ok, _, config = update_public_config(u.id, show_prices=False)
    assert ok and config.show_prices is False and config.is_active is True   # tylko podane
    ok2, _, config2 = update_public_config(u.id, is_active=False)
    assert ok2 and config2.is_active is False and config2.show_prices is False
    assert update_public_config(other.id)[1]['code'] == 'not_found'          # brak configu


def test_toggle_item_public(db, make_user):
    from modules.client.collection_service import toggle_item_public
    u, other = make_user(), make_user()
    item = _make_item(db, u)                                  # is_public default True
    ok, _, it = toggle_item_public(u.id, item.id)
    assert ok and it.is_public is False
    ok2, _, it2 = toggle_item_public(u.id, item.id)
    assert ok2 and it2.is_public is True
    assert toggle_item_public(other.id, item.id)[1]['code'] == 'not_found'
```
> Plus smoke: webowe trasy public + PUBLICZNA strona BEZ auth:
```python
def test_web_public_create_and_config_parity(client, db, make_user, login):
    u = make_user(profile_completed=True); login(u)
    r = client.post('/client/collection/public/create')
    assert r.status_code == 200 and r.get_json()['token']
    assert client.post('/client/collection/public/create').status_code == 409  # duplikat
    r2 = client.post('/client/collection/public/config', json={'show_prices': False})
    assert r2.status_code == 200 and r2.get_json()['success'] is True


def test_public_collection_page_no_auth(client, db, make_user):
    """Publiczna strona działa BEZ logowania; pokazuje tylko is_public; szanuje is_active."""
    from modules.client.collection_service import create_public_config, update_public_config
    u = make_user()
    _make_item(db, u, name='Widoczny')
    _make_item(db, u, name='Ukryty', is_public=False)
    _, _, config = create_public_config(u)
    r = client.get(f'/collection/{config.token}')             # BEZ auth
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Widoczny' in html and 'Ukryty' not in html
    update_public_config(u.id, is_active=False)
    r2 = client.get(f'/collection/{config.token}')
    assert r2.status_code == 200 and 'Widoczny' not in r2.get_data(as_text=True)  # inactive
    assert client.get('/collection/zlyTokenXYZ1').status_code == 404
```
- [ ] **Step 2: Testy mobilne (RED)** — dopisz do `tests/test_mobile_api_collection.py`:
```python
# === Task 5: publiczna strona ===

def test_public_config_get_not_exists(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/collection/public/config', headers=h)
    assert r.status_code == 200
    assert r.get_json()['data'] == {'exists': False, 'config': None}


def test_public_config_post_upsert_creates_then_updates(client, db, make_user):
    h, u = _auth(client, db, make_user)
    r1 = client.post('/api/mobile/v1/collection/public/config',
                     json={'show_prices': False}, headers=h)
    assert r1.status_code == 201
    d1 = r1.get_json()['data']
    assert d1['created'] is True and d1['config']['show_prices'] is False
    assert d1['config']['is_active'] is True
    assert d1['config']['public_url'].startswith('http')
    assert d1['config']['public_url'].endswith('/collection/' + d1['config']['token'])
    r2 = client.post('/api/mobile/v1/collection/public/config',
                     json={'is_active': False}, headers=h)
    assert r2.status_code == 200
    d2 = r2.get_json()['data']
    assert d2['created'] is False and d2['config']['is_active'] is False
    assert d2['config']['token'] == d1['config']['token']     # ten sam config
    g = client.get('/api/mobile/v1/collection/public/config', headers=h).get_json()['data']
    assert g['exists'] is True and g['config']['is_active'] is False


def test_toggle_public_flips_and_masks(client, db, make_user):
    h, u = _auth(client, db, make_user)
    other = make_user()
    item = _make_item(db, u)
    r = client.post(f'/api/mobile/v1/collection/items/{item.id}/toggle-public', headers=h)
    assert r.status_code == 200 and r.get_json()['data']['is_public'] is False
    r2 = client.post(f'/api/mobile/v1/collection/items/{item.id}/toggle-public', headers=h)
    assert r2.get_json()['data']['is_public'] is True
    foreign = _make_item(db, other)
    r3 = client.post(f'/api/mobile/v1/collection/items/{foreign.id}/toggle-public', headers=h)
    assert r3.status_code == 404 and r3.get_json()['error']['code'] == 'item_not_found'


def test_mobile_config_visible_on_public_web_page(client, db, make_user):
    """E2E: konfiguracja przez mobile → publiczna strona webowa odzwierciedla stan."""
    h, u = _auth(client, db, make_user)
    _make_item(db, u, name='Mobilny item')
    token = client.post('/api/mobile/v1/collection/public/config', json={},
                        headers=h).get_json()['data']['config']['token']
    r = client.get(f'/collection/{token}')                    # BEZ auth
    assert r.status_code == 200 and 'Mobilny item' in r.get_data(as_text=True)
```
> Run → FAIL.

- [ ] **Step 3: Implementacja serwisu (public)** — dopisz do `collection_service.py`:
```python
def get_public_config(user_id):
    from modules.client.models import PublicCollectionConfig
    return PublicCollectionConfig.query.filter_by(user_id=user_id).first()


def create_public_config(user):
    """(ok, err, config). Token + defaulty + achievement. Parytet web public/create
    (l. 405-425); 'exists' gdy już jest (web: 409)."""
    from modules.client.models import PublicCollectionConfig
    if get_public_config(user.id):
        return False, {'code': 'exists'}, None
    config = PublicCollectionConfig(user_id=user.id,
                                    token=PublicCollectionConfig.generate_token(),
                                    show_prices=True, is_active=True)
    db.session.add(config)
    db.session.commit()
    try:                                                      # achievement (parytet l. 421-425)
        from modules.achievements.services import AchievementService
        AchievementService().check_event(user, 'collection_public_toggle')
    except Exception:
        pass
    return True, None, config


def update_public_config(user_id, show_prices=None, is_active=None):
    """(ok, err, config). Tylko podane flagi. Parytet web public/config POST (l. 479-493)."""
    config = get_public_config(user_id)
    if config is None:
        return False, {'code': 'not_found'}, None
    if show_prices is not None:
        config.show_prices = bool(show_prices)
    if is_active is not None:
        config.is_active = bool(is_active)
    db.session.commit()
    return True, None, config


def toggle_item_public(user_id, item_id):
    """(ok, err, item). Parytet web toggle-public (l. 512-518)."""
    item = get_owned_item(user_id, item_id)
    if item is None:
        return False, {'code': 'not_found'}, None
    item.is_public = not item.is_public
    db.session.commit()
    return True, None, item
```
- [ ] **Step 4: Refaktor webowych tras public** — `modules/client/collection.py`:
  - `collection_public_create()`: `ok, err, config = create_public_config(current_user)`;
    `exists` → istniejące 409; sukces → `{success, message, token, url}` BEZ zmian. Achievement
    w serwisie — USUŃ z trasy.
  - `collection_public_config_update()`: `data = request.get_json()` (None-check BEZ zmian);
    `ok, err, _ = update_public_config(current_user.id,
    show_prices=data.get('show_prices') if 'show_prices' in data else None,
    is_active=data.get('is_active') if 'is_active' in data else None)`; `not_found` → istniejące
    404. UWAGA: web rozróżniał `'show_prices' in data` — zachowaj semantykę kluczy-obecnych
    (bool(False) jest legalną wartością!).
  - `collection_toggle_public()`: ZACHOWAJ `get_or_404` + 403-guard; potem
    `toggle_item_public(...)`; odpowiedź `{success, is_public}` BEZ zmian.
  - `collection_public_config_get()` (GET) i `collection_toggle_all_public()` zostają INLINE
    (czysta serializacja / web-only — D7, Korekta 12).
- [ ] **Step 5: Implementacja mobilna** — dopisz do `collection_routes.py`:
```python
def _serialize_public_config(config):
    return {
        'token': config.token,
        'show_prices': bool(config.show_prices),
        'is_active': bool(config.is_active),
        'public_url': request.url_root.rstrip('/') + f'/collection/{config.token}',
    }


@api_mobile_bp.route('/collection/public/config', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def collection_public_config_get():
    config = svc.get_public_config(int(get_jwt_identity()))
    if config is None:                                        # Korekta 7: stan, nie błąd
        return json_ok({'exists': False, 'config': None})
    return json_ok({'exists': True, 'config': _serialize_public_config(config)})


@api_mobile_bp.route('/collection/public/config', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_public_config_update():
    """UPSERT (D6): pierwszy POST tworzy config (token + achievement), każdy aplikuje flagi."""
    data = request.get_json(silent=True) or {}
    user = User.query.get(int(get_jwt_identity()))
    created = False
    if svc.get_public_config(user.id) is None:
        svc.create_public_config(user)
        created = True
    _, _, config = svc.update_public_config(
        user.id,
        show_prices=data.get('show_prices') if 'show_prices' in data else None,
        is_active=data.get('is_active') if 'is_active' in data else None)
    return json_ok({'created': created, 'config': _serialize_public_config(config)},
                   201 if created else 200)


@api_mobile_bp.route('/collection/items/<int:item_id>/toggle-public', methods=['POST'])
@jwt_required()
@limiter.limit("30 per minute")
def collection_item_toggle_public(item_id):
    ok, err, item = svc.toggle_item_public(int(get_jwt_identity()), item_id)
    if not ok:
        return json_err('item_not_found', 'Przedmiot nie istnieje.', 404)
    return json_ok({'id': item.id, 'is_public': bool(item.is_public)})
```
- [ ] **Step 6: GREEN** — oba pliki testów + pełny suite (0 regresji).
- [ ] **Step 7: Commit** — `git commit -m "feat(mobile-api): kolekcja — publiczna strona (config upsert, toggle-public)"`

**DoD:** GET/POST public/config (upsert z absolutnym `public_url`) + toggle-public działają;
publiczna strona webowa odzwierciedla mobilną konfigurację (test E2E bez auth); webowe trasy public
wołają serwis bez zmiany zachowania (create → 409, config POST → 404). **Szacunek: +9 testów**
(3 serwis + 2 smoke + 4 mobile).

---

### Task 6: Aktualizacja specu (korekty kontraktu E8) + finalny suite

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** W sekcji „Kolekcja — `/collection/` (bez QR)" (l. 299) dopisz notkę o korektach E8
  (analogicznie do notek E5/E6/E7): prefiks `/collection/`; `market_price` w GROSZACH w obie strony;
  czysty PATCH multipart, częściowy; ownership → 404 maskujące (`item_not_found`/`image_not_found`);
  POST items: >3 zdjęć → 400 + `details.max_images`, zły plik → 400 `invalid_file` (all-or-nothing),
  limit 10 MB/plik → 400 `file_too_large`, `@idempotent`; add image: limit → `409 max_images`;
  GET public/config: brak → `200 {exists:false}`; POST public/config = UPSERT (`201 created` przy
  pierwszym, absolutny `public_url`); `toggle-all` web-only poza kontraktem; zdjęcia przez publiczny
  `/static` (parytet publicznej strony — bez trasy JWT). W liście etapów (l. 404) oznacz
  **E8 jako ukończone**.
- [ ] **Step 2:** Pełny suite: `source venv/bin/activate && python -m pytest -q` → oczekiwane
  **363 + ~53 = ~416 passed**, zero regresji.
- [ ] **Step 3: Commit** — `git commit -m "docs(mobile-api): korekty kontraktu E8 (kolekcja)"`
  (spec jest w `/docs` → `git add -f`).

**DoD:** spec odzwierciedla zaimplementowany kontrakt E8; cały suite zielony.

---

## Podsumowanie szacunków

| Task | Zakres | Nowe testy |
|------|--------|-----------|
| 1 | Serwis itemów + refaktor web + smoke | +14 |
| 2 | Mobilne trasy itemów (CRUD, multipart, idempotent) | +15 |
| 3 | Serwis zdjęć + refaktor web + smoke | +7 |
| 4 | Mobilne trasy zdjęć | +8 |
| 5 | Public (serwis + web + mobile + E2E publiczna strona) | +9 |
| 6 | Spec + finalny suite | 0 |
| **Razem** | | **~53** |

**Baseline przed E8: `363 passed` (zweryfikowane 2026-06-13, ~62 s). Oczekiwane po E8: ~416 passed.
Migracje: ZERO (head `c72aad290158`).**
