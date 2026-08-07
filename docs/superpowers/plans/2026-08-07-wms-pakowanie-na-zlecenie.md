# Pakowanie na poziomie zlecenia wysyłki — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** W sesji WMS opakowanie, waga i zdjęcie paczki podawane są raz na całe zlecenie wysyłki, a nie przy każdym zamówieniu osobno.

**Architecture:** Wspólna funkcja `pack_shipping_request_group()` w nowym module `modules/orders/wms_packing.py` pakuje wszystkie zamówienia jednego zlecenia obecne w sesji jako jedną paczkę — odejmuje jedno opakowanie ze stanu, wysyła jednego maila, a dane paczki kopiuje na każde zamówienie z grupy. Endpoint HTTP (desktop) i handler WebSocket (telefon) są cienkimi nakładkami na tę funkcję. Dotychczasowe pakowanie per zamówienie (`pack-order`, `mark_order_packed`) znika, żeby nie istniały dwie ścieżki z różnym zachowaniem stanu magazynowego.

**Tech Stack:** Python 3.12, Flask, Flask-SQLAlchemy, Flask-SocketIO, pytest, waniliowy JavaScript (bez frameworka i bez testów JS), Jinja2.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-07-wms-pakowanie-na-zlecenie-design.md`
- Gałąź: `feature/wms-pakowanie-na-zlecenie` (już utworzona, spec zacommitowany)
- **Bez migracji bazy danych.** Żadnych nowych kolumn — dane paczki kopiujemy na każde zamówienie z grupy.
- Jedno zlecenie wysyłki = jedna paczka. Podział na kilka paczek jest poza zakresem.
- Do WMS trafiają wyłącznie zamówienia wchodzące w skład zleceń wysyłki.
- `Order` **nie ma** kolumny `shipping_request_id` — powiązanie idzie przez `ShippingRequestOrder`; w kodzie używamy właściwości `order.shipping_request` (`modules/orders/models.py:657`) i `sr.orders` (`modules/orders/models.py:1470`).
- Komentarze i komunikaty dla użytkownika po polsku, zgodnie z resztą modułu.
- Commity po polsku, w konwencji `typ(zakres): opis`.
- Testy uruchamiamy komendą `python -m pytest` (nie samym `pytest`).
- `docs/` jest w `.gitignore` — pliki planu i speca dodajemy przez `git add -f`.

---

### Task 1: Sugestie opakowań dla grupy zamówień

**Files:**
- Modify: `modules/orders/wms_utils.py:12-30` (nagłówek funkcji `suggest_packaging`)
- Modify: `modules/orders/wms_utils.py:1-7` (docstring modułu)
- Test: `tests/test_wms_packing_group.py` (nowy plik)

**Interfaces:**
- Produces: `suggest_packaging_for_orders(orders) -> dict` z kluczami `suggestions` (list), `warnings` (list[str]), `total_weight` (float), `total_volume` (float)
- Produces: `suggest_packaging(order) -> dict` — bez zmian w zachowaniu, deleguje do powyższej

- [x] **Step 1: Napisz test, który ma nie przejść**

Utwórz `tests/test_wms_packing_group.py`:

```python
"""WMS: pakowanie zlecenia wysyłki jako jednej paczki."""

import pytest


# ---------- pomocnicze ----------

def _seed_statuses(db):
    """Statusy zamówień — testowa baza startuje pusta."""
    from modules.orders.models import OrderStatus
    for slug, name in (('dostarczone_gom', 'Dostarczone GOM'),
                       ('spakowane', 'Spakowane'),
                       ('wyslane', 'Wysłane')):
        if not OrderStatus.query.filter_by(slug=slug).first():
            db.session.add(OrderStatus(slug=slug, name=name, is_active=True))
    db.session.commit()


def _order_with_item(db, user, make_order, make_product, weight, dims, qty=1):
    """Zamówienie z jedną pozycją produktową o zadanej wadze i wymiarach."""
    from modules.orders.models import OrderItem
    o = make_order(user, status='dostarczone_gom')
    p = make_product(weight=weight, length=dims[0], width=dims[1], height=dims[2])
    # price i total są NOT NULL w OrderItem — muszą być podane wprost.
    db.session.add(OrderItem(order_id=o.id, product_id=p.id, quantity=qty,
                             price=10.00, total=10.00 * qty,
                             picked=True, picked_quantity=qty))
    db.session.commit()
    return o


# ---------- Task 1: sugestie dla grupy ----------

def test_suggest_for_group_sums_weight_of_all_orders(app, db, make_user, make_order,
                                                     make_product):
    """Dopasowanie liczy się po sumie wszystkich zamówień z paczki, nie po jednym."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o1 = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))
    o2 = _order_with_item(db, u, make_order, make_product, weight=2.0, dims=(10, 10, 10))

    result = suggest_packaging_for_orders([o1, o2])

    assert result['total_weight'] == 3.5
    # objętość: 2 × 1000 cm³ × bufor 1.3
    assert result['total_volume'] == pytest.approx(2600.0)


def test_suggest_single_order_unchanged(app, db, make_user, make_order, make_product):
    """suggest_packaging(order) zwraca to samo co suggest_packaging_for_orders([order])."""
    from modules.orders.wms_utils import suggest_packaging, suggest_packaging_for_orders
    u = make_user()
    o = _order_with_item(db, u, make_order, make_product, weight=1.5, dims=(10, 10, 10))

    assert suggest_packaging(o) == suggest_packaging_for_orders([o])


def test_suggest_for_group_without_items_warns(app, db, make_user, make_order):
    """Grupa bez pozycji zwraca ostrzeżenie zamiast wywalać się."""
    from modules.orders.wms_utils import suggest_packaging_for_orders
    u = make_user()
    o = make_order(u, status='dostarczone_gom')

    result = suggest_packaging_for_orders([o])

    assert result['suggestions'] == []
    assert result['warnings'] == ['Zamówienie nie ma pozycji']
```

- [x] **Step 2: Uruchom test i sprawdź, że nie przechodzi**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: FAIL — `ImportError: cannot import name 'suggest_packaging_for_orders'`

- [x] **Step 3: Zaimplementuj minimum**

W `modules/orders/wms_utils.py` zamień docstring modułu (linie 1-7) na:

```python
"""
WMS Utilities — Packaging Suggestion Algorithm
================================================

Provides suggest_packaging_for_orders(orders), which analyzes the items of one
or more orders packed together and returns ranked packaging suggestions.
Jedno zlecenie wysyłki jedzie w jednej paczce, więc dopasowanie liczymy po
sumie wagi i objętości wszystkich zamówień z paczki.
"""
```

Następnie zamień nagłówek funkcji (linie 12-22, od `def suggest_packaging(order):` do `items = order.items or []`) na:

```python
def suggest_packaging(order):
    """Sugestie opakowań dla pojedynczego zamówienia — cienka nakładka
    na suggest_packaging_for_orders(), zostawiona dla istniejących endpointów."""
    return suggest_packaging_for_orders([order])


def suggest_packaging_for_orders(orders):
    """
    Analyze items of orders packed together and suggest best-fit packaging materials.

    Returns dict with keys:
      - suggestions: list of top 3 material dicts (sorted by fit_score desc, cost asc)
      - warnings: list of warning strings
      - total_weight: total product weight in kg (float)
      - total_volume: total needed volume in cm³ (float)
    """
    items = []
    for order in orders or []:
        items.extend(order.items or [])
```

Reszta ciała funkcji (od `if not items:` w dół) zostaje **bez żadnych zmian**.

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add modules/orders/wms_utils.py tests/test_wms_packing_group.py
git commit -m "feat(wms): sugestie opakowań liczone dla grupy zamówień"
```

---

### Task 2: Moduł pakowania zlecenia jako jednej paczki

**Files:**
- Create: `modules/orders/wms_packing.py`
- Modify: `modules/orders/wms.py:235-287` (usunięcie przeniesionych helperów)
- Modify: `modules/orders/wms.py:30-33` (import)
- Modify: `modules/orders/wms.py:1077`, `modules/orders/wms.py:1139` (wywołania `_release_order_lock`)
- Test: `tests/test_wms_packing_group.py` (dopisanie testów)

**Interfaces:**
- Consumes: nic z wcześniejszych zadań
- Produces:
  - `class PackingGroupError(Exception)` z atrybutem `status_code` (int, domyślnie 400)
  - `release_order_lock(order) -> None` (przeniesione z `wms.py:_release_order_lock`)
  - `update_sr_after_packing(order) -> dict | None` (przeniesione z `wms.py:_update_sr_after_packing`, bez zmian w środku)
  - `get_packing_group(session, shipping_request) -> list[Order]`
  - `pack_shipping_request_group(session, shipping_request, packaging_material_id=None, total_package_weight=None, send_email=False, user_id=None) -> dict` z kluczami `orders` (list[dict]), `low_stock_warning` (str | None), `shipping_request` (dict | None), `packed_at` (str, ISO)

- [x] **Step 1: Napisz testy, które mają nie przejść**

Dopisz na końcu `tests/test_wms_packing_group.py`:

```python
# ---------- Task 2: pakowanie grupy ----------

def _material(db, name='Karton B', stock=7):
    from modules.orders.wms_models import PackagingMaterial
    mat = PackagingMaterial(name=name, type='karton', quantity_in_stock=stock, is_active=True)
    db.session.add(mat)
    db.session.commit()
    return mat


def _sr_in_session(db, admin, make_user, make_order, make_product, orders_count=3,
                   in_session=None):
    """Zlecenie wysyłki + sesja WMS. in_session = ile zamówień wchodzi do sesji."""
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    from modules.orders.wms_models import WmsSession, WmsSessionOrder
    u = make_user()
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='oplacone')
    db.session.add(sr)
    db.session.commit()

    orders = []
    for _ in range(orders_count):
        o = _order_with_item(db, u, make_order, make_product, weight=1.0, dims=(10, 10, 10))
        db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
        orders.append(o)
    db.session.commit()

    session = WmsSession(session_token='tok-pack', user_id=admin.id, status='active')
    db.session.add(session)
    db.session.commit()

    count = orders_count if in_session is None else in_session
    for o in orders[:count]:
        db.session.add(WmsSessionOrder(session_id=session.id, order_id=o.id))
    db.session.commit()

    return sr, orders, session


@pytest.fixture
def packing_emails(monkeypatch):
    """Podmienia mail/push ze zdjęciem paczki na zapis do listy."""
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager
    sent = []
    monkeypatch.setattr(EmailManager, 'notify_packing_photo',
                        staticmethod(lambda order: sent.append(order.id)))
    monkeypatch.setattr(PushManager, 'notify_packing_photo',
                        staticmethod(lambda order: None))
    return sent


def test_pack_group_packs_all_orders_once(app, db, make_user, make_order, make_product,
                                          packing_emails):
    """Jedno wywołanie pakuje wszystkie zamówienia, zdejmuje 1 karton, wysyła 1 mail."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    for o in orders:
        o.packing_photo = 'uploads/packing_photos/x.jpg'
    db.session.commit()

    result = pack_shipping_request_group(
        session, sr, packaging_material_id=mat.id, total_package_weight=2.5,
        send_email=True, user_id=admin.id,
    )
    db.session.commit()

    assert len(result['orders']) == 3
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'
        assert o.packaging_material_id == mat.id
        assert float(o.total_package_weight) == 2.5
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6          # jedno opakowanie, nie trzy
    assert len(packing_emails) == 1            # jeden mail na paczkę
    db.session.refresh(sr)
    assert sr.status == 'spakowane'
    assert sr.packaging_material_id == mat.id  # wycena zgodna z rzeczywistością


def test_pack_group_partial_session_leaves_sr_unpacked(app, db, make_user, make_order,
                                                       make_product, packing_emails):
    """W sesji są 2 z 3 zamówień — pakują się 2, zlecenie nie jest jeszcze spakowane."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product,
                                         orders_count=3, in_session=2)
    mat = _material(db, stock=7)

    result = pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                         user_id=admin.id)
    db.session.commit()

    assert len(result['orders']) == 2
    db.session.refresh(orders[2])
    assert orders[2].status == 'dostarczone_gom'
    db.session.refresh(sr)
    assert sr.status != 'spakowane'
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6


def test_pack_group_rejects_unpicked_order(app, db, make_user, make_order, make_product,
                                           packing_emails):
    """Niedokompletowane zamówienie blokuje pakowanie całej paczki."""
    from modules.orders.wms_packing import pack_shipping_request_group, PackingGroupError
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[1].items[0].picked_quantity = 0
    db.session.commit()

    with pytest.raises(PackingGroupError):
        pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                    user_id=admin.id)
    db.session.rollback()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'dostarczone_gom'


def test_pack_group_rejects_empty_group(app, db, make_user, make_order, make_product,
                                        packing_emails):
    """Drugie pakowanie tego samego zlecenia odbija się błędem."""
    from modules.orders.wms_packing import pack_shipping_request_group, PackingGroupError
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()

    with pytest.raises(PackingGroupError):
        pack_shipping_request_group(session, sr, packaging_material_id=mat.id,
                                    user_id=admin.id)


def test_pack_group_copies_photo_across_orders(app, db, make_user, make_order, make_product,
                                               packing_emails):
    """Zdjęcie zrobione przy pierwszym zamówieniu trafia do całej paczki."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[0].packing_photo = 'uploads/packing_photos/paczka.jpg'
    db.session.commit()

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()

    for o in orders:
        db.session.refresh(o)
        assert o.packing_photo == 'uploads/packing_photos/paczka.jpg'


def test_pack_group_without_material_does_not_touch_stock(app, db, make_user, make_order,
                                                          make_product, packing_emails):
    """Brak wybranego opakowania — pakujemy, ale nic nie schodzi ze stanu."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, user_id=admin.id)
    db.session.commit()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'


def test_pack_group_with_deleted_material_warns_and_packs(app, db, make_user, make_order,
                                                          make_product, packing_emails):
    """Materiał skasowany między wyceną a pakowaniem — pakujemy z ostrzeżeniem."""
    from modules.orders.wms_packing import pack_shipping_request_group
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    result = pack_shipping_request_group(session, sr, packaging_material_id=999999,
                                         user_id=admin.id)
    db.session.commit()

    assert result['low_stock_warning']         # użytkownik dowiaduje się, że coś nie gra
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'
        assert o.packaging_material_id is None
```

- [x] **Step 2: Uruchom testy i sprawdź, że nie przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.orders.wms_packing'`

- [x] **Step 3: Utwórz `modules/orders/wms_packing.py`**

```python
"""
WMS — pakowanie zlecenia wysyłki jako jednej paczki
====================================================

Jedno zlecenie wysyłki = jedna paczka. Opakowanie schodzi ze stanu raz,
mail ze zdjęciem idzie raz, a dane paczki (opakowanie, waga, zdjęcie)
kopiowane są na każde zamówienie z grupy — historia zamówienia i mail
czytają je z zamówienia, więc nie ruszamy schematu bazy.

Moduł jest wspólny dla drogi HTTP (desktop, modules/orders/wms.py) i drogi
WebSocket (telefon, modules/orders/wms_events.py) — obie ścieżki muszą
zachowywać się identycznie, inaczej stan magazynowy się rozjedzie.
"""

import json

from flask import current_app

from extensions import db
from modules.orders.models import get_local_now
from modules.orders.wms_models import PackagingMaterial, WmsSessionOrder
from utils.activity_logger import log_activity


class PackingGroupError(Exception):
    """Pakowania nie da się wykonać — np. grupa pusta albo coś niezebrane."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def release_order_lock(order):
    """Release WMS lock from an order."""
    order.wms_locked_at = None
    order.wms_session_id = None


def update_sr_after_packing(order):
    """
    After packing an order, check if all orders in its ShippingRequest are packed.
    If so, change SR status to 'spakowane'.
    Also ensure 'spakowane' is in allowed shipping statuses.
    Returns dict with SR status info or None.
    """
    from modules.auth.models import Settings

    sr = order.shipping_request
    if not sr:
        return None

    all_packed = all(o.status == 'spakowane' for o in sr.orders)

    sr_status_changed = False
    if all_packed and sr.status != 'spakowane':
        sr.status = 'spakowane'
        sr_status_changed = True

    # Auto-add 'spakowane' to allowed shipping statuses (one-time)
    setting = Settings.query.filter_by(key='shipping_request_allowed_statuses').first()
    if setting and setting.value:
        try:
            allowed = json.loads(setting.value)
        except (json.JSONDecodeError, TypeError):
            allowed = []
        if 'spakowane' not in allowed:
            allowed.append('spakowane')
            setting.value = json.dumps(allowed)
    elif not setting:
        setting = Settings(
            key='shipping_request_allowed_statuses',
            value=json.dumps(['dostarczone_gom', 'spakowane']),
            type='json',
            description='Lista statusów zamówień kwalifikujących się do zlecenia wysyłki'
        )
        db.session.add(setting)

    return {
        'id': sr.id,
        'request_number': sr.request_number,
        'all_orders_packed': all_packed,
        'sr_status_changed': sr_status_changed,
        'sr_new_status': 'spakowane' if sr_status_changed else sr.status,
    }


def _is_fully_picked(order):
    """Czy zamówienie jest w całości zebrane (po ilościach, nie po flagach)."""
    total = sum(i.quantity for i in order.items)
    picked = sum(i.picked_quantity or 0 for i in order.items)
    return total > 0 and picked >= total


def get_packing_group(session, shipping_request):
    """
    Zamówienia tego zlecenia, które należą do tej sesji WMS i nie są jeszcze
    spakowane — czyli dokładnie to, co fizycznie ląduje w jednym kartonie.
    """
    group = []
    for so in session.session_orders:
        if so.packing_completed_at or not so.order:
            continue
        sr = so.order.shipping_request
        if sr and sr.id == shipping_request.id:
            group.append(so.order)
    return group


def pack_shipping_request_group(session, shipping_request, packaging_material_id=None,
                                total_package_weight=None, send_email=False, user_id=None):
    """
    Pakuje całe zlecenie jako jedną paczkę.

    Zwraca dict: orders (lista dictów zamówień), low_stock_warning, shipping_request,
    packed_at. Rzuca PackingGroupError, gdy grupa jest pusta albo któreś zamówienie
    nie jest do końca zebrane.

    Uwaga: funkcja NIE commituje — commit należy do wywołującego, żeby cała paczka
    weszła do bazy jednym kawałkiem albo wcale.
    """
    group = get_packing_group(session, shipping_request)
    if not group:
        raise PackingGroupError(
            f'{shipping_request.request_number}: brak zamówień do spakowania '
            f'(zlecenie już spakowane albo nie należy do tej sesji)'
        )

    not_picked = [o.order_number for o in group if not _is_fully_picked(o)]
    if not_picked:
        raise PackingGroupError(
            'Nie wszystkie zamówienia są zebrane: ' + ', '.join(not_picked)
        )

    now = get_local_now()
    old_statuses = {o.id: o.status for o in group}

    # Waga paczki — jedna na całą grupę.
    weight_value = None
    if total_package_weight is not None:
        try:
            weight_value = float(total_package_weight)
        except (ValueError, TypeError):
            weight_value = None

    # Opakowanie — jedno na całą grupę, ze stanu schodzi RAZ.
    material = None
    low_stock_warning = None
    if packaging_material_id:
        material = db.session.get(PackagingMaterial, packaging_material_id)
        if material:
            material.quantity_in_stock = max(0, material.quantity_in_stock - 1)
            if material.is_low_stock:
                low_stock_warning = (
                    f'Materiał "{material.name}": stan magazynowy: '
                    f'{material.quantity_in_stock}'
                )
            shipping_request.packaging_material_id = material.id
        else:
            low_stock_warning = 'Wybrane opakowanie już nie istnieje — stan nie został zmieniony'

    # Zdjęcie paczki robione jest raz; kopiujemy je na całą grupę.
    photo = next((o.packing_photo for o in group if o.packing_photo), None)

    for order in group:
        order.status = 'spakowane'
        order.packed_at = now
        order.packed_by = user_id
        if material:
            order.packaging_material_id = material.id
        if weight_value is not None:
            order.total_package_weight = weight_value
        if photo:
            order.packing_photo = photo
        release_order_lock(order)

        session_order = WmsSessionOrder.query.filter_by(
            session_id=session.id, order_id=order.id
        ).first()
        if session_order:
            session_order.packing_completed_at = now

    from modules.auth.models import User  # import odłożony — modele auth ładują się później
    log_activity(
        user=db.session.get(User, user_id) if user_id else None,
        action='shipping_request_packed',
        entity_type='shipping_request',
        entity_id=shipping_request.id,
        old_value={'orders': old_statuses},
        new_value={
            'status': 'spakowane',
            'wms_session_id': session.id,
            'packaging_material_id': material.id if material else None,
            'total_package_weight': weight_value,
            'order_ids': [o.id for o in group],
        },
    )

    sr_info = update_sr_after_packing(group[0])

    if send_email and photo:
        try:
            from utils.email_manager import EmailManager
            from utils.push_manager import PushManager
            EmailManager.notify_packing_photo(group[0])
            PushManager.notify_packing_photo(group[0])
        except Exception as email_err:
            current_app.logger.error(f'WMS packing email error: {email_err}')

    return {
        'orders': [{
            'id': o.id,
            'order_number': o.order_number,
            'status': o.status,
            'status_display_name': o.status_display_name,
            'packed_at': now.isoformat(),
            'packaging_material_name': material.name if material else None,
            'total_package_weight': weight_value,
        } for o in group],
        'low_stock_warning': low_stock_warning,
        'shipping_request': sr_info,
        'packed_at': now.isoformat(),
    }
```

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: PASS (10 passed)

- [x] **Step 5: Usuń przeniesione helpery z `wms.py` i podepnij import**

W `modules/orders/wms.py` skasuj funkcje `_release_order_lock` (linie 235-238) oraz
`_update_sr_after_packing` (linie 241-287) wraz z ich nagłówkami komentarzy.

W bloku importów (po linii 33) dodaj:

```python
from modules.orders.wms_packing import (
    pack_shipping_request_group, get_packing_group, release_order_lock,
    update_sr_after_packing, PackingGroupError,
)
```

Następnie zamień **wszystkie** pozostałe wywołania na wersje bez podkreślnika —
także te w endpoincie `pack-order`, który zniknie dopiero w Tasku 3. Dzięki temu po
każdym commicie aplikacja jest spójna, a nie „działa dopiero po następnym zadaniu":

```bash
grep -n "_release_order_lock\|_update_sr_after_packing" modules/orders/wms.py
```

`_release_order_lock(order)` → `release_order_lock(order)`,
`_update_sr_after_packing(order)` → `update_sr_after_packing(order)`.
Po zamianie ta sama komenda nie może zwrócić nic.

- [x] **Step 6: Uruchom cały zestaw testów WMS**

Run: `python -m pytest tests/test_wms_ship_and_reopen.py tests/test_wms_packing_group.py -v`
Expected: PASS (wszystkie)

- [x] **Step 7: Commit**

```bash
git add modules/orders/wms_packing.py modules/orders/wms.py tests/test_wms_packing_group.py
git commit -m "feat(wms): wspólna logika pakowania zlecenia jako jednej paczki"
```

---

### Task 3: Endpoint HTTP dla pakowania zlecenia (desktop)

**Files:**
- Modify: `modules/orders/wms.py:795-939` (zamiana endpointu `pack-order` na `pack-shipping-request`)
- Test: `tests/test_wms_packing_group.py` (dopisanie testów)

**Interfaces:**
- Consumes: `pack_shipping_request_group()`, `PackingGroupError` z Taska 2
- Produces: `POST /admin/orders/wms/<int:session_id>/pack-shipping-request` — body JSON `{shipping_request_id, packaging_material_id?, total_package_weight?, send_email?}`, odpowiedź `{success, message, orders: [...], session: {...}, shipping_request: {...}, low_stock_warning?}`

- [x] **Step 1: Napisz testy, które mają nie przejść**

Dopisz na końcu `tests/test_wms_packing_group.py`:

```python
# ---------- Task 3: endpoint HTTP ----------

def test_endpoint_packs_shipping_request(client, app, db, make_user, make_order,
                                         make_product, login, packing_emails):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    r = client.post(f'/admin/orders/wms/{session.id}/pack-shipping-request',
                    json={'shipping_request_id': sr.id,
                          'packaging_material_id': mat.id,
                          'total_package_weight': 2.5})

    assert r.status_code == 200
    assert len(r.get_json()['orders']) == 3
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'


def test_endpoint_rejects_unpicked(client, app, db, make_user, make_order, make_product,
                                   login, packing_emails):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    orders[1].items[0].picked_quantity = 0
    db.session.commit()

    r = client.post(f'/admin/orders/wms/{session.id}/pack-shipping-request',
                    json={'shipping_request_id': sr.id, 'packaging_material_id': mat.id})

    assert r.status_code == 400
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'dostarczone_gom'


def test_old_pack_order_endpoint_is_gone(client, app, db, make_user, make_order,
                                         make_product, login):
    """Pakowanie per zamówienie znika — została jedna droga, przez zlecenie."""
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    r = client.post(f'/admin/orders/wms/{session.id}/pack-order',
                    json={'order_id': orders[0].id})

    assert r.status_code == 404
```

- [x] **Step 2: Uruchom testy i sprawdź, że nie przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -k endpoint -v`
Expected: FAIL — 404 na `pack-shipping-request`

- [x] **Step 3: Zamień endpoint w `modules/orders/wms.py`**

Usuń **całą** funkcję `wms_pack_order()` wraz z dekoratorami (linie 795-939, od
`@orders_bp.route('/admin/orders/wms/<int:session_id>/pack-order', methods=['POST'])`
do `}), 500` przed `@orders_bp.route(... '/ship-sr' ...)`) i wstaw w to miejsce:

```python
@orders_bp.route('/admin/orders/wms/<int:session_id>/pack-shipping-request', methods=['POST'])
@login_required
@role_required('admin', 'mod')
def wms_pack_shipping_request(session_id):
    """
    Pakuje całe zlecenie wysyłki jako jedną paczkę.
    Jedno zlecenie = jeden karton, więc opakowanie schodzi ze stanu raz,
    a klient dostaje jednego maila ze zdjęciem.
    """
    try:
        session = db.session.get(WmsSession, session_id)
        if not session:
            return jsonify({'success': False, 'message': 'Sesja nie istnieje'}), 404

        if not session.is_active:
            return jsonify({'success': False, 'message': 'Sesja WMS nie jest aktywna'}), 400

        data = request.get_json(silent=True) or {}
        sr_id = data.get('shipping_request_id')
        if not sr_id:
            return jsonify({'success': False, 'message': 'Brak shipping_request_id'}), 400

        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not shipping_request:
            return jsonify({'success': False, 'message': 'Zlecenie wysyłki nie istnieje'}), 404

        result = pack_shipping_request_group(
            session,
            shipping_request,
            packaging_material_id=data.get('packaging_material_id'),
            total_package_weight=data.get('total_package_weight'),
            send_email=bool(data.get('send_email')),
            user_id=current_user.id,
        )
        db.session.commit()

        response = {
            'success': True,
            'message': f'Zlecenie {shipping_request.request_number} spakowane '
                       f'({len(result["orders"])} zam.)',
            'orders': result['orders'],
            'session': {
                'picked_orders_count': session.picked_orders_count,
                'packed_orders_count': session.packed_orders_count,
                'progress_percentage': session.progress_percentage,
            },
            'shipping_request': result['shipping_request'],
        }
        if result['low_stock_warning']:
            response['low_stock_warning'] = result['low_stock_warning']

        socketio.emit('shipping_request_packed', {
            'orders': result['orders'],
            'session': response['session'],
            'shipping_request': result['shipping_request'],
            'low_stock_warning': result['low_stock_warning'],
        }, to=f'wms_{session.id}')

        return jsonify(response)

    except PackingGroupError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f'WMS pack shipping request error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
```

Nazwa pokoju `wms_{session.id}` jest ta sama, której używa `_get_room()`
(`modules/orders/wms_events.py:21`) i pozostałe emity w `wms.py` (linie 1086, 1148, 1425).

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: PASS (13 passed)

- [x] **Step 5: Commit**

```bash
git add modules/orders/wms.py tests/test_wms_packing_group.py
git commit -m "feat(wms): endpoint pakowania całego zlecenia zamiast pojedynczego zamówienia"
```

---

### Task 4: Zwrot opakowania raz na paczkę przy powrocie do WMS

**Files:**
- Modify: `modules/orders/wms_utils.py:376-396` (pętla w `reopen_orders_for_wms`)
- Test: `tests/test_wms_packing_group.py` (dopisanie testu)

**Interfaces:**
- Consumes: nic
- Produces: `reopen_orders_for_wms(orders, mode, shipping_requests=())` — zachowanie bez zmian poza zwrotem opakowania liczonym raz na zlecenie

- [x] **Step 1: Napisz test, który ma nie przejść**

Dopisz na końcu `tests/test_wms_packing_group.py`:

```python
# ---------- Task 4: zwrot opakowania raz na paczkę ----------

def test_reopen_returns_one_material_per_package(app, db, make_user, make_order,
                                                 make_product, packing_emails):
    """Spakowanie zdjęło 1 karton — cofnięcie musi oddać 1, nie 3."""
    from modules.orders.wms_packing import pack_shipping_request_group
    from modules.orders.wms_utils import reopen_orders_for_wms
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    pack_shipping_request_group(session, sr, packaging_material_id=mat.id, user_id=admin.id)
    db.session.commit()
    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6

    reopen_orders_for_wms(orders, mode='full', shipping_requests=[sr])
    db.session.commit()

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 7          # stan wraca do punktu wyjścia
    for o in orders:
        db.session.refresh(o)
        assert o.packaging_material_id is None
        assert o.status == 'dostarczone_gom'
```

- [x] **Step 2: Uruchom test i sprawdź, że nie przechodzi**

Run: `python -m pytest tests/test_wms_packing_group.py -k reopen_returns_one -v`
Expected: FAIL — `assert 9 == 7` (stan urósł o 3 zamiast o 1)

- [x] **Step 3: Popraw `reopen_orders_for_wms()`**

W `modules/orders/wms_utils.py` zamień pętlę (linie 376-396) na:

```python
    # Opakowanie schodzi ze stanu raz na paczkę (jedno zlecenie = jeden karton),
    # więc przy cofaniu też oddajemy je raz — inaczej stan rósłby z powietrza.
    returned_packages = set()

    for order in orders:
        if order.status != 'spakowane':
            continue

        order.status = 'dostarczone_gom'
        order.packed_at = None
        order.packed_by = None

        if order.packaging_material_id:
            sr = order.shipping_request
            package_key = ('sr', sr.id) if sr else ('order', order.id)
            if package_key not in returned_packages:
                returned_packages.add(package_key)
                mat = db.session.get(PackagingMaterial, order.packaging_material_id)
                if mat:   # materiał mógł zostać skasowany od czasu pakowania
                    mat.quantity_in_stock = (mat.quantity_in_stock or 0) + 1
            order.packaging_material_id = None

        if mode == 'full':
            for item in order.items:
                item.picked = False
                item.picked_quantity = 0
                item.picked_at = None
                item.picked_by = None
                item.wms_status = 'do_zebrania'
```

Zaktualizuj też docstring funkcji (linie 367-369) — akapit o opakowaniu zamień na:

```python
    Opakowanie wraca na stan raz na paczkę (jedno zlecenie wysyłki = jeden karton)
    i przypisanie się czyści, żeby ponowne pakowanie odjęło je normalnie — dzięki
    temu stan magazynowy nie rozjeżdża się przy wielokrotnym cofaniu.
```

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py tests/test_wms_ship_and_reopen.py -v`
Expected: PASS — w szczególności `test_reopen_full_resets_picking` i
`test_reopen_repack_keeps_picking` (zlecenia jednozamówieniowe, więc dalej `+1`)

- [x] **Step 5: Commit**

```bash
git add modules/orders/wms_utils.py tests/test_wms_packing_group.py
git commit -m "fix(wms): powrót zlecenia do WMS oddaje jedno opakowanie na paczkę"
```

---

### Task 5: Endpointy sugestii opakowań dla zlecenia

**Files:**
- Modify: `modules/orders/wms.py:1217-1322` (dwa istniejące endpointy sugestii + nowe)
- Test: `tests/test_wms_packing_group.py` (dopisanie testów)

**Interfaces:**
- Consumes: `suggest_packaging_for_orders()` (Task 1), `get_packing_group()` (Task 2)
- Produces:
  - `_packaging_materials_payload() -> list[dict]` — wspólna lista materiałów (usuwa duplikat z dwóch endpointów)
  - `GET /api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>` (logowanie)
  - `GET /api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>/<session_token>` (telefon, autoryzacja tokenem)
  - obie zwracają `{success, suggestions, warnings, total_weight, total_volume, all_materials, suggested_material_id, orders_count}`

- [x] **Step 1: Napisz testy, które mają nie przejść**

Dopisz na końcu `tests/test_wms_packing_group.py`:

```python
# ---------- Task 5: sugestie dla zlecenia ----------

def test_suggest_sr_endpoint_returns_group_totals(client, app, db, make_user, make_order,
                                                  make_product, login):
    _seed_statuses(db)
    admin = make_user(role='admin')
    login(admin)
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)
    sr.packaging_material_id = mat.id
    db.session.commit()

    r = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}')

    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['orders_count'] == 3
    assert data['total_weight'] == 3.0            # 3 × 1.0 kg
    assert data['suggested_material_id'] == mat.id
    assert any(m['id'] == mat.id for m in data['all_materials'])


def test_suggest_sr_endpoint_mobile_requires_valid_token(client, app, db, make_user,
                                                         make_order, make_product):
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)

    ok = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}/tok-pack')
    bad = client.get(f'/api/orders/wms/{session.id}/suggest-packaging-sr/{sr.id}/zly-token')

    assert ok.status_code == 200
    assert ok.get_json()['orders_count'] == 3
    assert bad.status_code == 403
```

- [x] **Step 2: Uruchom testy i sprawdź, że nie przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -k suggest_sr -v`
Expected: FAIL — 404 na nowych adresach

- [x] **Step 3: Dodaj wspólny payload materiałów i nowe endpointy**

W `modules/orders/wms.py` w bloku importów z `wms_utils` (linia 30) dopisz
`suggest_packaging_for_orders` do listy importowanych nazw.

Nad `wms_suggest_packaging()` (przed linią 1217) dodaj:

```python
def _packaging_materials_payload():
    """Lista aktywnych materiałów dla ręcznego wyboru — wspólna dla wszystkich
    endpointów sugestii, żeby nie utrzymywać trzech kopii tego samego kodu."""
    materials = PackagingMaterial.query.filter_by(is_active=True).order_by(
        PackagingMaterial.sort_order
    ).all()
    return [{
        'id': m.id,
        'name': m.name,
        'type': m.type,
        'type_display': m.type_display,
        'dimensions_display': m.dimensions_display,
        'max_weight': float(m.max_weight) if m.max_weight else None,
        'own_weight': float(m.own_weight) if m.own_weight else None,
        'quantity_in_stock': m.quantity_in_stock,
        'is_low_stock': m.is_low_stock,
        'cost': float(m.cost) if m.cost else None,
    } for m in materials]


def _suggest_for_shipping_request(session, shipping_request):
    """Wspólna odpowiedź sugestii dla całej paczki — desktop i telefon."""
    group = get_packing_group(session, shipping_request)
    result = suggest_packaging_for_orders(group)
    return {
        'success': True,
        'suggestions': result['suggestions'],
        'warnings': result['warnings'],
        'total_weight': result['total_weight'],
        'total_volume': result['total_volume'],
        'all_materials': _packaging_materials_payload(),
        'suggested_material_id': shipping_request.packaging_material_id,
        'orders_count': len(group),
    }


@orders_bp.route('/api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>')
@login_required
@role_required('admin', 'mod')
def wms_suggest_packaging_sr(session_id, sr_id):
    """Sugestie opakowań dla całego zlecenia wysyłki (desktop)."""
    try:
        session = db.session.get(WmsSession, session_id)
        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not session or not shipping_request:
            return jsonify({'success': False, 'message': 'Nie znaleziono'}), 404

        return jsonify(_suggest_for_shipping_request(session, shipping_request))

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging (SR) error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500


@orders_bp.route(
    '/api/orders/wms/<int:session_id>/suggest-packaging-sr/<int:sr_id>/<session_token>'
)
def wms_suggest_packaging_sr_mobile(session_id, sr_id, session_token):
    """Sugestie opakowań dla zlecenia na telefonie — autoryzacja tokenem sesji."""
    try:
        session = WmsSession.query.filter_by(
            id=session_id, session_token=session_token
        ).first()
        if not session or not session.is_active:
            return jsonify({'success': False, 'message': 'Nieprawidłowy token sesji'}), 403

        shipping_request = db.session.get(ShippingRequest, sr_id)
        if not shipping_request:
            return jsonify({'success': False, 'message': 'Zlecenie nie istnieje'}), 404

        return jsonify(_suggest_for_shipping_request(session, shipping_request))

    except Exception as e:
        current_app.logger.error(f'WMS suggest packaging (SR, mobile) error: {e}')
        return jsonify({'success': False, 'message': f'Błąd: {str(e)}'}), 500
```

Następnie w istniejących `wms_suggest_packaging()` i `wms_suggest_packaging_mobile()`
zamień oba bloki budujące `all_materials_data` (linie ~1233-1248 i ~1294-1309) na
wywołanie `_packaging_materials_payload()`, a w zwracanym JSON-ie użyj
`'all_materials': _packaging_materials_payload(),`.

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: PASS (16 passed — Task 4 dołożył jeden test)

- [x] **Step 5: Commit**

```bash
git add modules/orders/wms.py tests/test_wms_packing_group.py
git commit -m "feat(wms): sugestie opakowań dla całego zlecenia wysyłki"
```

---

### Task 6: WebSocket — pakowanie zlecenia z telefonu

**Files:**
- Modify: `modules/orders/wms_events.py:246-360` (zamiana handlera `mark_order_packed`)
- Test: `tests/test_wms_packing_group.py` (dopisanie testu)

**Interfaces:**
- Consumes: `pack_shipping_request_group()`, `PackingGroupError` (Task 2)
- Produces: handler SocketIO `mark_shipping_request_packed` przyjmujący `{shipping_request_id, packaging_material_id?, weight?, send_email?}`, emitujący do pokoju sesji zdarzenie `shipping_request_packed` z polami `orders`, `session`, `shipping_request`, `low_stock_warning`

- [x] **Step 1: Napisz test, który ma nie przejść**

Dopisz na końcu `tests/test_wms_packing_group.py`:

```python
# ---------- Task 6: WebSocket ----------

def test_socket_handler_uses_shared_packing(app, db, make_user, make_order, make_product,
                                            packing_emails, monkeypatch):
    """Handler z telefonu pakuje przez tę samą funkcję co desktop — inaczej stan
    magazynowy rozjechałby się między jedną a drugą drogą."""
    import modules.orders.wms_events as wms_events
    _seed_statuses(db)
    admin = make_user(role='admin')
    sr, orders, session = _sr_in_session(db, admin, make_user, make_order, make_product)
    mat = _material(db, stock=7)

    emitted = []
    monkeypatch.setattr(wms_events, 'emit',
                        lambda event, payload=None, **kw: emitted.append((event, payload)))
    monkeypatch.setattr(wms_events, 'connected_clients',
                        {'sid-test': {'session_id': session.id, 'role': 'mobile'}})

    class _Req:
        sid = 'sid-test'
    monkeypatch.setattr(wms_events, 'flask_request', _Req)

    wms_events.handle_mark_shipping_request_packed({
        'shipping_request_id': sr.id,
        'packaging_material_id': mat.id,
        'weight': 2.5,
    })

    db.session.refresh(mat)
    assert mat.quantity_in_stock == 6
    assert any(name == 'shipping_request_packed' for name, _ in emitted)
    for o in orders:
        db.session.refresh(o)
        assert o.status == 'spakowane'
```

- [x] **Step 2: Uruchom test i sprawdź, że nie przechodzi**

Run: `python -m pytest tests/test_wms_packing_group.py -k socket_handler -v`
Expected: FAIL — `AttributeError: module has no attribute 'handle_mark_shipping_request_packed'`

- [x] **Step 3: Zamień handler w `modules/orders/wms_events.py`**

Usuń całą funkcję `handle_mark_order_packed()` wraz z dekoratorem
`@socketio.on('mark_order_packed')` (linie 246-360) i wstaw w to miejsce:

```python
@socketio.on('mark_shipping_request_packed')
def handle_mark_shipping_request_packed(data):
    """Telefon spakował całe zlecenie — jedno zlecenie, jedna paczka."""
    from modules.orders.models import ShippingRequest
    from modules.orders.wms_packing import pack_shipping_request_group, PackingGroupError

    sid = flask_request.sid
    client = connected_clients.get(sid)
    if not client:
        emit('error', {'message': 'Nie jesteś podłączony do sesji'})
        return

    session_id = client['session_id']
    sr_id = (data or {}).get('shipping_request_id')

    if not sr_id:
        emit('error', {'message': 'Brak shipping_request_id'})
        return

    wms_session = db.session.get(WmsSession, session_id)
    if not wms_session or not wms_session.is_active:
        emit('error', {'message': 'Sesja WMS nie jest aktywna'})
        return

    shipping_request = db.session.get(ShippingRequest, sr_id)
    if not shipping_request:
        emit('error', {'message': 'Zlecenie wysyłki nie istnieje'})
        return

    try:
        result = pack_shipping_request_group(
            wms_session,
            shipping_request,
            packaging_material_id=data.get('packaging_material_id'),
            total_package_weight=data.get('weight'),
            send_email=bool(data.get('send_email')),
            user_id=wms_session.user_id,
        )
        db.session.commit()
    except PackingGroupError as e:
        db.session.rollback()
        emit('error', {'message': e.message})
        return

    room = _get_room(session_id)
    session_progress = _build_session_progress(wms_session)

    emit('shipping_request_packed', {
        'orders': result['orders'],
        'session': session_progress,
        'shipping_request': result['shipping_request'],
        'low_stock_warning': result['low_stock_warning'],
    }, to=room)

    emit('session_progress', session_progress, to=room)
```

- [x] **Step 4: Uruchom testy i sprawdź, że przechodzą**

Run: `python -m pytest tests/test_wms_packing_group.py -v`
Expected: PASS (17 passed)

- [x] **Step 5: Commit**

```bash
git add modules/orders/wms_events.py tests/test_wms_packing_group.py
git commit -m "feat(wms): telefon pakuje całe zlecenie przez wspólną logikę"
```

---

### Task 7: Panel pakowania zlecenia — desktop

**Files:**
- Modify: `templates/admin/orders/wms.html:268-323` (sekcja `#wmsPackAction`)
- Modify: `static/js/pages/admin/wms.js` — `updatePackAction()` (995-1022), `fetchPackingSuggestions()` / `renderPackingSuggestions()` (1028-1143), `packOrder()` (1164-1230), `handleOrderPacked()` (374-415), rejestracja zdarzeń (253), skrót klawiszowy (1457, 1504-1509)
- Modify: `static/css/pages/admin/wms.css` (nowe klasy nagłówka panelu)

**Interfaces:**
- Consumes: `POST /admin/orders/wms/<session_id>/pack-shipping-request`, `GET /api/orders/wms/<session_id>/suggest-packaging-sr/<sr_id>`, zdarzenie `shipping_request_packed` (Taski 3, 5, 6)
- Produces: nic dla kolejnych zadań

**Uwaga:** w tym repo nie ma testów JavaScript (brak `package.json`), więc weryfikacja jest ręczna, opisana w Kroku 6.

- [x] **Step 1: Zmień nagłówek panelu w szablonie**

W `templates/admin/orders/wms.html` zamień linie 275-276 (`<h3>Pakowanie</h3>` wraz
z linią ostrzeżeń) na:

```html
                    <h3>Pakowanie zlecenia</h3>
                    <div class="wms-packing-sr-info" id="wmsPackingSrInfo"></div>
                    <div class="wms-packing-warnings" id="wmsPackingWarnings"></div>
```

Zmień etykietę wagi (linia 296) na `<label for="wmsPackingWeight">Waga całej paczki (kg):</label>`
oraz napis na przycisku (linia 321) z `Potwierdź pakowanie` na `Spakuj zlecenie`.

- [x] **Step 2: Dodaj styl nagłówka**

Na końcu `static/css/pages/admin/wms.css` dopisz (jasny i ciemny motyw — obowiązkowo oba):

```css
/* Nagłówek panelu pakowania: numer zlecenia + klient + liczba zamówień */
.wms-packing-sr-info {
    font-size: 0.85rem;
    color: #4b5563;
    margin-top: 2px;
}

[data-theme="dark"] .wms-packing-sr-info {
    color: #9ca3af;
}
```

- [x] **Step 3: Przebuduj logikę panelu w `static/js/pages/admin/wms.js`**

a) Zamień stan cache (linia 31) na klucz po zleceniu:

```javascript
    var packingSuggestionsCache = {}; // {shippingRequestId: {suggestions, all_materials, total_weight}}
    var currentPackingSrId = null;    // zlecenie, dla którego pokazany jest panel
```

b) Dodaj obok `autoAdvanceToNextOrder()` (nad linią 1232) pomocniczą funkcję grupy:

```javascript
    /**
     * Zamówienia danego zlecenia obecne w tej sesji i jeszcze niespakowane —
     * dokładnie to, co idzie do jednego kartonu.
     */
    function packingGroupFor(srId) {
        return (sessionData.orders || []).filter(function (o) {
            return o.shipping_request && o.shipping_request.id === srId &&
                   !o.packing_completed_at;
        });
    }
```

c) Zamień `updatePackAction()` (linie 995-1022) na:

```javascript
    function updatePackAction(order) {
        var packAction = el('wmsPackAction');
        var packBtn = el('btnPackOrder');
        var srInfo = el('wmsPackingSrInfo');
        if (!packAction || !packBtn) return;

        var sr = order && order.shipping_request;

        if (!isSessionActive || !sr) {
            packAction.style.display = 'none';
            currentPackingSrId = null;
            hidePackingPhoto();
            return;
        }

        var group = packingGroupFor(sr.id);
        var allPicked = group.length > 0 && group.every(function (o) { return o.is_picked; });

        if (!allPicked) {
            packAction.style.display = 'none';
            packBtn.disabled = true;
            currentPackingSrId = null;
            hidePackingPhoto();
            return;
        }

        packAction.style.display = '';
        packBtn.disabled = false;
        currentPackingSrId = sr.id;

        if (srInfo) {
            srInfo.textContent = sr.request_number + ' — ' + (sr.shipping_name || '') +
                ' — ' + group.length + (group.length === 1 ? ' zamówienie' : ' zam.');
        }

        fetchPackingSuggestions(sr.id);

        var withPhoto = group.find(function (o) { return o.packing_photo_url; });
        if (withPhoto) {
            showPackingPhoto(withPhoto.packing_photo_url);
        } else {
            hidePackingPhoto();
        }
    }
```

d) W `fetchPackingSuggestions()` (linie 1028-1052) zamień parametr i adres:

```javascript
    function fetchPackingSuggestions(srId) {
        if (packingSuggestionsCache[srId]) {
            renderPackingSuggestions(srId, packingSuggestionsCache[srId]);
            return;
        }

        var loadingEl = el('wmsPackingSuggestionsLoading');
        if (loadingEl) loadingEl.style.display = '';

        fetch('/api/orders/wms/' + sessionId + '/suggest-packaging-sr/' + srId, {
            headers: { 'X-CSRFToken': getCSRFToken() },
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (!data.success) return;

            packingSuggestionsCache[srId] = data;
            renderPackingSuggestions(srId, data);
        })
        .catch(function () {
            if (loadingEl) loadingEl.style.display = 'none';
        });
    }
```

e) W `renderPackingSuggestions()` zamień sygnaturę (linia 1054) na
`function renderPackingSuggestions(srId, data) {` i na końcu funkcji, zaraz za blokiem
`// Pre-fill weight` (linie 1139-1142), dopisz podpowiedź opakowania z wyceny:

```javascript
        // Opakowanie z wyceny zlecenia — podpowiadamy, nie zmuszamy
        if (data.suggested_material_id) {
            selectPackingMaterial(data.suggested_material_id, container, selectEl);
        }
```

f) Zamień `packOrder()` (linie 1164-1230) na `packShippingRequest()`:

```javascript
    function packShippingRequest(srId) {
        var group = packingGroupFor(srId);
        if (!group.length) return;

        var sr = group[0].shipping_request;

        var selectEl = el('wmsPackingMaterialSelect');
        var materialId = selectedMaterialId || (selectEl ? parseInt(selectEl.value) || null : null);

        var weightInput = el('wmsPackingWeight');
        var weight = weightInput ? parseFloat(weightInput.value) || null : null;

        var sendEmailCheckbox = el('wmsSendEmailCheckbox');
        var sendEmail = sendEmailCheckbox ? sendEmailCheckbox.checked : false;
        var hasPhoto = group.some(function (o) { return o.packing_photo_url; });

        if (!confirm('Spakować zlecenie ' + sr.request_number + ' (' + group.length +
                     ' zam.) jako jedną paczkę?')) {
            return;
        }

        var body = { shipping_request_id: srId };
        if (materialId) body.packaging_material_id = materialId;
        if (weight) body.total_package_weight = weight;
        if (sendEmail && hasPhoto) body.send_email = true;

        var packBtn = el('btnPackOrder');
        setButtonLoading(packBtn, true);

        postJSON('/admin/orders/wms/' + sessionId + '/pack-shipping-request', body)
        .then(function (result) {
            setButtonLoading(packBtn, false);
            if (!result.success) {
                showToast(result.message || 'Błąd pakowania', 'error');
                return;
            }

            applyPackedOrders(result.orders);

            selectedMaterialId = null;
            currentPackingSrId = null;
            delete packingSuggestionsCache[srId];

            if (result.session) {
                updateSessionProgress(result.session);
            }
            if (result.low_stock_warning) {
                showToast(result.low_stock_warning, 'warning');
            }

            showToast(result.message || 'Zlecenie spakowane!', 'success');

            var lastId = result.orders[result.orders.length - 1].id;
            selectOrder(lastId);
            autoAdvanceToNextOrder(lastId);

            checkAndShowShippingPanel(sr);

        }).catch(function (err) {
            setButtonLoading(packBtn, false);
            console.error('WMS packShippingRequest error:', err);
            showToast('Błąd połączenia', 'error');
        });
    }

    /** Nanosi na lokalny stan zamówienia zwrócone przez backend jako spakowane. */
    function applyPackedOrders(packedOrders) {
        (packedOrders || []).forEach(function (od) {
            var order = ordersMap[od.id];
            if (!order) return;
            order.packing_completed_at = od.packed_at;
            order.status = od.status;
            order.status_display_name = od.status_display_name;
            if (od.packaging_material_name) {
                order.packaging_material_name = od.packaging_material_name;
            }
            if (od.total_package_weight) {
                order.total_package_weight = od.total_package_weight;
            }
            updateQueueCard(od.id);
        });
    }
```

g) Zamień `handleOrderPacked()` (linie 374-415) na wersję dla całej paczki:

```javascript
    function handleShippingRequestPacked(data) {
        applyPackedOrders(data.orders);

        if (data.session) {
            updateSessionProgress(data.session);
        }
        if (data.low_stock_warning) {
            showToast(data.low_stock_warning, 'warning');
        }

        var srNumber = (data.shipping_request && data.shipping_request.request_number) || '';
        showToast('Zlecenie ' + srNumber + ' spakowane!', 'success');

        var packed = data.orders || [];
        var stillHere = packed.some(function (od) { return od.id === currentOrderId; });
        if (stillHere) {
            selectOrder(currentOrderId);
        }

        if (packed.length) {
            autoAdvanceToNextOrder(packed[packed.length - 1].id);
        }
        refreshPreviewIfVisible();

        var firstOrder = packed.length ? ordersMap[packed[0].id] : null;
        if (firstOrder && firstOrder.shipping_request) {
            checkAndShowShippingPanel(firstOrder.shipping_request);
        }
    }
```

h) Podmień rejestrację zdarzenia (linia 253):

```javascript
        socket.on('shipping_request_packed', handleShippingRequestPacked);
```

i) Popraw skrót klawiszowy — w linii 1457 zamień `if (currentOrderId) packOrder(currentOrderId);` na:

```javascript
                if (currentPackingSrId) packShippingRequest(currentPackingSrId);
```

oraz blok obsługi Entera (linie 1504-1509) na:

```javascript
                var order = ordersMap[currentOrderId];
                if (order && currentPackingSrId) {
                    e.preventDefault();
                    packShippingRequest(currentPackingSrId);
                }
```

- [x] **Step 4: Sprawdź, że nie zostały wywołania starych nazw**

Run:
```bash
grep -n "packOrder\|handleOrderPacked\|pack-order\|suggest-packaging/" static/js/pages/admin/wms.js
```
Expected: brak wyników.

- [x] **Step 5: Uruchom pełny zestaw testów (regresja backendu)**

Run: `python -m pytest -q`
Expected: PASS — bez nowych błędów

- [x] **Step 6: Weryfikacja ręczna w przeglądarce**

1. Uruchom serwer deweloperski narzędziem podglądu (`preview_start`), nie przez Bash.
2. Wejdź w `WMS → Zlecenia wysyłki`, zabierz do WMS zlecenie z **co najmniej dwoma** zamówieniami.
3. Wybierz tryb „Komputer". Zbierz pozycje pierwszego zamówienia → panel pakowania **nie** może się pokazać.
4. Zbierz pozycje ostatniego zamówienia → panel pojawia się raz, z numerem zlecenia, nazwiskiem i liczbą zamówień; opakowanie z wyceny jest już zaznaczone.
5. Kliknij „Spakuj zlecenie" → wszystkie zamówienia zlecenia stają się spakowane, pojawia się panel wysyłki.
6. Sprawdź konsolę przeglądarki (`read_console_messages`) — bez błędów.
7. W `WMS → Materiały` sprawdź, że stan wybranego opakowania spadł **o 1**.

- [x] **Step 7: Commit**

```bash
git add templates/admin/orders/wms.html static/js/pages/admin/wms.js static/css/pages/admin/wms.css
git commit -m "feat(wms): panel pakowania na poziomie zlecenia na komputerze"
```

---

### Task 8: Panel pakowania zlecenia — telefon

**Files:**
- Modify: `templates/admin/orders/wms_mobile.html:70-134` (sekcja `#wmsMPackSection`)
- Modify: `static/js/pages/admin/wms-mobile.js` — `updatePackButton()` (607-625), `fetchPackingSuggestionsMobile()` / `renderPackingSuggestionsMobile()` (631-728), `uploadPackingPhoto()` (820-851), `onPackOrder()` (870-904), handler `order_packed` (199-232)
- Modify: `static/css/pages/admin/wms-mobile.css` (nagłówek panelu)

**Interfaces:**
- Consumes: `GET /api/orders/wms/<session_id>/suggest-packaging-sr/<sr_id>/<session_token>`, zdarzenia `mark_shipping_request_packed` / `shipping_request_packed` (Taski 5, 6)
- Produces: nic dla kolejnych zadań

- [x] **Step 1: Dodaj nagłówek zlecenia w szablonie telefonu**

W `templates/admin/orders/wms_mobile.html` zaraz po otwarciu sekcji (po linii 70) wstaw:

```html
        <!-- Nagłówek: które zlecenie pakujemy -->
        <div class="wms-m-pack-sr-info" id="wmsMPackSrInfo"></div>
```

Zmień etykietę wagi (linia 88) na `<label for="wmsMPackingWeight">Waga całej paczki (kg):</label>`
i napis przycisku (linia 132) z `Spakuj zamówienie` na `Spakuj zlecenie`.

- [x] **Step 2: Dodaj styl nagłówka**

Na końcu `static/css/pages/admin/wms-mobile.css` dopisz (oba motywy):

```css
/* Nagłówek panelu pakowania na telefonie */
.wms-m-pack-sr-info {
    font-size: 0.85rem;
    font-weight: 600;
    color: #374151;
    padding: 6px 0;
}

[data-theme="dark"] .wms-m-pack-sr-info {
    color: #d1d5db;
}
```

- [x] **Step 3: Przebuduj logikę w `static/js/pages/admin/wms-mobile.js`**

a) Zamień komentarz przy cache (linia 28) i dodaj stan zlecenia:

```javascript
    var packingSuggestionsCache = {}; // {shippingRequestId: dane sugestii}
    var currentPackingSrId = null;    // zlecenie, dla którego pokazany jest panel
```

b) Dodaj nad `updatePackButton()` (przed linią 607) pomocniczą funkcję grupy:

```javascript
    /** Zamówienia zlecenia obecne w sesji i jeszcze niespakowane. */
    function packingGroupForM(srId) {
        return ordersOrder.map(function (id) { return ordersMap[id]; })
            .filter(function (o) {
                return o && o.shipping_request && o.shipping_request.id === srId &&
                       !o.packing_completed_at;
            });
    }
```

c) Zamień `updatePackButton()` (linie 607-625) na:

```javascript
    function updatePackButton(order) {
        var section = document.getElementById('wmsMPackSection');
        var btn = document.getElementById('wmsMPackBtn');
        var info = document.getElementById('wmsMPackSrInfo');
        if (!section || !btn) return;

        var sr = order && order.shipping_request;
        if (!sr) {
            section.style.display = 'none';
            currentPackingSrId = null;
            return;
        }

        var group = packingGroupForM(sr.id);
        var allPicked = group.length > 0 && group.every(function (o) { return o.is_picked; });

        if (!allPicked) {
            section.style.display = 'none';
            btn.disabled = true;
            currentPackingSrId = null;
            return;
        }

        section.style.display = '';
        btn.disabled = false;
        currentPackingSrId = sr.id;

        if (info) {
            info.textContent = sr.request_number + ' — ' + group.length +
                (group.length === 1 ? ' zamówienie' : ' zam.');
        }

        fetchPackingSuggestionsMobile(sr.id);
    }
```

d) Zamień `fetchPackingSuggestionsMobile()` (linie 631-647) na:

```javascript
    function fetchPackingSuggestionsMobile(srId) {
        if (packingSuggestionsCache[srId]) {
            renderPackingSuggestionsMobile(srId, packingSuggestionsCache[srId]);
            return;
        }

        fetch('/api/orders/wms/' + sessionId + '/suggest-packaging-sr/' + srId + '/' + sessionToken)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) return;
            packingSuggestionsCache[srId] = data;
            renderPackingSuggestionsMobile(srId, data);
        })
        .catch(function () {
            // Sugestie niedostępne — zostaje ręczny wybór z listy
        });
    }
```

Zmienna `sessionId` już istnieje w tym pliku (`static/js/pages/admin/wms-mobile.js:20`,
ustawiana z `window.WMS_SESSION_ID` w linii 69) — nie trzeba jej dodawać.

e) Zamień sygnaturę `renderPackingSuggestionsMobile()` (linia 649) na
`function renderPackingSuggestionsMobile(srId, data) {` i na końcu funkcji, za blokiem
`// Pre-fill weight` (linie 724-727), dopisz:

```javascript
        // Opakowanie z wyceny zlecenia — podpowiadamy je od razu
        if (data.suggested_material_id) {
            selectedMaterialId = data.suggested_material_id;
            if (selectEl) selectEl.value = data.suggested_material_id;
            if (container) {
                container.querySelectorAll('.wms-m-suggestion-card').forEach(function (c) {
                    c.classList.toggle('suggestion-selected',
                        parseInt(c.getAttribute('data-material-id')) === data.suggested_material_id);
                });
            }
        }
```

f) W `uploadPackingPhoto()` (linia 821) zamień pobranie zamówienia — zdjęcie robimy dla
pierwszego zamówienia z paczki:

```javascript
        var group = currentPackingSrId ? packingGroupForM(currentPackingSrId) : [];
        var orderId = group.length ? group[0].id : ordersOrder[currentOrderIdx];
```

g) Zamień `onPackOrder()` (linie 870-904) na:

```javascript
    function onPackOrder() {
        if (!currentPackingSrId) return;

        var group = packingGroupForM(currentPackingSrId);
        if (!group.length) return;

        var sr = group[0].shipping_request;

        if (!confirm('Spakować zlecenie ' + sr.request_number + ' (' + group.length +
                     ' zam.) jako jedną paczkę?')) {
            return;
        }

        if (!socket || !isConnected) {
            showToast('Brak połączenia', 'error');
            return;
        }

        var selectEl = document.getElementById('wmsMPackingMaterialSelect');
        var materialId = selectedMaterialId || (selectEl ? parseInt(selectEl.value) || null : null);

        var weightInput = document.getElementById('wmsMPackingWeight');
        var weight = weightInput ? parseFloat(weightInput.value) || null : null;

        var sendEmailCheckbox = document.getElementById('wmsMSendEmailCheckbox');
        var sendEmail = sendEmailCheckbox ? sendEmailCheckbox.checked : false;

        var payload = { shipping_request_id: currentPackingSrId };
        if (materialId) payload.packaging_material_id = materialId;
        if (weight) payload.weight = weight;
        if (sendEmail && uploadedPhotoUrl) payload.send_email = true;

        socket.emit('mark_shipping_request_packed', payload);

        selectedMaterialId = null;
        delete packingSuggestionsCache[currentPackingSrId];
        currentPackingSrId = null;
        resetPhotoState();
    }
```

h) Zamień handler zdarzenia (linie 199-232) na:

```javascript
        // Zlecenie spakowane (z dowolnego źródła)
        socket.on('shipping_request_packed', function (data) {
            var sessionProgress = data.session;

            (data.orders || []).forEach(function (od) {
                var order = ordersMap[od.id];
                if (!order) return;
                order.packing_completed_at = od.packed_at;
                order.status = od.status;
                order.status_display_name = od.status_display_name;
            });

            if (sessionProgress) {
                sessionData.session.packed_orders_count = sessionProgress.packed_orders_count;
                sessionData.session.progress_percentage = sessionProgress.progress_percentage;
                updateSessionProgressUI();
            }

            if (data.low_stock_warning) {
                showToast(data.low_stock_warning, 'warning');
            }

            vibrate(200);
            var srNumber = (data.shipping_request && data.shipping_request.request_number) || '';
            showToast('Zlecenie ' + srNumber + ' spakowane!', 'success');

            var nextIdx = findFirstNonPackedIndex();
            if (nextIdx >= 0 && nextIdx !== currentOrderIdx) {
                currentOrderIdx = nextIdx;
            }
            renderCurrentOrder();
        });
```

- [x] **Step 4: Sprawdź, że nie zostały wywołania starych nazw**

Run:
```bash
grep -n "mark_order_packed\|order_packed\|suggest-packaging/" static/js/pages/admin/wms-mobile.js
```
Expected: brak wyników.

- [x] **Step 5: Uruchom pełny zestaw testów**

Run: `python -m pytest -q`
Expected: PASS

- [x] **Step 6: Weryfikacja ręczna na telefonie (widok mobilny w podglądzie)**

1. Uruchom serwer podglądu i przełącz okno na `preset: "mobile"`.
2. Wejdź do sesji WMS przez adres mobilny (z tokenem sesji).
3. Zbierz pozycje wszystkich zamówień zlecenia — panel pakowania pojawia się dopiero po ostatnim.
4. Zrób zdjęcie, wybierz opakowanie, wpisz wagę, kliknij „Spakuj zlecenie".
5. Sprawdź, że widok komputera (druga karta) zaktualizował się przez WebSocket.
6. Sprawdź konsolę (`read_console_messages`) — bez błędów.

- [x] **Step 7: Commit**

```bash
git add templates/admin/orders/wms_mobile.html static/js/pages/admin/wms-mobile.js static/css/pages/admin/wms-mobile.css
git commit -m "feat(wms): panel pakowania na poziomie zlecenia na telefonie"
```

---

### Task 9: Weryfikacja końcowa i porządki

**Files:**
- Modify: `docs/superpowers/plans/2026-08-07-wms-pakowanie-na-zlecenie.md` (odhaczenie kroków)

**Interfaces:**
- Consumes: wszystko powyżej
- Produces: gałąź gotowa do decyzji o wdrożeniu

- [x] **Step 1: Pełny zestaw testów**

Run: `python -m pytest -q`
Expected: PASS, zero błędów i zero nowych ostrzeżeń o brakujących nazwach

- [x] **Step 2: Sprawdź, że nigdzie nie zostały odwołania do usuniętych ścieżek**

Run:
```bash
grep -rn "pack-order\|mark_order_packed\|_update_sr_after_packing\|_release_order_lock" modules/ static/ templates/ tests/ | grep -v ".pyc"
```
Expected: brak wyników

- [x] **Step 3: Sprawdź, że nie dodano migracji**

Run: `git diff --name-only main...HEAD -- migrations/`
Expected: brak wyników (zmiana miała nie ruszać schematu bazy)

- [x] **Step 4: Przegląd zmian**

Run: `git diff main...HEAD --stat`
Expected: zmiany wyłącznie w `modules/orders/`, `static/`, `templates/`, `tests/`, `docs/`

- [x] **Step 5: Commit odhaczonego planu**

```bash
git add -f docs/superpowers/plans/2026-08-07-wms-pakowanie-na-zlecenie.md
git commit -m "docs(wms): odhaczony plan pakowania na poziomie zlecenia"
```

- [x] **Step 6: Zgłoś gotowość właścicielce**

Podsumuj: co się zmieniło, co zostało sprawdzone testami, co sprawdzone ręcznie.
**Nie scalaj do `main` i nie pushuj** — decyzja o wdrożeniu należy do właścicielki,
a push do `main` to wdrożenie na produkcję.
