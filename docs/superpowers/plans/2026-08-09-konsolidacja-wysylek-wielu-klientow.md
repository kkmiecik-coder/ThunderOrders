# Konsolidacja wysyłek wielu klientów — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin może scalić zlecenia wysyłki kilku różnych klientów w jedną paczkę zbiorczą z wybranym adresem wiodącym, a każdy uczestnik zachowuje swoje zlecenie, swoje dane i swoje powiadomienia.

**Architecture:** Paczka zbiorcza to nowy `ShippingRequest` z nowym numerem — dzięki temu dziedziczy cały pipeline WMS bez zmian. Zlecenia źródłowe zostają w bazie ze wskaźnikiem `consolidated_into_id`, tracą swoje `ShippingRequestOrder` (przeniesione do zbiorczego, ze śladem `source_request_id`) i dostają propagowany status logistyczny. Statusy finansowe zostają indywidualne.

**Tech Stack:** Flask, SQLAlchemy, Flask-Migrate (Alembic), MariaDB, Jinja2, waniliowy JS, pytest.

Spec: [`docs/superpowers/specs/2026-08-09-konsolidacja-wysylek-wielu-klientow-design.md`](../specs/2026-08-09-konsolidacja-wysylek-wielu-klientow-design.md)
Zadanie ClickUp: [869eckz7u](https://app.clickup.com/t/869eckz7u)
Gałąź: `feat/konsolidacja-wysylek-wielu-klientow` (już utworzona, spec zacommitowany)

## Global Constraints

- **Testy uruchamiaj przez `./venv/bin/python -m pytest`** — gołe `pytest` pada na `No module named 'app'`, a `python` nie istnieje w PATH tej maszyny. Baseline: 951 testów zebranych, wszystkie przechodzą.
- **Importy modeli i managerów wewnątrz funkcji**, nigdy na górze modułu testowego ani w `email_manager.py` — `create_app()` musi najpierw zainicjalizować SQLAlchemy.
- **Każda zmiana CSS ma wariant light i dark** (`[data-theme="dark"]`). W `shipping-requests-list.css` sekcja dark zaczyna się w linii 696 — nowe reguły dark idą tam, nie obok reguł light.
- **Style modali wyłącznie w `static/css/components/modals.css`.**
- **Komunikaty błędów po polsku**, z numerem zlecenia i powodem. Nigdy gołego 403/500 bez treści.
- **`log_activity` przyjmuje dict, nie `json.dumps`** — styl z `wms_utils.py`. W `routes.py` jest błędny wariant z podwójnym kodowaniem; nie naśladować.
- **Nowy kod: docstringi i komentarze po polsku**, wyjaśniające *dlaczego*, nie *co*.
- **Encje pobieraj przez `db.session.get(Model, id)`**, nie `Model.query.get()` — repo przeszło tę migrację osobnym commitem.
- **Helpery nie commitują — commituje endpoint.** Wyjątek istniejący: `ship_shipping_request` commituje sam.
- **Nie pushuj.** Push do `main` uruchamia auto-deploy; wdrożenie na produkcję to osobna decyzja Konrada.

---

## Pliki

**Nowe:**

| Plik | Odpowiedzialność |
|---|---|
| `migrations/versions/<rev>_add_shipping_consolidation.py` | trzy kolumny + FK z `ondelete='SET NULL'` |
| `modules/orders/consolidation.py` | cała logika domenowa konsolidacji + `ConsolidationError` |
| `templates/emails/shipment_consolidated.html` | mail „Twoja wysyłka została połączona” |
| `tests/test_shipping_consolidation.py` | model, serwis, propagacja |
| `tests/test_shipping_consolidation_api.py` | endpointy admina |
| `tests/test_shipping_consolidation_client.py` | panel klienta web + mobile, wycieki |
| `tests/test_shipping_consolidation_notifications.py` | powiadomienia per uczestnik |

**Modyfikowane:** `modules/orders/models.py`, `modules/orders/routes.py`, `modules/orders/wms.py`, `modules/orders/wms_utils.py`, `modules/orders/wms_packing.py`, `modules/orders/inpost_export.py`, `modules/admin/payment_confirmations.py`, `modules/client/shipping.py`, `modules/client/shipping_service.py`, `modules/api_mobile/shipping_routes.py`, `utils/email_manager.py`, `utils/email_sender.py`, `utils/push_manager.py`, `templates/admin/orders/wms_dashboard.html`, `templates/client/shipping/requests_list.html`, `templates/client/orders/detail.html`, `static/js/pages/admin/shipping-requests.js`, `static/css/pages/admin/shipping-requests-list.css`, `static/css/components/modals.css`, `tests/test_shipment_sent_notification.py`.

---

## Task 1: Migracja i kolumny modelu

**Files:**
- Create: `migrations/versions/<rev>_add_shipping_consolidation.py`
- Modify: `modules/orders/models.py` (klasa `ShippingRequest` ok. 1443-1510, klasa `ShippingRequestOrder` ok. 1629-1648)
- Test: `tests/test_shipping_consolidation.py`

**Interfaces:**
- Produces: `ShippingRequest.consolidated_into_id`, `ShippingRequest.lead_source_request_id`, `ShippingRequest.consolidated_sources` (lista SR), `ShippingRequest.consolidated_into` (SR albo None), `ShippingRequest.lead_source` (SR albo None), `ShippingRequestOrder.source_request_id`.

- [ ] **Step 1: Napisz failujący test relacji**

W nowym pliku `tests/test_shipping_consolidation.py`:

```python
"""Konsolidacja zleceń wysyłki wielu klientów: model, serwis i propagacja statusów."""
import pytest


def _seed_sr_statuses(db):
    """Statusy zleceń wysyłki w kolejności łańcucha — sort_order decyduje o „najmniej zaawansowanym"."""
    from modules.orders.models import ShippingRequestStatus
    for i, (slug, name) in enumerate([
        ('czeka_na_wycene', 'Czeka na wycenę'),
        ('czeka_na_oplacenie', 'Czeka na opłacenie'),
        ('oplacone', 'Opłacone'),
        ('spakowane', 'Spakowane'),
        ('wyslane', 'Wysłane'),
        ('dostarczone', 'Dostarczone'),
    ]):
        db.session.add(ShippingRequestStatus(
            slug=slug, name=name, sort_order=i,
            is_active=True, is_initial=(slug == 'czeka_na_wycene'),
        ))
    db.session.commit()


def _sr(db, user, make_order, status='oplacone', orders_count=1):
    """Zlecenie wysyłki z zamówieniami danego klienta."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    sr = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=user.id, status=status, address_type='home',
        shipping_name=f'{user.first_name} {user.last_name}',
        shipping_address='ul. Kwiatowa 12', shipping_postal_code='30-001',
        shipping_city='Kraków',
    )
    db.session.add(sr)
    db.session.flush()
    orders = []
    for _ in range(orders_count):
        o = make_order(user)
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()
    return sr, orders


def test_konsolidacja_ma_relacje_do_zrodel(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home',
    )
    db.session.add(zbiorcze)
    db.session.flush()
    sr_a.consolidated_into_id = zbiorcze.id
    sr_b.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = sr_a.id
    db.session.commit()

    assert {s.id for s in zbiorcze.consolidated_sources} == {sr_a.id, sr_b.id}
    assert zbiorcze.lead_source.id == sr_a.id
    assert sr_b.consolidated_into.id == zbiorcze.id
```

- [ ] **Step 2: Uruchom test — ma paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

Oczekiwane: `AttributeError` / `TypeError` — `consolidated_into_id` nie istnieje.

- [ ] **Step 3: Dodaj kolumny i relacje do modelu**

W `modules/orders/models.py`, w klasie `ShippingRequest`, tuż po `payment_deadline`:

```python
    # Konsolidacja — paczka zbiorcza łącząca zlecenia kilku klientów (task 869eckz7u).
    # Na zleceniu ŹRÓDŁOWYM: wskazuje paczkę zbiorczą, w której jadą jego zamówienia.
    consolidated_into_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )
    # Na zleceniu ZBIORCZYM: które ze źródeł jest wiodące (adres, adresat, kontakt).
    lead_source_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )

    consolidated_into = db.relationship(
        'ShippingRequest', remote_side=[id], foreign_keys=[consolidated_into_id],
        backref=db.backref('consolidated_sources', lazy='select'),
    )
    lead_source = db.relationship(
        'ShippingRequest', remote_side=[id], foreign_keys=[lead_source_request_id],
    )
```

W klasie `ShippingRequestOrder`, po `shipping_cost`:

```python
    # Z którego zlecenia przyszło zamówienie. NULL = leży tu od początku.
    # Bez tego wypięcie i rozwiązanie konsolidacji nie wie, dokąd zwrócić zamówienie.
    source_request_id = db.Column(
        db.Integer, db.ForeignKey('shipping_requests.id', ondelete='SET NULL'), nullable=True
    )
```

- [ ] **Step 4: Uruchom test — ma przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 5: Wygeneruj i popraw migrację**

```bash
./venv/bin/python -m flask db migrate -m "Konsolidacja zleceń wysyłki"
```

Otwórz wygenerowany plik i upewnij się, że: `down_revision = '5d55aefadf79'` (aktualny head), każdy `create_foreign_key` ma `ondelete='SET NULL'`, a `downgrade()` jest symetryczny — `drop_constraint(type_='foreignkey')` przed `drop_column`. Docelowa treść:

```python
def upgrade():
    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('consolidated_into_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('lead_source_request_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_shipping_requests_consolidated_into', 'shipping_requests',
            ['consolidated_into_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key(
            'fk_shipping_requests_lead_source', 'shipping_requests',
            ['lead_source_request_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('shipping_request_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_request_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_shipping_request_orders_source_request', 'shipping_requests',
            ['source_request_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('shipping_request_orders', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shipping_request_orders_source_request', type_='foreignkey')
        batch_op.drop_column('source_request_id')

    with op.batch_alter_table('shipping_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_shipping_requests_lead_source', type_='foreignkey')
        batch_op.drop_constraint('fk_shipping_requests_consolidated_into', type_='foreignkey')
        batch_op.drop_column('lead_source_request_id')
        batch_op.drop_column('consolidated_into_id')
```

- [ ] **Step 6: Zastosuj migrację lokalnie i sprawdź obie strony**

```bash
./venv/bin/python -m flask db upgrade && ./venv/bin/python -m flask db downgrade && ./venv/bin/python -m flask db upgrade
```

Oczekiwane: trzy razy bez błędu. `downgrade` musi przejść — jeśli padnie na kluczu obcym, nazwy w `drop_constraint` nie zgadzają się z tymi z `upgrade`.

- [ ] **Step 7: Commit**

```bash
git add migrations/versions modules/orders/models.py tests/test_shipping_consolidation.py
git commit -m "feat(wms): kolumny konsolidacji zleceń wysyłki"
```

---

## Task 2: Właściwości modelu

**Files:**
- Modify: `modules/orders/models.py` (klasa `ShippingRequest` — przy istniejących `orders`, `orders_count`, `can_cancel`, `calculated_shipping_cost`; klasa `Order` — przy `shipping_request` ok. 685)
- Test: `tests/test_shipping_consolidation.py`

**Interfaces:**
- Consumes: kolumny z Task 1.
- Produces: `ShippingRequest.is_consolidation` → bool, `ShippingRequest.is_consolidated_source` → bool, `ShippingRequest.display_orders` → list[Order], `ShippingRequest.consolidation_participants` → list[dict] o kluczach `user`, `source_request`, `orders`; `Order.client_shipping_request` → ShippingRequest|None.

- [ ] **Step 1: Napisz failujące testy właściwości**

Dopisz do `tests/test_shipping_consolidation.py`:

```python
def _skonsoliduj(db, zbiorcze, zrodla, lead):
    """Ręczne złożenie konsolidacji — serwis powstaje dopiero w Task 3."""
    from modules.orders.models import ShippingRequestOrder
    for zr in zrodla:
        for ro in list(zr.request_orders):
            ro.shipping_request_id = zbiorcze.id
            ro.source_request_id = zr.id
        zr.consolidated_into_id = zbiorcze.id
    zbiorcze.lead_source_request_id = lead.id
    db.session.commit()
    db.session.expire_all()


def test_display_orders_zwraca_tylko_wlasne_zamowienia(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, orders_count=2)
    sr_b, orders_b = _sr(db, b, make_order, orders_count=1)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    assert zbiorcze.is_consolidation is True
    assert sr_b.is_consolidated_source is True
    assert {o.id for o in sr_b.display_orders} == {orders_b[0].id}
    assert {o.id for o in sr_a.display_orders} == {o.id for o in orders_a}
    assert len(zbiorcze.display_orders) == 3


def test_uczestnicy_pogrupowani_po_wlascicielu(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, orders_count=2)
    sr_b, _ = _sr(db, b, make_order, orders_count=1)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    uczestnicy = zbiorcze.consolidation_participants
    assert len(uczestnicy) == 2
    assert [len(u['orders']) for u in uczestnicy] == [2, 1]
    assert uczestnicy[0]['source_request'].id == sr_a.id


def test_zamowienie_pokazuje_klientowi_jego_zlecenie(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    zamowienie_b = orders_b[0]
    # WMS musi widzieć paczkę zbiorczą…
    assert zamowienie_b.shipping_request.id == zbiorcze.id
    # …ale klient B swoje własne zlecenie, nie cudzy adres.
    assert zamowienie_b.client_shipping_request.id == sr_b.id


def test_skonsolidowanego_zlecenia_klient_nie_anuluje(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, status='czeka_na_wycene')
    sr_b, _ = _sr(db, b, make_order, status='czeka_na_wycene')

    from modules.orders.models import ShippingRequest
    assert sr_a.can_cancel is True  # przed konsolidacją wolno

    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='czeka_na_wycene', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    # Status początkowy, brak kosztu i trackingu — a mimo to nie wolno.
    assert sr_a.can_cancel is False
    assert sr_b.can_cancel is False
    assert zbiorcze.can_cancel is False


def test_koszt_zrodlowego_liczony_z_jego_zamowien(db, make_user, make_order):
    from decimal import Decimal
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)
    orders_a[0].shipping_cost = Decimal('12.00')
    orders_b[0].shipping_cost = Decimal('8.00')
    db.session.commit()

    from modules.orders.models import ShippingRequest
    zbiorcze = ShippingRequest(
        request_number=ShippingRequest.generate_request_number(),
        user_id=a.id, status='oplacone', address_type='home')
    db.session.add(zbiorcze)
    db.session.flush()
    _skonsoliduj(db, zbiorcze, [sr_a, sr_b], sr_a)

    assert sr_b.calculated_shipping_cost == Decimal('8.00')
    assert zbiorcze.calculated_shipping_cost == Decimal('20.00')
    assert sr_b.orders_count == 1
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 3: Dodaj właściwości do `ShippingRequest`**

Obok istniejącej `orders` (ok. 1512):

```python
    @property
    def is_consolidation(self):
        """Paczka zbiorcza: ma podpięte zlecenia źródłowe. Jedyne źródło prawdy —
        nie ma osobnej flagi w bazie, żeby stan nie mógł się rozjechać z relacją."""
        return bool(self.consolidated_sources)

    @property
    def is_consolidated_source(self):
        """Zlecenie oddane do paczki zbiorczej — nie jest już samodzielną paczką."""
        return self.consolidated_into_id is not None

    @property
    def display_orders(self):
        """Zamówienia, które należą do TEGO zlecenia z punktu widzenia jego właściciela.

        Po konsolidacji wiersze junction wiszą przy zleceniu zbiorczym, więc źródłowe
        musi odnaleźć swoje zamówienia po source_request_id. Wszystko, co pokazujemy
        klientowi, idzie tędy — self.orders dałoby mu zamówienia obcych osób.
        """
        if self.consolidated_into_id and self.consolidated_into:
            return [
                ro.order for ro in self.consolidated_into.request_orders
                if ro.source_request_id == self.id and ro.order
            ]
        return self.orders

    @property
    def consolidation_participants(self):
        """Uczestnicy paczki zbiorczej, pogrupowani po właścicielu.

        Kolejność: zlecenie wiodące pierwsze, reszta wg numeru zlecenia. Z tego
        korzystają karta w WMS, modal, maile i pushe — jedno miejsce grupowania.
        """
        if not self.is_consolidation:
            return []
        po_zrodle = {}
        for ro in self.request_orders:
            if not ro.order or not ro.source_request_id:
                continue
            po_zrodle.setdefault(ro.source_request_id, []).append(ro.order)

        wynik = []
        for source in self.consolidated_sources:
            wynik.append({
                'user': source.user,
                'source_request': source,
                'orders': po_zrodle.get(source.id, []),
            })
        wynik.sort(key=lambda u: (
            u['source_request'].id != self.lead_source_request_id,
            u['source_request'].request_number or '',
        ))
        return wynik
```

- [ ] **Step 4: Przepnij `can_cancel`, `orders_count` i `calculated_shipping_cost`**

W `can_cancel`, jako **pierwszy** warunek (przed sprawdzeniem `status_rel`):

```python
        # Paczka zbiorcza to ustalenie między kilkoma osobami i magazynem — rozmontować
        # ją może wyłącznie admin, niezależnie od statusu, kosztu i numeru przesyłki.
        if self.is_consolidated_source or self.is_consolidation:
            return False
```

W `orders_count` zamień `len(self.request_orders)` na `len(self.display_orders)`.

W `calculated_shipping_cost` zamień pętlę `for ro in self.request_orders:` na:

```python
        for order in self.display_orders:
            if order.shipping_cost:
                total += Decimal(str(order.shipping_cost))
```

- [ ] **Step 5: Dodaj `client_shipping_request` do `Order`**

W `modules/orders/models.py`, tuż po istniejącej właściwości `shipping_request` (ok. 691):

```python
    @property
    def client_shipping_request(self):
        """Zlecenie wysyłki, które należy POKAZAĆ właścicielowi tego zamówienia.

        shipping_request zwraca zlecenie, w którym zamówienie fizycznie leży — po
        konsolidacji jest to paczka zbiorcza z adresem i zamówieniami innej osoby.
        Każdy widok klienta musi używać tej właściwości, inaczej pokaże cudze dane.
        """
        if not self.shipping_request_orders:
            return None
        ro = self.shipping_request_orders[0]
        if ro.source_request_id:
            from modules.orders.models import ShippingRequest
            return db.session.get(ShippingRequest, ro.source_request_id)
        return ro.shipping_request
```

- [ ] **Step 6: Uruchom testy — mają przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 7: Uruchom pełny zestaw — nic nie mogło się zepsuć**

```bash
./venv/bin/python -m pytest -q
```

Oczekiwane: 951 przechodzi (plus nowe). Zmiana `orders_count` i `calculated_shipping_cost` dotyka istniejących widoków — jeśli coś padnie, `display_orders` musi zwracać dokładnie to samo co `orders` dla zleceń bez konsolidacji.

- [ ] **Step 8: Commit**

```bash
git add modules/orders/models.py tests/test_shipping_consolidation.py
git commit -m "feat(wms): właściwości konsolidacji na modelu zlecenia i zamówienia"
```

---

## Task 3: Serwis konsolidacji — tworzenie paczki

**Files:**
- Create: `modules/orders/consolidation.py`
- Test: `tests/test_shipping_consolidation.py`

**Interfaces:**
- Consumes: właściwości z Task 2.
- Produces: `ConsolidationError(message, status_code=400)`, `waliduj_do_konsolidacji(requests, target=None) -> None`, `utworz_konsolidacje(request_ids, lead_request_id, user=None) -> ShippingRequest`, `status_najmniej_zaawansowany(requests) -> str`.

- [ ] **Step 1: Napisz failujące testy tworzenia**

```python
def test_konsolidacja_tworzy_nowy_numer_i_przenosi_zamowienia(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order, orders_count=2)
    sr_b, orders_b = _sr(db, b, make_order, orders_count=1)

    from modules.orders.consolidation import utworz_konsolidacje
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    assert zbiorcze.request_number not in (sr_a.request_number, sr_b.request_number)
    assert len(zbiorcze.request_orders) == 3
    assert zbiorcze.user_id == a.id
    assert zbiorcze.shipping_city == sr_a.shipping_city
    assert sr_a.consolidated_into_id == zbiorcze.id
    assert sr_b.consolidated_into_id == zbiorcze.id
    # Ślad pochodzenia — bez niego wypięcie nie wie, dokąd wrócić.
    zrodla = {ro.order_id: ro.source_request_id for ro in zbiorcze.request_orders}
    assert zrodla[orders_b[0].id] == sr_b.id
    assert zrodla[orders_a[0].id] == sr_a.id


def test_status_zbiorczego_to_najmniej_zaawansowany(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, status='oplacone')
    sr_b, _ = _sr(db, b, make_order, status='czeka_na_oplacenie')

    from modules.orders.consolidation import utworz_konsolidacje
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    assert zbiorcze.status == 'czeka_na_oplacenie'
    # Opłacone zlecenie NIE cofa się — finanse są indywidualne.
    assert sr_a.status == 'oplacone'


def test_odmowa_dla_jednego_zlecenia_i_wyslanych(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order, status='wyslane')

    from modules.orders.consolidation import utworz_konsolidacje, ConsolidationError
    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id], lead_request_id=sr_a.id)
    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)


def test_odmowa_konsolidacji_zagniezdzonej(db, make_user, make_order):
    _seed_sr_statuses(db)
    a, b, c = make_user(), make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    sr_c, _ = _sr(db, c, make_order)

    from modules.orders.consolidation import utworz_konsolidacje, ConsolidationError
    utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()

    with pytest.raises(ConsolidationError):
        utworz_konsolidacje([sr_a.id, sr_c.id], lead_request_id=sr_c.id)


def test_przepiecie_nie_kasuje_wierszy_przez_kaskade(db, make_user, make_order):
    """Regres: request_orders ma cascade='all, delete-orphan'. Odczytanie kolekcji
    przed przepięciem i późniejszy delete kasował właśnie przeniesione wiersze."""
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order, orders_count=2)
    sr_b, _ = _sr(db, b, make_order, orders_count=2)

    from modules.orders.consolidation import utworz_konsolidacje
    from modules.orders.models import ShippingRequestOrder
    zbiorcze = utworz_konsolidacje([sr_a.id, sr_b.id], lead_request_id=sr_a.id)
    db.session.commit()
    db.session.expire_all()

    assert ShippingRequestOrder.query.filter_by(shipping_request_id=zbiorcze.id).count() == 4
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q -k konsolidacja
```

Oczekiwane: `ModuleNotFoundError: No module named 'modules.orders.consolidation'`.

- [ ] **Step 3: Napisz `modules/orders/consolidation.py`**

```python
"""Konsolidacja zleceń wysyłki — paczka zbiorcza dla kilku klientów (task 869eckz7u).

Paczka zbiorcza jest zwykłym ShippingRequest, dzięki czemu dziedziczy cały pipeline
WMS. Zlecenia źródłowe zostają w bazie: tracą swoje wiersze junction (przeniesione
do zbiorczego ze śladem source_request_id), ale nadal są tym, co widzi ich właściciel.

Funkcje NIE commitują — commituje endpoint, zgodnie z konwencją modułu.
"""
from extensions import db


class ConsolidationError(Exception):
    """Odmowa operacji na konsolidacji. status_code czytany wprost przez endpoint."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# Paczka, która już pojechała, nie podlega scalaniu ani rozmontowaniu.
STATUSY_ZAMKNIETE = ('wyslane', 'dostarczone')


def _sesja_wms_blokujaca(sr):
    """Zwraca aktywną/wstrzymaną sesję WMS trzymającą to zlecenie, albo None."""
    from modules.orders.wms_models import WmsSession, WmsSessionShippingRequest
    return (
        WmsSessionShippingRequest.query.join(WmsSession)
        .filter(
            WmsSessionShippingRequest.shipping_request_id == sr.id,
            WmsSession.status.in_(['active', 'paused']),
        )
        .first()
    )


def status_najmniej_zaawansowany(requests):
    """Status paczki zbiorczej — najniższy sort_order ze scalanych zleceń.

    Paczka nie może być „opłacona", dopóki którykolwiek uczestnik nie zapłacił;
    WMS blokuje wysyłkę nieopłaconych, więc to samo z siebie wstrzymuje wysyłkę.
    """
    from modules.orders.models import ShippingRequestStatus
    slugi = [sr.status for sr in requests if sr.status]
    if not slugi:
        return 'czeka_na_wycene'
    kolejnosc = {
        s.slug: s.sort_order
        for s in ShippingRequestStatus.query.filter(ShippingRequestStatus.slug.in_(slugi)).all()
    }
    return min(slugi, key=lambda s: kolejnosc.get(s, 0))


def waliduj_do_konsolidacji(requests, target=None):
    """Sprawdza, czy zlecenia wolno scalić. Rzuca ConsolidationError z powodem."""
    if len(requests) < 2 and target is None:
        raise ConsolidationError('Wybierz co najmniej 2 zlecenia do konsolidacji.')

    for sr in requests:
        if sr.status in STATUSY_ZAMKNIETE:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} zostało już wysłane — nie można go konsolidować.',
                status_code=409,
            )
        if sr.is_consolidated_source:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} należy już do innej paczki zbiorczej.',
                status_code=409,
            )
        if sr.is_consolidation and sr is not target:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} jest paczką zbiorczą — '
                f'nie łączymy paczek zbiorczych ze sobą.',
                status_code=409,
            )
        sesja = _sesja_wms_blokujaca(sr)
        if sesja:
            raise ConsolidationError(
                f'Zlecenie {sr.request_number} jest w otwartej sesji WMS #{sesja.session_id} — '
                f'dokończ ją albo anuluj.',
                status_code=409,
            )


def _kopiuj_adres(zbiorcze, lead):
    """Adres, adresat i właściciel paczki idą z wiodącego. Kopia, nie referencja —
    eksport InPost i etykiety czytają pola zlecenia wprost."""
    zbiorcze.user_id = lead.user_id
    for pole in (
        'address_type', 'shipping_name', 'shipping_address', 'shipping_postal_code',
        'shipping_city', 'shipping_voivodeship', 'shipping_country',
        'pickup_courier', 'pickup_point_id', 'pickup_address',
        'pickup_postal_code', 'pickup_city',
    ):
        setattr(zbiorcze, pole, getattr(lead, pole))


def _nowy_numer():
    """Numer paczki zbiorczej. Generator czyta ostatni wiersz bez blokady, a admin
    tworzy zlecenia równolegle do klientów — przy kolizji próbujemy ponownie."""
    from sqlalchemy.exc import IntegrityError
    from modules.orders.models import ShippingRequest
    for _ in range(5):
        numer = ShippingRequest.generate_request_number()
        if not ShippingRequest.query.filter_by(request_number=numer).first():
            return numer
    raise ConsolidationError('Nie udało się nadać numeru paczki — spróbuj ponownie.', 500)


def utworz_konsolidacje(request_ids, lead_request_id, user=None):
    """Tworzy paczkę zbiorczą z podanych zleceń. Zwraca nowy ShippingRequest."""
    from modules.orders.models import ShippingRequest

    requests = ShippingRequest.query.filter(ShippingRequest.id.in_(request_ids)).all()
    if len(requests) != len(set(request_ids)):
        raise ConsolidationError('Nie znaleziono części wybranych zleceń.', status_code=404)

    waliduj_do_konsolidacji(requests)

    lead = next((sr for sr in requests if sr.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError('Zlecenie wiodące musi być jednym ze scalanych zleceń.')

    zbiorcze = ShippingRequest(
        request_number=_nowy_numer(),
        status=status_najmniej_zaawansowany(requests),
    )
    _kopiuj_adres(zbiorcze, lead)
    db.session.add(zbiorcze)
    db.session.flush()

    # Przepinamy przez ORM, po jednym wierszu. Bulk .update() z pominięciem ORM
    # zostawiłby w sesji nieaktualną kolekcję request_orders, a ta ma
    # cascade='all, delete-orphan' — kasowanie źródła zabrałoby przeniesione wiersze.
    for zrodlo in requests:
        for ro in list(zrodlo.request_orders):
            ro.shipping_request_id = zbiorcze.id
            ro.source_request_id = zrodlo.id
        zrodlo.request_orders = []
        zrodlo.consolidated_into_id = zbiorcze.id

    zbiorcze.lead_source_request_id = lead.id
    db.session.flush()
    return zbiorcze
```

- [ ] **Step 4: Uruchom testy — mają przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 5: Commit**

```bash
git add modules/orders/consolidation.py tests/test_shipping_consolidation.py
git commit -m "feat(wms): serwis tworzenia paczki zbiorczej"
```

---

## Task 4: Serwis — dopięcie, wypięcie, zmiana wiodącego, rozwiązanie

**Files:**
- Modify: `modules/orders/consolidation.py`
- Test: `tests/test_shipping_consolidation.py`

**Interfaces:**
- Produces: `dopnij_do_konsolidacji(target, request_ids) -> ShippingRequest`, `wypnij_zlecenie(target, source_id) -> bool` (True gdy konsolidacja została rozwiązana), `zmien_wiodace(target, lead_request_id) -> None`, `rozwiaz_konsolidacje(target) -> list[ShippingRequest]`.

- [ ] **Step 1: Napisz failujące testy edycji**

```python
def _konsolidacja(db, make_user, make_order, ile=2, orders_count=1):
    from modules.orders.consolidation import utworz_konsolidacje
    zrodla = []
    for _ in range(ile):
        sr, _o = _sr(db, make_user(), make_order, orders_count=orders_count)
        zrodla.append(sr)
    zbiorcze = utworz_konsolidacje([s.id for s in zrodla], lead_request_id=zrodla[0].id)
    db.session.commit()
    return zbiorcze, zrodla


def test_zmiana_wiodacego_przepisuje_adres_i_wlasciciela(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.shipping_city = 'Gdańsk'
    db.session.commit()

    from modules.orders.consolidation import zmien_wiodace
    zmien_wiodace(zbiorcze, sr_b.id)
    db.session.commit()

    assert zbiorcze.lead_source_request_id == sr_b.id
    assert zbiorcze.user_id == sr_b.user_id
    assert zbiorcze.shipping_city == 'Gdańsk'


def test_wypiecie_zwraca_zamowienia_do_zrodla(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3)
    sr_c = zrodla[2]

    from modules.orders.consolidation import wypnij_zlecenie
    rozwiazana = wypnij_zlecenie(zbiorcze, sr_c.id)
    db.session.commit()
    db.session.expire_all()

    assert rozwiazana is False
    assert sr_c.consolidated_into_id is None
    assert len(sr_c.request_orders) == 1
    assert len(zbiorcze.request_orders) == 2


def test_wypiecie_przedostatniego_rozwiazuje_konsolidacje(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze_id = zbiorcze.id

    from modules.orders.consolidation import wypnij_zlecenie
    from modules.orders.models import ShippingRequest
    rozwiazana = wypnij_zlecenie(zbiorcze, sr_b.id)
    db.session.commit()

    assert rozwiazana is True
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    assert sr_a.consolidated_into_id is None
    assert len(sr_a.request_orders) == 1


def test_rozwiazanie_zwraca_wszystko_i_kasuje_zbiorcze(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3, orders_count=2)
    zbiorcze_id = zbiorcze.id

    from modules.orders.consolidation import rozwiaz_konsolidacje
    from modules.orders.models import ShippingRequest
    zwrocone = rozwiaz_konsolidacje(zbiorcze)
    db.session.commit()
    db.session.expire_all()

    assert len(zwrocone) == 3
    assert db.session.get(ShippingRequest, zbiorcze_id) is None
    for sr in zrodla:
        assert sr.consolidated_into_id is None
        assert len(sr.request_orders) == 2


def test_edycja_zablokowana_po_spakowaniu(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from modules.orders.consolidation import wypnij_zlecenie, rozwiaz_konsolidacje, ConsolidationError
    with pytest.raises(ConsolidationError):
        wypnij_zlecenie(zbiorcze, sr_b.id)
    with pytest.raises(ConsolidationError):
        rozwiaz_konsolidacje(zbiorcze)
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 3: Dopisz funkcje edycyjne do `consolidation.py`**

```python
# Po spakowaniu skład paczki odpowiada temu, co fizycznie leży w kartonie —
# zmiana w systemie byłaby kłamstwem wobec magazynu.
STATUSY_BEZ_EDYCJI = ('spakowane', 'wyslane', 'dostarczone')


def _sprawdz_edytowalnosc(target):
    if not target.is_consolidation:
        raise ConsolidationError(
            f'Zlecenie {target.request_number} nie jest paczką zbiorczą.', status_code=404)
    if target.status in STATUSY_BEZ_EDYCJI:
        raise ConsolidationError(
            f'Paczka {target.request_number} jest już spakowana — '
            f'nie można zmieniać jej składu.', status_code=409)
    sesja = _sesja_wms_blokujaca(target)
    if sesja:
        raise ConsolidationError(
            f'Paczka {target.request_number} jest w otwartej sesji WMS #{sesja.session_id} — '
            f'dokończ ją albo anuluj.', status_code=409)


def zmien_wiodace(target, lead_request_id):
    """Przełącza zlecenie wiodące — przepisuje adres, adresata i właściciela paczki."""
    _sprawdz_edytowalnosc(target)
    lead = next((s for s in target.consolidated_sources if s.id == lead_request_id), None)
    if lead is None:
        raise ConsolidationError('Wskazane zlecenie nie należy do tej paczki.', status_code=404)
    _kopiuj_adres(target, lead)
    target.lead_source_request_id = lead.id


def dopnij_do_konsolidacji(target, request_ids):
    """Dokłada kolejne zlecenia do istniejącej paczki zbiorczej."""
    from modules.orders.models import ShippingRequest
    _sprawdz_edytowalnosc(target)

    nowe = ShippingRequest.query.filter(ShippingRequest.id.in_(request_ids)).all()
    if not nowe:
        raise ConsolidationError('Nie znaleziono zleceń do dopięcia.', status_code=404)
    waliduj_do_konsolidacji(nowe, target=target)

    for zrodlo in nowe:
        if zrodlo.id == target.id:
            raise ConsolidationError('Nie można dopiąć paczki do samej siebie.')
        for ro in list(zrodlo.request_orders):
            ro.shipping_request_id = target.id
            ro.source_request_id = zrodlo.id
        zrodlo.request_orders = []
        zrodlo.consolidated_into_id = target.id

    target.status = status_najmniej_zaawansowany(list(target.consolidated_sources) + nowe)
    db.session.flush()
    return target


def _oddaj_zamowienia(target, zrodlo):
    """Zwraca wiersze junction do zlecenia źródłowego, zgodnie ze śladem pochodzenia."""
    for ro in list(target.request_orders):
        if ro.source_request_id == zrodlo.id:
            ro.shipping_request_id = zrodlo.id
            ro.source_request_id = None
    zrodlo.consolidated_into_id = None


def rozwiaz_konsolidacje(target):
    """Rozmontowuje paczkę: zamówienia wracają do źródeł, zlecenie zbiorcze znika."""
    _sprawdz_edytowalnosc(target)
    zrodla = list(target.consolidated_sources)
    for zrodlo in zrodla:
        _oddaj_zamowienia(target, zrodlo)
    target.lead_source_request_id = None
    db.session.flush()
    # Kolekcja jest już pusta, więc delete-orphan nie ma czego zabrać.
    db.session.delete(target)
    return zrodla


def wypnij_zlecenie(target, source_id):
    """Wypina jedno zlecenie z paczki. Zwraca True, gdy paczka została rozwiązana,
    bo z jednym uczestnikiem przestaje mieć sens."""
    _sprawdz_edytowalnosc(target)
    zrodlo = next((s for s in target.consolidated_sources if s.id == source_id), None)
    if zrodlo is None:
        raise ConsolidationError('Wskazane zlecenie nie należy do tej paczki.', status_code=404)

    _oddaj_zamowienia(target, zrodlo)
    db.session.flush()

    pozostale = [s for s in target.consolidated_sources if s.id != source_id]
    if len(pozostale) <= 1:
        rozwiaz_konsolidacje(target)
        return True

    if target.lead_source_request_id == source_id:
        zmien_wiodace(target, pozostale[0].id)
    target.status = status_najmniej_zaawansowany(pozostale)
    return False
```

- [ ] **Step 4: Uruchom testy — mają przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 5: Commit**

```bash
git add modules/orders/consolidation.py tests/test_shipping_consolidation.py
git commit -m "feat(wms): edycja paczki zbiorczej — dopięcie, wypięcie, rozwiązanie"
```

---

## Task 5: Propagacja statusu i trackingu na zlecenia źródłowe

**Files:**
- Modify: `modules/orders/consolidation.py`, `modules/orders/routes.py` (`admin_update_shipping_request`, auto-status po wycenie, `admin_bulk_status_shipping_requests`), `modules/orders/wms_utils.py` (`ship_shipping_request`, `reopen_orders_for_wms`), `modules/orders/wms_packing.py` (`update_sr_after_packing`), `modules/admin/payment_confirmations.py` (`_check_sr_auto_oplacone`)
- Test: `tests/test_shipping_consolidation.py`

**Interfaces:**
- Produces: `propaguj_na_zrodla(sr) -> list[ShippingRequest]` (zlecenia, którym zmienił się stan), `przelicz_status_zbiorczego(source) -> None`.

**Kierunki:** logistyka (`spakowane`/`wyslane`/`dostarczone` + `tracking_number` + `courier`) płynie **w dół** ze zbiorczego na źródłowe. Finanse (`czeka_na_wycene`/`czeka_na_oplacenie`/`oplacone`) zostają indywidualne, a status zbiorczego przelicza się **w górę** jako najmniej zaawansowany ze źródeł.

- [ ] **Step 1: Napisz failujące testy propagacji**

```python
def test_wyslanie_paczki_propaguje_status_i_tracking(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'wyslane'
    zbiorcze.tracking_number = '622334455'
    zbiorcze.courier = 'inpost'

    from modules.orders.consolidation import propaguj_na_zrodla
    zmienione = propaguj_na_zrodla(zbiorcze)
    db.session.commit()

    assert len(zmienione) == 2
    for sr in (sr_a, sr_b):
        assert sr.status == 'wyslane'
        assert sr.tracking_number == '622334455'
        assert sr.courier == 'inpost'


def test_propagacja_nie_cofa_statusu_finansowego(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'oplacone'
    sr_b.status = 'czeka_na_oplacenie'
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()

    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()

    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'czeka_na_oplacenie'


def test_oplacenie_zrodla_podnosi_status_zbiorczego(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'czeka_na_oplacenie'
    sr_b.status = 'czeka_na_oplacenie'
    zbiorcze.status = 'czeka_na_oplacenie'
    db.session.commit()

    from modules.orders.consolidation import przelicz_status_zbiorczego
    sr_a.status = 'oplacone'
    przelicz_status_zbiorczego(sr_a)
    db.session.commit()
    assert zbiorcze.status == 'czeka_na_oplacenie'  # B jeszcze nie zapłacił

    sr_b.status = 'oplacone'
    przelicz_status_zbiorczego(sr_b)
    db.session.commit()
    assert zbiorcze.status == 'oplacone'


def test_cofniecie_do_wms_propaguje_w_dol(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()
    assert sr_a.status == 'spakowane'

    zbiorcze.status = 'oplacone'
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()
    assert sr_a.status == 'oplacone'
    assert sr_b.status == 'oplacone'
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 3: Dopisz propagację do `consolidation.py`**

```python
# Statusy opisujące jedną fizyczną paczkę — te zjeżdżają na zlecenia źródłowe.
STATUSY_LOGISTYCZNE = ('spakowane', 'wyslane', 'dostarczone')


def propaguj_na_zrodla(sr):
    """Kopiuje stan paczki zbiorczej na jej zlecenia źródłowe.

    Idą tylko statusy logistyczne plus tracking i kurier. Statusy finansowe
    zostają indywidualne — inaczej zlecenie klienta, który już zapłacił, cofnęłoby
    się na „czeka na opłacenie" razem z mailem o wpłacie.

    Cofnięcie paczki do WMS też tędy przechodzi: gdy zbiorcze wraca ze „spakowane"
    na „oplacone", źródłowe muszą zejść razem z nim.

    Zwraca listę zleceń, którym faktycznie coś się zmieniło.
    """
    if not sr.is_consolidation:
        return []

    zmienione = []
    for zrodlo in sr.consolidated_sources:
        zmiana = False
        if sr.status in STATUSY_LOGISTYCZNE or zrodlo.status in STATUSY_LOGISTYCZNE:
            if zrodlo.status != sr.status:
                zrodlo.status = sr.status
                zmiana = True
        if zrodlo.tracking_number != sr.tracking_number:
            zrodlo.tracking_number = sr.tracking_number
            zmiana = True
        if zrodlo.courier != sr.courier:
            zrodlo.courier = sr.courier
            zmiana = True
        if zmiana:
            zmienione.append(zrodlo)
    return zmienione


def przelicz_status_zbiorczego(source):
    """Podnosi status paczki po zmianie statusu finansowego jednego z uczestników.

    Woła się po stronie zdarzeń płatniczych: paczka jest opłacona dopiero wtedy,
    gdy zapłacili wszyscy. Paczki po spakowaniu już nie ruszamy.
    """
    if not source.is_consolidated_source:
        return
    zbiorcze = source.consolidated_into
    if not zbiorcze or zbiorcze.status in STATUSY_LOGISTYCZNE:
        return
    zbiorcze.status = status_najmniej_zaawansowany(list(zbiorcze.consolidated_sources))
```

- [ ] **Step 4: Uruchom testy — mają przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q
```

- [ ] **Step 5: Wepnij propagację we wszystkie osiem miejsc zapisu**

Audyt naliczył osiem niezależnych writerów statusu lub trackingu. W każdym z nich, **po** zapisie a **przed** commitem, dodaj wywołanie:

```python
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(sr)
```

Miejsca (nazwy funkcji, bo numery linii przesuną się w trakcie pracy):

| Plik | Funkcja | Uwaga |
|---|---|---|
| `modules/orders/routes.py` | `admin_update_shipping_request` | po zapisie `status`/`courier`/`tracking_number` |
| `modules/orders/routes.py` | `admin_update_shipping_request` | także po auto-przejściu `czeka_na_wycene` → `czeka_na_oplacenie` |
| `modules/orders/routes.py` | `admin_bulk_status_shipping_requests` | w pętli po `sr`, przed zbiorczym commitem |
| `modules/orders/wms_utils.py` | `ship_shipping_request` | przed `db.session.commit()` w środku funkcji |
| `modules/orders/wms_utils.py` | `reopen_orders_for_wms` | po zdjęciu `spakowane` |
| `modules/orders/wms_packing.py` | `update_sr_after_packing` | po ustawieniu `sr.status = 'spakowane'` |
| `modules/admin/payment_confirmations.py` | `_check_sr_auto_oplacone` | **w tej samej transakcji** — funkcja ma własny `db.session.commit()`, wywołanie musi być przed nim |

W `_check_sr_auto_oplacone` dodatkowo, po znalezieniu zlecenia:

```python
    # Zlecenie źródłowe: opłacenie podnosi status paczki, gdy zapłacili już wszyscy.
    from modules.orders.consolidation import przelicz_status_zbiorczego
    przelicz_status_zbiorczego(sr)
```

- [ ] **Step 6: Test integracyjny wysyłki przez WMS**

```python
def test_wyslanie_przez_wms_propaguje_na_zrodla(db, make_user, make_order):
    from tests.test_wms_ship_and_reopen import _seed_statuses
    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'spakowane'
    db.session.commit()

    from modules.orders.wms_utils import ship_shipping_request
    ship_shipping_request(zbiorcze, courier='inpost', tracking_number='622999888')
    db.session.expire_all()

    assert sr_a.status == 'wyslane'
    assert sr_b.tracking_number == '622999888'
```

- [ ] **Step 7: Uruchom pełny zestaw**

```bash
./venv/bin/python -m pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add modules/orders/consolidation.py modules/orders/routes.py modules/orders/wms_utils.py modules/orders/wms_packing.py modules/admin/payment_confirmations.py tests/test_shipping_consolidation.py
git commit -m "feat(wms): propagacja statusu i trackingu paczki zbiorczej na zlecenia źródłowe"
```

---

## Task 6: Guardy — puste zlecenie źródłowe nie udaje paczki

**Files:**
- Modify: `modules/orders/wms_packing.py` (`update_sr_after_packing`), `modules/admin/payment_confirmations.py` (`_check_sr_auto_oplacone`), `modules/orders/wms.py` (`_wms_lock_blocking_session`, `admin_ship_shipping_request`), `modules/orders/routes.py` (`admin_update_shipping_request` — auto-status)
- Test: `tests/test_shipping_consolidation.py`

**Problem:** `all([])` zwraca `True`, a `sr.orders` zlecenia źródłowego jest puste. Bez guardów źródłowe samo wskakuje na `spakowane` i `oplacone`, a blokada „w sesji WMS" przestaje działać.

- [ ] **Step 1: Napisz failujące testy**

```python
def test_puste_zrodlowe_nie_wskakuje_na_spakowane(db, make_user, make_order):
    from tests.test_wms_ship_and_reopen import _seed_statuses
    _seed_sr_statuses(db)
    _seed_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'oplacone'
    db.session.commit()

    from modules.orders.wms_packing import update_sr_after_packing
    zamowienie = zbiorcze.request_orders[0].order
    zamowienie.status = 'spakowane'
    db.session.commit()
    update_sr_after_packing(zamowienie)
    db.session.commit()

    # Zlecenie źródłowe nie ma własnych zamówień — all([]) nie może go „spakować".
    assert sr_a.status != 'spakowane' or zbiorcze.status == 'spakowane'
    assert sr_a.status == zbiorcze.status


def test_puste_zrodlowe_nie_wskakuje_na_oplacone(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.status = 'czeka_na_oplacenie'
    db.session.commit()

    from modules.admin.payment_confirmations import _check_sr_auto_oplacone
    # Zamówienie należy do zbiorczego; źródłowe jest puste i nie ma czego zatwierdzać.
    zamowienie = zbiorcze.request_orders[0].order
    _check_sr_auto_oplacone(zamowienie)
    db.session.commit()

    assert sr_a.status == 'czeka_na_oplacenie'
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q -k puste
```

- [ ] **Step 3: Dodaj guardy**

W `modules/orders/wms_packing.py`, w `update_sr_after_packing`, tuż po pobraniu `sr`:

```python
    # Zlecenie oddane do paczki zbiorczej nie ma własnych zamówień — all([]) uznałby
    # je za spakowane bez niczego fizycznego. Jego stan przychodzi z propagacji.
    if not sr or sr.is_consolidated_source:
        return
```

W `modules/admin/payment_confirmations.py`, w `_check_sr_auto_oplacone`, po znalezieniu `sr`:

```python
    # Puste zlecenie źródłowe przeszłoby pętlę bez ani jednej iteracji i zostało
    # uznane za opłacone. Płatności rozstrzygamy na paczce zbiorczej.
    if sr.is_consolidated_source:
        from modules.orders.consolidation import przelicz_status_zbiorczego
        przelicz_status_zbiorczego(sr)
        return
```

W `modules/orders/wms.py`, w `_wms_lock_blocking_session`, na początku:

```python
    # Źródłowe nie ma własnych zamówień, więc pętla po sr.orders nie wykryłaby
    # blokady. Sesję trzyma paczka zbiorcza — pytamy o nią.
    if sr.is_consolidated_source and sr.consolidated_into:
        sr = sr.consolidated_into
```

W `modules/orders/wms.py`, w `admin_ship_shipping_request`, po pobraniu `sr` i przed sprawdzeniem statusu:

```python
    if sr.is_consolidated_source:
        return jsonify({
            'success': False,
            'message': f'Zlecenie {sr.request_number} jedzie w paczce zbiorczej '
                       f'{sr.consolidated_into.request_number} — wyślij tamtą paczkę.',
        }), 409
```

- [ ] **Step 4: Uruchom testy — mają przejść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add modules/orders/wms_packing.py modules/admin/payment_confirmations.py modules/orders/wms.py tests/test_shipping_consolidation.py
git commit -m "fix(wms): puste zlecenie źródłowe nie przechodzi bramek gotowości"
```

---

## Task 7: Endpointy admina

**Files:**
- Modify: `modules/orders/routes.py` (obok istniejących endpointów zleceń; usuń `admin_bulk_merge_shipping_requests`)
- Test: `tests/test_shipping_consolidation_api.py`

**Interfaces:**
- Consumes: cały `modules/orders/consolidation.py`.
- Produces: `GET /admin/orders/shipping-requests/consolidation-preview?ids=1,2`, `POST /admin/orders/shipping-requests/consolidate`, `POST /admin/orders/shipping-requests/<id>/consolidation/lead`, `.../detach`, `.../dissolve`.

- [ ] **Step 1: Napisz failujące testy endpointów**

Nowy plik `tests/test_shipping_consolidation_api.py`:

```python
"""Endpointy admina do konsolidacji zleceń wysyłki."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def test_preview_zwraca_zlecenia_z_adresami(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.get(f'/admin/orders/shipping-requests/consolidation-preview?ids={sr_a.id},{sr_b.id}')
    assert r.status_code == 200
    dane = r.get_json()
    assert dane['success'] is True
    assert len(dane['requests']) == 2
    assert dane['requests'][0]['full_address']
    assert dane['requests'][0]['client_name']
    assert dane['blocked'] == []


def test_konsolidacja_endpointem(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    db.session.expire_all()
    assert sr_a.consolidated_into_id is not None


def test_konsolidacja_odrzuca_wyslane(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order, status='wyslane')
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code == 409
    assert 'wysłane' in r.get_json()['error']


def test_zmiana_wiodacego_wypiecie_i_rozwiazanie(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3)
    login(_admin(make_user))

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/lead',
                    json={'lead_request_id': zrodla[1].id})
    assert r.status_code == 200

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/detach',
                    json={'source_id': zrodla[2].id})
    assert r.status_code == 200
    assert r.get_json()['dissolved'] is False

    r = client.post(f'/admin/orders/shipping-requests/{zbiorcze.id}/consolidation/dissolve', json={})
    assert r.status_code == 200


def test_endpointy_wymagaja_admina(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, _ = _sr(db, a, make_order)
    sr_b, _ = _sr(db, b, make_order)
    login(make_user())  # zwykły klient

    r = client.post('/admin/orders/shipping-requests/consolidate', json={
        'ids': [sr_a.id, sr_b.id], 'lead_request_id': sr_a.id,
    })
    assert r.status_code in (302, 403)


def test_stary_bulk_merge_zniknal(db, client, login, make_user):
    login(_admin(make_user))
    r = client.post('/admin/orders/shipping-requests/bulk-merge', json={'ids': [1, 2]})
    assert r.status_code == 404
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_api.py -q
```

- [ ] **Step 3: Usuń stary endpoint scalania**

W `modules/orders/routes.py` skasuj całą funkcję `admin_bulk_merge_shipping_requests` razem z dekoratorem trasy `/admin/orders/shipping-requests/bulk-merge`.

- [ ] **Step 4: Dopisz pięć endpointów**

W `modules/orders/routes.py`, w miejscu po usuniętym `bulk-merge`:

```python
@orders_bp.route('/admin/orders/shipping-requests/consolidation-preview')
@login_required
@role_required('admin', 'mod')
def admin_consolidation_preview():
    """Dane do modalu konsolidacji — pełne adresy i powody blokady.

    Modal nie może karmić się danymi z kart: karty nie mają kompletu adresów,
    a stan mógł się zmienić od załadowania strony.
    """
    from modules.orders.consolidation import waliduj_do_konsolidacji, ConsolidationError

    surowe = request.args.get('ids', '')
    ids = [int(x) for x in surowe.split(',') if x.strip().isdigit()]
    if not ids:
        return jsonify({'error': 'Nie wskazano zleceń'}), 400

    requests_list = ShippingRequest.query.filter(ShippingRequest.id.in_(ids)).all()

    pozycje = []
    for sr in requests_list:
        pozycje.append({
            'id': sr.id,
            'request_number': sr.request_number,
            'client_name': f'{sr.user.first_name or ""} {sr.user.last_name or ""}'.strip()
                           if sr.user else 'Brak klienta',
            'client_email': sr.user.email if sr.user else None,
            'client_phone': sr.user.phone if sr.user else None,
            'full_address': sr.full_address,
            'address_type': sr.address_type,
            'status': sr.status,
            'status_name': sr.status_display_name,
            'orders_count': len(sr.display_orders),
            'is_consolidation': sr.is_consolidation,
            'has_tracking': bool(sr.tracking_number),
            # Potrzebne modalowi w trybie zarządzania gotową paczką (Task 14).
            'source_ids': [s.id for s in sr.consolidated_sources],
            'lead_source_request_id': sr.lead_source_request_id,
        })

    blokady = []
    try:
        waliduj_do_konsolidacji(requests_list)
    except ConsolidationError as e:
        blokady.append(e.message)

    return jsonify({'success': True, 'requests': pozycje, 'blocked': blokady})


@orders_bp.route('/admin/orders/shipping-requests/consolidate', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_consolidate_shipping_requests():
    """Tworzy paczkę zbiorczą albo dopina zlecenia do istniejącej."""
    from modules.orders.consolidation import (
        utworz_konsolidacje, dopnij_do_konsolidacji, ConsolidationError)

    data = request.get_json() or {}
    ids = [int(x) for x in data.get('ids', [])]
    lead_id = data.get('lead_request_id')
    target_id = data.get('target_id')

    try:
        if target_id:
            target = db.session.get(ShippingRequest, int(target_id))
            if not target:
                return jsonify({'error': 'Nie znaleziono paczki zbiorczej'}), 404
            dopnij_do_konsolidacji(target, [i for i in ids if i != target.id])
            zbiorcze = target
        else:
            if not lead_id:
                return jsonify({'error': 'Wskaż zlecenie wiodące'}), 400
            zbiorcze = utworz_konsolidacje(ids, int(lead_id))
        db.session.commit()
    except ConsolidationError as e:
        db.session.rollback()
        return jsonify({'error': e.message}), e.status_code
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'Błąd konsolidacji zleceń {ids}: {e}')
        return jsonify({'error': 'Nie udało się utworzyć paczki zbiorczej'}), 500

    _powiadom_o_konsolidacji(zbiorcze)

    log_activity(
        user=current_user, action='shipping_requests_consolidated',
        entity_type='shipping_request', entity_id=zbiorcze.id,
        new_value={
            'consolidation_number': zbiorcze.request_number,
            'source_numbers': [s.request_number for s in zbiorcze.consolidated_sources],
            'lead_request_id': zbiorcze.lead_source_request_id,
        },
    )
    return jsonify({
        'success': True,
        'message': f'Utworzono paczkę zbiorczą {zbiorcze.request_number} '
                   f'z {len(zbiorcze.consolidated_sources)} zleceń',
        'consolidation_id': zbiorcze.id,
    })


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>/consolidation/lead',
                 methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_consolidation_change_lead(shipping_request_id):
    """Przełącza zlecenie wiodące — zmienia adres i adresata paczki."""
    from modules.orders.consolidation import zmien_wiodace, ConsolidationError

    target = db.session.get(ShippingRequest, shipping_request_id)
    if not target:
        return jsonify({'error': 'Nie znaleziono zlecenia'}), 404

    data = request.get_json() or {}
    try:
        zmien_wiodace(target, int(data.get('lead_request_id', 0)))
        db.session.commit()
    except ConsolidationError as e:
        db.session.rollback()
        return jsonify({'error': e.message}), e.status_code

    log_activity(
        user=current_user, action='shipping_request_consolidation_lead_changed',
        entity_type='shipping_request', entity_id=target.id,
        new_value={'lead_request_id': target.lead_source_request_id},
    )
    return jsonify({
        'success': True,
        'message': f'Adresatem paczki {target.request_number} jest teraz {target.shipping_name}',
    })


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>/consolidation/detach',
                 methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_consolidation_detach(shipping_request_id):
    """Wypina jedno zlecenie z paczki. Przy jednym uczestniku paczka znika."""
    from modules.orders.consolidation import wypnij_zlecenie, ConsolidationError

    target = db.session.get(ShippingRequest, shipping_request_id)
    if not target:
        return jsonify({'error': 'Nie znaleziono zlecenia'}), 404

    data = request.get_json() or {}
    numer = target.request_number
    try:
        rozwiazana = wypnij_zlecenie(target, int(data.get('source_id', 0)))
        db.session.commit()
    except ConsolidationError as e:
        db.session.rollback()
        return jsonify({'error': e.message}), e.status_code

    log_activity(
        user=current_user, action='shipping_request_consolidation_detached',
        entity_type='shipping_request',
        new_value={'consolidation_number': numer, 'source_id': data.get('source_id'),
                   'dissolved': rozwiazana},
    )
    return jsonify({
        'success': True, 'dissolved': rozwiazana,
        'message': ('Paczka została rozwiązana — został tylko jeden uczestnik'
                    if rozwiazana else 'Zlecenie wypięte z paczki'),
    })


@orders_bp.route('/admin/orders/shipping-requests/<int:shipping_request_id>/consolidation/dissolve',
                 methods=['POST'])
@login_required
@role_required('admin', 'mod')
def admin_consolidation_dissolve(shipping_request_id):
    """Rozmontowuje paczkę zbiorczą — wszystkie zamówienia wracają do swoich zleceń."""
    from modules.orders.consolidation import rozwiaz_konsolidacje, ConsolidationError

    target = db.session.get(ShippingRequest, shipping_request_id)
    if not target:
        return jsonify({'error': 'Nie znaleziono zlecenia'}), 404

    numer = target.request_number
    try:
        zrodla = rozwiaz_konsolidacje(target)
        numery = [s.request_number for s in zrodla]
        db.session.commit()
    except ConsolidationError as e:
        db.session.rollback()
        return jsonify({'error': e.message}), e.status_code

    log_activity(
        user=current_user, action='shipping_request_consolidation_dissolved',
        entity_type='shipping_request',
        new_value={'consolidation_number': numer, 'restored_numbers': numery},
    )
    return jsonify({
        'success': True,
        'message': f'Paczka {numer} rozwiązana — zlecenia wróciły do samodzielnej wysyłki',
    })
```

Tymczasowa zaślepka powiadomienia (właściwa treść w Task 12) — dopisz obok:

```python
def _powiadom_o_konsolidacji(zbiorcze):
    """Powiadomienia dla uczestników paczki. Pełna implementacja w utils/email_manager.py."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    try:
        EmailManager.notify_shipment_consolidated(zbiorcze)
        PushManager.notify_shipment_consolidated(zbiorcze)
    except Exception as e:
        current_app.logger.error(
            f'Błąd powiadomienia o konsolidacji {zbiorcze.request_number}: {e}')
```

- [ ] **Step 5: Uruchom testy — endpointy mają działać (powiadomienia jeszcze nie istnieją, ale są w try/except)**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_api.py -q
```

- [ ] **Step 6: Commit**

```bash
git add modules/orders/routes.py tests/test_shipping_consolidation_api.py
git commit -m "feat(wms): endpointy konsolidacji zleceń, usunięcie bulk-merge"
```

---

## Task 8: Listy i eksport — źródłowe znikają z widoku admina

**Files:**
- Modify: `modules/orders/wms.py` (`build_shipping_requests_query`, `shipping_requests_filtered_ids`, `wms_dashboard` — `sr_total_count`), `modules/orders/routes.py` (`admin_export_shipping_requests_inpost`)
- Test: `tests/test_shipping_consolidation_api.py`

- [ ] **Step 1: Napisz failujące testy**

```python
def test_lista_wms_pokazuje_paczke_zamiast_zrodel(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/admin/orders/wms')
    tresc = r.get_data(as_text=True)
    assert zbiorcze.request_number in tresc
    assert zrodla[0].request_number not in tresc


def test_filtr_scalone_pokazuje_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/admin/orders/wms?consolidation=sources')
    tresc = r.get_data(as_text=True)
    assert zrodla[0].request_number in tresc


def test_filtered_ids_pomija_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.get('/api/orders/shipping-requests/filtered-ids')
    ids = {int(x['id']) for x in r.get_json()['requests']}
    assert zbiorcze.id in ids
    assert zrodla[0].id not in ids


def test_eksport_inpost_nie_dubluje_etykiet(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    zbiorcze.parcel_size = 'A'
    for zr in zrodla:
        zr.parcel_size = 'A'
    db.session.commit()
    login(_admin(make_user))

    r = client.post('/admin/orders/shipping-requests/export-inpost',
                    json={'ids': [zbiorcze.id] + [z.id for z in zrodla]})
    assert r.status_code == 200
    csv_text = r.get_json()['csv']
    # Jedna paczka fizyczna = jeden wiersz, niezależnie od liczby zaznaczonych zleceń.
    assert csv_text.count(zbiorcze.request_number) <= 1
    for zr in zrodla:
        assert zr.request_number not in csv_text
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_api.py -q -k "lista or filtr or filtered or eksport"
```

- [ ] **Step 3: Dodaj filtry**

W `modules/orders/wms.py`, w `build_shipping_requests_query`, zmień sygnaturę na
`build_shipping_requests_query(status_filter=None, order_type_filter=None, search=None, consolidation_filter=None)`
i zaraz po `query = ShippingRequest.query` dodaj:

```python
    from sqlalchemy.orm import selectinload
    from modules.auth.models import User as _User

    if consolidation_filter == 'sources':
        # Podgląd zleceń oddanych do paczek zbiorczych — normalnie ukrytych.
        query = query.filter(ShippingRequest.consolidated_into_id.isnot(None))
    else:
        # Domyślnie admin widzi jedną paczkę zamiast N pozycji tej samej przesyłki.
        query = query.filter(ShippingRequest.consolidated_into_id.is_(None))

    # Karta zbiorcza pokazuje uczestników — bez tego mamy N+1 na źródłach i userach.
    query = query.options(
        selectinload(ShippingRequest.consolidated_sources).selectinload(ShippingRequest.user)
    )
```

W `wms_dashboard` przekaż nowy filtr:

```python
    sr_consolidation_filter = request.args.get('consolidation', '')
    sr_query = build_shipping_requests_query(
        sr_status_filter, order_type_filter, sr_search, sr_consolidation_filter)
```

oraz zmień licznik:

```python
    sr_total_count = ShippingRequest.query.filter(
        ShippingRequest.consolidated_into_id.is_(None)).count()
```

i dodaj `sr_consolidation_filter=sr_consolidation_filter` do `render_template`.

W `shipping_requests_filtered_ids` przekaż `request.args.get('consolidation', '')` jako czwarty argument.

W `admin_export_shipping_requests_inpost`, do zapytania dołóż warunek:

```python
    shipping_requests = ShippingRequest.query.filter(
        ShippingRequest.id.in_(ids),
        # Zlecenie źródłowe ma własny adres i gabaryt, więc trafiłoby do pliku
        # jako druga przesyłka na tę samą paczkę — realny koszt u kuriera.
        ShippingRequest.consolidated_into_id.is_(None),
    ).order_by(ShippingRequest.request_number).all()
```

- [ ] **Step 4: Uruchom testy**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_api.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add modules/orders/wms.py modules/orders/routes.py tests/test_shipping_consolidation_api.py
git commit -m "feat(wms): zlecenia źródłowe znikają z listy, zaznaczania i eksportu InPost"
```

---

## Task 9: Panel klienta — filtr list i blokada anulowania

**Files:**
- Modify: `modules/client/shipping.py` (`shipping_requests_list`, `shipping_requests_list_json`), `modules/client/shipping_service.py` (`cancel_request`), `modules/api_mobile/shipping_routes.py` (`shipping_requests_list`, `_serialize_request`, `shipping_request_cancel`)
- Test: `tests/test_shipping_consolidation_client.py`

**Uwaga:** zapytania listujące są **trzy**, nie dwa — `shipping.py` ma dodatkowo `/client/shipping/requests/list` (JSON). Trasa jest dziś bez konsumenta w UI, ale odpowiada na żądania, więc liczy się jako powierzchnia wycieku.

- [ ] **Step 1: Napisz failujące testy**

Nowy plik `tests/test_shipping_consolidation_client.py`:

```python
"""Panel klienta przy paczce zbiorczej — brak wycieków i blokada anulowania."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


def test_klient_wiodacy_nie_widzi_paczki_zbiorczej(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(sr_a.user)

    tresc = client.get('/client/shipping/requests').get_data(as_text=True)
    assert sr_a.request_number in tresc
    assert zbiorcze.request_number not in tresc


def test_json_listy_tez_nie_ujawnia_zbiorczego(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    login(sr_a.user)

    dane = client.get('/client/shipping/requests/list').get_json()
    numery = {r['request_number'] for r in dane['requests']}
    assert zbiorcze.request_number not in numery
    assert sr_a.request_number in numery


def test_mobile_nie_ujawnia_zbiorczego(db, client, make_user, make_order):
    from test_mobile_api_shipping import _auth
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    # Logujemy właściciela zlecenia wiodącego — to on jest user_id paczki zbiorczej.
    sr_a.user.set_password('Haslo123!')
    db.session.commit()
    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': sr_a.user.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    dane = client.get('/api/mobile/v1/shipping/requests',
                      headers={'Authorization': f'Bearer {token}'}).get_json()
    numery = {r['request_number'] for r in dane['data']['requests']}
    assert zbiorcze.request_number not in numery
    assert sr_a.request_number in numery


def test_klient_nie_anuluje_skonsolidowanego_web(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.status = 'czeka_na_wycene'
    db.session.commit()
    login(sr_b.user)

    r = client.post(f'/client/shipping/requests/{sr_b.id}/cancel',
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    assert r.status_code == 400
    assert 'zbiorcz' in r.get_json()['error'].lower()

    from modules.orders.models import ShippingRequest
    assert db.session.get(ShippingRequest, sr_b.id) is not None


def test_klient_nie_anuluje_skonsolidowanego_mobile(db, client, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_b.user.set_password('Haslo123!')
    sr_b.status = 'czeka_na_wycene'
    db.session.commit()

    r = client.post('/api/mobile/v1/auth/login',
                    json={'email': sr_b.user.email, 'password': 'Haslo123!'})
    token = r.get_json()['data']['access_token']
    r = client.post(f'/api/mobile/v1/shipping/requests/{sr_b.id}/cancel',
                    headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 409
    assert r.get_json()['error']['code'] == 'consolidated'


def test_klient_zrodlowy_widzi_swoje_zamowienia_i_tracking(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.status = 'wyslane'
    zbiorcze.tracking_number = '622111222'
    zbiorcze.courier = 'inpost'
    from modules.orders.consolidation import propaguj_na_zrodla
    propaguj_na_zrodla(zbiorcze)
    db.session.commit()
    login(sr_b.user)

    tresc = client.get('/client/shipping/requests').get_data(as_text=True)
    assert '622111222' in tresc
    assert sr_b.display_orders[0].order_number in tresc
    # …ale nie zamówienie drugiego klienta.
    assert sr_a.display_orders[0].order_number not in tresc
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_client.py -q
```

- [ ] **Step 3: Dodaj filtr do trzech zapytań**

W `modules/client/shipping_service.py` dopisz wspólny helper (konwencja parytetu web/mobile):

```python
def list_client_requests(user_id):
    """Zlecenia wysyłki widoczne dla klienta.

    Paczki zbiorcze są bytem magazynu: mają user_id klienta wiodącego, więc bez
    tego filtra zobaczyłby w panelu zamówienia obcych osób. Każdy uczestnik widzi
    swoje zlecenie źródłowe — ono zostaje.
    """
    from modules.orders.models import ShippingRequest
    return (
        ShippingRequest.query
        .filter_by(user_id=user_id)
        .filter(~ShippingRequest.consolidated_sources.any())
        .order_by(ShippingRequest.created_at.desc())
        .all()
    )
```

Podmień na nie zapytania w `modules/client/shipping.py` (`shipping_requests_list` i `shipping_requests_list_json`) oraz w `modules/api_mobile/shipping_routes.py` (`shipping_requests_list`).

W `shipping_requests_list_json` zamień też `req.request_orders[:3]` na `req.display_orders[:3]`, a w `_serialize_request` (mobile) użyj `req.display_orders` zamiast `req.orders`.

- [ ] **Step 4: Zablokuj anulowanie w serwisie**

W `modules/client/shipping_service.py`, w `cancel_request`, **przed** `db.session.delete(req)`:

```python
    # Paczka zbiorcza to ustalenie kilku osób i magazynu — klient nie może się z niej
    # wypisać sam. Blokada musi być tutaj, bo cancel_request KASUJE rekord, a
    # request_orders ma cascade='all, delete-orphan'.
    if req.is_consolidated_source or req.is_consolidation:
        return False, {'code': 'consolidated'}
```

- [ ] **Step 5: Zmapuj nowy kod błędu w obu kanałach**

W `modules/client/shipping.py`, w `shipping_requests_cancel`, dodaj gałąź przed generyczną:

```python
        if err['code'] == 'consolidated':
            return jsonify({
                'success': False,
                'error': 'To zlecenie jedzie w paczce zbiorczej — aby je anulować, '
                         'skontaktuj się z obsługą.',
            }), 400
```

W `modules/api_mobile/shipping_routes.py`, w `shipping_request_cancel`, przed zwinięciem do `cannot_cancel`:

```python
        if err['code'] == 'consolidated':
            return json_err(
                'consolidated',
                'To zlecenie jedzie w paczce zbiorczej — aby je anulować, '
                'skontaktuj się z obsługą.',
                409,
            )
```

- [ ] **Step 6: Uruchom testy**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_client.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add modules/client/ modules/api_mobile/shipping_routes.py tests/test_shipping_consolidation_client.py
git commit -m "feat(klient): paczka zbiorcza ukryta w panelu, anulowanie tylko przez admina"
```

---

## Task 10: Szablony klienta na `client_shipping_request`

**Files:**
- Modify: `templates/client/orders/detail.html` (ok. 483, 484, 502, 549), `modules/orders/models.py` (`shipping_icon_state` ok. 822, `shipping_request_other_orders` ok. 699), `modules/orders/routes.py` (mapa śledzenia, ok. 1873), `templates/client/shipping/requests_list.html`
- Test: `tests/test_shipping_consolidation_client.py`

- [ ] **Step 1: Napisz failujący test wycieku na karcie zamówienia**

```python
def test_karta_zamowienia_nie_pokazuje_cudzego_adresu(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    sr_a.shipping_address = 'ul. Tajna 7'
    sr_a.shipping_name = 'Adresat Wiodacy'
    from modules.orders.consolidation import zmien_wiodace
    zmien_wiodace(zbiorcze, sr_a.id)
    db.session.commit()

    zamowienie_b = sr_b.display_orders[0]
    login(sr_b.user)
    tresc = client.get(f'/client/orders/{zamowienie_b.id}').get_data(as_text=True)

    assert 'ul. Tajna 7' not in tresc
    assert 'Adresat Wiodacy' not in tresc
    assert sr_a.display_orders[0].order_number not in tresc
    assert sr_b.request_number in tresc
```

- [ ] **Step 2: Uruchom test — ma paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_client.py -q -k karta_zamowienia
```

- [ ] **Step 3: Przełącz szablon karty zamówienia**

W `templates/client/orders/detail.html` zmień **obie** linie — warunek i przypisanie (`{% if %}` i `{% set %}` czytają właściwość niezależnie):

```jinja
{% if order.client_shipping_request %}
{% set sr = order.client_shipping_request %}
```

Sekcja z listą zamówień zlecenia (ok. 502) ma iterować `sr.display_orders`, a nie `sr.orders`.

- [ ] **Step 4: Przełącz `shipping_icon_state` i mapę śledzenia**

W `modules/orders/models.py`, w `shipping_icon_state`, zamień `self.shipping_request` na `self.client_shipping_request` — ta właściwość renderuje tooltip na liście zamówień klienta (`templates/client/orders/list.html:208` i `:370`), więc naprawa idzie w modelu, nie w dwóch miejscach szablonu.

W `shipping_request_other_orders` zamień na:

```python
    @property
    def shipping_request_other_orders(self):
        """Inne zamówienia klienta z tego samego zlecenia — WYŁĄCZNIE jego własne.
        Dla paczki zbiorczej surowe request_orders zwróciłyby zamówienia obcych osób."""
        sr = self.client_shipping_request
        if not sr:
            return []
        return [o for o in sr.display_orders if o.id != self.id]
```

W `modules/orders/routes.py`, w widoku mapy śledzenia (ok. 1873), zamień `order.shipping_request` na `order.client_shipping_request`.

- [ ] **Step 5: Dodaj oznaczenie paczki zbiorczej na karcie klienta**

W `templates/client/shipping/requests_list.html`, w nagłówku karty zlecenia:

```jinja
{% if req.is_consolidated_source %}
<span class="req-consolidated-badge" title="Twoje zamówienia jadą w jednej paczce z zamówieniami innej osoby">
    Wysyłka zbiorcza
</span>
{% endif %}
```

Pod adresem, gdy zlecenie jest źródłowe:

```jinja
{% if req.is_consolidated_source and req.consolidated_into and req.consolidated_into.shipping_name %}
<p class="req-consolidated-note">
    Paczka jedzie na adres: {{ req.consolidated_into.shipping_name }}
</p>
{% endif %}
```

Pętla po zamówieniach w tym szablonie ma używać `req.display_orders`.

Przycisk „Anuluj" — tooltip zależny od powodu:

```jinja
title="{% if req.is_consolidated_source %}Zlecenie jedzie w paczce zbiorczej — skontaktuj się z obsługą{% else %}Zlecenie w trakcie realizacji - nie można anulować{% endif %}"
```

- [ ] **Step 6: Dodaj style badge'a (light + dark)**

W `static/css/pages/client/shipping-requests.css`:

```css
.req-consolidated-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    background: rgba(102, 126, 234, 0.12);
    color: #667eea;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.req-consolidated-note {
    margin: 4px 0 0;
    font-size: 12px;
    color: #666;
}

[data-theme="dark"] .req-consolidated-badge {
    background: rgba(240, 147, 251, 0.15);
    color: #f093fb;
}

[data-theme="dark"] .req-consolidated-note {
    color: rgba(255, 255, 255, 0.6);
}
```

- [ ] **Step 7: Uruchom testy**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_client.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add templates/client modules/orders/models.py modules/orders/routes.py static/css/pages/client/shipping-requests.css tests/test_shipping_consolidation_client.py
git commit -m "fix(klient): widoki zamówień pokazują własne zlecenie zamiast paczki zbiorczej"
```

---

## Task 11: Powiadomienia o wysyłce per uczestnik

**Files:**
- Modify: `utils/email_manager.py` (`notify_shipment_sent`, `notify_shipping_status_change`), `utils/email_sender.py` (nowa `prepare_shipment_sent_email`), `utils/push_manager.py` (`notify_shipment_sent`, `notify_shipping_status_change`), `tests/test_shipment_sent_notification.py`
- Test: `tests/test_shipping_consolidation_notifications.py`

**Problem:** dziś mail idzie do `sr.user` z listą **wszystkich** zamówień zlecenia (wyciek dla paczki zbiorczej), a dla pustego zlecenia źródłowego funkcja robi wczesny return (cisza dla pozostałych uczestników).

- [ ] **Step 1: Napisz failujące testy**

Nowy plik `tests/test_shipping_consolidation_notifications.py`:

```python
"""Powiadomienia o paczce zbiorczej — każdy uczestnik dostaje swoje, bez cudzych danych."""
import pytest
from test_shipping_consolidation import _seed_sr_statuses, _sr, _konsolidacja  # noqa: E402


@pytest.fixture
def przechwycone(monkeypatch):
    from utils.push_manager import PushManager
    import utils.email_sender as es
    dane = {'email': [], 'push': []}
    monkeypatch.setattr(es, 'prepare_shipment_sent_email',
                        lambda **kw: dane['email'].append(kw) or None)
    monkeypatch.setattr(es, 'send_email_batch', lambda messages: None)
    monkeypatch.setattr(PushManager, '_fire_and_forget',
                        staticmethod(lambda **kw: dane['push'].append(kw)))
    return dane


def test_kazdy_uczestnik_dostaje_wlasna_liste_zamowien(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zbiorcze.tracking_number = '622333444'
    zbiorcze.courier = 'inpost'
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444', courier='inpost')

    assert len(przechwycone['email']) == 2
    po_adresie = {m['user_email']: m for m in przechwycone['email']}
    mail_b = po_adresie[sr_b.user.email]
    moje = {o.order_number for o in sr_b.display_orders}
    cudze = {o.order_number for o in sr_a.display_orders}
    assert set(mail_b['order_numbers']) == moje
    assert not (set(mail_b['order_numbers']) & cudze)


def test_uczestnik_niewiodacy_dostaje_push(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    db.session.commit()

    from utils.push_manager import PushManager
    PushManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    odbiorcy = {p['user_id'] for p in przechwycone['push']}
    assert odbiorcy == {sr_a.user_id, sr_b.user_id}


def test_paczka_bez_wlasciciela_nie_wysyla_nic(db, przechwycone, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)
    zbiorcze.user_id = None
    sr_a.user_id = None
    sr_b.user_id = None
    db.session.commit()

    from utils.email_manager import EmailManager
    EmailManager.notify_shipment_sent(zbiorcze, tracking_number='622333444')

    # Fallback na adres z pierwszego zamówienia wysłałby obcej osobie listę
    # zamówień wszystkich uczestników — dla paczki zbiorczej jest wyłączony.
    assert przechwycone['email'] == []
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_notifications.py -q
```

- [ ] **Step 3: Dodaj `prepare_shipment_sent_email` do `utils/email_sender.py`**

Obok istniejącej `send_shipment_sent_email`, wzorem pary `send_cost_added_email` / `prepare_cost_added_email`:

```python
def prepare_shipment_sent_email(user_email, user_name, request_number, order_numbers,
                                tracking_number=None, courier_name=None, tracking_url=None,
                                shipping_requests_url=None, consolidation_note=None):
    """Wersja send_shipment_sent_email do wysyłki wsadowej.

    Pętla po uczestnikach paczki zbiorczej na send_email() otworzyłaby osobne
    połączenie SMTP na każdy mail — Hostinger limituje uwierzytelnienia per IP.
    """
    subject = _shipment_sent_subject(request_number, tracking_number)
    return prepare_email(
        to=user_email,
        subject=subject,
        template='shipment_sent',
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        tracking_number=tracking_number,
        courier_name=courier_name,
        tracking_url=tracking_url,
        shipping_requests_url=shipping_requests_url,
        consolidation_note=consolidation_note,
    )
```

Jeśli `send_shipment_sent_email` buduje temat inline, wyciągnij go do `_shipment_sent_subject(request_number, tracking_number)` i użyj w obu funkcjach — wzór: `_cost_added_subject`.

- [ ] **Step 4: Przepisz `EmailManager.notify_shipment_sent`**

Zamień ciało po sprawdzeniu przełącznika na rozgałęzienie:

```python
        from utils.email_sender import (
            send_shipment_sent_email, prepare_shipment_sent_email, send_email_batch)

        if shipping_request.is_consolidation:
            EmailManager._shipment_sent_consolidated(
                shipping_request, tracking_number, courier, courier_name, tracking_url)
            return

        # Poniżej zostaje dotychczasowe ciało metody, słowo w słowo: pobranie
        # orders = list(shipping_request.orders), wczesny return na pustej liście,
        # rozwiązanie odbiorcy i wywołanie send_shipment_sent_email.
```

I nowa metoda obok:

```python
    @staticmethod
    def _shipment_sent_consolidated(sr, tracking_number, courier, courier_name, tracking_url):
        """Paczka zbiorcza: jeden mail na uczestnika, każdy ze swoją listą zamówień.

        Wspólny mail ujawniłby adresatowi numery zamówień pozostałych osób.
        """
        from flask import url_for
        from utils.email_sender import prepare_shipment_sent_email, send_email_batch
        from modules.orders.utils import get_tracking_url

        if not tracking_url and tracking_number and courier:
            tracking_url = get_tracking_url(courier, tracking_number)
        # URL-e liczymy tu, w kontekście requestu — wątek batcha go nie ma.
        requests_url = url_for('client.shipping_requests_list', _external=True)
        adresat = sr.shipping_name or (sr.user.first_name if sr.user else None)

        wiadomosci = []
        for uczestnik in sr.consolidation_participants:
            user = uczestnik['user']
            if not user or not user.email:
                # Konto usunięte: fallback na adres z zamówienia wysłałby listę
                # zamówień wszystkich uczestników obcej osobie.
                current_app.logger.warning(
                    f'Uczestnik paczki {sr.request_number} bez adresu e-mail — pomijam')
                continue
            czy_adresat = uczestnik['source_request'].id == sr.lead_source_request_id
            wiadomosci.append(prepare_shipment_sent_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=uczestnik['source_request'].request_number,
                order_numbers=[o.order_number for o in uczestnik['orders']],
                tracking_number=tracking_number,
                courier_name=courier_name,
                tracking_url=tracking_url,
                shipping_requests_url=requests_url,
                consolidation_note=None if czy_adresat else (
                    f'Twoje zamówienia jadą w paczce zbiorczej wysłanej na adres: {adresat}.'
                ),
            ))

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili o paczce zbiorczej {sr.request_number}')
```

Analogicznie rozgałęź `notify_shipping_status_change` — dla `is_consolidation` iteruj uczestników i buduj listę zamówień z `uczestnik['orders']`.

- [ ] **Step 5: Przepisz `PushManager.notify_shipment_sent`**

Przed wczesnym returnem na pustej liście zamówień:

```python
        if shipping_request.is_consolidation:
            for uczestnik in shipping_request.consolidation_participants:
                user = uczestnik['user']
                if not user:
                    continue
                PushManager._fire_and_forget(
                    user_id=user.id,
                    title='Twoja paczka jest w drodze',
                    body=(f'{_orders_label(len(uczestnik["orders"]))} '
                          f'w paczce zbiorczej'
                          + (f' · {tracking_number}' if tracking_number else '')),
                    url=url_for('client.shipping_requests_list'),
                    tag=f'shipment-{shipping_request.id}',
                    notification_type='shipping_updates',
                )
            return
```

To samo w `notify_shipping_status_change`.

- [ ] **Step 6: Przepisz dwa testy opisujące stare zachowanie**

W `tests/test_shipment_sent_notification.py` testy `test_email_skipped_when_no_orders` (ok. 536) i bliźniaczy test pusha (ok. 556) opisują pominięcie pustego zlecenia. Zawęź je: zlecenie ma być puste **i nie być paczką zbiorczą ani zleceniem źródłowym**. Dopisz w docstringu, że dla konsolidacji obowiązuje ścieżka z `tests/test_shipping_consolidation_notifications.py`.

- [ ] **Step 7: Dodaj `consolidation_note` do szablonu maila**

W `templates/emails/shipment_sent.html`, nad listą zamówień:

```jinja
{% if consolidation_note %}
<p style="margin: 0 0 16px; padding: 12px 16px; background: #e3f2fd; border-left: 4px solid #2196F3; color: #212121; font-size: 14px;">
    {{ consolidation_note }}
</p>
{% endif %}
```

- [ ] **Step 8: Uruchom testy**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_notifications.py tests/test_shipment_sent_notification.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 9: Commit**

```bash
git add utils/ templates/emails/shipment_sent.html tests/
git commit -m "feat(powiadomienia): mail i push o paczce zbiorczej per uczestnik"
```

---

## Task 12: Powiadomienie o samym scaleniu

**Files:**
- Create: `templates/emails/shipment_consolidated.html`
- Modify: `utils/email_manager.py`, `utils/email_sender.py`, `utils/push_manager.py`
- Test: `tests/test_shipping_consolidation_notifications.py`

**Interfaces:**
- Consumes: `_powiadom_o_konsolidacji` z Task 7 (woła `EmailManager.notify_shipment_consolidated` i `PushManager.notify_shipment_consolidated`).

- [ ] **Step 1: Napisz failujący test**

```python
def test_powiadomienie_o_scaleniu_idzie_do_wszystkich(db, przechwycone, monkeypatch,
                                                      make_user, make_order):
    import utils.email_sender as es
    maile = []
    monkeypatch.setattr(es, 'prepare_shipment_consolidated_email',
                        lambda **kw: maile.append(kw) or None)
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    EmailManager.notify_shipment_consolidated(zbiorcze)
    PushManager.notify_shipment_consolidated(zbiorcze)

    assert {m['user_email'] for m in maile} == {sr_a.user.email, sr_b.user.email}
    # Adresat wie, że to jego adres; pozostali widzą, do kogo jedzie paczka.
    assert any(m['is_recipient'] for m in maile)
    assert any(not m['is_recipient'] for m in maile)
    assert {p['user_id'] for p in przechwycone['push']} == {sr_a.user_id, sr_b.user_id}
```

- [ ] **Step 2: Uruchom test — ma paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_notifications.py -q -k scaleniu
```

- [ ] **Step 3: Utwórz szablon maila**

`templates/emails/shipment_consolidated.html` — skopiuj strukturę z `shipment_sent.html` (ta sama tabela 600px, logo `cid:logo@thunderorders`, ta sama stopka) i podmień treść:

```jinja
<h1 style="margin: 0 0 16px; color: #240046; font-size: 22px;">Twoja wysyłka została połączona</h1>
<p style="margin: 0 0 16px; color: #212121; font-size: 15px;">Cześć {{ user_name }},</p>
<p style="margin: 0 0 16px; color: #212121; font-size: 15px;">
    {% if is_recipient %}
        Twoje zlecenie {{ request_number }} zostało połączone z zamówieniami innych osób
        w jedną paczkę zbiorczą. Paczka pojedzie na Twój adres.
    {% else %}
        Twoje zlecenie {{ request_number }} zostało połączone z zamówieniami innych osób
        w jedną paczkę zbiorczą, która pojedzie na adres: <strong>{{ recipient_name }}</strong>.
        Odbierz swoje rzeczy bezpośrednio od tej osoby.
    {% endif %}
</p>
<p style="margin: 0 0 8px; color: #616161; font-size: 14px;">Twoje zamówienia w tej paczce:</p>
<ul style="margin: 0 0 20px; padding-left: 20px; color: #212121; font-size: 14px;">
    {% for numer in order_numbers %}<li style="margin-bottom: 4px;">{{ numer }}</li>{% endfor %}
</ul>
<p style="margin: 0 0 24px; font-size: 14px;">
    <a href="{{ shipping_requests_url }}" style="color: #7B2CBF;">{{ shipping_requests_url }}</a>
</p>
```

- [ ] **Step 4: Dodaj funkcję wysyłkową**

W `utils/email_sender.py`:

```python
def prepare_shipment_consolidated_email(user_email, user_name, request_number, order_numbers,
                                        recipient_name, is_recipient,
                                        shipping_requests_url=None):
    """Mail o połączeniu wysyłki w paczkę zbiorczą — wersja wsadowa (jedno połączenie SMTP)."""
    return prepare_email(
        to=user_email,
        subject=f'Twoja wysyłka {request_number} została połączona w paczkę zbiorczą',
        template='shipment_consolidated',
        user_name=user_name,
        request_number=request_number,
        order_numbers=order_numbers,
        recipient_name=recipient_name,
        is_recipient=is_recipient,
        shipping_requests_url=shipping_requests_url,
    )
```

- [ ] **Step 5: Dodaj metody managerów**

W `utils/email_manager.py`:

```python
    @staticmethod
    def notify_shipment_consolidated(sr):
        """Informuje uczestników, że ich wysyłki pojechały do jednej paczki.

        Bez tego klient dowiaduje się o zmianie dopiero z maila o wysyłce, gdzie
        nagle pojawia się cudzy adres.
        """
        if not EmailManager.is_email_enabled('notify_status_change'):
            current_app.logger.info(
                "Email notification 'notify_status_change' is disabled, skipping")
            return
        if not sr.is_consolidation:
            return

        from flask import url_for
        from utils.email_sender import prepare_shipment_consolidated_email, send_email_batch

        requests_url = url_for('client.shipping_requests_list', _external=True)
        adresat = sr.shipping_name or 'osoby odbierającej paczkę'

        wiadomosci = []
        for uczestnik in sr.consolidation_participants:
            user = uczestnik['user']
            if not user or not user.email:
                continue
            wiadomosci.append(prepare_shipment_consolidated_email(
                user_email=user.email,
                user_name=user.first_name or 'Kliencie',
                request_number=uczestnik['source_request'].request_number,
                order_numbers=[o.order_number for o in uczestnik['orders']],
                recipient_name=adresat,
                is_recipient=uczestnik['source_request'].id == sr.lead_source_request_id,
                shipping_requests_url=requests_url,
            ))

        send_email_batch(wiadomosci)
        current_app.logger.info(
            f'Wysłano {len(wiadomosci)} maili o konsolidacji {sr.request_number}')
```

W `utils/push_manager.py`:

```python
    @staticmethod
    def notify_shipment_consolidated(sr):
        """Push o połączeniu wysyłek — po jednym na uczestnika paczki."""
        from flask import url_for
        if not sr.is_consolidation:
            return
        adresat = sr.shipping_name or 'innej osoby'
        for uczestnik in sr.consolidation_participants:
            user = uczestnik['user']
            if not user:
                continue
            czy_adresat = uczestnik['source_request'].id == sr.lead_source_request_id
            PushManager._fire_and_forget(
                user_id=user.id,
                title='Wysyłka połączona w paczkę zbiorczą',
                body=('Twoje zamówienia pojadą w jednej paczce na Twój adres'
                      if czy_adresat else
                      f'Twoje zamówienia pojadą w jednej paczce na adres: {adresat}'),
                url=url_for('client.shipping_requests_list'),
                tag=f'consolidation-{sr.id}',
                notification_type='shipping_updates',
            )
```

- [ ] **Step 6: Dopisz mail do rejestru w docstringu**

W nagłówkowym docstringu `utils/email_manager.py` (sekcja „WYSYŁKA", ok. linii 33-36) dodaj linijkę o `shipment_consolidated`.

- [ ] **Step 7: Uruchom testy**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_notifications.py -q && ./venv/bin/python -m pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add utils/ templates/emails/shipment_consolidated.html tests/test_shipping_consolidation_notifications.py
git commit -m "feat(powiadomienia): mail i push o połączeniu wysyłek w paczkę zbiorczą"
```

---

## Task 13: Anulowane zamówienie wypina się z paczki

**Files:**
- Modify: `modules/orders/consolidation.py`, `modules/orders/routes.py` (ścieżki zmiany statusu zamówienia na `anulowane`), `modules/admin/offers.py` (`offers_cancel_orders`)
- Test: `tests/test_shipping_consolidation.py`

**Problem:** bramki gotowości wymagają kompletu zamówień (`all(o.status == 'spakowane')`, zatwierdzone E4 dla każdego). Anulowane zamówienie nigdy tego nie osiągnie i zablokuje wysyłkę **wszystkim** uczestnikom.

- [ ] **Step 1: Napisz failujące testy**

```python
def test_anulowane_zamowienie_wypina_sie_z_paczki(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order, orders_count=2)
    zamowienie = sr_b.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert len(zbiorcze.request_orders) == 3
    assert zamowienie.id not in {o.id for o in zbiorcze.display_orders}
    assert sr_b.consolidated_into_id == zbiorcze.id  # drugie zamówienie B zostaje


def test_anulowanie_ostatniego_zamowienia_wypina_zlecenie(db, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order, ile=3, orders_count=1)
    sr_c = zrodla[2]
    zamowienie = sr_c.display_orders[0]

    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(zamowienie)
    db.session.commit()
    db.session.expire_all()

    assert sr_c.consolidated_into_id is None
    assert len(zbiorcze.consolidated_sources) == 2
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation.py -q -k anulow
```

- [ ] **Step 3: Dodaj funkcję do `consolidation.py`**

```python
def odepnij_anulowane_zamowienie(order):
    """Wyjmuje anulowane zamówienie z paczki zbiorczej.

    Bramki gotowości wymagają KOMPLETU zamówień: `all(o.status == 'spakowane')`
    przy pakowaniu i zatwierdzonego E4 dla każdego przy opłaceniu. Anulowane
    zamówienie nigdy ich nie spełni, więc jedno anulowanie zablokowałoby wysyłkę
    wszystkim uczestnikom paczki.
    """
    from modules.orders.models import ShippingRequestOrder

    ro = ShippingRequestOrder.query.filter_by(order_id=order.id).first()
    if not ro:
        return
    zbiorcze = ro.shipping_request
    if not zbiorcze or not zbiorcze.is_consolidation:
        return
    if zbiorcze.status in STATUSY_BEZ_EDYCJI:
        # Paczka spakowana — fizycznie zawiera tę przesyłkę, więc nie kłamiemy w bazie.
        return

    source_id = ro.source_request_id
    db.session.delete(ro)
    db.session.flush()

    if not source_id:
        return
    zostalo = [
        r for r in zbiorcze.request_orders if r.source_request_id == source_id
    ]
    if zostalo:
        return

    # Uczestnik nie ma już nic w paczce — jego zlecenie wraca do samodzielnego życia.
    zrodlo = db.session.get(type(zbiorcze), source_id)
    if zrodlo:
        zrodlo.consolidated_into_id = None
    db.session.flush()
    if len(list(zbiorcze.consolidated_sources)) <= 1:
        rozwiaz_konsolidacje(zbiorcze)
```

- [ ] **Step 4: Wepnij w ścieżki anulowania zamówienia**

Znajdź miejsca ustawiające `order.status = 'anulowane'`:

```bash
rg -n "= 'anulowane'" modules/ | grep -v test
```

W każdym z nich, po zmianie statusu a przed commitem:

```python
    from modules.orders.consolidation import odepnij_anulowane_zamowienie
    odepnij_anulowane_zamowienie(order)
```

Obejmuje to co najmniej `modules/orders/routes.py` (zmiana statusu zamówienia przez admina, akcje masowe) i `modules/admin/offers.py` (`offers_cancel_orders`).

- [ ] **Step 5: Uruchom testy**

```bash
./venv/bin/python -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add modules/orders/consolidation.py modules/orders/routes.py modules/admin/offers.py tests/test_shipping_consolidation.py
git commit -m "fix(wms): anulowane zamówienie nie blokuje paczki zbiorczej"
```

---

## Task 14: Modal konsolidacji

**Files:**
- Modify: `templates/admin/orders/wms_dashboard.html` (markup modalu przy istniejących `#material-modal`, `#wmsReopenModal`), `static/css/components/modals.css`, `static/js/pages/admin/shipping-requests.js`

**Interfaces:**
- Consumes: endpointy z Task 7.
- Produces: `openConsolidationModal(ids)` (tryb tworzenia), `openConsolidationManageModal(consolidationId)` (tryb edycji).

- [ ] **Step 1: Dodaj markup modalu**

W `templates/admin/orders/wms_dashboard.html`, obok istniejących modali:

```html
<div id="consolidationModal" class="modal-overlay">
    <div class="modal-content" style="max-width: 640px;">
        <div class="modal-header">
            <h3 id="consolidationModalTitle">Konsolidacja wysyłek</h3>
            <button type="button" class="modal-close" onclick="closeConsolidationModal();" aria-label="Zamknij">&times;</button>
        </div>
        <div class="modal-body">
            <p class="consolidation-hint" id="consolidationHint">
                Wybierz zlecenie wiodące — jego adres, adresat i kontakt trafią na paczkę.
            </p>
            <div id="consolidationList" class="consolidation-list"></div>
            <div class="consolidation-summary">
                <h4>Paczka po scaleniu</h4>
                <dl id="consolidationSummary"></dl>
            </div>
            <div id="consolidationWarnings" class="consolidation-warnings" style="display: none;"></div>
        </div>
        <div class="modal-footer">
            <button type="button" class="btn btn-secondary" onclick="closeConsolidationModal();">Anuluj</button>
            <button type="button" class="btn btn-danger" id="consolidationDissolveBtn" style="display: none;" onclick="dissolveConsolidation();">Rozwiąż paczkę</button>
            <button type="button" class="btn btn-primary" id="consolidationSubmitBtn" onclick="submitConsolidation();">Scal w paczkę zbiorczą</button>
        </div>
    </div>
</div>
```

- [ ] **Step 2: Dodaj style do `modals.css` (light + dark)**

```css
/* Konsolidacja wysyłek — lista zleceń z wyborem wiodącego */
.consolidation-hint {
    margin: 0 0 12px;
    font-size: 13px;
    color: #666;
}

.consolidation-row {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 10px 12px;
    margin-bottom: 8px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #f8f8fb;
    cursor: pointer;
}

.consolidation-row.is-lead {
    border-color: #667eea;
    background: rgba(102, 126, 234, 0.08);
}

.consolidation-row-main { flex: 1; min-width: 0; }

.consolidation-row-meta {
    margin-top: 3px;
    font-size: 12px;
    color: #777;
}

.consolidation-detach {
    background: transparent;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    color: #d33;
    cursor: pointer;
    font-size: 12px;
    padding: 3px 9px;
}

.consolidation-summary {
    margin-top: 12px;
    padding: 10px 12px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}

.consolidation-summary h4 {
    margin: 0 0 6px;
    font-size: 12px;
    font-weight: 600;
    color: #777;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.consolidation-summary dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 10px;
    margin: 0;
    font-size: 13px;
}

.consolidation-summary dt { color: #777; }
.consolidation-summary dd { margin: 0; }

.consolidation-warnings {
    margin-top: 10px;
    padding: 9px 11px;
    border-radius: 10px;
    background: #fdf3e3;
    color: #7a4a06;
    font-size: 12px;
    line-height: 1.5;
}

[data-theme="dark"] .consolidation-hint { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .consolidation-row {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .consolidation-row.is-lead {
    border-color: #f093fb;
    background: rgba(240, 147, 251, 0.12);
}

[data-theme="dark"] .consolidation-row-meta { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .consolidation-summary {
    border-color: rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .consolidation-summary h4,
[data-theme="dark"] .consolidation-summary dt { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .consolidation-detach {
    border-color: rgba(240, 147, 251, 0.3);
    color: #f5576c;
}

[data-theme="dark"] .consolidation-warnings {
    background: rgba(240, 147, 251, 0.1);
    color: #f5c88a;
}
```

- [ ] **Step 3: Dodaj logikę do `shipping-requests.js`**

```javascript
// ============================================
// KONSOLIDACJA WYSYŁEK
// ============================================

let consolidationState = { requests: [], leadId: null, targetId: null };

/** Pobiera dane zaznaczonych zleceń i otwiera modal w trybie tworzenia. */
async function openConsolidationModal(ids) {
    const dane = await fetchConsolidationPreview(ids);
    if (!dane) return;

    // Zaznaczona paczka zbiorcza oznacza dopięcie do niej, nie tworzenie nowej.
    const zbiorcze = dane.requests.find(r => r.is_consolidation);
    consolidationState = {
        requests: dane.requests,
        leadId: zbiorcze ? null : dane.requests[0].id,
        targetId: zbiorcze ? zbiorcze.id : null,
    };

    document.getElementById('consolidationModalTitle').textContent =
        zbiorcze ? `Dopnij do paczki ${zbiorcze.request_number}` : 'Konsolidacja wysyłek';
    document.getElementById('consolidationSubmitBtn').textContent =
        zbiorcze ? 'Dopnij do paczki' : 'Scal w paczkę zbiorczą';
    document.getElementById('consolidationDissolveBtn').style.display = 'none';

    renderConsolidation(dane.blocked);
    document.getElementById('consolidationModal').classList.add('active');
}

async function fetchConsolidationPreview(ids) {
    try {
        const r = await fetch(
            `/admin/orders/shipping-requests/consolidation-preview?ids=${ids.join(',')}`);
        if (!r.ok) {
            const e = await r.json();
            window.showToast(e.error || 'Nie udało się pobrać danych zleceń', 'error');
            return null;
        }
        return await r.json();
    } catch (error) {
        console.error('Consolidation preview error:', error);
        window.showToast('Nie udało się pobrać danych zleceń', 'error');
        return null;
    }
}

function renderConsolidation(blokady) {
    const lista = document.getElementById('consolidationList');
    lista.innerHTML = '';

    consolidationState.requests
        .filter(r => !r.is_consolidation)
        .forEach(r => {
            const row = document.createElement('div');
            row.className = 'consolidation-row' + (r.id === consolidationState.leadId ? ' is-lead' : '');
            row.dataset.id = r.id;
            row.innerHTML = `
                <div class="consolidation-row-main">
                    <strong>${escapeHtml(r.request_number)}</strong>
                    · ${escapeHtml(r.client_name)}
                    <div class="consolidation-row-meta">
                        ${escapeHtml(r.full_address)} · ${r.orders_count} zam. · ${escapeHtml(r.status_name)}
                    </div>
                </div>`;
            if (consolidationState.targetId) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'consolidation-detach';
                btn.textContent = 'Wypnij';
                btn.dataset.detach = r.id;
                row.appendChild(btn);
            }
            lista.appendChild(row);
        });

    // Event delegation — escapeHtml nie escapuje apostrofów, więc żadnych inline onclick
    // z danymi klienta. Klik w wiersz ustawia wiodące, klik w „Wypnij" wypina.
    lista.onclick = (e) => {
        const detach = e.target.closest('[data-detach]');
        if (detach) {
            detachFromConsolidation(parseInt(detach.dataset.detach, 10));
            return;
        }
        const row = e.target.closest('.consolidation-row');
        if (!row) return;
        consolidationState.leadId = parseInt(row.dataset.id, 10);
        renderConsolidation(blokady);
    };

    renderConsolidationSummary();

    const box = document.getElementById('consolidationWarnings');
    const submit = document.getElementById('consolidationSubmitBtn');
    if (blokady && blokady.length) {
        box.textContent = blokady.join(' ');
        box.style.display = '';
        submit.disabled = true;
    } else {
        box.style.display = 'none';
        submit.disabled = false;
    }
}

function renderConsolidationSummary() {
    const lead = consolidationState.requests.find(r => r.id === consolidationState.leadId);
    const suma = consolidationState.requests
        .filter(r => !r.is_consolidation)
        .reduce((acc, r) => acc + r.orders_count, 0);
    const dl = document.getElementById('consolidationSummary');
    dl.innerHTML = `
        <dt>Adresat</dt><dd>${lead ? escapeHtml(lead.client_name) : '—'}</dd>
        <dt>Adres</dt><dd>${lead ? escapeHtml(lead.full_address) : '—'}</dd>
        <dt>Kontakt</dt><dd>${lead && lead.client_email ? escapeHtml(lead.client_email) : '—'}</dd>
        <dt>Zawartość</dt><dd>${suma} zamówień</dd>`;
}

function closeConsolidationModal() {
    document.getElementById('consolidationModal').classList.remove('active');
}

async function submitConsolidation() {
    const ids = consolidationState.requests.map(r => r.id);
    const body = consolidationState.targetId
        ? { ids, target_id: consolidationState.targetId }
        : { ids, lead_request_id: consolidationState.leadId };

    const r = await fetch('/admin/orders/shipping-requests/consolidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        body: JSON.stringify(body),
    });
    const dane = await r.json();
    if (!r.ok) {
        window.showToast(dane.error || 'Nie udało się scalić zleceń', 'error');
        return;
    }
    sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);
    window.location.reload();
}

/** Modal w trybie zarządzania gotową paczką — z karty zbiorczej. */
async function openConsolidationManageModal(consolidationId) {
    const dane = await fetchConsolidationPreview([consolidationId]);
    if (!dane) return;
    const zbiorcze = dane.requests[0];

    const sources = await fetch(
        `/admin/orders/shipping-requests/consolidation-preview?ids=${zbiorcze.source_ids.join(',')}`
    ).then(r => r.json());

    consolidationState = {
        requests: sources.requests,
        leadId: zbiorcze.lead_source_request_id,
        targetId: consolidationId,
    };
    document.getElementById('consolidationModalTitle').textContent =
        `Paczka ${zbiorcze.request_number}`;
    document.getElementById('consolidationSubmitBtn').textContent = 'Zapisz adresata';
    document.getElementById('consolidationDissolveBtn').style.display = '';
    renderConsolidation(sources.blocked);
    document.getElementById('consolidationModal').classList.add('active');
}

async function detachFromConsolidation(sourceId) {
    if (!confirm('Wypiąć to zlecenie z paczki zbiorczej?')) return;
    const r = await fetch(
        `/admin/orders/shipping-requests/${consolidationState.targetId}/consolidation/detach`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify({ source_id: sourceId }),
        });
    const dane = await r.json();
    if (!r.ok) {
        window.showToast(dane.error || 'Nie udało się wypiąć zlecenia', 'error');
        return;
    }
    window.location.reload();
}

async function dissolveConsolidation() {
    if (!confirm('Rozwiązać paczkę zbiorczą? Zlecenia wrócą do samodzielnej wysyłki.')) return;
    const r = await fetch(
        `/admin/orders/shipping-requests/${consolidationState.targetId}/consolidation/dissolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify({}),
        });
    const dane = await r.json();
    if (!r.ok) {
        window.showToast(dane.error || 'Nie udało się rozwiązać paczki', 'error');
        return;
    }
    window.location.reload();
}
```

Pola `source_ids` i `lead_source_request_id`, których używa tryb zarządzania, endpoint `consolidation-preview` zwraca już od Task 7.

- [ ] **Step 4: Zweryfikuj w przeglądarce**

Uruchom serwer (`preview_start` z `.claude/launch.json`), wejdź na `/admin/orders/wms`, zaznacz dwa zlecenia różnych klientów, otwórz modal. Sprawdź: wybór wiodącego przelicza podsumowanie, przełącznik motywu nie psuje czytelności, konsola bez błędów.

- [ ] **Step 5: Commit**

```bash
git add templates/admin/orders/wms_dashboard.html static/css/components/modals.css static/js/pages/admin/shipping-requests.js modules/orders/routes.py
git commit -m "feat(wms): modal konsolidacji i zarządzania paczką zbiorczą"
```

---

## Task 15: Karta zbiorcza — badge i grupowanie zamówień

**Files:**
- Modify: `templates/admin/orders/wms_dashboard.html` (karta, ok. 187-360), `static/css/pages/admin/shipping-requests-list.css`

**Pułapki (z audytu kodu):**
1. Badge **nie może** trafić do `.sr-card-number` — dwa miejsca w JS czytają `el.textContent.trim()` z tego selektora (lista numerów w potwierdzeniu usuwania i pytanie o tryb powrotu do WMS).
2. W dark mode nagłówek karty **nie ma gradientu** (płaskie `#2d2d32`), więc badge z półprzezroczystej bieli wymaga wariantu dark.
3. `{% if loop.index > 3 %}` liczy w płaskiej pętli — po zagnieżdżeniu w grupy licznik restartuje się w każdej grupie. Potrzebny `namespace`.
4. `toggleOrderProducts` chodzi po `button.parentElement` — przycisk „Pokaż" i `.order-products-hidden` muszą zostać rodzeństwem w tym samym `.sr-order-compact`.
5. Przycisk „Pokaż więcej" musi zostać **bezpośrednim dzieckiem** `.sr-orders-compact`, inaczej `toggleExtraOrders` zobaczy tylko jedną grupę.

- [ ] **Step 1: Dodaj badge w nagłówku karty**

Zamień `.sr-card-header-right` na wariant z kolumną (numer + badge pod nim), zostawiając pigułkę statusu obok:

```jinja
                            <div class="sr-card-header-right">
                                <div class="sr-card-title-col">
                                    <span class="sr-card-number">{{ sr.request_number }}</span>
                                    {% if sr.is_consolidation %}
                                    <span class="sr-consolidated-badge">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>
                                        Zbiorcza · {{ sr.consolidated_sources|length }} zlecenia
                                    </span>
                                    {% endif %}
                                </div>
                                <span class="sr-card-status" style="background-color: {{ sr.status_badge_color }};">
                                    {{ sr.status_display_name }}
                                </span>
                            </div>
```

- [ ] **Step 2: Przebuduj sekcję zamówień na grupowanie**

Zamień blok `.sr-orders-compact` na wersję z grupami i wspólnym licznikiem:

```jinja
                            <div class="sr-orders-compact">
                                {% if sr.is_consolidation %}
                                {% set ns = namespace(i=0) %}
                                {% for uczestnik in sr.consolidation_participants %}
                                {% set grupa_od = ns.i %}
                                <div class="sr-order-group{% if grupa_od >= 3 %} sr-order-extra{% endif %}"{% if grupa_od >= 3 %} style="display: none;"{% endif %}>
                                    <div class="sr-order-group-head">
                                        <span class="sr-client-avatar sr-avatar-sm">{{ ((uczestnik.user.first_name or '')[:1] ~ (uczestnik.user.last_name or '')[:1]) | upper if uczestnik.user else '?' }}</span>
                                        <span class="sr-order-group-name">{{ uczestnik.user.first_name or '' }} {{ uczestnik.user.last_name or '' }}</span>
                                        <span class="sr-order-count">· {{ uczestnik.source_request.request_number }}</span>
                                        {% if uczestnik.source_request.id == sr.lead_source_request_id %}
                                        <span class="sr-lead-mark">adresat</span>
                                        {% endif %}
                                    </div>
                                    {% for order in uczestnik.orders %}
                                    {% set ns.i = ns.i + 1 %}
                                    {% set n = order.items|length %}
                                    <div class="sr-order-compact{% if ns.i > 3 and grupa_od < 3 %} sr-order-extra{% endif %}"{% if ns.i > 3 and grupa_od < 3 %} style="display: none;"{% endif %}>
                                        <svg class="sr-order-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>
                                        <a href="{{ url_for('orders.admin_detail', order_id=order.id) }}" class="order-badge-link" onclick="event.stopPropagation();">{{ order.order_number }}</a>
                                        <span class="sr-order-count">· {{ n }} {% if n == 1 %}produkt{% elif n % 10 in [2, 3, 4] and n % 100 not in [12, 13, 14] %}produkty{% else %}produktów{% endif %}</span>
                                        {% if n > 0 %}
                                        <button type="button" class="sr-order-toggle" onclick="event.stopPropagation(); toggleOrderProducts(this);">Pokaż</button>
                                        <div class="order-products-hidden" style="display: none;">
                                            {% for item in order.items %}
                                            <div class="order-product-item">
                                                <span class="product-qty">{{ item.quantity }}x</span>
                                                <span class="product-name">{{ item.product_name }}{% if item.selected_size %} <span class="size-badge">{{ item.selected_size }}</span>{% endif %}</span>
                                            </div>
                                            {% endfor %}
                                        </div>
                                        {% endif %}
                                    </div>
                                    {% endfor %}
                                </div>
                                {% endfor %}
                                {% if ns.i > 3 %}
                                <button type="button" class="sr-orders-toggle" data-expanded="false" onclick="event.stopPropagation(); toggleExtraOrders(this);">Pokaż więcej ({{ ns.i - 3 }})</button>
                                {% endif %}
                                {% else %}
                                {# Zwykłe zlecenie: przenieś tu obecny blok pętli po sr.orders
                                   z linii 283-304 pliku, bez żadnych zmian w środku. #}
                                {% endif %}
                            </div>
```

Grupa, której wszystkie zamówienia są ukryte, dostaje `.sr-order-extra` na samym wrapperze — inaczej nad pustką zostałby wiszący nagłówek.

- [ ] **Step 3: Dodaj przycisk zarządzania w stopce karty**

```jinja
                            {% if sr.is_consolidation %}
                            <button type="button" class="btn btn-sm btn-secondary" onclick="event.stopPropagation(); openConsolidationManageModal({{ sr.id }});">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path></svg>
                                Zarządzaj paczką
                            </button>
                            {% endif %}
```

- [ ] **Step 4: Dodaj style (light + dark)**

Do sekcji light w `shipping-requests-list.css`:

```css
.sr-card-title-col {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
}

.sr-consolidated-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.22);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}

.sr-order-group {
    padding: 7px 9px;
    border-radius: 8px;
    background: #f7f7fb;
}

.sr-order-group + .sr-order-group { margin-top: 6px; }

.sr-order-group-head {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 5px;
    font-size: 12px;
}

.sr-order-group-name { font-weight: 600; }

.sr-avatar-sm {
    width: 20px;
    height: 20px;
    font-size: 9px;
}

.sr-lead-mark {
    margin-left: auto;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: #667eea;
}
```

Do sekcji dark (od linii 696, po `[data-theme="dark"] .sr-card-header`):

```css
[data-theme="dark"] .sr-consolidated-badge {
    background: rgba(240, 147, 251, 0.18);
    color: #f093fb;
}

[data-theme="dark"] .sr-order-group {
    background: rgba(255, 255, 255, 0.05);
}

[data-theme="dark"] .sr-lead-mark { color: #f093fb; }
```

Do bloku `@media (max-width: 768px)`:

```css
    .sr-consolidated-badge {
        font-size: 9px;
        padding: 2px 7px;
    }
```

- [ ] **Step 5: Zweryfikuj w przeglądarce**

Na `/admin/orders/wms`: karta zbiorcza pokazuje badge pod numerem, grupy z nazwiskami, rozwijanie produktów działa w każdej grupie, „Pokaż więcej" odsłania resztę łącznie (nie per grupa). Przełącz motyw — badge czytelny w obu. Sprawdź zaznaczenie karty i usuwanie zbiorcze (numer w potwierdzeniu bez doklejonego tekstu badge'a).

- [ ] **Step 6: Commit**

```bash
git add templates/admin/orders/wms_dashboard.html static/css/pages/admin/shipping-requests-list.css
git commit -m "feat(wms): badge paczki zbiorczej i grupowanie zamówień po kliencie"
```

---

## Task 16: Usunięcie starego scalania z frontu

**Files:**
- Modify: `static/js/pages/admin/shipping-requests.js` (`allSelectedFromSameClient`, `updateBulkToolbar`, `bulkMergeRequests`, mapa handlerów), `templates/admin/orders/wms_dashboard.html` (pozycja menu, ok. 761-771), `static/css/pages/admin/shipping-requests-list.css` (ok. 23-65)

- [ ] **Step 1: Podmień pozycję w pasku akcji**

W `templates/admin/orders/wms_dashboard.html` zamień przycisk `data-action="merge"` / `id="btnBulkMerge"` na:

```html
                <button type="button" class="bulk-menu-item" data-action="consolidate" id="btnBulkConsolidate" role="menuitem" disabled>
                    Konsoliduj wysyłki
                    <small class="bulk-menu-hint" id="bulkConsolidateTooltip"></small>
                </button>
```

- [ ] **Step 2: Wyczyść JS**

Usuń funkcje `allSelectedFromSameClient` i `bulkMergeRequests`, a także `selectedRequestClients`, jeśli po usunięciu nie ma innych konsumentów (sprawdź `rg -n "selectedRequestClients" static/js/`).

W `updateBulkToolbar` zamień blok scalania na:

```javascript
    const consolidateBtn = document.getElementById('btnBulkConsolidate');
    const consolidateTooltip = document.getElementById('bulkConsolidateTooltip');
    if (consolidateBtn) {
        consolidateBtn.disabled = count < 2;
        if (consolidateTooltip) {
            consolidateTooltip.textContent = count < 2 ? 'Zaznacz co najmniej 2 zlecenia' : '';
        }
    }
```

W mapie handlerów zamień `'merge': bulkMergeRequests` na:

```javascript
            'consolidate': () => openConsolidationModal(getSelectedRequestIds().map(Number)),
```

- [ ] **Step 3: Przemianuj style tooltipa**

W `shipping-requests-list.css` zamień `.bulk-merge-tooltip` na `.bulk-consolidate-tooltip` w obu wariantach (light i dark) — albo usuń, jeśli klasa nie jest już używana w markupie.

- [ ] **Step 4: Sprawdź, że nic nie zostało**

```bash
rg -n "bulkMerge|btnBulkMerge|bulk-merge|allSelectedFromSameClient" static/ templates/ modules/
```

Oczekiwane: brak trafień.

- [ ] **Step 5: Uruchom pełny zestaw i sprawdź w przeglądarce**

```bash
./venv/bin/python -m pytest -q
```

Na `/admin/orders/wms` zaznacz dwa zlecenia różnych klientów — pozycja „Konsoliduj wysyłki" ma być aktywna, konsola bez błędów.

- [ ] **Step 6: Commit**

```bash
git add static/ templates/admin/orders/wms_dashboard.html
git commit -m "refactor(wms): pasek akcji przechodzi ze scalania na konsolidację"
```

---

## Task 17: Pozostałe ścieżki admina — kasowanie, koszty, zdjęcie paczki

**Files:**
- Modify: `modules/orders/routes.py` (`admin_delete_shipping_request`, `admin_bulk_cancel_shipping_requests`, `admin_update_shipping_request`), `modules/orders/wms_packing.py` (wywołanie `notify_packing_photo`), `utils/email_manager.py`, `utils/push_manager.py`
- Test: `tests/test_shipping_consolidation_api.py`, `tests/test_shipping_consolidation_notifications.py`

Trzy ścieżki, które spec wymienia w „Zabezpieczeniach", a które nie należą do żadnego wcześniejszego zadania.

- [ ] **Step 1: Napisz failujące testy**

W `tests/test_shipping_consolidation_api.py`:

```python
def test_kasowanie_paczki_odpina_zrodla(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{zbiorcze.id}')
    assert r.status_code == 200
    db.session.expire_all()

    from modules.orders.models import ShippingRequest
    for zr in zrodla:
        odswiezone = db.session.get(ShippingRequest, zr.id)
        assert odswiezone is not None
        assert odswiezone.consolidated_into_id is None
        # Zamówienia wróciły do właściciela, a nie zniknęły razem z paczką.
        assert len(odswiezone.request_orders) == 1


def test_nie_da_sie_skasowac_zrodlowego(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    zbiorcze, zrodla = _konsolidacja(db, make_user, make_order)
    login(_admin(make_user))

    r = client.delete(f'/admin/orders/shipping-requests/{zrodla[0].id}')
    assert r.status_code == 409
    assert 'zbiorcz' in r.get_json()['message'].lower()


def test_koszt_tylko_dla_zamowien_z_tego_zlecenia(db, client, login, make_user, make_order):
    _seed_sr_statuses(db)
    a, b = make_user(), make_user()
    sr_a, orders_a = _sr(db, a, make_order)
    sr_b, orders_b = _sr(db, b, make_order)
    login(_admin(make_user))

    r = client.put(f'/admin/orders/shipping-requests/{sr_a.id}', json={
        'order_costs': [{'order_id': orders_b[0].id, 'shipping_cost': 99}],
    })
    assert r.status_code == 400
    db.session.expire_all()
    assert orders_b[0].shipping_cost is None
```

W `tests/test_shipping_consolidation_notifications.py`:

```python
def test_zdjecie_paczki_idzie_do_wszystkich_uczestnikow(db, przechwycone, monkeypatch,
                                                        make_user, make_order):
    maile = []
    monkeypatch.setattr('utils.email_manager.EmailManager.notify_packing_photo',
                        staticmethod(lambda order: maile.append(order.user_id)))
    _seed_sr_statuses(db)
    zbiorcze, (sr_a, sr_b) = _konsolidacja(db, make_user, make_order)

    from utils.email_manager import EmailManager
    EmailManager.notify_packing_photo_for_request(zbiorcze)

    assert set(maile) == {sr_a.user_id, sr_b.user_id}
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
./venv/bin/python -m pytest tests/test_shipping_consolidation_api.py tests/test_shipping_consolidation_notifications.py -q
```

- [ ] **Step 3: Zabezpiecz kasowanie zleceń**

W `modules/orders/routes.py`, w `admin_delete_shipping_request`, po pobraniu `sr` a przed sprawdzeniem sesji WMS:

```python
    # Zlecenie źródłowe nie ma własnych zamówień i jest tylko widokiem dla klienta —
    # skasowanie go zostawiłoby paczkę z uczestnikiem, którego nie ma.
    if sr.is_consolidated_source:
        return jsonify({
            'success': False,
            'message': f'Zlecenie {sr.request_number} jedzie w paczce zbiorczej '
                       f'{sr.consolidated_into.request_number} — najpierw wypnij je z paczki.',
        }), 409

    # Kasowanie paczki zbiorczej: zamówienia muszą wrócić do właścicieli, inaczej
    # cascade='all, delete-orphan' zabierze powiązania zamówień obcych klientów.
    if sr.is_consolidation:
        from modules.orders.consolidation import rozwiaz_konsolidacje
        rozwiaz_konsolidacje(sr)
        db.session.commit()
        log_activity(
            user=current_user, action='shipping_request_consolidation_dissolved',
            entity_type='shipping_request',
            new_value={'consolidation_number': sr.request_number, 'reason': 'delete'},
        )
        return jsonify({'success': True,
                        'message': 'Paczka zbiorcza rozwiązana, zlecenia wróciły do klientów'})
```

Tę samą parę warunków dodaj w `admin_bulk_cancel_shipping_requests`, w pętli po zleceniach — zlecenia źródłowe pomijaj i dopisz je do `skipped_numbers`, tak jak dziś pomijane są zlecenia w sesji WMS.

- [ ] **Step 4: Waliduj przynależność zamówienia przy kosztach**

W `admin_update_shipping_request`, w pętli po `data['order_costs']`, po pobraniu `order`:

```python
        # Po konsolidacji to jedyne miejsce, gdzie admin mógłby ustawić kwotę E4
        # zamówieniu obcego klienta — modal renderuje tylko zamówienia tego zlecenia,
        # ale endpoint przyjmował dowolne ID.
        if order.id not in {ro.order_id for ro in sr.request_orders}:
            db.session.rollback()
            return jsonify({
                'error': f'Zamówienie {order.order_number} nie należy do zlecenia '
                         f'{sr.request_number}',
            }), 400
```

- [ ] **Step 5: Rozsyłaj zdjęcie paczki do wszystkich uczestników**

W `utils/email_manager.py`:

```python
    @staticmethod
    def notify_packing_photo_for_request(sr):
        """Zdjęcie spakowanej paczki — po jednym mailu na uczestnika.

        Dotychczas mail leciał z pojedynczego zamówienia, więc przy paczce zbiorczej
        dostawał go właściciel przypadkowego zamówienia z grupy, a reszta nic.
        Karton jest wspólny, więc zdjęcie należy się każdemu.
        """
        if not sr.is_consolidation:
            for order in sr.orders:
                EmailManager.notify_packing_photo(order)
            return

        for uczestnik in sr.consolidation_participants:
            if uczestnik['orders']:
                EmailManager.notify_packing_photo(uczestnik['orders'][0])
```

Analogiczna metoda `PushManager.notify_packing_photo_for_request(sr)`.

W `modules/orders/wms_packing.py` (i w `modules/orders/wms.py`, w endpointcie wysyłającym mail ze zdjęciem) zamień wywołanie per zamówienie na wywołanie per zlecenie.

- [ ] **Step 6: Uruchom testy**

```bash
./venv/bin/python -m pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add modules/orders/routes.py modules/orders/wms_packing.py modules/orders/wms.py utils/ tests/
git commit -m "fix(wms): kasowanie paczki, walidacja kosztów i zdjęcie paczki przy konsolidacji"
```

---

## Zamknięcie

- [ ] **Pełny zestaw testów**

```bash
./venv/bin/python -m pytest -q
```

Baseline przed pracą: 951 przechodzi. Po wdrożeniu ma być 951 + nowe, zero regresów.

- [ ] **Ręczny przebieg na localhost:5001**

Scal zlecenia dwóch klientów → sprawdź badge i grupy na karcie → zmień wiodącego → dopnij trzecie zlecenie → wypnij jedno → dodaj koszty per zamówienie → przeprowadź paczkę przez sesję WMS aż do „wysłane" → sprawdź w panelu obu klientów, że każdy widzi swoje zlecenie ze wspólnym trackingiem i wyłącznie własne zamówienia.

- [ ] **Zamknij zadanie ClickUp 869eckz7u** dopiero po akceptacji Konrada. Nie pushuj — push do `main` uruchamia auto-deploy.
