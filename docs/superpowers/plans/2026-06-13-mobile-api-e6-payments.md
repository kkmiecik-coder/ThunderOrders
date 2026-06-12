# Mobile API — Etap E6 (Płatności: metody, lista potwierdzeń, upload dowodu) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended)
> or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`)
> syntax for tracking.

> **REWIZJA 2026-06-13:** Konrad rozstrzygnął D1–D4. **D2 = wariant NOWY (inny niż obie pierwotne
> opcje): upload ZBIORCZY jak web** — jeden plik dowodu może pokrywać dowolne kombinacje
> (wiele etapów jednego zamówienia, wiele zamówień, mieszanki). To unieważnia kontrakt ze specu
> (pojedyncza para `order_id × payment_stage`) i przywraca ekstrakcję WSPÓLNEGO SERWISU z webowego
> bulk-uploadu jako naturalny wzorzec (jak E2/E5). Wykonalność ekstrakcji ZWERYFIKOWANA w kodzie —
> patrz „Zweryfikowane fakty / Webowy bulk-upload" i werdykt w Architecture.

**Goal:** Domknięcie warstwy PŁATNOŚCI mobilnego API — pierwsze MUTACJE plików w tym API. Trzy
endpointy (kontrakt POST ZREWIDOWANY względem specu — patrz Korekta 2):

```
GET  /payment-methods                                     → dane do przelewu (aktywne metody)
GET  /payment-confirmations  ?tab=active|archive          → moje potwierdzenia (orders + etapy)
POST /payment-confirmations  (multipart: file + items [JSON-string par {order_id, payment_stage}]
                              + payment_method_id?)       → BULK upload dowodu (parytet z webem)
GET  /payment-confirmations/proof/<filename>              → dowód (JWT, tylko właściciel) [D1=a]
```

E5 zrobiło ODCZYT etapów płatności (`GET /orders/<id>` → `payment_stages[]`). E6 dodaje **AKCJE**:
listę metod przelewu, listę potwierdzeń (active/archive), **zbiorczy upload dowodu** (jeden plik
przelewu → wiele wierszy `PaymentConfirmation` współdzielących `proof_file`) i serwowanie dowodów
przez JWT. **Pełny parytet kanałów** — web i mobile robią TEN SAM kształt bulku; QR komputer↔telefon
pozostaje POZA zakresem (spec: telefon ma aparat natywnie).

**Architecture:** Pięć odkryć kształtuje plan:
1. **Walidacja i zapis pliku są już wydzielonymi helperami** (`modules/client/payment_confirmations.py`):
   `allowed_proof_file(filename)`, `save_payment_proof_file(file)` (UUID-prefix →
   `uploads/payment_confirmations/`), `MAX_PROOF_FILE_SIZE = 5MB`, integralność przez
   `utils/file_validation.validate_proof_file()` (PIL load / magic bytes `%PDF-`). Reużywane wprost.
2. **Logika „czy można wgrać dany etap" jest scentralizowana jako `@property` na `Order`**
   (`can_upload_product_payment`, `can_upload_stage_2/3/4`, `modules/orders/models.py:800–939`) —
   webowy bulk waliduje per parę przez te properties. Zero duplikacji reguł.
3. **Webowy bulk-upload ma CZYSTE punkty cięcia dla ekstrakcji serwisu** (werdykt z badania kodu):
   (a) walidacja bulku (ownership + can_upload per para) to logika BEZ efektów ubocznych;
   (b) pętla record + notify + OCR przyjmuje `saved_filename` jako wejście — więc działa identycznie
   dla webowego normal-uploadu, webowego QR-flow (plik już na serwerze) i mobilnego multipart.
   W trasach zostaje tylko: parsowanie formularza, obsługa pliku, mapowanie wyniku na odpowiedź.
   **Decyzja architektoniczna: PEŁNA EKSTRAKCJA serwisu** `payment_confirmation_service.py`
   (`validate_bulk_upload` + `record_bulk_payment_proofs`) + refaktor webowej trasy (bez zmiany
   zachowania). Wariant „wspólne klocki + mobilna trasa bulk" ODRZUCONY: skoro oba kanały robią ten
   sam kształt, lokalna replika pętli record+notify (~60 linii z batchowaniem per-order) byłaby
   dokładnie tym rozjazdem, którego wzorzec E2/E5 unika; a fixtura `login` w conftest umożliwia
   smoke-testy webowej trasy po refaktorze (dziś NIETESTOWANEJ), więc ryzyko refaktoru jest mitygowane.
4. **Pliki dowodów serwowane przez trasę chronioną SESJĄ** (`orders.serve_payment_proof`) — mobile
   z Bearer JWT jej nie pobierze → bliźniacza trasa JWT (D1=a).
5. **Lista active/archive (~80 linii) jest INLINE w webowej trasie i nietestowana** → ekstrakcja
   `get_confirmation_orders(user_id)` + parytet-test (D3=a).

**Tech Stack:** Flask, flask-jwt-extended (JWT, bez sesji/CSRF), SQLAlchemy, Flask-Migrate (Alembic —
**ZERO migracji w E6**, head pozostaje `c72aad290158`), pytest (sqlite in-memory), Flask-Limiter,
PIL/Pillow (już w zależnościach). Nowe pliki: `modules/api_mobile/payments_routes.py`,
`modules/client/payment_confirmation_service.py`. Koperty `{success,data}`/`{success,error{code,
message,details?}}`, kwoty w **groszach (int)**, zdjęcia/dowody jako **absolutne URL-e** — spójne z E0–E5.

**Multipart w testach Flask:** `client.post(url, data={'file': (BytesIO(b'...'), 'proof.png'),
'items': json.dumps([{'order_id': o.id, 'payment_stage': 'product'}])},
content_type='multipart/form-data', headers=h)`. Walidne obrazy przez PIL (1×1 PNG), PDF przez `%PDF-`.

---

## Zweryfikowane fakty (z badania kodu — NIE odkrywaj ponownie)

### Webowy BULK-upload (`modules/client/payment_confirmations.py::payment_confirmations_upload`, l. 182–509) — WZORZEC DO EKSTRAKCJI
**Kształt wejścia (form-data):**
- `order_stages` = **JSON-string** `[{order_id: int, stages: ['product', ...]}, ...]` (l. 208–220);
  stages filtrowane do `VALID_STAGES = {'product','korean_shipping','customs_vat','domestic_shipping'}`;
  wpisy bez `oid`/`stages` pomijane; błąd parsowania → błąd całości.
- Fallback: `order_ids` (CSV lub JSON lista) → domyślny etap `'product'` (l. 222–233). (Legacy —
  mobile NIE implementuje.)
- `proof_file` = plik LUB `qr_session_token` (plik już na serwerze z sesji QR, l. 239–249 — POZA
  zakresem mobile). `payment_method_id` opcjonalny int, **pass-through BEZ walidacji** (l. 339).

**Kolejność operacji (istotna dla parytetu):**
1. Parsowanie `order_stages` → 2. plik: obecność/rozszerzenie/rozmiar (BEZ zapisu, l. 251–271) →
3. **ownership bulk**: `Order.query.filter(Order.id.in_(all_ids), Order.user_id==current_user.id)`;
   `len(orders) != len(set(all_ids))` → **błąd CAŁOŚCI** „Nie masz uprawnień..." (l. 273–284) →
4. **can_upload per para** (l. 286–308): mapa stage→property (`product→can_upload_product_payment`,
   `korean_shipping→can_upload_stage_2`, `customs_vat→can_upload_stage_3`,
   `domestic_shipping→can_upload_stage_4`); **JAKAKOLWIEK para False → błąd CAŁOŚCI** z listą
   `order_numbers` (**all-or-nothing**; web NIE rozróżnia „etap nie istnieje strukturalnie" od
   „nie można teraz" — properties zwracają False w obu przypadkach) →
5. **zapis pliku RAZ** + integralność (`validate_proof_file`; fail → usuń plik + błąd, l. 310–336) →
6. **pętla record per (order × stage)** (l. 341–416) →
7. **JEDEN `db.session.commit()`** po całej pętli (l. 419) →
8. **OCR**: JEDEN background task dla CAŁEGO bulku (`total_expected` = SUMA kwot wszystkich par,
   `order_numbers` = wszystkie; tylko gdy `Settings['ocr_enabled']`; try/except, l. 421–461) →
9. **notify admin BATCHOWANE PER ORDER** (l. 463–481): jeden `EmailManager.notify_admin_payment_uploaded(
   order, stage_names)` + jeden `PushManager...` per zamówienie, `stage_names` = nazwy PL etapów tego
   zamówienia po przecinku; try/except per order →
10. odpowiedź AJAX: `{success: true, message, updated_stages: [{order_id, stage, status:'pending'}]}`.

**Pętla record (krok 6) — semantyka wierszy:**
- **Kwota per para** z `stage_amounts` zamówienia: `product→effective_total`,
  `korean_shipping→proxy_shipping_total`, `customs_vat→customs_vat_total`,
  `domestic_shipping→Decimal(str(shipping_cost)) or 0` (l. 351–358).
- `existing = PaymentConfirmation.query.filter_by(order_id, payment_stage).first()`:
  - `is_approved` → **`continue`** (defensywny skip — walidacja w kroku 4 normalnie już odrzuciła;
    osiągalne tylko przy wyścigu walidacja↔pętla; `created_count` NIE rośnie);
  - pending/rejected → **nadpis**: `proof_file, uploaded_at=now, status='pending',
    rejection_reason=None, amount, payment_method_id` (l. 366–376);
  - brak → **nowy rekord** `status='pending'` (l. 391–401).
- **JEDEN plik (`saved_filename`) współdzielony przez WSZYSTKIE wiersze bulku** (docstring modelu
  `PaymentConfirmation` l. 1483: „Jeden plik może być przypisany do wielu zamówień").
- `log_activity` **per para** (`payment_confirmation_uploaded` / `_reuploaded`; `entity_id=order.id`,
  `new_value={order_number, payment_stage, filename, amount(float)}`).

**⚠️ Asymetria pending (fakt parytetu — wynika z properties Order):**
`can_upload_product_payment` blokuje TYLKO `approved` → **E1 w stanie `pending` MOŻNA nadpisać**.
`can_upload_stage_2/3/4` blokują `approved` I `pending` → **para E2–E4 w stanie `pending` ODRZUCA
CAŁY bulk** (all-or-nothing). Mobile dziedziczy tę asymetrię 1:1 (patrz P2).

### Walidacja i zapis pliku — REUŻYWALNE helpery
- `ALLOWED_PROOF_EXTENSIONS = {'jpg','jpeg','png','pdf'}` (l. 26); `MAX_PROOF_FILE_SIZE = 5MB` (l. 27).
- `allowed_proof_file(filename)` — tylko ROZSZERZENIE. `save_payment_proof_file(file)` —
  `secure_filename` + `uuid4().hex_` prefix → `<repo>/uploads/payment_confirmations/`; zwraca nazwę
  lub None. Rozmiar liczy trasa (`seek/tell`). Integralność: `validate_proof_file` (PIL load /
  `%PDF-`); web przy fail USUWA plik.

### Serwowanie dowodów (`modules/orders/routes.py:4184–4211`)
- `orders.serve_payment_proof` (`/payment-proof/<filename>`, **`@login_required`** — SESJA): szuka
  `PaymentConfirmation.filter_by(proof_file=filename).first()` → 404; client tylko własne (403);
  `send_from_directory(<root>/uploads/payment_confirmations)`. `PaymentConfirmation.proof_url`
  (model l. 1567) buduje URL do TEJ sesyjnej trasy — **bezużyteczne dla JWT** → bliźniacza trasa (D1=a).

### Metody płatności (`modules/payments/models.py` — `PaymentMethod`)
- `get_active()` → `filter_by(is_active=True).order_by(sort_order, name)`. `to_dict()` → pola danych
  przelewu + `logo_light_url`/`logo_dark_url` **WZGLĘDNE** (`/static/uploads/payment_methods/...`
  lub None) — mobile absolutyzuje.

### Lista potwierdzeń (web `payment_confirmations()`, l. 68–179) — logika active/archive
- `tab` ∈ `{active, archive}` (default active). `archive_cutoff = get_local_now() - timedelta(days=3)`.
- Zbiór bazowy: zamówienia usera z `(offer_page_id IS NOT NULL OR order_type=='on_hand')` AND
  `(status IN ['oczekujace','dostarczone_proxy','w_drodze_polska','urzad_celny','dostarczone_gom',
  'spakowane'] OR (order_type IN ['pre_order','on_hand'] AND status=='nowe'))`, sort `created_at.desc()`.
- Filtr exclusive: tylko gdy brak `offer_page` LUB `offer_page.is_fully_closed`.
- Podział: statusy WSZYSTKICH obecnych etapów → wszystkie `approved` → `max(updated_at)` zatwierdzonych
  `< cutoff` → **archive**, inaczej **fully_paid_recent** (active); cokolwiek nie-approved → **orders**.
- `active_total = len(orders)+len(fully_paid_recent)`; `archive_count`. Web NIE paginuje.

### E5 — mobilne serializery (`modules/api_mobile/orders_routes.py`) — REUŻYWALNE
- `_serialize_order_brief(order)` (l. 23–35), `_serialize_payment_stages(order)` (l. 88–116; obecność
  etapu: `product`/`domestic_shipping` zawsze, `korean_shipping` gdy `payment_stages==4`, `customs_vat`
  gdy `≠on_hand`), `_stage_entry` (l. 74–85), `_STAGE_LABELS`, `to_grosze`, `_abs_image`,
  `_get_owned_order_or_404`. Importowalne do `payments_routes.py`.

### Wzorce mutacji / błędów mobilnego API (E2/E4)
- Dekoratory: `@route` → `@jwt_required()` → `@limiter.limit(...)`. Heavy-write: checkout `10/min`.
- Błędy przez `json_err(code, message, status)` + mapy kodów→status; `details` w kopercie błędu
  (wzorzec `_PLACE_ORDER_ERR_STATUS` + `payload['details']`, offers_routes l. 285–337).
- D4=(a): **BEZ `@idempotent`** (rozstrzygnięte — patrz Decyzje).

### Testy / fixtury / środowisko / migracje
- **Baseline: `281 passed`** (zweryfikowane 2026-06-13, ~46 s). TYLKO `python -m pytest`.
- **Głowa migracji: `c72aad290158`** (zweryfikowane `flask db heads`). **ZERO migracji w E6.**
- conftest: fixtura **`app` function-scoped** (`create_app('testing')` per test → świeży limiter per
  test; serie POSTów w jednym teście trzymać <10). Fixtury `make_user/make_product/make_order`
  (jak w E5). **Jest fixtura `login(client)`** (l. 94–101, sesja Flask-Login: `sess['_user_id']`) —
  umożliwia smoke-testy WEBOWYCH tras po refaktorze. **Brak JAKICHKOLWIEK testów webowych
  potwierdzeń** (zweryfikowane grep) — Task 3/5 dają pierwsze pokrycie.
- `EmailManager.notify_admin_payment_uploaded` (utils/email_manager.py:987) i
  `PushManager.notify_admin_payment_uploaded` (utils/push_manager.py:762) istnieją.
  `log_activity(user=, action=, entity_type=, entity_id=, old_value=, new_value=)` (utils/activity_logger.py:12).
- Helpery `_auth`/`_add_payment` kopiowane z `tests/test_mobile_api_orders.py`.
- `/docs` w `.gitignore` → commit planu przez `git add -f`.

---

## Korekty kontraktu względem specu (parytet z kodem + E1–E5 — zatwierdzane wraz z planem)

1. **Kwoty w groszach (int)**, **URL-e absolutne** (logo metod, `proof_url`), **daty ISO** — parytet E1–E5.
2. **`[D2]` POST /payment-confirmations jest ZBIORCZY** — spec mówił `file + order_id + payment_stage`
   (pojedyncza para); NOWY kontrakt: `file + items` (JSON-string listy par `{order_id, payment_stage}`)
   `+ payment_method_id?`. Jeden plik → wiele wierszy `PaymentConfirmation` współdzielących
   `proof_file` (pełny parytet z webowym bulkiem). Task 6 aktualizuje spec.
3. **Format pól multipart:** `items` = **JSON-string w polu formularza** (płaska lista par).
   Uzasadnienie: multipart/form-data nie ma natywnych struktur zagnieżdżonych; Flutter
   (`http`/`dio` MultipartRequest) wysyła pola jako stringi — `jsonEncode(items)` to standard.
   Płaskie pary (1 para = 1 zaznaczony checkbox etapu w UI) są naturalniejsze dla apki niż webowy
   kształt grupowany `{order_id, stages[]}`; serwer grupuje wewnętrznie. Duplikaty par —
   **dedupe server-side** (cicho). Cap **50 par** (web bez capu — higiena API; >50 → 400).
   Pole pliku = **`file`** (web: `proof_file`; mobile trzyma się krótkiej nazwy — spec).
4. **Cudze/nieistniejące zamówienie W BULKU → `404 order_not_found`** (web: 400 „Nie masz uprawnień")
   + `details.missing_order_ids` — maskowanie istnienia jak E5, **all-or-nothing** jak web.
5. **Rozróżnienie błędów etapu** (czytelniej niż webowe zbiorcze „nie można wgrać"):
   - stage spoza enuma w `items` → `400 invalid_input`;
   - para z etapem strukturalnie nieobecnym (np. `korean_shipping` dla on_hand) →
     `400 stage_not_applicable` + `details.failures[{order_id, order_number, payment_stage}]`;
   - para nie-uploadowalna teraz (approved; pending dla E2–E4; kwota 0; exclusive niezamknięty;
     E1 poza dozwolonym statusem) → `409 stage_not_uploadable` + `details.failures[...]`.
   Wszystko **all-or-nothing** (parytet — patrz P1). Klasyfikację robi serwis; web dalej skleja
   jeden komunikat (bez zmiany zachowania).
6. **Walidacja pliku jak web:** zły typ → `400 invalid_file`; >5 MB → `400 file_too_large`; brak →
   `400 invalid_input`; uszkodzony → `400 invalid_file` (+ usunięcie pliku); błąd zapisu DB →
   `500 database_error` (+ usunięcie pliku).
7. **`tab` listy = zamknięty enum** `{active, archive}` (default active); nieznany → `400 invalid_input`.
8. **Lista potwierdzeń = orders z etapami** (order-centrycznie jak web): brief + `payment_summary
   {total_to_pay, paid_amount, remaining_to_pay}` (grosze) + `all_approved` + `payment_stages[]`
   (serializer E5, z `proof_url`). Meta `active_total`/`archive_count`. Bez paginacji (parytet).
9. **Efekty uboczne uploadu zachowane w SERWISIE** (log_activity per para + notify admin per order
   + OCR-gdy-włączony) — jeden kod dla obu kanałów; admin widzi akcje z telefonu (wzorzec E3).

---

## Decyzje — ROZSTRZYGNIĘTE przez Konrada 2026-06-13

> **D1 = (a):** trasa JWT serwowania dowodów + `proof_url` (tylko właściciel zamówienia;
> cudze/brak → 404 maskujące).
>
> **D2 = WARIANT NOWY (inny niż pierwotne a/b):** mobilny upload **ZBIORCZY jak webowy** — jeden
> dowód pokrywa dowolne kombinacje (wiele etapów × wiele zamówień). Pełny parytet kanałów; kontrakt
> specu (pojedyncza para) unieważniony. Architektura: **ekstrakcja WSPÓLNEGO SERWISU** z webowego
> bulk-uploadu (`validate_bulk_upload` + `record_bulk_payment_proofs`) + refaktor webowej trasy —
> wykonalność ZWERYFIKOWANA (czyste punkty cięcia: walidacja bez efektów ubocznych; record przyjmuje
> `saved_filename`, więc obsługuje normal/QR/mobile bez rozgałęzień; fixtura `login` umożliwia
> smoke-testy weba po refaktorze). Wariant „wspólne klocki + mobilna trasa bulk" odrzucony —
> uzasadnienie w Architecture pkt 3.
>
> **D3 = (a):** wspólny serwis listy active/archive (`get_confirmation_orders`) + refaktor webowej
> trasy + parytet-testy (pierwsze pokrycie tej logiki).
>
> **D4 = (a):** BEZ `@idempotent` na uploadzie.

### Rozstrzygnięte-przez-PARYTET (semantyka bulku — web MA te przypadki i je rozstrzyga; NIE wymagają decyzji Konrada)

- **P1 — All-or-nothing.** Jakakolwiek para w bulku niewalidna (cudzy order, etap nieobecny,
  nie-uploadowalny) → **CAŁY bulk odrzucony** z details (web: błąd całości z listą order_numbers,
  l. 283–308). Brak częściowego sukcesu. Apka buduje selekcję z flag `can_upload` (E5/lista), więc
  odrzucenie = stale state → apka odświeża.
- **P2 — Asymetria pending (dziedziczona z properties Order).** E1 (`product`) w stanie `pending`
  można nadpisać nowym dowodem; E2–E4 w stanie `pending` blokują (cały bulk → 409). `approved`
  blokuje zawsze; jeśli wyścig dopuści approved do pętli — defensywny **skip** (parytet webowego
  `continue`, wiersz nietykany).
- **P3 — Retry bulku bez @idempotent (uzasadnienie D4=a).** Jedyność wierszy per (order×stage)
  wymusza logika `.first()` → double-submit NIGDY nie duplikuje wierszy. Retry po utracie odpowiedzi:
  bulk tylko-E1 → 200 (nadpis tym samym plikiem-bis); bulk z E2–E4 → 409 `stage_not_uploadable`
  z details (pary już `pending`) — apka traktuje to jako „już wgrane" i odświeża listę. Jedyny koszt
  double-submitu: drugi notify/OCR (best-effort) i osierocony plik (akceptowalne — web ma identyczną
  charakterystykę). `@idempotent` dokładałby pułapkę cache'owanego błędu 5xx (retry tym samym kluczem
  odtwarzałby błąd) — bez korzyści.

---

## File Structure

- `modules/client/payment_confirmation_service.py` — **NOWY (serce E6)**: `order_stage_keys(order)`
  (kanon obecności etapów), `validate_bulk_upload(user_id, order_stages)`,
  `record_bulk_payment_proofs(user, order_stages, saved_filename, payment_method_id)`,
  `get_confirmation_orders(user_id)`. Tasks 2, 3, 5.
- `modules/client/payment_confirmations.py` — Tasks 3, 5: refaktor tras webowych (upload + lista) by
  wołać serwis — BEZ zmiany zachowania (parsowanie/QR/plik/odpowiedzi zostają w trasie).
- `modules/api_mobile/payments_routes.py` — **NOWY**: `GET /payment-methods`,
  `GET /payment-confirmations/proof/<filename>`, `POST /payment-confirmations` (bulk),
  `GET /payment-confirmations`. Tasks 1, 2, 4, 5.
- `modules/api_mobile/__init__.py` — Task 1: `from . import payments_routes`.
- `modules/api_mobile/orders_routes.py` — Task 2: `_serialize_payment_stages` używa
  `order_stage_keys` z serwisu (kanon) + ADDYTYWNIE `proof_url` w `_stage_entry`.
- `tests/test_payment_confirmation_service.py` — **NOWY** (Tasks 3, 5): testy serwisu + smoke
  webowych tras (fixtura `login`).
- `tests/test_mobile_api_payments.py` — **NOWY** (Tasks 1, 2, 4, 5): testy tras mobilnych.
- `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md` — Task 6: korekty kontraktu E6 (bulk!).

---

### Task 1: `GET /payment-methods` — aktywne metody przelewu (absolutne logo URL-e)

**Files:** Create `modules/api_mobile/payments_routes.py`; modify `modules/api_mobile/__init__.py`;
Create `tests/test_mobile_api_payments.py`

- [ ] **Step 1: Testy (RED)** — `tests/test_mobile_api_payments.py` (nagłówek + helpery + testy metod):
```python
"""Testy E6: mobilne API płatności (metody, lista potwierdzeń, BULK upload dowodu).

_auth skopiowany z tests/test_mobile_api_orders.py. Multipart: BytesIO + content_type.
"""
import io
import json
from decimal import Decimal


def _auth(client, db, make_user):
    u = make_user()
    u.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': u.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    return {'Authorization': f'Bearer {token}'}, u


def _tiny_png():
    """Najmniejszy WALIDNY PNG (PIL load przejdzie) jako bajty."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (1, 1), (255, 0, 0)).save(buf, 'PNG')
    buf.seek(0)
    return buf


def _add_payment(db, order, stage, status='pending', amount=Decimal('20.00'),
                 proof_file='proof.jpg', updated_at=None):
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=amount, status=status, proof_file=proof_file)
    db.session.add(pc); db.session.commit()
    if updated_at is not None:
        pc.updated_at = updated_at
        db.session.commit()
    return pc


def _make_method(db, **kw):
    from modules.payments.models import PaymentMethod
    m = PaymentMethod(name=kw.pop('name', 'BLIK'), is_active=kw.pop('is_active', True),
                      sort_order=kw.pop('sort_order', 0), **kw)
    db.session.add(m); db.session.commit()
    return m


def test_payment_methods_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/payment-methods').status_code == 401


def test_payment_methods_shape_and_active_only(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_method(db, name='BLIK', account_number='500600700', sort_order=1)
    _make_method(db, name='Stara', is_active=False, sort_order=0)   # nieaktywna — pomijana
    r = client.get('/api/mobile/v1/payment-methods', headers=h)
    assert r.status_code == 200
    methods = r.get_json()['data']['methods']
    assert [m['name'] for m in methods] == ['BLIK']
    m = methods[0]
    assert set(m) >= {'id', 'name', 'recipient', 'account_number', 'account_number_label',
                      'code', 'code_label', 'transfer_title', 'additional_info', 'sort_order',
                      'logo_light_url', 'logo_dark_url'}


def test_payment_methods_absolute_logo_url(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    _make_method(db, name='Revolut', logo_light='rev.png')
    m = client.get('/api/mobile/v1/payment-methods', headers=h).get_json()['data']['methods'][0]
    assert m['logo_light_url'].startswith('http')
    assert m['logo_light_url'].endswith('/static/uploads/payment_methods/rev.png')
    assert m['logo_dark_url'] is None
```
> Run: `python -m pytest tests/test_mobile_api_payments.py -v` → FAIL (404/no route).

- [ ] **Step 2: Implementacja** — `modules/api_mobile/payments_routes.py` (NOWY):
```python
"""Trasy płatności (metody, potwierdzenia, BULK upload dowodu) dla mobilnego API (E6)."""

from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from modules.payments.models import PaymentMethod
from . import api_mobile_bp
from .helpers import json_ok, json_err, to_grosze


def _abs_static(path):
    """Względny URL '/static/...' -> absolutny (kontrakt: pełne URL-e)."""
    if not path:
        return None
    if path.startswith('http'):
        return path
    return request.url_root.rstrip('/') + path


def _serialize_payment_method(m):
    d = m.to_dict()
    return {
        'id': d['id'], 'name': d['name'], 'recipient': d['recipient'],
        'account_number': d['account_number'], 'account_number_label': d['account_number_label'],
        'code': d['code'], 'code_label': d['code_label'], 'transfer_title': d['transfer_title'],
        'additional_info': d['additional_info'], 'sort_order': d['sort_order'],
        'logo_light_url': _abs_static(d['logo_light_url']),
        'logo_dark_url': _abs_static(d['logo_dark_url']),
    }


@api_mobile_bp.route('/payment-methods', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def payment_methods():
    methods = PaymentMethod.get_active()
    return json_ok({'methods': [_serialize_payment_method(m) for m in methods]})
```

- [ ] **Step 3: Rejestracja** — `modules/api_mobile/__init__.py`, po `from . import orders_routes`:
  `from . import payments_routes  # noqa: E402,F401`.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_payments.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): metody płatności (GET /payment-methods)"`

---

### Task 2: `[D1=a]` Trasa JWT serwowania dowodów + `proof_url` + kanon `order_stage_keys` w serwisie

**Files:** Create `modules/client/payment_confirmation_service.py` (start — sam `order_stage_keys`);
modify `modules/api_mobile/payments_routes.py`, `modules/api_mobile/orders_routes.py`,
`tests/test_mobile_api_payments.py`, `tests/test_mobile_api_orders.py`

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_payments.py`:
```python
def test_proof_requires_jwt(client, db, make_user, make_order):
    u = make_user(); o = make_order(u)
    _add_payment(db, o, 'domestic_shipping', proof_file='abc.png')
    assert client.get('/api/mobile/v1/payment-confirmations/proof/abc.png').status_code == 401


def test_proof_owner_gets_file(client, db, make_user, make_order, app):
    import os
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', shipping_cost=Decimal('10.00'))
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    os.makedirs(folder, exist_ok=True)
    fname = 'e6test_owner.png'
    with open(os.path.join(folder, fname), 'wb') as f:
        f.write(_tiny_png().read())
    _add_payment(db, o, 'domestic_shipping', proof_file=fname)
    try:
        r = client.get(f'/api/mobile/v1/payment-confirmations/proof/{fname}', headers=h)
        assert r.status_code == 200
        assert r.data[:8] == b'\x89PNG\r\n\x1a\n'
    finally:
        os.remove(os.path.join(folder, fname))


def test_proof_other_user_404(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    other = make_user()
    o = make_order(other, order_type='on_hand', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'domestic_shipping', proof_file='secret.png')
    r = client.get('/api/mobile/v1/payment-confirmations/proof/secret.png', headers=h)
    assert r.status_code == 404                               # maskowanie istnienia


def test_proof_missing_404(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    assert client.get('/api/mobile/v1/payment-confirmations/proof/nope.png',
                      headers=h).status_code == 404
```

- [ ] **Step 2: Serwowanie + `_proof_url`** — dopisz do `modules/api_mobile/payments_routes.py`:
```python
import os
from flask import current_app, send_from_directory, url_for
from werkzeug.utils import secure_filename
from modules.orders.models import PaymentConfirmation


def _proof_url(filename):
    """Absolutny URL dowodu przez bliźniaczą trasę JWT (D1=a)."""
    if not filename:
        return None
    return request.url_root.rstrip('/') + url_for('api_mobile.serve_proof_mobile',
                                                   filename=filename)


@api_mobile_bp.route('/payment-confirmations/proof/<path:filename>', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def serve_proof_mobile(filename):
    filename = secure_filename(filename)                      # traversal-guard
    conf = PaymentConfirmation.query.filter_by(proof_file=filename).first()
    if conf is None or conf.order is None or conf.order.user_id != int(get_jwt_identity()):
        return json_err('not_found', 'Plik nie istnieje.', 404)
    folder = os.path.join(current_app.root_path, 'uploads', 'payment_confirmations')
    return send_from_directory(folder, filename)
```
> Parytet ścieżki z webowym `serve_payment_proof`. `secure_filename` chroni przed `../`.

- [ ] **Step 3: Kanon `order_stage_keys` w serwisie** — utwórz
  `modules/client/payment_confirmation_service.py`:
```python
"""Wspólny serwis potwierdzeń płatności — web (bulk upload, lista) + mobilne API (E6)."""


def order_stage_keys(order):
    """Zbiór etapów STRUKTURALNIE obecnych dla zamówienia (kanon: web + E5 + walidacja bulku)."""
    keys = {'product', 'domestic_shipping'}
    if order.payment_stages == 4:
        keys.add('korean_shipping')
    if order.order_type != 'on_hand':
        keys.add('customs_vat')
    return keys
```
  W `modules/api_mobile/orders_routes.py::_serialize_payment_stages` zamień warunki inline
  (`payment_stages == 4` / `order_type != 'on_hand'`) na `order_stage_keys(order)` (import na górze —
  serwis nie importuje nic z api_mobile, brak cyklu).

- [ ] **Step 4: ADDYTYWNY `proof_url` w etapach E5** — w `_stage_entry` (orders_routes):
```python
    from .payments_routes import _proof_url   # import LOKALNY (uniknięcie cyklu modułów)
    ...
    'has_proof': bool(conf.has_proof) if conf else False,
    'proof_url': _proof_url(conf.proof_file) if (conf and conf.proof_file) else None,  # [D1=a]
    'rejection_reason': conf.rejection_reason if conf else None,
```
  Dopisz test w `tests/test_mobile_api_orders.py`: etap z `proof_file` ma `proof_url` zaczynające się
  `http` i kończące nazwą pliku; etap bez dowodu → `proof_url is None`.

- [ ] **Step 5: GREEN** — `python -m pytest tests/test_mobile_api_payments.py
  tests/test_mobile_api_orders.py -v`.
- [ ] **Step 6: Commit** — `git commit -m "feat(mobile-api): serwowanie dowodów płatności (JWT) + proof_url"`

---

### Task 3: Ekstrakcja serwisu BULK-uploadu z webowej trasy `[D2 — SERCE E6]`

**Files:** Modify `modules/client/payment_confirmation_service.py`,
`modules/client/payment_confirmations.py`; Create `tests/test_payment_confirmation_service.py`

> Czysty refaktor + pierwsze pokrycie testowe: webowa trasa zachowuje IDENTYCZNE zachowanie
> (komunikaty, all-or-nothing, batchowanie notify, QR-flow). Mobile podłączy się w Task 4.

- [ ] **Step 1: Testy serwisu (RED)** — `tests/test_payment_confirmation_service.py`:
```python
"""Testy serwisu bulk-uploadu potwierdzeń (ekstrakcja z webowej trasy — parytet)."""
from decimal import Decimal


def _stages(*pairs):
    """[(order, [stages])] -> kształt order_stages serwisu."""
    return [{'order_id': o.id, 'stages': list(st)} for o, st in pairs]


def test_validate_ok_multi_order(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('5.00'))
    ok, err = validate_bulk_upload(u.id, _stages((o1, ['product', 'domestic_shipping']),
                                                 (o2, ['product'])))
    assert ok and err is None


def test_validate_foreign_order_fails_whole_bulk(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u, other = make_user(), make_user()
    mine = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    foreign = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    ok, err = validate_bulk_upload(u.id, _stages((mine, ['product']), (foreign, ['product'])))
    assert not ok and err['code'] == 'orders_not_found'
    assert foreign.id in err['missing_order_ids']            # all-or-nothing (P1)


def test_validate_classifies_not_applicable(db, make_user, make_order):
    # on_hand nie ma E2/E3 → klasyfikacja strukturalna (web tego nie rozróżnia — mobile tak)
    from modules.client.payment_confirmation_service import validate_bulk_upload
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    ok, err = validate_bulk_upload(u.id, _stages((o, ['korean_shipping'])))
    assert not ok and err['code'] == 'stage_not_applicable'
    assert err['failures'][0]['payment_stage'] == 'korean_shipping'


def test_validate_pending_asymmetry(db, make_user, make_order):
    # P2: E1 pending PRZECHODZI (nadpis dozwolony); E4 pending ODRZUCA bulk
    from modules.client.payment_confirmation_service import validate_bulk_upload
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='pending')
    ok, _ = validate_bulk_upload(u.id, _stages((o, ['product'])))
    assert ok                                                 # E1 pending → wolno
    _add_payment(db, o, 'domestic_shipping', status='pending')
    ok2, err2 = validate_bulk_upload(u.id, _stages((o, ['product', 'domestic_shipping'])))
    assert not ok2 and err2['code'] == 'stage_not_uploadable'  # E4 pending → cały bulk pada


def test_validate_approved_rejects(db, make_user, make_order):
    from modules.client.payment_confirmation_service import validate_bulk_upload
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    ok, err = validate_bulk_upload(u.id, _stages((o, ['product'])))
    assert not ok and err['code'] == 'stage_not_uploadable'


def test_record_creates_rows_sharing_file(db, make_user, make_order, make_product):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from modules.orders.models import PaymentConfirmation, OrderItem
    u = make_user()
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('5.00'))
    p = make_product(sale_price=Decimal('50.00'))
    it = OrderItem(order_id=o1.id, product_id=p.id, quantity=1,
                   price=Decimal('50.00'), total=Decimal('50.00'))
    db.session.add(it); db.session.commit()
    entries = record_bulk_payment_proofs(u, _stages((o1, ['product', 'domestic_shipping']),
                                                    (o2, ['domestic_shipping'])),
                                         'shared_file.png', None)
    assert len(entries) == 3
    rows = PaymentConfirmation.query.all()
    assert {r.proof_file for r in rows} == {'shared_file.png'}   # JEDEN plik, wiele wierszy
    assert all(r.status == 'pending' for r in rows)
    by = {(r.order_id, r.payment_stage): r for r in rows}
    assert by[(o1.id, 'product')].amount == Decimal('50.00')      # effective_total
    assert by[(o1.id, 'domestic_shipping')].amount == Decimal('10.00')
    assert by[(o2.id, 'domestic_shipping')].amount == Decimal('5.00')


def test_record_overwrites_rejected_and_skips_approved(db, make_user, make_order):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    rej = _add_payment(db, o, 'domestic_shipping', status='rejected', proof_file='old.png')
    rej.rejection_reason = 'Nieczytelne'; db.session.commit()
    appr = _add_payment(db, o, 'product', status='approved', proof_file='done.png')
    entries = record_bulk_payment_proofs(u, _stages((o, ['product', 'domestic_shipping'])),
                                         'fresh.png', None)
    db.session.refresh(rej); db.session.refresh(appr)
    assert rej.status == 'pending' and rej.proof_file == 'fresh.png'
    assert rej.rejection_reason is None
    assert appr.status == 'approved' and appr.proof_file == 'done.png'   # P2: skip approved
    assert len(entries) == 1                                  # tylko nadpis liczony (parytet continue)


def test_record_logs_activity_per_pair(db, make_user, make_order):
    from modules.client.payment_confirmation_service import record_bulk_payment_proofs
    from modules.auth.models import ActivityLog               # ścieżkę potwierdzić przy implementacji
    u = make_user()
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    record_bulk_payment_proofs(u, _stages((o, ['product', 'domestic_shipping'])), 'f.png', None)
    actions = [a.action for a in ActivityLog.query.all()]
    assert actions.count('payment_confirmation_uploaded') == 2
```
> Plus **smoke webowej trasy po refaktorze** (fixtura `login` z conftest — pierwsze testy weba):
```python
def test_web_upload_route_parity_smoke(client, db, make_user, make_order, login):
    import io, json
    from PIL import Image
    u = make_user()
    login(u)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    buf = io.BytesIO(); Image.new('RGB', (1, 1)).save(buf, 'PNG'); buf.seek(0)
    r = client.post('/client/payment-confirmations/upload',
                    data={'order_stages': json.dumps([{'order_id': o.id,
                                                       'stages': ['domestic_shipping']}]),
                          'proof_file': (buf, 'p.png')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 200 and r.get_json()['success'] is True
    assert r.get_json()['updated_stages'] == [
        {'order_id': o.id, 'stage': 'domestic_shipping', 'status': 'pending'}]


def test_web_upload_route_rejects_foreign(client, db, make_user, make_order, login):
    import io, json
    u, other = make_user(), make_user()
    login(u)
    o = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = client.post('/client/payment-confirmations/upload',
                    data={'order_stages': json.dumps([{'order_id': o.id, 'stages': ['product']}]),
                          'proof_file': (io.BytesIO(b'x'), 'p.png')},
                    content_type='multipart/form-data',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400 and r.get_json()['success'] is False    # zachowanie weba BEZ zmian
```
> Prefiks URL webowej trasy potwierdzić przy implementacji (`client_bp` url_prefix — prawdopodobnie
> `/client`). Ścieżkę modelu `ActivityLog` potwierdzić (utils/activity_logger importuje skądś).

- [ ] **Step 2: Implementacja serwisu** — dopisz do `payment_confirmation_service.py`:
```python
from decimal import Decimal

from extensions import db
from modules.orders.models import Order, PaymentConfirmation, get_local_now
from utils.activity_logger import log_activity

VALID_STAGES = {'product', 'korean_shipping', 'customs_vat', 'domestic_shipping'}
_CAN_UPLOAD = {
    'product': 'can_upload_product_payment',
    'korean_shipping': 'can_upload_stage_2',
    'customs_vat': 'can_upload_stage_3',
    'domestic_shipping': 'can_upload_stage_4',
}
_STAGE_NAMES_PL = {
    'product': 'Płatność za produkt', 'korean_shipping': 'Wysyłka z Korei',
    'customs_vat': 'Cło i VAT', 'domestic_shipping': 'Wysyłka krajowa',
}


def stage_amount(order, stage):
    """Autorytatywna kwota etapu (przeniesione 1:1 z webowej pętli, l. 351-358)."""
    return {
        'product': order.effective_total,
        'korean_shipping': order.proxy_shipping_total,
        'customs_vat': order.customs_vat_total,
        'domestic_shipping': (Decimal(str(order.shipping_cost))
                              if order.shipping_cost else Decimal('0.00')),
    }[stage]


def validate_bulk_upload(user_id, order_stages):
    """Walidacja bulku ALL-OR-NOTHING (parytet web l. 273-308) + klasyfikacja błędów dla mobile.

    order_stages: [{'order_id': int, 'stages': [str]}] (stages już przefiltrowane do VALID_STAGES).
    Zwraca (True, None) lub (False, {'code', ...details}):
      orders_not_found        — brakujące/cudze id (missing_order_ids)
      stage_not_applicable    — etap strukturalnie nieobecny (failures[])
      stage_not_uploadable    — can_upload False mimo obecności (failures[])
    Web skleja oba ostatnie w jeden komunikat (parytet zachowany w trasie webowej).
    """
    all_ids = [e['order_id'] for e in order_stages]
    orders = Order.query.filter(Order.id.in_(all_ids), Order.user_id == user_id).all()
    orders_by_id = {o.id: o for o in orders}
    missing = sorted(set(all_ids) - set(orders_by_id))
    if missing:
        return False, {'code': 'orders_not_found', 'missing_order_ids': missing}

    not_applicable, not_uploadable = [], []
    for entry in order_stages:
        order = orders_by_id[entry['order_id']]
        present = order_stage_keys(order)
        for stage in entry['stages']:
            fail = {'order_id': order.id, 'order_number': order.order_number,
                    'payment_stage': stage}
            if stage not in present:
                not_applicable.append(fail)
            elif not getattr(order, _CAN_UPLOAD[stage]):
                not_uploadable.append(fail)
    if not_applicable:
        return False, {'code': 'stage_not_applicable', 'failures': not_applicable}
    if not_uploadable:
        return False, {'code': 'stage_not_uploadable', 'failures': not_uploadable}
    return True, None


def record_bulk_payment_proofs(user, order_stages, saved_filename, payment_method_id):
    """Pętla record + commit + OCR + notify (przeniesione 1:1 z webowej trasy l. 341-481).

    Zakłada wcześniejszą walidację (validate_bulk_upload); approved → defensywny skip (P2).
    Jeden saved_filename współdzielony przez wszystkie wiersze. Zwraca listę utworzonych/
    nadpisanych wpisów: [{'confirmation': pc, 'order': order, 'stage': str, 'action': str}].
    """
    now = get_local_now()
    all_ids = [e['order_id'] for e in order_stages]
    orders_by_id = {o.id: o for o in Order.query.filter(
        Order.id.in_(all_ids), Order.user_id == user.id).all()}
    entries = []
    for entry in order_stages:
        order = orders_by_id.get(entry['order_id'])
        if not order:
            continue
        for stage in entry['stages']:
            amount = stage_amount(order, stage)
            existing = PaymentConfirmation.query.filter_by(
                order_id=order.id, payment_stage=stage).first()
            if existing and existing.is_approved:
                continue                                     # parytet: defensywny skip (P2)
            if existing:
                existing.proof_file = saved_filename
                existing.uploaded_at = now
                existing.status = 'pending'
                existing.rejection_reason = None
                existing.amount = amount
                existing.payment_method_id = payment_method_id
                pc, action = existing, 'payment_confirmation_reuploaded'
            else:
                pc = PaymentConfirmation(order_id=order.id, payment_stage=stage, amount=amount,
                                         proof_file=saved_filename, uploaded_at=now,
                                         status='pending', payment_method_id=payment_method_id)
                db.session.add(pc)
                action = 'payment_confirmation_uploaded'
            log_activity(user=user, action=action, entity_type='order', entity_id=order.id,
                         new_value={'order_number': order.order_number, 'payment_stage': stage,
                                    'filename': saved_filename, 'amount': float(amount)})
            entries.append({'confirmation': pc, 'order': order, 'stage': stage, 'action': action})
    db.session.commit()
    _submit_ocr(user, entries, saved_filename, payment_method_id)
    _notify_admins(entries)
    return entries


def _submit_ocr(user, entries, saved_filename, payment_method_id):
    """JEDEN task OCR dla całego bulku (parytet l. 421-461; tylko gdy ocr_enabled)."""
    from flask import current_app
    try:
        from modules.auth.models import Settings
        if not Settings.get_value('ocr_enabled', False):
            return
        total = sum((Decimal(str(e['confirmation'].amount)) for e in entries), Decimal('0.00'))
        from extensions import executor
        from utils.ocr_background import process_ocr_verification
        executor.submit(process_ocr_verification, {
            'saved_filename': saved_filename, 'payment_method_id': payment_method_id,
            'user_id': user.id,
            'order_numbers': sorted({e['order'].order_number for e in entries}),
            'total_expected': float(total)})
    except Exception as e:
        current_app.logger.error(f'Error submitting OCR background task: {e}')


def _notify_admins(entries):
    """Notify BATCHOWANE PER ORDER (parytet l. 463-481): 1 email + 1 push per zamówienie."""
    from flask import current_app
    by_order = {}
    for e in entries:
        by_order.setdefault(e['order'].id, {'order': e['order'], 'stages': []})
        by_order[e['order'].id]['stages'].append(e['stage'])
    for group in by_order.values():
        stage_names = ', '.join(_STAGE_NAMES_PL.get(s, s) for s in group['stages'])
        try:
            from utils.email_manager import EmailManager
            from utils.push_manager import PushManager
            EmailManager.notify_admin_payment_uploaded(group['order'], stage_names)
            PushManager.notify_admin_payment_uploaded(group['order'], stage_names)
        except Exception as e:
            current_app.logger.error(f'Błąd powiadomienia admina o płatności: {e}')
```
> **Różnica vs web (świadoma, bez zmiany zachowania weba):** web liczy `created_count` także dla
> nadpisów i NIE liczy skipów approved — `entries` serwisu odzwierciedla to samo (skip approved →
> brak wpisu). Web buduje `updated_stages` z wejściowych par — po refaktorze buduje z `entries`
> (różnica TYLKO przy wyścigu approved; akceptowalna — dokładniejsza odpowiedź).
> **Notify per order:** web wysyła notify dla KAŻDEGO order z wejścia (nawet gdy wszystkie jego pary
> były skipnięte jako approved — przypadek wyścigowy); serwis batchuje z `entries` (tylko faktycznie
> zapisane) — różnica wyłącznie w przypadku wyścigowym, akceptowalna (dokładniejsze powiadomienia).

- [ ] **Step 3: Refaktor webowej trasy** — `payment_confirmations_upload()`:
  - l. 273–308 (ownership + can_upload) → `ok, err = validate_bulk_upload(current_user.id, order_stages)`;
    mapowanie na ISTNIEJĄCE komunikaty: `orders_not_found` → „Nie masz uprawnień do wybranych
    zamówień."; `stage_not_applicable`/`stage_not_uploadable` → „Nie można wgrać potwierdzenia dla
    zamówień: {numery z failures}" (sklejone, parytet);
  - l. 341–481 (pętla + commit + OCR + notify) → `entries = record_bulk_payment_proofs(current_user,
    order_stages, saved_filename, payment_method_id)`;
  - `updated_stages`/`created_count` budowane z `entries`. Parsowanie, fallback `order_ids`, QR-flow,
    zapis/walidacja pliku i odpowiedzi flash/AJAX — BEZ ZMIAN w trasie.
- [ ] **Step 4: GREEN** — `python -m pytest tests/test_payment_confirmation_service.py -v` +
  pełny suite (zero regresji).
- [ ] **Step 5: Commit** — `git commit -m "refactor(payments): ekstrakcja serwisu bulk-uploadu potwierdzeń (web parity + testy)"`

---

### Task 4: `POST /payment-confirmations` — mobilny BULK upload (multipart) `[D2 nowy, D4=a]`

**Files:** Modify `modules/api_mobile/payments_routes.py`, `tests/test_mobile_api_payments.py`

**Kontrakt multipart (form-data):**
- `file` — plik dowodu (jpg/jpeg/png/pdf, max 5 MB);
- `items` — **JSON-string**: `[{"order_id": 12, "payment_stage": "product"}, ...]` (płaskie pary;
  duplikaty dedupowane; max 50; serwer grupuje do kształtu webowego);
- `payment_method_id` — opcjonalny int (pass-through jak web).

**Kontrakt odpowiedzi (200):**
```json
{ "success": true, "data": {
    "confirmations": [ { "confirmation_id": 7, "order_id": 12, "order_number": "PO/00000012",
                         "payment_stage": "product", "status": "pending", "amount": 5000,
                         "action": "created" } ],
    "count": 1,
    "proof_url": "https://.../api/mobile/v1/payment-confirmations/proof/<uuid>_p.png" } }
```
(`proof_url` RAZ na poziomie `data` — jeden plik współdzielony przez wszystkie wiersze;
`action` ∈ `created|overwritten`.)

- [ ] **Step 1: Testy (RED)** — dopisz do `tests/test_mobile_api_payments.py`:
```python
def _post_proof(client, headers, items, fileobj=None, filename='proof.png', method_id=None,
                raw_items=None):
    data = {'items': raw_items if raw_items is not None else json.dumps(items),
            'file': (fileobj or _tiny_png(), filename)}
    if method_id is not None:
        data['payment_method_id'] = str(method_id)
    return client.post('/api/mobile/v1/payment-confirmations', data=data,
                       content_type='multipart/form-data', headers=headers)


def _pair(order, stage):
    return {'order_id': order.id, 'payment_stage': stage}


def test_upload_requires_jwt(client, db, make_user, make_order):
    u = make_user(); o = make_order(u, order_type='on_hand', shipping_cost=Decimal('10.00'))
    r = client.post('/api/mobile/v1/payment-confirmations',
                    data={'items': json.dumps([_pair(o, 'domestic_shipping')]),
                          'file': (_tiny_png(), 'p.png')},
                    content_type='multipart/form-data')
    assert r.status_code == 401


def test_upload_happy_single_pair(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('15.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['count'] == 1
    c = d['confirmations'][0]
    assert c['order_id'] == o.id and c['payment_stage'] == 'domestic_shipping'
    assert c['status'] == 'pending' and c['amount'] == 1500 and c['action'] == 'created'
    assert d['proof_url'].startswith('http')


def test_upload_bulk_multi_order_shared_file(client, db, make_user, make_order):
    # SERCE D2: 2 zamówienia × różne etapy, JEDEN plik → 3 wiersze z tym samym proof_file
    h, u = _auth(client, db, make_user)
    o1 = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    o2 = make_order(u, order_type='pre_order', status='nowe', payment_stages=3,
                    customs_vat_sale_cost=Decimal('20.00'), shipping_cost=Decimal('5.00'))
    r = _post_proof(client, h, [_pair(o1, 'domestic_shipping'),
                                _pair(o2, 'customs_vat'), _pair(o2, 'domestic_shipping')])
    assert r.status_code == 200
    d = r.get_json()['data']
    assert d['count'] == 3
    from modules.orders.models import PaymentConfirmation
    rows = PaymentConfirmation.query.all()
    assert len({row.proof_file for row in rows}) == 1         # jeden współdzielony plik
    by = {(c['order_id'], c['payment_stage']): c for c in d['confirmations']}
    assert by[(o2.id, 'customs_vat')]['amount'] == 2000       # grosze per para


def test_upload_dedupes_pairs(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping'), _pair(o, 'domestic_shipping')])
    assert r.status_code == 200 and r.get_json()['data']['count'] == 1


def test_upload_bad_items_json_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = _post_proof(client, h, None, raw_items='not-json')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_empty_items_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = _post_proof(client, h, [])
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_unknown_stage_enum_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'banana')])
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_foreign_order_404_all_or_nothing(client, db, make_user, make_order):
    # P1: jedna cudza para → CAŁY bulk 404 (nic nie utworzone, plik nie zapisany)
    h, u = _auth(client, db, make_user)
    other = make_user()
    mine = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    foreign = make_order(other, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(mine, 'domestic_shipping'), _pair(foreign, 'product')])
    assert r.status_code == 404 and r.get_json()['error']['code'] == 'order_not_found'
    assert foreign.id in r.get_json()['error']['details']['missing_order_ids']
    from modules.orders.models import PaymentConfirmation
    assert PaymentConfirmation.query.count() == 0             # nic nie powstało


def test_upload_stage_not_applicable_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping'), _pair(o, 'korean_shipping')])
    assert r.status_code == 400
    e = r.get_json()['error']
    assert e['code'] == 'stage_not_applicable'
    assert e['details']['failures'][0]['payment_stage'] == 'korean_shipping'


def test_upload_approved_pair_409_all_or_nothing(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    r = _post_proof(client, h, [_pair(o, 'product'), _pair(o, 'domestic_shipping')])
    assert r.status_code == 409 and r.get_json()['error']['code'] == 'stage_not_uploadable'


def test_upload_e1_pending_overwrite_e4_pending_blocks(client, db, make_user, make_order):
    # P2: asymetria pending — parytet z webem
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='pending', proof_file='old.png')
    r = _post_proof(client, h, [_pair(o, 'product')])
    assert r.status_code == 200                                # E1 pending → nadpis
    assert r.get_json()['data']['confirmations'][0]['action'] == 'overwritten'
    _add_payment(db, o, 'domestic_shipping', status='pending')
    r2 = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r2.status_code == 409                               # E4 pending → blokada


def test_upload_overwrites_rejected(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    pc = _add_payment(db, o, 'domestic_shipping', status='rejected', proof_file='old.png')
    pc.rejection_reason = 'Nieczytelne'; db.session.commit()
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')])
    assert r.status_code == 200
    db.session.refresh(pc)
    assert pc.status == 'pending' and pc.rejection_reason is None and pc.proof_file != 'old.png'


def test_upload_missing_file_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = client.post('/api/mobile/v1/payment-confirmations',
                    data={'items': json.dumps([_pair(o, 'domestic_shipping')])},
                    content_type='multipart/form-data', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_upload_bad_extension_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')],
                    fileobj=io.BytesIO(b'hello'), filename='evil.txt')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_upload_oversize_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    big = io.BytesIO(b'\x89PNG\r\n\x1a\n' + b'0' * (5 * 1024 * 1024 + 10))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')], fileobj=big, filename='big.png')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'file_too_large'


def test_upload_corrupt_image_400(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')],
                    fileobj=io.BytesIO(b'not really a png'), filename='fake.png')
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_file'


def test_upload_optional_payment_method(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    m = _make_method(db, name='BLIK')
    r = _post_proof(client, h, [_pair(o, 'domestic_shipping')], method_id=m.id)
    assert r.status_code == 200
    from modules.orders.models import PaymentConfirmation
    assert PaymentConfirmation.query.first().payment_method_id == m.id
```
> Sprzątanie plików: autouse-fixtura (Step 3). Limiter: fixtura `app` jest function-scoped (świeży
> limiter per test) — żaden test nie robi >10 POSTów, więc limit `10/min` nie przeszkadza.

- [ ] **Step 2: Implementacja trasy** — dopisz do `modules/api_mobile/payments_routes.py`:
```python
import json as _json
from extensions import db
from modules.orders.models import Order
from modules.client.payment_confirmation_service import (
    VALID_STAGES, validate_bulk_upload, record_bulk_payment_proofs,
)
from modules.client.payment_confirmations import (
    allowed_proof_file, save_payment_proof_file, MAX_PROOF_FILE_SIZE,
)
from utils.file_validation import validate_proof_file

MAX_BULK_PAIRS = 50


def _parse_items(raw):
    """JSON-string płaskich par -> webowy kształt order_stages (grupowanie + dedupe).

    Zwraca (order_stages, None) lub (None, komunikat_błędu).
    """
    try:
        parsed = _json.loads(raw or '')
    except (ValueError, TypeError):
        return None, 'Pole items musi być poprawnym JSON-em (lista par).'
    if not isinstance(parsed, list) or not parsed:
        return None, 'Pole items musi być niepustą listą par {order_id, payment_stage}.'
    if len(parsed) > MAX_BULK_PAIRS:
        return None, f'Maksymalnie {MAX_BULK_PAIRS} par w jednym żądaniu.'
    pairs = set()
    for it in parsed:
        if not isinstance(it, dict):
            return None, 'Każdy element items musi być obiektem {order_id, payment_stage}.'
        try:
            oid = int(it.get('order_id'))
        except (TypeError, ValueError):
            return None, 'Pole order_id musi być liczbą całkowitą.'
        stage = (it.get('payment_stage') or '').strip()
        if stage not in VALID_STAGES:
            return None, f'Nieznany etap płatności: {stage or "(brak)"}.'
        pairs.add((oid, stage))                               # dedupe (Korekta 3)
    grouped = {}
    for oid, stage in sorted(pairs):
        grouped.setdefault(oid, []).append(stage)
    return [{'order_id': oid, 'stages': stages} for oid, stages in grouped.items()], None


@api_mobile_bp.route('/payment-confirmations', methods=['POST'])
@jwt_required()
@limiter.limit("10 per minute")            # heavy-write (parytet checkout); D4=a: BEZ @idempotent
def upload_payment_confirmations():
    user_id = int(get_jwt_identity())
    order_stages, parse_err = _parse_items(request.form.get('items'))
    if parse_err:
        return json_err('invalid_input', parse_err, 400)

    # Walidacja bulku (wspólny serwis; all-or-nothing — P1)
    ok, err = validate_bulk_upload(user_id, order_stages)
    if not ok:
        if err['code'] == 'orders_not_found':                 # Korekta 4: maskowanie istnienia
            return _err_with_details('order_not_found', 'Zamówienie nie istnieje.', 404,
                                     {'missing_order_ids': err['missing_order_ids']})
        if err['code'] == 'stage_not_applicable':
            return _err_with_details('stage_not_applicable',
                                     'Etap nie dotyczy danego zamówienia.', 400,
                                     {'failures': err['failures']})
        return _err_with_details('stage_not_uploadable',
                                 'Nie można teraz wgrać dowodu dla wskazanych etapów.', 409,
                                 {'failures': err['failures']})

    # Plik (kolejność jak web: walidacja items/zamówień PRZED zapisem pliku)
    file = request.files.get('file')
    if file is None or file.filename == '':
        return json_err('invalid_input', 'Nie przesłano pliku dowodu (pole file).', 400)
    if not allowed_proof_file(file.filename):
        return json_err('invalid_file', 'Dozwolone formaty: JPG, PNG, PDF.', 400)
    file.seek(0, 2); size = file.tell(); file.seek(0)
    if size > MAX_PROOF_FILE_SIZE:
        return json_err('file_too_large', 'Maksymalny rozmiar pliku to 5 MB.', 400)
    saved = save_payment_proof_file(file)
    if not saved:
        return json_err('invalid_file', 'Błąd zapisu pliku.', 400)
    folder = os.path.join(current_app.root_path, 'uploads', 'payment_confirmations')
    valid, _msg = validate_proof_file(os.path.join(folder, saved))
    if not valid:
        _remove_quiet(os.path.join(folder, saved))
        return json_err('invalid_file', 'Plik jest uszkodzony lub niepełny.', 400)

    # Record + efekty uboczne — WSPÓLNY SERWIS (log_activity, commit, OCR, notify per order)
    from modules.auth.models import User
    user = User.query.get(user_id)
    method_id = request.form.get('payment_method_id', type=int)
    try:
        entries = record_bulk_payment_proofs(user, order_stages, saved, method_id)
    except Exception:
        db.session.rollback()
        _remove_quiet(os.path.join(folder, saved))
        return json_err('database_error', 'Wystąpił błąd zapisu. Spróbuj ponownie.', 500)

    return json_ok({
        'confirmations': [{
            'confirmation_id': e['confirmation'].id,
            'order_id': e['order'].id,
            'order_number': e['order'].order_number,
            'payment_stage': e['stage'],
            'status': 'pending',
            'amount': to_grosze(e['confirmation'].amount),
            'action': 'overwritten' if e['action'].endswith('reuploaded') else 'created',
        } for e in entries],
        'count': len(entries),
        'proof_url': _proof_url(saved),
    })


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _err_with_details(code, message, status, details):
    from flask import jsonify
    return jsonify({'success': False,
                    'error': {'code': code, 'message': message, 'details': details}}), status
```

- [ ] **Step 3: Sprzątanie plików w testach** — autouse-fixtura w `tests/test_mobile_api_payments.py`:
```python
import os
import pytest


@pytest.fixture(autouse=True)
def _cleanup_proofs(app):
    folder = os.path.join(app.root_path, 'uploads', 'payment_confirmations')
    before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
    yield
    if os.path.isdir(folder):
        for f in set(os.listdir(folder)) - before:           # usuwa TYLKO pliki z tego testu
            try:
                os.remove(os.path.join(folder, f))
            except OSError:
                pass
```
> Snapshot before/after — bezpieczne także lokalnie (nie tyka plików deweloperskich).
> Tę samą fixturę dodać w `tests/test_payment_confirmation_service.py` (smoke webowe też zapisują pliki).

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_mobile_api_payments.py -v`.
- [ ] **Step 5: Commit** — `git commit -m "feat(mobile-api): BULK upload dowodu płatności (POST /payment-confirmations)"`

---

### Task 5: Lista active/archive — wspólny serwis `[D3=a]` + `GET /payment-confirmations`

**Files:** Modify `modules/client/payment_confirmation_service.py`,
`modules/client/payment_confirmations.py`, `modules/api_mobile/payments_routes.py`,
`tests/test_payment_confirmation_service.py`, `tests/test_mobile_api_payments.py`

- [ ] **Step 1: Testy serwisu (RED)** — dopisz do `tests/test_payment_confirmation_service.py`:
```python
def test_confirmation_orders_base_set_and_owner(db, make_user, make_order):
    from modules.client.payment_confirmation_service import get_confirmation_orders
    u, other = make_user(), make_user()
    inscope = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    make_order(u, order_type='on_hand', status='anulowane')        # poza zbiorem statusów
    make_order(other, order_type='on_hand', status='nowe')         # cudzy
    groups = get_confirmation_orders(u.id)
    assert [o.id for o in groups['payable']] == [inscope.id]
    assert groups['recent_paid'] == [] and groups['archived'] == []


def test_confirmation_orders_archive_split(db, make_user, make_order):
    from modules.client.payment_confirmation_service import get_confirmation_orders
    from datetime import timedelta
    from modules.orders.models import get_local_now
    from tests.test_mobile_api_payments import _add_payment
    u = make_user()
    old = get_local_now() - timedelta(days=5)
    o_arch = make_order(u, order_type='on_hand', status='dostarczone_gom',
                        shipping_cost=Decimal('10.00'))
    _add_payment(db, o_arch, 'product', status='approved', updated_at=old)
    _add_payment(db, o_arch, 'domestic_shipping', status='approved', updated_at=old)
    o_recent = make_order(u, order_type='on_hand', status='dostarczone_gom',
                          shipping_cost=Decimal('10.00'))
    _add_payment(db, o_recent, 'product', status='approved')       # updated_at = teraz
    _add_payment(db, o_recent, 'domestic_shipping', status='approved')
    groups = get_confirmation_orders(u.id)
    assert [o.id for o in groups['archived']] == [o_arch.id]
    assert [o.id for o in groups['recent_paid']] == [o_recent.id]
```
> (Filtr exclusive `is_fully_closed` wymaga `OfferPage` — jeśli fixtura strony istnieje w testach
> E3/E4, dodaj trzeci test; inaczej pokrywa go parytet kodu 1:1 — odnotować przy implementacji.)

- [ ] **Step 2: Serwis** — przenieś logikę z webowej trasy (l. 99–149) do
  `get_confirmation_orders(user_id)` w `payment_confirmation_service.py` (1:1, `current_user.id` →
  parametr; zwraca `{'payable': [...], 'recent_paid': [...], 'archived': [...]}`). Refaktor webowej
  `payment_confirmations()`: woła serwis, mapuje grupy na dotychczasowe zmienne szablonu
  (`orders=payable`, `fully_paid_recent=recent_paid`, `archive_orders=archived`) — zachowanie i
  template context BEZ ZMIAN.
- [ ] **Step 3: Testy trasy mobilnej (RED)** — dopisz do `tests/test_mobile_api_payments.py`:
```python
def test_confirmations_requires_jwt(client, db, make_user):
    assert client.get('/api/mobile/v1/payment-confirmations').status_code == 401


def test_confirmations_invalid_tab_400(client, db, make_user):
    h, _ = _auth(client, db, make_user)
    r = client.get('/api/mobile/v1/payment-confirmations?tab=banana', headers=h)
    assert r.status_code == 400 and r.get_json()['error']['code'] == 'invalid_input'


def test_confirmations_active_shape(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='nowe', shipping_cost=Decimal('10.00'))
    d = client.get('/api/mobile/v1/payment-confirmations', headers=h).get_json()['data']
    assert d['tab'] == 'active'
    row = next(r for r in d['orders'] if r['id'] == o.id)
    assert 'payment_stages' in row
    assert {'total_to_pay', 'paid_amount', 'remaining_to_pay'} <= set(row['payment_summary'])
    assert row['all_approved'] is False
    assert 'active_total' in d and 'archive_count' in d


def test_confirmations_archive_tab(client, db, make_user, make_order):
    from datetime import timedelta
    from modules.orders.models import get_local_now
    h, u = _auth(client, db, make_user)
    old = get_local_now() - timedelta(days=5)
    o = make_order(u, order_type='on_hand', status='dostarczone_gom',
                   shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved', updated_at=old)
    _add_payment(db, o, 'domestic_shipping', status='approved', updated_at=old)
    active = client.get('/api/mobile/v1/payment-confirmations?tab=active',
                        headers=h).get_json()['data']
    archive = client.get('/api/mobile/v1/payment-confirmations?tab=archive',
                         headers=h).get_json()['data']
    assert all(r['id'] != o.id for r in active['orders'])
    assert any(r['id'] == o.id for r in archive['orders'])
    assert archive['archive_count'] == 1


def test_confirmations_recent_paid_stays_active(client, db, make_user, make_order):
    h, u = _auth(client, db, make_user)
    o = make_order(u, order_type='on_hand', status='dostarczone_gom',
                   shipping_cost=Decimal('10.00'))
    _add_payment(db, o, 'product', status='approved')
    _add_payment(db, o, 'domestic_shipping', status='approved')
    active = client.get('/api/mobile/v1/payment-confirmations?tab=active',
                        headers=h).get_json()['data']
    row = next(r for r in active['orders'] if r['id'] == o.id)
    assert row['all_approved'] is True
```

- [ ] **Step 4: Trasa mobilna** — dopisz do `payments_routes.py`:
```python
from modules.client.payment_confirmation_service import get_confirmation_orders
from .orders_routes import _serialize_order_brief, _serialize_payment_stages

ALLOWED_CONFIRMATION_TABS = ('active', 'archive')


def _serialize_confirmation_row(order):
    row = _serialize_order_brief(order)
    stages = _serialize_payment_stages(order)                 # zawiera proof_url (Task 2)
    row['payment_stages'] = stages
    row['payment_summary'] = {
        'total_to_pay': to_grosze(order.total_to_pay),
        'paid_amount': to_grosze(order.paid_amount),
        'remaining_to_pay': to_grosze(order.remaining_to_pay),
    }
    row['all_approved'] = all(s['status'] == 'approved' for s in stages)
    return row


@api_mobile_bp.route('/payment-confirmations', methods=['GET'])
@jwt_required()
@limiter.limit("60 per minute")
def list_payment_confirmations():
    user_id = int(get_jwt_identity())
    tab = (request.args.get('tab') or 'active').strip()
    if tab not in ALLOWED_CONFIRMATION_TABS:
        return json_err('invalid_input', f'Nieznana zakładka: {tab}.', 400)
    groups = get_confirmation_orders(user_id)
    shown = groups['archived'] if tab == 'archive' else groups['payable'] + groups['recent_paid']
    return json_ok({
        'tab': tab,
        'orders': [_serialize_confirmation_row(o) for o in shown],
        'active_total': len(groups['payable']) + len(groups['recent_paid']),
        'archive_count': len(groups['archived']),
    })
```

- [ ] **Step 5: GREEN** — `python -m pytest tests/test_payment_confirmation_service.py
  tests/test_mobile_api_payments.py -v` + pełny suite (zero regresji weba).
- [ ] **Step 6: Commit** — `git commit -m "feat(mobile-api): lista potwierdzeń płatności (serwis active/archive + GET /payment-confirmations)"`

---

### Task 6: Korekty kontraktu w specu + finalna weryfikacja

**Files:** Modify `docs/superpowers/specs/2026-06-11-mobile-api-backend-design.md`

- [ ] **Step 1:** W sekcji „Płatności wieloetapowe" ZAMIEŃ wiersz POST (pojedyncza para) na bulk:
  `POST /payment-confirmations (multipart: file + items [JSON par {order_id, payment_stage}] +
  payment_method_id?)` i dopisz blok „Korekty kontraktu (E6)": bulk = parytet webowy (jeden plik →
  wiele wierszy, all-or-nothing, asymetria pending E1 vs E2–E4); kody `order_not_found(404)+details` /
  `stage_not_applicable(400)` / `stage_not_uploadable(409)` / `invalid_file` / `file_too_large`;
  dedupe par, cap 50; `tab` walidowane; `proof_url` (trasa JWT, D1=a) w uploadzie/liście/etapach E5;
  lista = orders+etapy bez paginacji; kwoty grosze; `payment_method_id` opcjonalny pass-through;
  bez `Idempotency-Key` (naturalna jedyność per para — P3).
- [ ] **Step 2: Pełny suite** — `source venv/bin/activate && python -m pytest` → oczekiwane
  **~325 passed** (281 baseline + ~44 nowych; doprecyzuj po implementacji), **zero regresji**
  (szczególnie: brak regresji webowego uploadu/listy po refaktorach Task 3/5), **zero migracji**
  (`flask db heads` = `c72aad290158`).
- [ ] **Step 3: Commit** — `git commit -m "docs(mobile-api): korekty kontraktu E6 (bulk upload płatności)"`

---

## Definition of Done

- [ ] `GET /payment-methods` — aktywne metody, logo URL-e absolutne, 401 bez JWT.
- [ ] `GET /payment-confirmations/proof/<filename>` `[D1=a]` — właściciel pobiera plik; cudze/brak →
  404 maskujące; 401 bez JWT; `proof_url` addytywnie w etapach E5, uploadzie i liście.
- [ ] **Wspólny serwis** `payment_confirmation_service.py` (`order_stage_keys`,
  `validate_bulk_upload`, `record_bulk_payment_proofs`, `get_confirmation_orders`) — webowe trasy
  uploadu i listy zrefaktorowane by go wołać **BEZ zmiany zachowania** (smoke-testy webowe z fixturą
  `login` zielone; QR-flow i fallback `order_ids` nietknięte).
- [ ] `POST /payment-confirmations` (BULK) — `items` JSON-string par (dedupe, cap 50), jeden plik →
  wiele wierszy ze wspólnym `proof_file`; all-or-nothing (P1); kody: `invalid_input`,
  `order_not_found(404)+missing_order_ids`, `stage_not_applicable(400)+failures`,
  `stage_not_uploadable(409)+failures`, `invalid_file`, `file_too_large`, `database_error(500,
  plik sprzątnięty)`; asymetria pending E1/E2–E4 (P2); odpowiedź: `confirmations[]` (amount w
  groszach, action) + `count` + `proof_url`. Efekty uboczne przez serwis (log_activity per para,
  notify per order, OCR-gdy-włączony). Rate-limit `10/min`, **bez `@idempotent`** (D4=a, P3).
- [ ] `GET /payment-confirmations` — active/archive przez wspólny serwis (parytet: zbiór bazowy,
  filtr exclusive, podział 3-dniowy); `tab` walidowane; pozycje = brief+stages+summary+all_approved;
  `active_total`/`archive_count`.
- [ ] Kwoty wszędzie w groszach; URL-e absolutne; daty ISO.
- [ ] `python -m pytest` zielone (~325), zero regresji, zero migracji (head `c72aad290158`).
- [ ] NIE pushować bez zgody Konrada (push = auto-deploy na żywy sklep).

## Szacunek testów

- Task 1 (metody): **3**.
- Task 2 (proof serving + proof_url): **5** (4 + 1 w E5).
- Task 3 (serwis bulk + smoke web): **~12** (validate: ok-multi, foreign-all-or-nothing,
  not_applicable, asymetria pending, approved; record: wiersze+wspólny plik+kwoty, nadpis/skip,
  log_activity; +2 smoke webowej trasy po refaktorze).
- Task 4 (mobilny bulk POST): **~17** (401, happy single, bulk multi-order, dedupe, zły JSON, puste
  items, zły enum, foreign 404+details+nic-nie-powstało, not_applicable+details, approved 409,
  asymetria pending, nadpis rejected, brak pliku, zły typ, oversize, corrupt, metoda płatności).
- Task 5 (serwis listy + mobilne GET): **~7** (2 serwis + 5 trasa).
- **Razem ~44 nowych** → baseline **281 → ~325**.

## Notatki ryzyka

- **Refaktor produkcyjnych tras weba (Task 3/5).** Mitygacja: ekstrakcja mechaniczna 1:1 (kwoty,
  all-or-nothing, batchowanie notify per order, jeden task OCR), smoke-testy webowe (fixtura `login`)
  + pełny suite po refaktorze; QR-flow i fallback `order_ids` zostają w trasie nietknięte
  (serwis przyjmuje gotowe `order_stages` + `saved_filename`).
- **Pliki na dysku w testach.** Autouse-fixtura snapshot-diff (Task 4 Step 3) usuwa tylko pliki
  utworzone przez dany test (dodać też w pliku testów serwisu).
- **Import cykliczny.** `payments_routes` importuje z `orders_routes` (serializery) — OK;
  `orders_routes._stage_entry` importuje `_proof_url` z `payments_routes` **LOKALNIE w funkcji**
  (nie na poziomie modułu). Serwis w `modules/client/` nie importuje nic z `api_mobile`
  (kierunek zależności: api_mobile → client, nigdy odwrotnie).
- **Limiter w testach.** Fixtura `app` function-scoped → świeży limiter per test; żaden pojedynczy
  test nie przekracza 10 POSTów uploadu.
- **`secure_filename` round-trip** w trasie proof — nazwy w bazie już przeszły `secure_filename`
  przy zapisie, więc lookup jest stabilny (test `test_proof_owner_gets_file` potwierdza).
- **Ścieżki do potwierdzenia przy implementacji:** model `ActivityLog` (import w teście Task 3),
  prefiks URL `client_bp` (smoke-testy webowe).
- **NIE dotykać produkcji / NIE pushować** — Konrad zatwierdza każdy push (auto-deploy na żywy sklep).
