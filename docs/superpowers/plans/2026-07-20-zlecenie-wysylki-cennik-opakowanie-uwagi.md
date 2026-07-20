# Zlecenie wysyłki: cennik + typ opakowania + uwagi — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rozszerzyć zlecenie wysyłki (`ShippingRequest`) o wycenę opartą o materiały opakowaniowe (cena z cennika + gabaryt + typ karton/koperta) oraz o kliencką sugestię opakowania i uwagi klienta.

**Architecture:** Baza `PackagingMaterial` (WMS) staje się cennikiem — dokładamy `sale_price` + `size_category`. Admin, obsługując zlecenie, wybiera materiał → JS podstawia cenę do istniejącego pola kosztu (dystrybucja na zamówienia bez zmian) i gabaryt; backend zapisuje `packaging_material_id` na `ShippingRequest`. Klient przy tworzeniu podaje sugerowany typ opakowania (karton/koperta) i uwagi, oraz widzi cennik liczony z aktywnych materiałów.

**Tech Stack:** Flask + Flask-Migrate (Alembic) + MariaDB, Jinja2, vanilla JS, pytest (`python -m pytest`).

## Global Constraints

- **Migracje przez Flask-Migrate** — każda zmiana struktury bazy w pliku migracyjnym; test `flask db upgrade` lokalnie. Repo ma **3 rozgałęzione heady** — najpierw `flask db merge`.
- **CSS: light + dark mode** — każdy nowy element ma wariant `[data-theme="dark"]`. Style modali w `static/css/components/modals.css`; style stron w `static/css/pages/...`. Bez inline CSS/JS w HTML (poza dynamicznymi wartościami Jinja2).
- **Toast:** globalny `window.showToast(msg, type)` — nie ma `window.Toast`.
- **Testy:** uruchamiane `python -m pytest` (gołe `pytest` pada na `No module named 'app'`). Fixtury w `tests/conftest.py`: `app`, `db`, `client`, `make_user`, `make_product`, `make_order`, `login`. Importy modeli/serwisów **wewnątrz** funkcji testowej (po `create_app()`).
- **Sugerowany typ opakowania (klient) = tylko `karton` / `koperta`** (bez podtypów).
- **Magazyn nietknięty** — wybór materiału na zleceniu nie zmienia `quantity_in_stock`.
- **Praca na branchu** `feature/zlecenie-wysylki-cennik-opakowanie-uwagi`. Bez pusha (push = auto-deploy).
- Wartości `size_category`: `mini`, `A`, `B`, `C`. Cennik referencyjny (taski): Mini/koperta 12,99 · A/karton 19,49 · A/koperta 17,99 · B/karton 21,49 · C/karton 23,49.

---

### Task 1: Model `PackagingMaterial` — cena sprzedaży + gabaryt

**Files:**
- Modify: `modules/orders/wms_models.py:144-201`
- Test: `tests/test_packaging_material_pricing.py` (create)

**Interfaces:**
- Produces: `PackagingMaterial.sale_price` (Numeric 8,2, nullable), `PackagingMaterial.size_category` (String(10), nullable, wartości `mini`/`A`/`B`/`C`), `PackagingMaterial.SIZE_CHOICES` (dict), property `PackagingMaterial.size_display` (str | None).

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_packaging_material_pricing.py`:

```python
"""Testy rozszerzenia PackagingMaterial o cenę sprzedaży i gabaryt."""


def test_sale_price_and_size_category_persist(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Karton A', type='karton',
                          sale_price=19.49, size_category='A')
    db.session.add(m)
    db.session.commit()
    db.session.refresh(m)
    assert float(m.sale_price) == 19.49
    assert m.size_category == 'A'


def test_size_display_maps_known_and_unknown(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Koperta Mini', type='koperta', size_category='mini')
    assert m.size_display == 'Mini'
    m2 = PackagingMaterial(name='Bez gabarytu', type='karton', size_category=None)
    assert m2.size_display is None


def test_size_choices_contains_expected_keys(db):
    from modules.orders.wms_models import PackagingMaterial
    assert set(PackagingMaterial.SIZE_CHOICES.keys()) == {'mini', 'A', 'B', 'C'}
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_packaging_material_pricing.py -v`
Expected: FAIL (`TypeError: 'sale_price' is an invalid keyword argument` / brak `SIZE_CHOICES`).

- [ ] **Step 3: Dodaj kolumny, słownik i property**

W `modules/orders/wms_models.py` po linii `cost = db.Column(...)` (162) dodaj:

```python
    sale_price = db.Column(db.Numeric(8, 2), nullable=True)  # cena sprzedaży wysyłki (cennik)
    size_category = db.Column(db.String(10), nullable=True)  # gabaryt: mini, A, B, C
```

Po `TYPE_CHOICES` (po linii 196) dodaj słownik i property:

```python
    SIZE_CHOICES = {
        'mini': 'Mini',
        'A': 'Gabaryt A',
        'B': 'Gabaryt B',
        'C': 'Gabaryt C',
    }

    @property
    def size_display(self):
        """Returns human-readable size category name or None."""
        if not self.size_category:
            return None
        return self.SIZE_CHOICES.get(self.size_category, self.size_category)
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_packaging_material_pricing.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/orders/wms_models.py tests/test_packaging_material_pricing.py
git commit -m "feat(wms): PackagingMaterial — sale_price + size_category (cennik wysyłki)"
```

---

### Task 2: Model `ShippingRequest` — materiał, sugestia klienta, uwagi klienta

**Files:**
- Modify: `modules/orders/models.py:1341-1352`
- Test: `tests/test_shipping_request_fields.py` (create)

**Interfaces:**
- Consumes: `PackagingMaterial` (Task 1).
- Produces: `ShippingRequest.packaging_material_id` (FK `packaging_materials.id`, nullable), `ShippingRequest.packaging_material` (relacja), `ShippingRequest.client_package_preference` (String(30), nullable, `karton`/`koperta`), `ShippingRequest.client_notes` (Text, nullable), `ShippingRequest.parcel_size` poszerzone do String(10).

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_shipping_request_fields.py`:

```python
"""Testy nowych pól ShippingRequest: materiał, sugestia opakowania, uwagi klienta."""


def test_new_fields_persist(db):
    from modules.orders.models import ShippingRequest
    from modules.orders.wms_models import PackagingMaterial
    mat = PackagingMaterial(name='Karton A', type='karton', sale_price=19.49, size_category='A')
    db.session.add(mat)
    db.session.commit()

    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        packaging_material_id=mat.id,
        client_package_preference='koperta',
        client_notes='Proszę o dodatkowe zabezpieczenie',
        parcel_size='mini',
    )
    db.session.add(sr)
    db.session.commit()
    db.session.refresh(sr)

    assert sr.packaging_material.id == mat.id
    assert sr.packaging_material.sale_price is not None
    assert sr.client_package_preference == 'koperta'
    assert sr.client_notes == 'Proszę o dodatkowe zabezpieczenie'
    assert sr.parcel_size == 'mini'
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_shipping_request_fields.py -v`
Expected: FAIL (`TypeError: 'packaging_material_id' is an invalid keyword argument`).

- [ ] **Step 3: Dodaj pola i relację**

W `modules/orders/models.py`, w klasie `ShippingRequest`, zmień linię 1349:

```python
    # Parcel size (mini, A, B, C)
    parcel_size = db.Column(db.String(10), nullable=True)  # mini, A, B, C
```

Po sekcji `# Notes` (po linii 1352 `admin_notes = ...`) dodaj:

```python
    # Wybrany materiał opakowaniowy (źródło ceny/gabarytu/typu — task 869e674tp/xk)
    packaging_material_id = db.Column(db.Integer, db.ForeignKey('packaging_materials.id'), nullable=True)
    packaging_material = db.relationship('PackagingMaterial', foreign_keys=[packaging_material_id])

    # Sugerowany przez klienta typ opakowania: 'karton' / 'koperta' (task 869e674xk)
    client_package_preference = db.Column(db.String(30), nullable=True)

    # Uwagi klienta do wysyłki (task 869e674je) — read-only dla admina
    client_notes = db.Column(db.Text, nullable=True)
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_shipping_request_fields.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/orders/models.py tests/test_shipping_request_fields.py
git commit -m "feat(wysyłki): ShippingRequest — materiał, sugestia opakowania, uwagi klienta"
```

---

### Task 3: Migracja bazy (merge headów + nowe kolumny)

**Files:**
- Create: `migrations/versions/<auto>_merge_heads_before_shipping_pricing.py` (przez `flask db merge`)
- Create: `migrations/versions/<auto>_shipping_packaging_pricing.py` (przez `flask db migrate`)

**Interfaces:**
- Consumes: modele z Task 1 i Task 2.
- Produces: kolumny w bazie: `packaging_materials.sale_price`, `packaging_materials.size_category`, `shipping_requests.packaging_material_id` (+FK), `shipping_requests.client_package_preference`, `shipping_requests.client_notes`, ALTER `shipping_requests.parcel_size` → String(10).

- [ ] **Step 1: Sprawdź heady**

Run: `python -m flask db heads`
Expected: 3 heady (`f5fe71f921ef`, `830b9d3167ad`, `b1c2d3e4f5a6`) — potwierdź nazwy przed merge.

- [ ] **Step 2: Zmerguj heady**

Run: `python -m flask db merge -m "merge heads before shipping packaging pricing" f5fe71f921ef 830b9d3167ad b1c2d3e4f5a6`
(Użyj faktycznych nazw ze Step 1, jeśli inne.)
Expected: powstaje plik merge w `migrations/versions/`.

- [ ] **Step 3: Wygeneruj migrację kolumn**

Run: `python -m flask db migrate -m "shipping packaging pricing"`
Expected: nowy plik migracji. **Otwórz go i zweryfikuj** — musi zawierać `add_column` dla 5 nowych kolumn, `create_foreign_key` dla `packaging_material_id` oraz `alter_column('shipping_requests','parcel_size', type_=sa.String(length=10))`. Usuń ewentualne przypadkowe zmiany niezwiązane z tym zadaniem. Wzorzec FK: patrz `migrations/versions/ba7ae52feb68_add_packaging_materials_table_and_fk_on_.py`. Jeśli autogen pominął ALTER `parcel_size`, dopisz ręcznie:

```python
    op.alter_column('shipping_requests', 'parcel_size',
                    existing_type=sa.String(length=1),
                    type_=sa.String(length=10),
                    existing_nullable=True)
```

- [ ] **Step 4: Zastosuj i przetestuj lokalnie**

Run: `python -m flask db upgrade`
Expected: `OK` bez błędów. Weryfikacja (XAMPP): `SHOW COLUMNS FROM packaging_materials LIKE 'sale_price';` i `SHOW COLUMNS FROM shipping_requests LIKE 'parcel_size';` (Type = `varchar(10)`).

- [ ] **Step 5: Sanity — cały zestaw testów modeli przechodzi**

Run: `python -m pytest tests/test_packaging_material_pricing.py tests/test_shipping_request_fields.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/
git commit -m "migrate(wysyłki): merge headów + kolumny cennika/materiału/uwag"
```

---

### Task 4: Backend CRUD materiałów — obsługa `sale_price` + `size_category`

**Files:**
- Modify: `modules/orders/wms.py:1471-1601`
- Test: `tests/test_packaging_material_crud.py` (create)

**Interfaces:**
- Consumes: `PackagingMaterial.SIZE_CHOICES` (Task 1).
- Produces: endpointy przyjmują/zwracają `sale_price` i `size_category`. `packaging_materials_list_api` dodatkowo zwraca `size_display` i `sale_price` (używane przez modal zlecenia — Task 10).

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_packaging_material_crud.py`:

```python
"""Testy CRUD materiałów opakowaniowych z ceną sprzedaży i gabarytem."""


def _admin(make_user):
    return make_user(role='admin')


def test_create_persists_sale_price_and_size(client, db, make_user, login):
    login(_admin(make_user))
    r = client.post('/admin/orders/packaging-materials/create', json={
        'name': 'Karton A', 'type': 'karton', 'sale_price': 19.49, 'size_category': 'A',
    })
    assert r.status_code == 200 and r.get_json()['success']
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial.query.filter_by(name='Karton A').first()
    assert float(m.sale_price) == 19.49 and m.size_category == 'A'


def test_create_rejects_bad_size_category(client, db, make_user, login):
    login(_admin(make_user))
    r = client.post('/admin/orders/packaging-materials/create', json={
        'name': 'Zły gabaryt', 'type': 'karton', 'size_category': 'XL',
    })
    assert r.status_code == 200
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial.query.filter_by(name='Zły gabaryt').first()
    assert m.size_category is None  # niepoprawny gabaryt odrzucony → None


def test_get_and_list_expose_new_fields(client, db, make_user, login):
    login(_admin(make_user))
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Koperta Mini', type='koperta',
                          sale_price=12.99, size_category='mini', is_active=True)
    db.session.add(m); db.session.commit()

    g = client.get(f'/api/orders/packaging-materials/{m.id}').get_json()['material']
    assert g['sale_price'] == 12.99 and g['size_category'] == 'mini'

    lst = client.get('/api/orders/packaging-materials').get_json()['materials']
    row = next(x for x in lst if x['id'] == m.id)
    assert row['sale_price'] == 12.99 and row['size_category'] == 'mini'
    assert row['size_display'] == 'Mini'
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_packaging_material_crud.py -v`
Expected: FAIL (`KeyError: 'sale_price'` / `size_category` nie zapisany).

- [ ] **Step 3: Dodaj obsługę w 4 miejscach `wms.py`**

W `packaging_material_get` (serializacja, po `'cost'` ~1490) dodaj:

```python
            'sale_price': float(m.sale_price) if m.sale_price else None,
            'size_category': m.size_category,
```

W `packaging_materials_list_api` (serializacja, po `'cost'` ~1517) dodaj:

```python
            'sale_price': float(m.sale_price) if m.sale_price else None,
            'size_category': m.size_category,
            'size_display': m.size_display,
```

W `packaging_material_create` — po walidacji `mat_type` (przed `PackagingMaterial(`, ~1537) dodaj walidację gabarytu:

```python
        size_category = data.get('size_category')
        if size_category not in PackagingMaterial.SIZE_CHOICES:
            size_category = None
```

i w konstruktorze `PackagingMaterial(...)` (po `cost=...`) dodaj:

```python
            sale_price=data.get('sale_price'),
            size_category=size_category,
```

W `packaging_material_update` — po walidacji `mat_type` (~1580) dodaj:

```python
        size_category = data.get('size_category')
        if size_category not in PackagingMaterial.SIZE_CHOICES:
            size_category = None
```

i po `m.cost = data.get('cost')` (~1591) dodaj:

```python
        m.sale_price = data.get('sale_price')
        m.size_category = size_category
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_packaging_material_crud.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add modules/orders/wms.py tests/test_packaging_material_crud.py
git commit -m "feat(wms): CRUD materiałów obsługuje sale_price + size_category"
```

---

### Task 5: Backend — klient zapisuje sugestię opakowania i uwagi

**Files:**
- Modify: `modules/client/shipping_service.py:139-199`
- Modify: `modules/client/shipping.py:224-266`
- Modify: `modules/api_mobile/shipping_routes.py:157-181`
- Test: `tests/test_shipping_request_client_fields.py` (create)

**Interfaces:**
- Consumes: `ShippingRequest.client_package_preference`, `client_notes` (Task 2).
- Produces: `validate_and_create_request(user, order_ids, address_id, client_package_preference=None, client_notes=None)` — nowe **opcjonalne** parametry (wsteczna kompatybilność). Web i mobile czytają je z payloadu.

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_shipping_request_client_fields.py`:

```python
"""Klient przy tworzeniu zlecenia zapisuje sugestię opakowania i uwagi."""


def _addr(user, db):
    from modules.auth.models import ShippingAddress
    a = ShippingAddress(user_id=user.id, address_type='home', shipping_name='Jan',
                        shipping_address='Główna 1', shipping_postal_code='00-001',
                        shipping_city='Warszawa', is_active=True)
    db.session.add(a); db.session.commit()
    return a


def _order_ready(user, db, make_order):
    # status dozwolony do zlecenia; make_order tworzy zamówienie z customs_vat_sale_cost=0,
    # więc is_customs_vat_settled (property) zwraca True automatycznie — nie ustawiaj go ręcznie.
    return make_order(user, status='dostarczone_gom')


def test_create_saves_preference_and_notes(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    a = _addr(u, db)
    o = _order_ready(u, db, make_order)
    ok, err, req = validate_and_create_request(
        u, [o.id], a.id,
        client_package_preference='koperta',
        client_notes='Delikatna zawartość',
    )
    assert ok, err
    assert req.client_package_preference == 'koperta'
    assert req.client_notes == 'Delikatna zawartość'


def test_create_rejects_invalid_preference(db, make_user, make_order):
    from modules.client.shipping_service import validate_and_create_request
    u = make_user()
    a = _addr(u, db)
    o = _order_ready(u, db, make_order)
    ok, err, req = validate_and_create_request(
        u, [o.id], a.id, client_package_preference='paczka', client_notes='x' * 5000)
    assert ok
    assert req.client_package_preference is None       # spoza {karton,koperta} → None
    assert len(req.client_notes) <= 2000               # przycięte
```

> Uwaga: jeśli `dostarczone_gom` nie jest w dozwolonych statusach w środowisku testowym, w teście ustaw status z `allowed_request_statuses()` lub zmockuj `Settings`. Sprawdź `tests/test_shipping_service.py`, jak istniejące testy dobierają status.

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_shipping_request_client_fields.py -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'client_package_preference'`).

- [ ] **Step 3: Rozszerz serwis**

W `modules/client/shipping_service.py` zmień sygnaturę (139):

```python
def validate_and_create_request(user, order_ids, address_id,
                                client_package_preference=None, client_notes=None):
```

Przed `db.session.add(req)` (przed 176), po ustawieniu snapshotu adresu, znormalizuj i przypisz nowe pola:

```python
    pref = (client_package_preference or '').strip().lower() or None
    if pref not in ('karton', 'koperta'):
        pref = None
    req.client_package_preference = pref
    notes = (client_notes or '').strip() or None
    if notes and len(notes) > 2000:
        notes = notes[:2000]
    req.client_notes = notes
```

- [ ] **Step 4: Przekaż pola z trasy web**

W `modules/client/shipping.py`, `shipping_requests_create` (~232), po odczycie `address_id` dodaj i przekaż:

```python
        client_package_preference = data.get('client_package_preference')
        client_notes = data.get('client_notes')

        ok, err, shipping_request = validate_and_create_request(
            current_user, order_ids, address_id,
            client_package_preference=client_package_preference,
            client_notes=client_notes,
        )
```

(Zastąp istniejące wywołanie `validate_and_create_request(current_user, order_ids, address_id)`.)

- [ ] **Step 5: Przekaż pola z API mobilnego (parytet)**

W `modules/api_mobile/shipping_routes.py`, `shipping_request_create` (~171), przed wywołaniem serwisu dodaj i przekaż:

```python
    client_package_preference = p.get('client_package_preference')
    client_notes = p.get('client_notes')
    ok, err, req = svc.validate_and_create_request(
        user, order_ids, address_id,
        client_package_preference=client_package_preference,
        client_notes=client_notes,
    )
```

(Zastąp istniejące `svc.validate_and_create_request(user, order_ids, address_id)`.)

- [ ] **Step 6: Uruchom testy — mają przejść**

Run: `python -m pytest tests/test_shipping_request_client_fields.py tests/test_shipping_service.py tests/test_mobile_api_shipping.py -v`
Expected: PASS (nowe + brak regresji w istniejących).

- [ ] **Step 7: Commit**

```bash
git add modules/client/shipping_service.py modules/client/shipping.py modules/api_mobile/shipping_routes.py tests/test_shipping_request_client_fields.py
git commit -m "feat(wysyłki): klient zapisuje sugestię opakowania + uwagi (web+mobile)"
```

---

### Task 6: Backend admin — materiał na zleceniu + serializacja pól

**Files:**
- Modify: `modules/orders/routes.py:3662-3706` (GET), `3746-3802` (PUT)
- Test: `tests/test_admin_shipping_request_material.py` (create)

**Interfaces:**
- Consumes: `ShippingRequest.packaging_material_id`, `PackagingMaterial.size_category/sale_price` (Task 1/2).
- Produces: PUT przyjmuje `packaging_material_id` (ustawia FK; gdy `parcel_size` nie podane, wyprowadza je z `material.size_category`); bez zmian stanu magazynowego. GET zwraca `packaging_material_id`, `packaging_material` (nazwa/typ/gabaryt/cena), `client_package_preference`, `client_notes`.

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_admin_shipping_request_material.py`:

```python
"""Admin: wybór materiału na zleceniu ustawia FK + gabaryt, nie rusza magazynu."""


def _admin(make_user):
    return make_user(role='admin')


def _sr(db, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='czeka_na_wycene')
    db.session.add(sr); db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr


def _material(db):
    from modules.orders.wms_models import PackagingMaterial
    m = PackagingMaterial(name='Karton B', type='karton', sale_price=21.49,
                          size_category='B', quantity_in_stock=10, is_active=True)
    db.session.add(m); db.session.commit()
    return m


def test_put_sets_material_and_derives_parcel_size(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'packaging_material_id': mat.id})
    assert r.status_code == 200
    db.session.refresh(sr); db.session.refresh(mat)
    assert sr.packaging_material_id == mat.id
    assert sr.parcel_size == 'B'                 # wyprowadzone z materiału
    assert mat.quantity_in_stock == 10           # magazyn NIE ruszony


def test_put_explicit_parcel_size_wins(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    r = client.put(f'/admin/orders/shipping-requests/{sr.id}',
                   json={'packaging_material_id': mat.id, 'parcel_size': 'C'})
    assert r.status_code == 200
    db.session.refresh(sr)
    assert sr.parcel_size == 'C'                 # jawny parcel_size ma priorytet


def test_get_serializes_new_fields(client, db, make_user, make_order, login):
    login(_admin(make_user))
    sr = _sr(db, make_user, make_order)
    mat = _material(db)
    sr.packaging_material_id = mat.id
    sr.client_package_preference = 'koperta'
    sr.client_notes = 'Ostrożnie'
    db.session.commit()
    data = client.get(f'/admin/orders/shipping-requests/{sr.id}').get_json()
    assert data['packaging_material_id'] == mat.id
    assert data['packaging_material']['size_category'] == 'B'
    assert data['client_package_preference'] == 'koperta'
    assert data['client_notes'] == 'Ostrożnie'
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_admin_shipping_request_material.py -v`
Expected: FAIL (brak `packaging_material_id` w odpowiedzi / nie ustawiany).

- [ ] **Step 3: Rozszerz GET (serializacja)**

W `admin_get_shipping_request` (`modules/orders/routes.py`), w słowniku `jsonify({...})` (po `'admin_notes': sr.admin_notes,` ~3691) dodaj:

```python
        'packaging_material_id': sr.packaging_material_id,
        'packaging_material': ({
            'id': sr.packaging_material.id,
            'name': sr.packaging_material.name,
            'type': sr.packaging_material.type,
            'type_display': sr.packaging_material.type_display,
            'size_category': sr.packaging_material.size_category,
            'size_display': sr.packaging_material.size_display,
            'sale_price': float(sr.packaging_material.sale_price) if sr.packaging_material.sale_price else None,
        } if sr.packaging_material else None),
        'client_package_preference': sr.client_package_preference,
        'client_notes': sr.client_notes,
```

- [ ] **Step 4: Rozszerz PUT (materiał + gabaryt z materiału)**

W `admin_update_shipping_request`, w bloku „Update basic fields", po obsłudze `parcel_size` (po linii 3779) i `admin_notes`, dodaj obsługę materiału. Ważne: kolejność — najpierw ustaw `packaging_material_id`, potem wyprowadź `parcel_size`, jeśli nie podano jawnie:

```python
    if 'packaging_material_id' in data:
        mat_id = data['packaging_material_id'] or None
        sr.packaging_material_id = mat_id
        # Wyprowadź gabaryt z materiału, o ile admin nie podał parcel_size jawnie w tym żądaniu.
        if mat_id and 'parcel_size' not in data:
            from modules.orders.wms_models import PackagingMaterial
            mat = db.session.get(PackagingMaterial, mat_id)
            if mat and mat.size_category:
                sr.parcel_size = mat.size_category
        # Bez zmian quantity_in_stock — magazyn obsługiwany przy pakowaniu zamówienia.
```

> Cena: pozostaje sterowana przez `order_costs` (frontend podstawia `sale_price` do pola kosztu i rozkłada na zamówienia — Task 10). Backend PUT nie modyfikuje kosztu na podstawie materiału.

- [ ] **Step 5: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_admin_shipping_request_material.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Sanity — brak regresji na istniejących trasach admina**

Run: `python -m pytest tests/ -k "shipping" -v`
Expected: PASS (bez nowych failów).

- [ ] **Step 7: Commit**

```bash
git add modules/orders/routes.py tests/test_admin_shipping_request_material.py
git commit -m "feat(wysyłki): admin — materiał na zleceniu + serializacja pól (bez ruszania magazynu)"
```

---

### Task 7: Backend — helper cennika dla klienta

**Files:**
- Modify: `modules/client/shipping_service.py` (dodaj helper na końcu pliku)
- Modify: `modules/client/shipping.py:108-130` (`shipping_requests_list`)
- Test: `tests/test_shipping_pricing_helper.py` (create)

**Interfaces:**
- Consumes: `PackagingMaterial` (Task 1).
- Produces: `get_shipping_pricing()` → dict `{'min_price': float|None, 'rows': [{'size_category','size_display','type','type_display','sale_price'}]}` z aktywnych materiałów z ustawionymi `sale_price` i `size_category`, posortowane rosnąco po cenie. Kontekst szablonu `shipping_requests_list` dostaje `pricing=get_shipping_pricing()`.

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_shipping_pricing_helper.py`:

```python
"""Helper cennika liczony z aktywnych materiałów."""


def test_pricing_min_and_rows(db):
    from modules.orders.wms_models import PackagingMaterial
    from modules.client.shipping_service import get_shipping_pricing
    db.session.add_all([
        PackagingMaterial(name='Koperta Mini', type='koperta', sale_price=12.99,
                          size_category='mini', is_active=True),
        PackagingMaterial(name='Karton A', type='karton', sale_price=19.49,
                          size_category='A', is_active=True),
        PackagingMaterial(name='Nieaktywny', type='karton', sale_price=5.00,
                          size_category='A', is_active=False),   # pominięty
        PackagingMaterial(name='Bez ceny', type='karton', sale_price=None,
                          size_category='B', is_active=True),    # pominięty
    ])
    db.session.commit()
    p = get_shipping_pricing()
    assert p['min_price'] == 12.99
    names = [(r['size_display'], r['type_display'], r['sale_price']) for r in p['rows']]
    assert ('Mini', 'Koperta', 12.99) in names
    assert ('Gabaryt A', 'Karton', 19.49) in names
    assert all(r['sale_price'] != 5.00 for r in p['rows'])       # nieaktywny pominięty
    assert p['rows'][0]['sale_price'] <= p['rows'][-1]['sale_price']  # sortowanie rosnąco


def test_pricing_empty_when_no_materials(db):
    from modules.client.shipping_service import get_shipping_pricing
    p = get_shipping_pricing()
    assert p == {'min_price': None, 'rows': []}
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m pytest tests/test_shipping_pricing_helper.py -v`
Expected: FAIL (`ImportError: cannot import name 'get_shipping_pricing'`).

- [ ] **Step 3: Dodaj helper**

Na końcu `modules/client/shipping_service.py` dodaj (upewnij się, że `PackagingMaterial` jest zaimportowany — jeśli nie, użyj importu lokalnego w funkcji):

```python
def get_shipping_pricing():
    """Cennik wysyłki z aktywnych materiałów (cena + gabaryt). Do podglądu u klienta."""
    from modules.orders.wms_models import PackagingMaterial
    mats = PackagingMaterial.query.filter(
        PackagingMaterial.is_active.is_(True),
        PackagingMaterial.sale_price.isnot(None),
        PackagingMaterial.size_category.isnot(None),
    ).order_by(PackagingMaterial.sale_price.asc()).all()
    rows = [{
        'size_category': m.size_category,
        'size_display': m.size_display,
        'type': m.type,
        'type_display': m.type_display,
        'sale_price': float(m.sale_price),
    } for m in mats]
    return {'min_price': rows[0]['sale_price'] if rows else None, 'rows': rows}
```

- [ ] **Step 4: Wstrzyknij do kontekstu strony klienta**

W `modules/client/shipping.py`, `shipping_requests_list` (~125), dodaj import przy górze pliku (jeśli brak) i przekaż do szablonu:

```python
    from modules.client.shipping_service import get_shipping_pricing
    return render_template(
        'client/shipping/requests_list.html',
        title='Zlecenia wysyłki',
        requests=requests,
        addresses=addresses,
        pricing=get_shipping_pricing(),
    )
```

- [ ] **Step 5: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_shipping_pricing_helper.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add modules/client/shipping_service.py modules/client/shipping.py tests/test_shipping_pricing_helper.py
git commit -m "feat(wysyłki): helper cennika z materiałów + kontekst strony klienta"
```

---

### Task 8: Frontend admin — pola ceny i gabarytu w modalu materiału

**Files:**
- Modify: `templates/admin/orders/wms_dashboard.html:473-564` (kolumny listy), `571-652` (modal)
- Modify: `static/js/pages/admin/wms-dashboard.js:37-113`
- Modify: `static/css/pages/admin/wms-dashboard.css`

**Interfaces:**
- Consumes: endpointy CRUD z Task 4 (przyjmują/zwracają `sale_price`, `size_category`).
- Produces: modal materiału ma input ceny sprzedaży (`#material-sale-price`) i select gabarytu (`#material-size`); lista pokazuje cenę sprzedaży i gabaryt.

- [ ] **Step 1: Dodaj pola do modalu materiału**

W `templates/admin/orders/wms_dashboard.html`, w `#material-modal`, po grupie `#material-cost` (~po linii 634) dodaj cenę sprzedaży i gabaryt (użyj istniejących klas form-group):

```html
                <div class="form-group">
                    <label for="material-sale-price">Cena sprzedaży wysyłki (zł)</label>
                    <input type="number" id="material-sale-price" class="form-input" step="0.01" min="0" placeholder="np. 19.49">
                </div>
                <div class="form-group">
                    <label for="material-size">Gabaryt (cennik)</label>
                    <select id="material-size" class="form-select">
                        <option value="">-- brak --</option>
                        {% for key, label in size_choices.items() %}
                        <option value="{{ key }}">{{ label }}</option>
                        {% endfor %}
                    </select>
                </div>
```

- [ ] **Step 2: Przekaż `size_choices` do szablonu**

W `modules/orders/wms.py`, w `wms_dashboard` (render kontekstu ~380-392), po `material_types=PackagingMaterial.TYPE_CHOICES` dodaj:

```python
        size_choices=PackagingMaterial.SIZE_CHOICES,
```

- [ ] **Step 3: Dodaj kolumny do listy materiałów**

W `templates/admin/orders/wms_dashboard.html`, w nagłówku desktop (~473-480) dodaj `<th>Cena sprz.</th>` i `<th>Gabaryt</th>` przed kolumną „Akcje"; w wierszu `.material-list-item` (~482-519) dodaj odpowiadające komórki:

```html
                    <td>{{ '%.2f zł'|format(material.sale_price) if material.sale_price else '—' }}</td>
                    <td>{{ material.size_display or '—' }}</td>
```

W kartach mobile (`.material-card`, ~528-564) dodaj linijkę, gdy dane istnieją, np.:

```html
                {% if material.sale_price or material.size_display %}
                <div class="material-card-row">
                    <span>Wysyłka: {{ '%.2f zł'|format(material.sale_price) if material.sale_price else '—' }}</span>
                    <span>{{ material.size_display or '' }}</span>
                </div>
                {% endif %}
```

- [ ] **Step 4: Rozszerz JS (fill + payload)**

W `static/js/pages/admin/wms-dashboard.js`, w `openMaterialModal` — w gałęzi edycji (po `material-cost`, ~61) dodaj:

```javascript
                    document.getElementById('material-sale-price').value = m.sale_price || '';
                    document.getElementById('material-size').value = m.size_category || '';
```

w gałęzi „dodaj nowy" (po `material-cost` reset, ~77) dodaj:

```javascript
            document.getElementById('material-sale-price').value = '';
            document.getElementById('material-size').value = '';
```

W `saveMaterial`, w obiekcie `data` (po `cost: ...`, ~107) dodaj:

```javascript
            sale_price: parseFloat(document.getElementById('material-sale-price').value) || null,
            size_category: document.getElementById('material-size').value || null,
```

- [ ] **Step 5: Dostrój CSS listy (light + dark)**

W `static/css/pages/admin/wms-dashboard.css` upewnij się, że nowe kolumny/wiersze mieszczą się (szerokości/`white-space`). Jeśli dodajesz nowy selektor, dodaj też wariant `[data-theme="dark"]`. Przykład, gdy potrzebny akcent ceny:

```css
.material-card-row { display: flex; justify-content: space-between; font-size: 0.85rem; color: #555; }
[data-theme="dark"] .material-card-row { color: rgba(255,255,255,0.7); }
```

- [ ] **Step 6: Weryfikacja w przeglądarce**

Uruchom dev server (preview_start `{name}` z `.claude/launch.json`; port 5001). Zaloguj jako admin, wejdź w WMS → materiały. Dodaj materiał „Karton A" z ceną 19.49 i gabarytem A; zapisz; edytuj — pola mają się wypełnić. Sprawdź `read_console_messages` (brak błędów) i listę (kolumny cena/gabaryt). Zrób screenshot listy + modalu (light i dark: `resize_window` z `colorScheme`).

- [ ] **Step 7: Commit**

```bash
git add templates/admin/orders/wms_dashboard.html static/js/pages/admin/wms-dashboard.js static/css/pages/admin/wms-dashboard.css modules/orders/wms.py
git commit -m "feat(wms): modal materiału — cena sprzedaży + gabaryt (light/dark)"
```

---

### Task 9: Frontend klient — sugerowane opakowanie, uwagi, cennik w wizardzie

**Files:**
- Modify: `templates/client/shipping/requests_list.html:226-275` (krok 2)
- Modify: `static/js/pages/client/shipping-requests.js:446-455`
- Modify: `static/css/pages/client/shipping-requests.css`

**Interfaces:**
- Consumes: `pricing` z kontekstu (Task 7); backend create przyjmuje `client_package_preference` + `client_notes` (Task 5).
- Produces: `submitShippingRequest` wysyła `client_package_preference` (`karton`/`koperta`/puste) i `client_notes`.

- [ ] **Step 1: Dodaj sekcję opcji wysyłki w kroku 2**

W `templates/client/shipping/requests_list.html`, w `#wizard-step-2` po `.address-selection` (przed zamknięciem `{% if addresses %}` bloku, ~po linii 264) dodaj:

```html
                    <div class="shipping-options">
                        <div class="form-group">
                            <label class="form-label">Sugerowane opakowanie</label>
                            <div class="package-pref-options">
                                <label class="package-pref-option">
                                    <input type="radio" name="package_pref" value="karton"> Karton
                                </label>
                                <label class="package-pref-option">
                                    <input type="radio" name="package_pref" value="koperta"> Koperta
                                </label>
                            </div>
                            <small class="form-hint">Ostateczne opakowanie i cenę ustala obsługa.</small>
                        </div>

                        <div class="form-group">
                            <label for="client-notes" class="form-label">Dodatkowe uwagi</label>
                            <textarea id="client-notes" class="form-control" rows="3" maxlength="2000"
                                      placeholder="np. proszę o dodatkowe zabezpieczenie"></textarea>
                        </div>

                        {% if pricing and pricing.min_price %}
                        <div class="shipping-pricing-box">
                            <div class="shipping-pricing-head">
                                Koszt wysyłki: od {{ '%.2f zł'|format(pricing.min_price) }}
                            </div>
                            <details class="shipping-pricing-details">
                                <summary>Zobacz cennik</summary>
                                <table class="shipping-pricing-table">
                                    <thead><tr><th>Gabaryt</th><th>Opakowanie</th><th>Cena</th></tr></thead>
                                    <tbody>
                                        {% for row in pricing.rows %}
                                        <tr>
                                            <td>{{ row.size_display }}</td>
                                            <td>{{ row.type_display }}</td>
                                            <td>{{ '%.2f zł'|format(row.sale_price) }}</td>
                                        </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </details>
                        </div>
                        {% endif %}
                    </div>
```

- [ ] **Step 2: Wyślij nowe pola w JS**

W `static/js/pages/client/shipping-requests.js`, w `submitShippingRequest` (~452), rozszerz `body` o odczyt preferencji i uwag:

```javascript
        body: JSON.stringify({
            order_ids: selectedOrders,
            address_id: parseInt(addressSelect.value),
            client_package_preference: (document.querySelector('input[name="package_pref"]:checked') || {}).value || null,
            client_notes: (document.getElementById('client-notes') || {}).value || null
        })
```

- [ ] **Step 3: Style (light + dark)**

W `static/css/pages/client/shipping-requests.css` dodaj style nowych elementów z wariantem dark:

```css
.shipping-options { margin-top: 20px; }
.package-pref-options { display: flex; gap: 16px; }
.package-pref-option { display: flex; align-items: center; gap: 6px; cursor: pointer; min-height: 44px; }
.form-hint { color: #777; font-size: 0.8rem; }
.shipping-pricing-box { margin-top: 12px; padding: 12px; border-radius: 8px; background: #f6f6f8; border: 1px solid #e0e0e0; }
.shipping-pricing-head { font-weight: 600; }
.shipping-pricing-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 0.85rem; }
.shipping-pricing-table th, .shipping-pricing-table td { padding: 4px 6px; text-align: left; border-bottom: 1px solid #eee; }

[data-theme="dark"] .form-hint { color: rgba(255,255,255,0.6); }
[data-theme="dark"] .shipping-pricing-box { background: rgba(255,255,255,0.05); border: 1px solid rgba(240,147,251,0.15); color: #fff; }
[data-theme="dark"] .shipping-pricing-table th, [data-theme="dark"] .shipping-pricing-table td { border-bottom: 1px solid rgba(255,255,255,0.1); }
```

> Touch target: opcje radio mają `min-height: 44px` (wymóg mobilny).

- [ ] **Step 4: Weryfikacja w przeglądarce**

Dev server (port 5001). Zaloguj jako klient z ≥1 zamówieniem kwalifikującym się do wysyłki. Otwórz „Zleć wysyłkę" → krok 2: widoczne radio karton/koperta, textarea uwag, box „od X zł" z rozwijaną tabelą. Utwórz zlecenie z wybraną kopertą i uwagą. `read_network_requests` — POST `/client/shipping/requests/create` ma w body `client_package_preference` i `client_notes`. Screenshot light + dark.

- [ ] **Step 5: Commit**

```bash
git add templates/client/shipping/requests_list.html static/js/pages/client/shipping-requests.js static/css/pages/client/shipping-requests.css
git commit -m "feat(wysyłki): wizard klienta — opakowanie, uwagi, podgląd cennika (light/dark)"
```

---

### Task 10: Frontend admin — wybór materiału w modalu zlecenia + podgląd pól klienta

**Files:**
- Modify: `templates/admin/orders/_shipping_request_modal.html:34-113`
- Modify: `static/js/pages/admin/shipping-requests.js:501-596` (fill), `800-851` (save)
- Modify: `static/css/pages/admin/shipping-requests-list.css`

**Interfaces:**
- Consumes: `/api/orders/packaging-materials` (Task 4, zwraca `sale_price`/`size_category`/`size_display`); GET zlecenia (Task 6, zwraca `packaging_material_id`, `client_package_preference`, `client_notes`); PUT przyjmuje `packaging_material_id` (Task 6); istniejące `distributeShippingCost()`.
- Produces: select materiału (`#srPackagingMaterial`); po wyborze podstawia `sale_price` do `#srTotalCost` + rozkłada na zamówienia i ustawia `#srParcelSize`; PUT zawiera `packaging_material_id`. Sekcja read-only z sugestią i uwagami klienta.

- [ ] **Step 1: Dodaj „Mini" do selecta gabarytu**

W `templates/admin/orders/_shipping_request_modal.html`, w `#srParcelSize` (105-110), dodaj opcję Mini na początku listy:

```html
                                    <option value="mini">Mini</option>
```

- [ ] **Step 2: Dodaj select materiału + podgląd pól klienta**

W `_shipping_request_modal.html`, po sekcji „Zamówienia w zleceniu" (po linii 48, przed sekcją „Adres dostawy") dodaj sekcję opakowania i podglądu klienta:

```html
                <div class="sr-section">
                    <h3>Opakowanie i wycena</h3>
                    <div class="form-group">
                        <label for="srPackagingMaterial">Materiał / cennik</label>
                        <select id="srPackagingMaterial" name="packaging_material_id" class="form-select">
                            <option value="">-- Wybierz materiał --</option>
                        </select>
                        <small class="sr-hint">Wybór podstawia cenę i gabaryt (można nadpisać ręcznie).</small>
                    </div>
                    <div class="sr-client-hints">
                        <div class="sr-client-hint-row">
                            <span class="sr-hint-label">Sugestia klienta</span>
                            <span class="sr-hint-value" id="srClientPreference">—</span>
                        </div>
                        <div class="sr-client-hint-row">
                            <span class="sr-hint-label">Uwagi klienta</span>
                            <span class="sr-hint-value" id="srClientNotes">—</span>
                        </div>
                    </div>
                </div>
```

- [ ] **Step 3: Załaduj materiały i wypełnij pola przy otwarciu modalu**

W `static/js/pages/admin/shipping-requests.js`, w `openShippingRequestModal` (po `document.getElementById('srModalId').value = data.id;`, ~516) dodaj wypełnienie podglądu klienta i selecta materiału:

```javascript
        // Podgląd pól klienta (read-only)
        const prefMap = { karton: 'Karton', koperta: 'Koperta' };
        document.getElementById('srClientPreference').textContent =
            prefMap[data.client_package_preference] || '—';
        document.getElementById('srClientNotes').textContent = data.client_notes || '—';

        // Załaduj listę materiałów do selecta i zaznacz aktualny
        const matSelect = document.getElementById('srPackagingMaterial');
        if (matSelect) {
            const resp = await fetch('/api/orders/packaging-materials');
            const matData = await resp.json();
            matSelect.innerHTML = '<option value="">-- Wybierz materiał --</option>';
            (matData.materials || []).forEach(m => {
                const price = m.sale_price != null ? ` — ${m.sale_price.toFixed(2)} zł` : '';
                const size = m.size_display ? ` (${m.size_display})` : '';
                const opt = document.createElement('option');
                opt.value = m.id;
                opt.textContent = `${m.type_display} ${m.name}${size}${price}`;
                opt.dataset.salePrice = m.sale_price != null ? m.sale_price : '';
                opt.dataset.sizeCategory = m.size_category || '';
                matSelect.appendChild(opt);
            });
            matSelect.value = data.packaging_material_id || '';
        }
```

> `openShippingRequestModal` jest już `async` (Task-referenced linia 501), więc `await fetch` jest dozwolony.

- [ ] **Step 4: Auto-podstawianie ceny i gabarytu po wyborze materiału**

W tym samym pliku dodaj listener (np. na końcu w bloku `DOMContentLoaded`, obok istniejącego handlera formularza ~801):

```javascript
    const matSelectEl = document.getElementById('srPackagingMaterial');
    if (matSelectEl) {
        matSelectEl.addEventListener('change', function() {
            const opt = this.options[this.selectedIndex];
            const salePrice = parseFloat(opt.dataset.salePrice);
            const size = opt.dataset.sizeCategory;
            if (!isNaN(salePrice) && salePrice > 0) {
                document.getElementById('srTotalCost').value = salePrice.toFixed(2);
                distributeShippingCost();   // rozłóż na zamówienia (istniejąca funkcja)
            }
            const parcel = document.getElementById('srParcelSize');
            if (parcel && size) parcel.value = size;
        });
    }
```

- [ ] **Step 5: Dołącz `packaging_material_id` do PUT**

W handlerze `submit` formularza, w obiekcie `formData` (po `payment_deadline`, ~842) dodaj:

```javascript
                packaging_material_id: parseInt(document.getElementById('srPackagingMaterial').value) || null,
```

- [ ] **Step 6: Style sekcji (light + dark)**

W `static/css/pages/admin/shipping-requests-list.css` dodaj:

```css
.sr-hint { display: block; color: #777; font-size: 0.8rem; margin-top: 4px; }
.sr-client-hints { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.sr-client-hint-row { display: flex; gap: 8px; }
.sr-hint-label { min-width: 120px; color: #666; font-size: 0.85rem; }
.sr-hint-value { font-size: 0.85rem; }

[data-theme="dark"] .sr-hint, [data-theme="dark"] .sr-hint-label { color: rgba(255,255,255,0.6); }
[data-theme="dark"] .sr-hint-value { color: #fff; }
```

- [ ] **Step 7: Weryfikacja w przeglądarce**

Dev server (5001), zaloguj jako admin. Wejdź w WMS → zakładka zleceń wysyłki (`/admin/orders/wms?tab=shipping`), otwórz zlecenie utworzone w Task 9. Sprawdź: podgląd „Sugestia klienta: Koperta" i „Uwagi klienta". Wybierz materiał „Karton A — 19.49 zł" → pole „Całkowity koszt" ustawia 19.49 i rozkłada na zamówienia, gabaryt = A. Zapisz. `read_network_requests` — PUT ma `packaging_material_id`. Po ponownym otwarciu select pokazuje wybrany materiał. Screenshot light + dark.

- [ ] **Step 8: Pełny zestaw testów backendu**

Run: `python -m pytest tests/ -k "shipping or packaging" -v`
Expected: PASS (bez regresji).

- [ ] **Step 9: Commit**

```bash
git add templates/admin/orders/_shipping_request_modal.html static/js/pages/admin/shipping-requests.js static/css/pages/admin/shipping-requests-list.css
git commit -m "feat(wysyłki): modal zlecenia — wybór materiału (cena+gabaryt) + podgląd pól klienta"
```

---

## Podsumowanie pokrycia tasków ClickUp

- **869e674tp (ceny):** Task 1 (sale_price), Task 4 (CRUD), Task 6 (materiał→koszt via order_costs), Task 7 (cennik klienta), Task 8/10 (UI).
- **869e674xk (karton/koperta):** Task 1 (type już jest + size), Task 2 (`client_package_preference`), Task 5 (zapis), Task 9 (radio klienta), Task 10 (select materiału admina).
- **869e674je (uwagi):** Task 2 (`client_notes`), Task 5 (zapis web+mobile), Task 9 (textarea klienta), Task 10 (podgląd u admina).

Po ukończeniu wszystkich tasków i przejściu testów: uruchom pełny `python -m pytest tests/ -q`, a przed zamknięciem tasków w ClickUp poczekaj na decyzję Konrada o deployu (push = auto-deploy).
