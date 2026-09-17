# Moja kolekcja — produkty zamówione i opłacone: plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** „Moja kolekcja" pokazuje nie tylko rzeczy dostarczone, ale też produkty już kupione i opłacone — każdy z etapem realizacji.

**Architecture:** Warstwa odczytu. Pozycje „w drodze" wyliczamy z `OrderItem` jako obiekty `VirtualCollectionItem` o tym samym interfejsie co `CollectionItem`, więc istniejące szablony renderują je bez przepisywania. Nic nie zapisujemy do bazy — `auto_add_order_to_collection` nadal materializuje pozycje dopiero przy statusie `dostarczone`. Zero migracji.

**Tech Stack:** Flask, SQLAlchemy, Jinja2, pytest (uruchamiany przez `python -m pytest`), vanilla JS, CSS z obowiązkowym wariantem dark mode.

**Spec:** `docs/superpowers/specs/2026-09-17-kolekcja-produkty-w-drodze-design.md`

**ClickUp:** [869f3nvfc](https://app.clickup.com/t/869f3nvfc)

## Global Constraints

- **Testy uruchamiaj przez `python -m pytest`** — gołe `pytest` pada na `No module named 'app'`
- **Każdy styl CSS musi mieć wariant dark mode** (`[data-theme="dark"]`, paleta glassmorphism: tła `rgba(255,255,255,0.05)`, obramowania `rgba(240,147,251,0.15)`, akcenty `#f093fb` / `#f5576c`)
- **CSS i JS w osobnych plikach**, nie inline w HTML
- **Żadnych migracji** — ten plan nie dotyka struktury bazy
- **Brak regresji dla mobile API:** `list_items()` wywołane bez `include_incoming` musi zwracać dokładnie to, co dziś
- **Odpowiadaj po polsku**, komentarze w kodzie po polsku (zgodnie z konwencją modułu)
- Importy modeli **wewnątrz funkcji**, nie na górze pliku — wzorzec całego modułu `modules/client/`

---

### Task 1: Słownik etapów i mapowanie statusu zamówienia

**Files:**
- Create: `modules/client/collection_incoming.py`
- Test: `tests/test_collection_incoming.py`

**Interfaces:**
- Consumes: nic (pierwsze zadanie)
- Produces:
  - `STAGE_UNPAID = 'unpaid'`, `STAGE_ORDERED = 'ordered'`, `STAGE_TRANSIT = 'transit'`, `STAGE_WAREHOUSE = 'warehouse'`, `STAGE_SHIPPED = 'shipped'`, `STAGE_OWNED = 'owned'`
  - `STAGE_LABELS: dict[str, str]`
  - `EXCLUDED_STATUSES: frozenset[str]`
  - `stage_for_order(order) -> str`

- [ ] **Step 1: Write the failing test**

```python
"""Testy pozycji kolekcji wyliczanych z zamówień (produkty w drodze)."""
from decimal import Decimal

import pytest


def _potwierdzenie(db, order, stage='product', status='approved', amount='100.00'):
    """Potwierdzenie płatności dla etapu — domyślnie zatwierdzone E1."""
    from modules.orders.models import PaymentConfirmation
    pc = PaymentConfirmation(order_id=order.id, payment_stage=stage,
                             amount=Decimal(amount), status=status)
    db.session.add(pc)
    db.session.commit()
    return pc


def test_mapowanie_statusow_na_etapy(db, make_user, make_order):
    from modules.client.collection_incoming import (
        stage_for_order, STAGE_ORDERED, STAGE_TRANSIT, STAGE_WAREHOUSE, STAGE_SHIPPED, STAGE_OWNED)
    u = make_user()
    oczekiwane = {
        'nowe': STAGE_ORDERED,
        'oczekujace': STAGE_ORDERED,
        'dostarczone_proxy': STAGE_ORDERED,
        'w_drodze_polska': STAGE_TRANSIT,
        'urzad_celny': STAGE_TRANSIT,
        'dostarczone_gom': STAGE_WAREHOUSE,
        'spakowane': STAGE_WAREHOUSE,
        'wyslane': STAGE_SHIPPED,
        'dostarczone': STAGE_OWNED,
    }
    for status, etap in oczekiwane.items():
        o = make_order(u, status=status, order_type='on_hand')
        _potwierdzenie(db, o)
        assert stage_for_order(o) == etap, f'status {status}'


def test_wyslane_ma_wlasny_etap_nie_magazynowy(db, make_user, make_order):
    """Rozdział spakowane/wyslane: paczka w drodze do klienta to inny komunikat."""
    from modules.client.collection_incoming import stage_for_order, STAGE_WAREHOUSE, STAGE_SHIPPED
    u = make_user()
    spakowane = make_order(u, status='spakowane', order_type='on_hand')
    wyslane = make_order(u, status='wyslane', order_type='on_hand')
    _potwierdzenie(db, spakowane)
    _potwierdzenie(db, wyslane)
    assert stage_for_order(spakowane) == STAGE_WAREHOUSE
    assert stage_for_order(wyslane) == STAGE_SHIPPED


def test_exclusive_bez_zatwierdzonego_e1_jest_do_oplacenia(db, make_user, make_order):
    from modules.client.collection_incoming import stage_for_order, STAGE_UNPAID
    u = make_user()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    assert stage_for_order(o) == STAGE_UNPAID


def test_exclusive_po_zatwierdzeniu_e1_przestaje_byc_do_oplacenia(db, make_user, make_order):
    from modules.client.collection_incoming import stage_for_order, STAGE_ORDERED
    u = make_user()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    _potwierdzenie(db, o)
    assert stage_for_order(o) == STAGE_ORDERED


def test_exclusive_w_transporcie_nie_wraca_do_do_oplacenia(db, make_user, make_order):
    """Nieopłacone E1 przy zamówieniu, które już jedzie, to zaległość admina —
    klientowi nie mówimy 'Do opłacenia' o paczce w drodze."""
    from modules.client.collection_incoming import stage_for_order, STAGE_TRANSIT
    u = make_user()
    o = make_order(u, status='w_drodze_polska', order_type='exclusive')
    assert stage_for_order(o) == STAGE_TRANSIT


def test_nieznany_status_ladnie_degraduje_do_zamowione(db, make_user, make_order):
    """Admin może dodać status z panelu ustawień — kolekcja nie może się wywalić."""
    from modules.client.collection_incoming import stage_for_order, STAGE_ORDERED
    from modules.orders.models import OrderStatus
    db.session.add(OrderStatus(slug='nowy_dziwny_status', name='Dziwny', sort_order=99, is_active=True))
    db.session.commit()
    u = make_user()
    o = make_order(u, status='nowy_dziwny_status', order_type='on_hand')
    assert stage_for_order(o) == STAGE_ORDERED


def test_etykiety_istnieja_dla_kazdego_etapu():
    from modules.client.collection_incoming import STAGE_LABELS, STAGE_BY_STATUS, STAGE_UNPAID
    etapy = set(STAGE_BY_STATUS.values()) | {STAGE_UNPAID}
    assert etapy <= set(STAGE_LABELS)
    assert STAGE_LABELS[STAGE_UNPAID] == 'Do opłacenia'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.client.collection_incoming'`

- [ ] **Step 3: Write minimal implementation**

Create `modules/client/collection_incoming.py`:

```python
"""Pozycje kolekcji wyliczane z zamówień — produkty kupione, ale jeszcze nieodebrane.

Warstwa ODCZYTU: nic tu nie trafia do bazy. Materializacją nadal zajmuje się
`collection_utils.auto_add_order_to_collection` przy statusie `dostarczone`.
Dzięki temu anulowanie zamówienia samo usuwa pozycję z kolekcji, a klient nie
traci zdjęć ani notatek (pozycje wirtualne ich nie mają).
"""

# Etapy realizacji pokazywane klientowi. Celowo jest ich mniej niż statusów
# zamówienia — żargon magazynowy (GOM, proxy) nie ma czego szukać w panelu klienta.
STAGE_UNPAID = 'unpaid'
STAGE_ORDERED = 'ordered'
STAGE_TRANSIT = 'transit'
STAGE_WAREHOUSE = 'warehouse'
STAGE_SHIPPED = 'shipped'
STAGE_OWNED = 'owned'

STAGE_BY_STATUS = {
    'nowe': STAGE_ORDERED,
    'oczekujace': STAGE_ORDERED,
    'dostarczone_proxy': STAGE_ORDERED,
    'w_drodze_polska': STAGE_TRANSIT,
    'urzad_celny': STAGE_TRANSIT,
    'dostarczone_gom': STAGE_WAREHOUSE,
    'spakowane': STAGE_WAREHOUSE,
    'wyslane': STAGE_SHIPPED,
    'dostarczone': STAGE_OWNED,
}

STAGE_LABELS = {
    STAGE_UNPAID: 'Do opłacenia',
    STAGE_ORDERED: 'Zamówione',
    STAGE_TRANSIT: 'W drodze do Polski',
    STAGE_WAREHOUSE: 'Gotowe do wysyłki',
    STAGE_SHIPPED: 'Wysłane',
    STAGE_OWNED: 'W kolekcji',
}

# Zamówienie w którymkolwiek z tych stanów nie jest już niczyją własnością.
EXCLUDED_STATUSES = frozenset({'anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'})

# Statusy, w których exclusive czeka na wpłatę. Dalej w łańcuchu brak
# zatwierdzonego E1 oznacza zaległość po stronie admina, nie klienta — nie
# straszymy go „Do opłacenia" komunikatem o paczce, która już jedzie.
_UNPAID_STATUSES = frozenset({'nowe', 'oczekujace'})


def stage_for_order(order):
    """Etap realizacji pokazywany przy pozycji z tego zamówienia."""
    if (order.order_type == 'exclusive'
            and order.status in _UNPAID_STATUSES
            and order.product_payment_status != 'approved'):
        return STAGE_UNPAID
    return STAGE_BY_STATUS.get(order.status, STAGE_ORDERED)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: PASS — 7 testów

- [ ] **Step 5: Commit**

```bash
git add modules/client/collection_incoming.py tests/test_collection_incoming.py
git commit -m "feat(kolekcja): mapowanie statusow zamowien na etapy widoczne dla klienta"
```

---

### Task 2: Kwalifikacja pozycji i budowa pozycji wirtualnych

**Files:**
- Modify: `modules/client/collection_incoming.py`
- Test: `tests/test_collection_incoming.py`

**Interfaces:**
- Consumes: `stage_for_order`, `EXCLUDED_STATUSES`, `STAGE_LABELS` (Task 1)
- Produces:
  - `class VirtualCollectionItem` — pola `id=None`, `dom_id: str`, `name: str`, `market_price: Decimal|None`, `created_at: datetime`, `image_url: str`, `primary_image=None`, `product`, `product_id`, `is_from_order=True`, `is_virtual=True`, `stage: str`, `stage_label: str`, `order`, `source='order'`, `images=()`, `images_count=0`, `can_add_image=False`, `notes=None`, `is_public=False`
  - `incoming_items(user_id, limit=MAX_INCOMING) -> list[VirtualCollectionItem]` — posortowane malejąco po `created_at`
  - `MAX_INCOMING = 2000`

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_collection_incoming.py`:

```python
def _pozycja(db, order, product, quantity=1, price='50.00', **kw):
    from modules.orders.models import OrderItem
    oi = OrderItem(order_id=order.id, product_id=product.id, quantity=quantity,
                   price=Decimal(price), total=Decimal(price) * quantity, **kw)
    db.session.add(oi)
    db.session.commit()
    return oi


def test_on_hand_bez_platnosci_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


def test_on_hand_po_zatwierdzeniu_e1_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items, STAGE_ORDERED
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, price='79.00')
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].name == 'Album NCT'
    assert pozycje[0].market_price == Decimal('79.00')
    assert pozycje[0].stage == STAGE_ORDERED
    assert pozycje[0].is_virtual is True and pozycje[0].id is None


def test_pre_order_oplacony_w_statusie_nowe_wchodzi(db, make_user, make_order, make_product):
    """Pre-order klient płaci od razu po złożeniu — status zostaje 'nowe',
    a zamówienie jest już w produkcji. Kryterium to płatność, nie status."""
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='pre_order')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 1


def test_pre_order_nieoplacony_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='pre_order')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


def test_exclusive_wchodzi_od_oczekujace_bez_platnosci(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items, STAGE_UNPAID
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='exclusive')
    _pozycja(db, o, p)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1
    assert pozycje[0].stage == STAGE_UNPAID
    assert pozycje[0].stage_label == 'Do opłacenia'


def test_exclusive_w_statusie_nowe_jeszcze_nie_wchodzi(db, make_user, make_order, make_product):
    """Exclusive przed domknięciem oferty nie ma przydziału — nie jest niczyje."""
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='nowe', order_type='exclusive')
    _pozycja(db, o, p)
    assert incoming_items(u.id) == []


@pytest.mark.parametrize('status', ['anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone'])
def test_anulowane_i_zwroty_nie_wchodza(db, make_user, make_order, make_product, status):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status=status, order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_pozycja_nieprzydzielona_w_secie_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, is_set_fulfilled=False)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_pozycja_z_zerowa_iloscia_zrealizowana_nie_wchodzi(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=2, fulfilled_quantity=0)
    _potwierdzenie(db, o)
    assert incoming_items(u.id) == []


def test_ilosc_wieksza_niz_jeden_daje_osobne_pozycje(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product(name='PC Jisoo')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=3)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert [x.name for x in pozycje] == ['PC Jisoo (1/3)', 'PC Jisoo (2/3)', 'PC Jisoo (3/3)']
    assert len({x.dom_id for x in pozycje}) == 3


def test_czesciowa_realizacja_liczy_sie_po_fulfilled_quantity(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=5, fulfilled_quantity=2)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 2


def test_pozycja_juz_zmaterializowana_nie_duplikuje_sie(db, make_user, make_order, make_product):
    """Po dostarczeniu auto_add tworzy wiersz w collection_items — pozycja
    wirtualna musi wtedy zniknąć, inaczej klient widzi ją dwa razy."""
    from modules.client.collection_incoming import incoming_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    o = make_order(u, status='dostarczone', order_type='on_hand')
    oi = _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert len(incoming_items(u.id)) == 1          # jeszcze niezmaterializowana
    db.session.add(CollectionItem(user_id=u.id, name=p.name, source='order', order_item_id=oi.id))
    db.session.commit()
    assert incoming_items(u.id) == []


def test_dostarczone_bez_materializacji_nadal_widoczne(db, make_user, make_order, make_product):
    """Gdyby auto_add padł, klient nie może stracić rzeczy, którą fizycznie ma."""
    from modules.client.collection_incoming import incoming_items, STAGE_OWNED
    u, p = make_user(), make_product()
    o = make_order(u, status='dostarczone', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    pozycje = incoming_items(u.id)
    assert len(pozycje) == 1 and pozycje[0].stage == STAGE_OWNED


def test_cudze_zamowienia_nie_wchodza(db, make_user, make_order, make_product):
    from modules.client.collection_incoming import incoming_items
    ja, ktos_inny, p = make_user(), make_user(), make_product()
    o = make_order(ktos_inny, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)
    assert incoming_items(ja.id) == []


def test_sortowanie_malejaco_po_dacie_zamowienia(db, make_user, make_order, make_product):
    from datetime import datetime
    from modules.client.collection_incoming import incoming_items
    u, p = make_user(), make_product()
    stare = make_order(u, status='oczekujace', order_type='on_hand',
                       created_at=datetime(2026, 1, 1, 10, 0))
    nowe = make_order(u, status='oczekujace', order_type='on_hand',
                      created_at=datetime(2026, 6, 1, 10, 0))
    _pozycja(db, stare, p, price='10.00')
    _pozycja(db, nowe, p, price='20.00')
    _potwierdzenie(db, stare)
    _potwierdzenie(db, nowe)
    assert [x.market_price for x in incoming_items(u.id)] == [Decimal('20.00'), Decimal('10.00')]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: FAIL — `ImportError: cannot import name 'incoming_items'`

- [ ] **Step 3: Write minimal implementation**

Dopisz do `modules/client/collection_incoming.py`:

```python
# Zapora na konto z patologiczną liczbą zamówień — scalanie i sortowanie robimy
# w Pythonie, więc lista musi mieć sufit. Przekroczenie logujemy: to sygnał, że
# warto wrócić do wariantu z UNION ALL opisanego w specu.
MAX_INCOMING = 2000

PLACEHOLDER_IMAGE = '/static/img/placeholders/collection-item.svg'


class VirtualCollectionItem:
    """Pozycja kolekcji wyliczona z zamówienia — bez wiersza w bazie.

    Interfejs celowo powtarza `CollectionItem`: wszystkie trzy widoki kolekcji
    (karuzela, siatka, lista) iterują po jednej liście i czytają te same pola,
    więc udawanie modelu jest tańsze niż rozgałęzianie szablonów.
    """

    is_virtual = True
    id = None                 # brak wiersza w bazie — szablony używają dom_id
    source = 'order'
    is_from_order = True
    is_public = False         # pozycje wirtualne nie trafiają na publiczną stronę
    notes = None
    images = ()
    images_count = 0
    can_add_image = False
    primary_image = None

    def __init__(self, order_item, unit_index, unit_count, stage):
        self.order = order_item.order
        self.product = order_item.product
        self.product_id = order_item.product_id
        self.order_item_id = order_item.id
        name = order_item.product_name
        if unit_count > 1:                       # parytet z auto_add: egzemplarze osobno
            name = f'{name} ({unit_index + 1}/{unit_count})'
        self.name = name
        self.market_price = order_item.price
        self.created_at = self.order.created_at
        self.stage = stage
        self.dom_id = f'oi-{order_item.id}-{unit_index}'

    @property
    def stage_label(self):
        return STAGE_LABELS.get(self.stage, STAGE_LABELS[STAGE_ORDERED])

    @property
    def image_url(self):
        """Zdjęcie produktu albo placeholder — parytet z CollectionItem.image_url."""
        if self.product is not None:
            product_img = self.product.primary_image
            if product_img:
                return f'/static/{product_img.path_compressed}'
        return PLACEHOLDER_IMAGE


def _order_qualifies(order):
    """Czy zamówienie jest na tyle zaawansowane, żeby klient uznał je za swoje."""
    if order.status in EXCLUDED_STATUSES:
        return False
    if order.order_type == 'exclusive':
        # Exclusive płaci dopiero po domknięciu oferty (can_upload_product_payment),
        # czyli już po wejściu w 'oczekujace' — dlatego kryterium statusowe.
        return order.status != 'nowe'
    # Pre-order i on-hand płacą od razu po złożeniu, więc o posiadaniu decyduje
    # zatwierdzone E1, a nie status (opłacony pre-order zostaje w 'nowe').
    return order.product_payment_status == 'approved'


def _effective_quantity(order_item):
    """Ile sztuk realnie jedzie — parytet z auto_add_order_to_collection."""
    if order_item.is_set_fulfilled is False:
        return 0
    if order_item.fulfilled_quantity is not None:
        return order_item.fulfilled_quantity
    return order_item.quantity


def incoming_items(user_id, limit=MAX_INCOMING):
    """Pozycje kolekcji wyliczone z zamówień użytkownika, najnowsze pierwsze."""
    from flask import current_app
    from sqlalchemy.orm import joinedload

    from extensions import db
    from modules.client.models import CollectionItem
    from modules.orders.models import Order, OrderItem, PaymentConfirmation

    orders = (
        Order.query
        .filter(Order.user_id == user_id, ~Order.status.in_(EXCLUDED_STATUSES))
        .options(joinedload(Order.items).joinedload(OrderItem.product))
        .order_by(Order.created_at.desc())
        .all()
    )
    if not orders:
        return []

    # Batch preload potwierdzeń — `payment_confirmations` jest lazy='dynamic',
    # więc bez tego każde zamówienie odpalałoby własne zapytanie przy czytaniu
    # product_payment_status. Wzorzec 1:1 z payment_overdue_service.
    order_ids = [o.id for o in orders]
    confirmations_by_order = {}
    for conf in (PaymentConfirmation.query
                 .filter(PaymentConfirmation.order_id.in_(order_ids))
                 .order_by(PaymentConfirmation.id)
                 .all()):
        confirmations_by_order.setdefault(conf.order_id, {})[conf.payment_stage] = conf
    for order in orders:
        order._cached_payment_confirmations = confirmations_by_order.get(order.id, {})

    # Pozycje już zmaterializowane przez auto_add — wykluczamy po order_item_id,
    # a nie po statusie: gdyby materializacja padła, pozycja ma zostać widoczna.
    materialized = {
        row[0] for row in db.session.query(CollectionItem.order_item_id)
        .filter(CollectionItem.user_id == user_id,
                CollectionItem.order_item_id.isnot(None))
        .all()
    }

    result = []
    for order in orders:
        if not _order_qualifies(order):
            continue
        stage = stage_for_order(order)
        for order_item in order.items:
            if order_item.id in materialized:
                continue
            quantity = _effective_quantity(order_item)
            for unit_index in range(quantity):
                result.append(VirtualCollectionItem(order_item, unit_index, quantity, stage))
                if len(result) >= limit:
                    current_app.logger.warning(
                        'Kolekcja: użytkownik %s przekroczył limit %s pozycji w drodze — '
                        'lista ucięta. Rozważ przejście na UNION ALL.', user_id, limit)
                    return result
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: PASS — wszystkie testy z Task 1 i Task 2

- [ ] **Step 5: Commit**

```bash
git add modules/client/collection_incoming.py tests/test_collection_incoming.py
git commit -m "feat(kolekcja): pozycje w drodze wyliczane z zamowien, bez zapisu do bazy"
```

---

### Task 3: Właściwości dopełniające na CollectionItem

**Files:**
- Modify: `modules/client/models.py:40-105` (klasa `CollectionItem`)
- Test: `tests/test_collection_incoming.py`

**Interfaces:**
- Consumes: `STAGE_OWNED`, `STAGE_LABELS` (Task 1)
- Produces: `CollectionItem.is_virtual = False`, `CollectionItem.dom_id -> str`, `CollectionItem.stage -> str`, `CollectionItem.stage_label -> str`

Cel: szablony mają traktować oba rodzaje pozycji jednolicie, bez `{% if %}` przy każdym polu.

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_collection_incoming.py`:

```python
def test_zmaterializowana_pozycja_ma_etap_w_kolekcji(db, make_user):
    from modules.client.models import CollectionItem
    from modules.client.collection_incoming import STAGE_OWNED
    u = make_user()
    item = CollectionItem(user_id=u.id, name='PC', source='manual')
    db.session.add(item)
    db.session.commit()
    assert item.is_virtual is False
    assert item.stage == STAGE_OWNED
    assert item.stage_label == 'W kolekcji'
    assert item.dom_id == f'ci-{item.id}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collection_incoming.py::test_zmaterializowana_pozycja_ma_etap_w_kolekcji -v`
Expected: FAIL — `AttributeError: 'CollectionItem' object has no attribute 'is_virtual'`

- [ ] **Step 3: Write minimal implementation**

W `modules/client/models.py`, w klasie `CollectionItem`, zaraz za `can_add_image`:

```python
    # --- Dopełnienie interfejsu VirtualCollectionItem ---
    # Kolekcja miesza wiersze z bazy z pozycjami wyliczanymi z zamówień. Żeby
    # szablony nie rozgałęziały się przy każdym polu, oba rodzaje pozycji
    # odpowiadają na ten sam zestaw pytań.

    is_virtual = False

    @property
    def dom_id(self):
        """Identyfikator dla DOM — pozycje wirtualne nie mają id z bazy."""
        return f'ci-{self.id}'

    @property
    def stage(self):
        """Wiersz w collection_items znaczy, że klient to fizycznie ma."""
        from modules.client.collection_incoming import STAGE_OWNED
        return STAGE_OWNED

    @property
    def stage_label(self):
        from modules.client.collection_incoming import STAGE_LABELS
        return STAGE_LABELS[self.stage]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/client/models.py tests/test_collection_incoming.py
git commit -m "feat(kolekcja): CollectionItem odpowiada na te same pytania co pozycja wirtualna"
```

---

### Task 4: Scalanie, filtrowanie i paginacja w serwisie

**Files:**
- Modify: `modules/client/collection_service.py:28-44` (`list_items`)
- Test: `tests/test_collection_incoming.py`

**Interfaces:**
- Consumes: `incoming_items` (Task 2), `STAGE_OWNED` (Task 1), `CollectionItem.stage` (Task 3)
- Produces:
  - `list_items(user_id, search=None, sort='newest', page=1, per_page=24, include_incoming=False, stage_filter=None)` — zwraca obiekt zgodny z interfejsem `Pagination`
  - `FILTER_ALL = 'all'`, `FILTER_INCOMING = 'incoming'`, `FILTER_OWNED = 'owned'`
  - `class MergedPagination` — pola `items`, `page`, `per_page`, `total`, `pages`, `has_prev`, `has_next`, `prev_num`, `next_num`, metoda `iter_pages()`

**Krytyczne:** wywołanie bez `include_incoming` musi zachowywać się dokładnie jak dziś — mobile API i publiczna kolekcja zależą od tego zachowania.

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_collection_incoming.py`:

```python
def test_parytet_bez_include_incoming(db, make_user, make_order, make_product):
    """Mobile API woła list_items bez nowych parametrów — nic nie może się zmienić."""
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id)
    assert [x.name for x in strona.items] == ['Reczna']
    assert strona.total == 1


def test_include_incoming_scala_obie_listy(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Album')
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, include_incoming=True)
    assert sorted(x.name for x in strona.items) == ['Album', 'Reczna']
    assert strona.total == 2


def test_filtr_w_drodze_i_w_kolekcji(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items, FILTER_INCOMING, FILTER_OWNED
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Album')
    db.session.add(CollectionItem(user_id=u.id, name='Reczna', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    w_drodze = list_items(u.id, include_incoming=True, stage_filter=FILTER_INCOMING)
    assert [x.name for x in w_drodze.items] == ['Album']

    posiadane = list_items(u.id, include_incoming=True, stage_filter=FILTER_OWNED)
    assert [x.name for x in posiadane.items] == ['Reczna']


def test_szukanie_obejmuje_pozycje_w_drodze(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    db.session.add(CollectionItem(user_id=u.id, name='Photocard Jisoo', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, search='nct', include_incoming=True)
    assert [x.name for x in strona.items] == ['Album NCT']


def test_sortowanie_mieszanej_listy_po_nazwie(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product(name='Bravo')
    db.session.add(CollectionItem(user_id=u.id, name='Alfa', source='manual'))
    db.session.add(CollectionItem(user_id=u.id, name='Czarli', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    strona = list_items(u.id, sort='name_asc', include_incoming=True)
    assert [x.name for x in strona.items] == ['Alfa', 'Bravo', 'Czarli']


def test_sortowanie_po_cenie_wrzuca_braki_na_koniec(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(name='Drogi')
    db.session.add(CollectionItem(user_id=u.id, name='Bez ceny', source='manual'))
    db.session.add(CollectionItem(user_id=u.id, name='Tania', market_price=Decimal('10.00')))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, price='999.00')
    _potwierdzenie(db, o)

    strona = list_items(u.id, sort='price_desc', include_incoming=True)
    assert [x.name for x in strona.items][:2] == ['Drogi', 'Tania']
    assert strona.items[-1].name == 'Bez ceny'


def test_paginacja_mieszanej_listy(db, make_user, make_order, make_product):
    from modules.client.collection_service import list_items
    from modules.client.models import CollectionItem
    u, p = make_user(), make_product()
    for i in range(3):
        db.session.add(CollectionItem(user_id=u.id, name=f'Reczna {i}', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p, quantity=4)
    _potwierdzenie(db, o)

    strona1 = list_items(u.id, page=1, per_page=3, include_incoming=True)
    assert len(strona1.items) == 3
    assert strona1.total == 7 and strona1.pages == 3
    assert strona1.has_prev is False and strona1.has_next is True
    assert strona1.next_num == 2

    strona3 = list_items(u.id, page=3, per_page=3, include_incoming=True)
    assert len(strona3.items) == 1
    assert strona3.has_next is False and strona3.prev_num == 2
    assert list(strona3.iter_pages()) == [1, 2, 3]


def test_strona_poza_zakresem_daje_pusta_liste(db, make_user):
    from modules.client.collection_service import list_items
    u = make_user()
    strona = list_items(u.id, page=99, include_incoming=True)
    assert strona.items == [] and strona.total == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collection_incoming.py -v -k "parytet or scala or filtr or szukanie or sortowanie_mieszanej or po_cenie or paginacja or poza_zakresem"`
Expected: FAIL — `TypeError: list_items() got an unexpected keyword argument 'include_incoming'`

- [ ] **Step 3: Write minimal implementation**

W `modules/client/collection_service.py` zamień funkcję `list_items` i dopisz nad nią:

```python
FILTER_ALL = 'all'
FILTER_INCOMING = 'incoming'
FILTER_OWNED = 'owned'
ALLOWED_FILTERS = (FILTER_ALL, FILTER_INCOMING, FILTER_OWNED)


class MergedPagination:
    """Odpowiednik flask-sqlalchemy Pagination dla listy scalonej w Pythonie.

    Pozycji wirtualnych nie ma w żadnej tabeli, więc LIMIT/OFFSET po stronie
    bazy nie wchodzi w grę — tniemy gotową listę i podajemy szablonowi ten sam
    interfejs, którego używał dotąd (szablon paginacji zostaje bez zmian).
    """

    def __init__(self, items, page, per_page):
        self.total = len(items)
        self.per_page = per_page
        self.pages = max(1, (self.total + per_page - 1) // per_page) if self.total else 0
        self.page = page
        start = (page - 1) * per_page
        self.items = items[start:start + per_page]

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def prev_num(self):
        return self.page - 1 if self.has_prev else None

    @property
    def next_num(self):
        return self.page + 1 if self.has_next else None

    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        """Uproszczona wersja — kolekcja klienta nie dochodzi do setek stron."""
        for num in range(1, self.pages + 1):
            yield num


def _sort_key(sort):
    """(funkcja klucza, malejąco) dla listy scalonej — parytet z sortami SQL."""
    from decimal import Decimal
    if sort == 'oldest':
        return (lambda i: i.created_at), False
    if sort == 'name_asc':
        return (lambda i: (i.name or '').lower()), False
    if sort == 'price_desc':
        # NULL-e na koniec niezależnie od kierunku — tak samo jak db.case w SQL
        return (lambda i: (i.market_price is not None,
                           Decimal(str(i.market_price)) if i.market_price is not None
                           else Decimal('0'))), True
    return (lambda i: i.created_at), True          # newest (domyślny)


def list_items(user_id, search=None, sort='newest', page=1, per_page=24,
               include_incoming=False, stage_filter=None):
    """Pagination obiekt. Bez `include_incoming` zachowanie jest identyczne jak
    przed dodaniem pozycji w drodze — mobile API i publiczna kolekcja na tym stoją.

    Z `include_incoming` scalamy wiersze z bazy z pozycjami wyliczonymi z zamówień,
    sortujemy wspólnie i tniemy na strony w Pythonie (patrz MergedPagination).
    """
    query = CollectionItem.query.filter_by(user_id=user_id)
    if search:
        query = query.filter(CollectionItem.name.ilike(f'%{search}%'))

    if not include_incoming:                       # ŚCIEŻKA BEZ ZMIAN
        if sort == 'oldest':
            query = query.order_by(CollectionItem.created_at.asc())
        elif sort == 'name_asc':
            query = query.order_by(CollectionItem.name.asc())
        elif sort == 'price_desc':
            query = query.order_by(
                db.case((CollectionItem.market_price.is_(None), 1), else_=0),
                CollectionItem.market_price.desc())
        else:
            query = query.order_by(CollectionItem.created_at.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    from modules.client.collection_incoming import incoming_items

    stage_filter = stage_filter if stage_filter in ALLOWED_FILTERS else FILTER_ALL

    owned = [] if stage_filter == FILTER_INCOMING else query.all()
    if stage_filter == FILTER_OWNED:
        incoming = []
    else:
        incoming = incoming_items(user_id)
        if search:
            needle = search.lower()
            incoming = [i for i in incoming if needle in (i.name or '').lower()]

    key, reverse = _sort_key(sort)
    merged = sorted(owned + incoming, key=key, reverse=reverse)
    return MergedPagination(merged, page=page, per_page=per_page)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collection_incoming.py tests/test_collection_service.py tests/test_mobile_api_collection.py -v`
Expected: PASS — nowe testy plus komplet dotychczasowych (parytet dla mobile API)

- [ ] **Step 5: Commit**

```bash
git add modules/client/collection_service.py tests/test_collection_incoming.py
git commit -m "feat(kolekcja): scalanie pozycji posiadanych i w drodze z wspolna paginacja"
```

---

### Task 5: Trasa kolekcji — filtr i rozbite statystyki

**Files:**
- Modify: `modules/client/collection.py:16-62` (`collection_list`)
- Test: `tests/test_collection_incoming.py`

**Interfaces:**
- Consumes: `list_items(include_incoming, stage_filter)`, `FILTER_*` (Task 4), `incoming_items` (Task 2)
- Produces: kontekst szablonu wzbogacony o `filter_mode: str`, `total_incoming: int`; `total_items` nadal liczy tylko pozycje posiadane

- [ ] **Step 1: Write the failing test**

Dopisz do `tests/test_collection_incoming.py`:

```python
def test_strona_kolekcji_pokazuje_pozycje_w_drodze(db, client, login, make_user,
                                                    make_order, make_product):
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='w_drodze_polska', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    resp = client.get('/client/collection')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Album NCT' in html


def test_filtr_w_kolekcji_ukrywa_pozycje_w_drodze(db, client, login, make_user,
                                                   make_order, make_product):
    from modules.client.models import CollectionItem
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    db.session.add(CollectionItem(user_id=u.id, name='Photocard Jisoo', source='manual'))
    db.session.commit()
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection?filter=owned').get_data(as_text=True)
    assert 'Photocard Jisoo' in html
    assert 'Album NCT' not in html


def test_nieznany_filtr_nie_wywala_strony(db, client, login, make_user):
    u = make_user()
    login(u)
    assert client.get('/client/collection?filter=cokolwiek').status_code == 200
```

Fixture `login` z `tests/conftest.py:282` przyjmuje obiekt użytkownika i ustawia sesję Flask-Login.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_collection_incoming.py -v -k "strona_kolekcji or filtr_w_kolekcji or nieznany_filtr"`
Expected: FAIL — `'Album NCT' not in html` (trasa jeszcze nie prosi o pozycje w drodze)

- [ ] **Step 3: Write minimal implementation**

W `modules/client/collection.py`, w `collection_list`, po odczycie `sort`:

```python
    # Filtr etapu: wszystko / w drodze / w kolekcji
    filter_mode = request.args.get('filter', collection_service.FILTER_ALL)
    if filter_mode not in collection_service.ALLOWED_FILTERS:
        filter_mode = collection_service.FILTER_ALL
```

Zamień wywołanie `list_items` na:

```python
    pagination = collection_service.list_items(
        current_user.id, search=search or None, sort=sort, page=page, per_page=per_page,
        include_incoming=True, stage_filter=filter_mode)
    items = pagination.items
```

Po bloku ze statystykami dopisz:

```python
    # Licznik pozycji w drodze — pokazywany obok liczby rzeczy posiadanych.
    # total_items i total_value liczą WYŁĄCZNIE rzeczy zmaterializowane: wartość
    # kolekcji to wartość tego, co klient ma, a nie tego, co dopiero jedzie.
    from modules.client.collection_incoming import incoming_items
    total_incoming = len(incoming_items(current_user.id))
```

Dopisz do `render_template(...)`:

```python
                           filter_mode=filter_mode,
                           total_incoming=total_incoming,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: PASS — komplet, bez czerwonych. Asercja o etykiecie etapu w HTML należy do Task 6,
który dopiero dodaje badge; tutaj sprawdzamy wyłącznie, że pozycja w drodze trafia na stronę.

- [ ] **Step 5: Commit**

```bash
git add modules/client/collection.py tests/test_collection_incoming.py
git commit -m "feat(kolekcja): trasa podaje pozycje w drodze i filtr etapu"
```

---

### Task 6: Badge etapu w trzech widokach

**Files:**
- Modify: `templates/client/collection/_item_card.html` (siatka)
- Modify: `templates/client/collection/_item_row.html` (lista)
- Modify: `templates/client/collection/index.html` (karuzela, nagłówek listy, filtr, statystyki, linki paginacji)

**Interfaces:**
- Consumes: `item.stage`, `item.stage_label`, `item.is_virtual`, `item.dom_id`, `item.order` (Taski 1–3); `filter_mode`, `total_incoming` (Task 5)
- Produces: klasy CSS `collection-badge`, `collection-badge--<stage>`, `collection-filter`, konsumowane w Task 7

- [ ] **Step 1: Siatka — badge etapu i akcje zależne od rodzaju pozycji**

W `_item_card.html` zamień otwierający `<div>` oraz blok `card-image` i `card-actions`:

**UWAGA — nie zmieniaj `data-item-id` na `dom_id`.** JS czyta ten atrybut w dwóch miejscach:
`collection.js:457` robi `parseInt(slide.dataset.itemId, 10)` przy kliknięciu slajdu karuzeli,
a `collection.js:1179` szuka po nim elementów po usunięciu pozycji. Wartość `ci-123` dałaby
`NaN` i rozsypała edycję. Zamiast tego **pomijamy atrybut przy pozycjach wirtualnych** — wtedy
`slide.dataset.itemId` jest `undefined`, istniejący warunek `if (slide && slide.dataset.itemId)`
sam odfiltrowuje te pozycje i JS nie wymaga żadnej zmiany.

```html
<div class="collection-card"{% if not item.is_virtual %} data-item-id="{{ item.id }}"{% endif %}
     data-dom-id="{{ item.dom_id }}">
    <div class="card-image">
        <img src="{{ item.image_url }}" alt="{{ item.name }}" loading="lazy">
        <span class="collection-badge collection-badge--{{ item.stage }}">{{ item.stage_label }}</span>
    </div>
```

Blok `card-actions` obejmij warunkiem — pozycji wirtualnych nie da się edytować ani usunąć, bo nie mają wiersza w bazie:

```html
    <div class="card-actions">
        {% if item.is_virtual %}
        <a class="btn-icon btn-order-link" href="{{ url_for('orders.client_detail', order_id=item.order.id) }}"
           title="Zobacz zamówienie {{ item.order.order_number }}">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8.636 3.5a.5.5 0 00-.5-.5H1.5A1.5 1.5 0 000 4.5v10A1.5 1.5 0 001.5 16h10a1.5 1.5 0 001.5-1.5V7.864a.5.5 0 00-1 0V14.5a.5.5 0 01-.5.5h-10a.5.5 0 01-.5-.5v-10a.5.5 0 01.5-.5h6.636a.5.5 0 00.5-.5z"/>
                <path d="M16 .5a.5.5 0 00-.5-.5h-5a.5.5 0 000 1h3.793L6.146 9.146a.5.5 0 10.708.708L15 1.707V5.5a.5.5 0 001 0v-5z"/>
            </svg>
        </a>
        {% else %}
        <button class="btn-icon btn-edit" onclick="openEditModal({{ item.id }})" title="Edytuj">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M12.146.146a.5.5 0 01.708 0l3 3a.5.5 0 010 .708l-10 10a.5.5 0 01-.168.11l-5 2a.5.5 0 01-.65-.65l2-5a.5.5 0 01.11-.168l10-10zM11.207 2.5L13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 01.5.5v.5h.5a.5.5 0 01.5.5v.5h.293l6.5-6.5zm-9.761 5.175l-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 015 12.5V12h-.5a.5.5 0 01-.5-.5V11h-.5a.5.5 0 01-.468-.325z"/>
            </svg>
        </button>
        <button class="btn-icon btn-delete" onclick="openDeleteModal({{ item.id }}, '{{ item.name|e }}')" title="Usuń">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/>
                <path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H5.5l1-1h3l1 1H14a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
            </svg>
        </button>
        {% endif %}
    </div>
```

Endpoint `orders.client_detail` to trasa szczegółów zamówienia po stronie klienta — ta sama, której używa lista „Moje zamówienia".

- [ ] **Step 2: Lista — nowa kolumna Status**

W `_item_row.html` zamień otwierający `<div>` tak samo jak w siatce (atrybut `data-item-id`
tylko dla pozycji realnych):

```html
<div class="collection-row"{% if not item.is_virtual %} data-item-id="{{ item.id }}"{% endif %}
     data-dom-id="{{ item.dom_id }}">
```

Dopisz kolumnę zaraz za `col-source`:

```html
    <span class="list-col col-stage">
        <span class="collection-badge collection-badge--{{ item.stage }}">{{ item.stage_label }}</span>
    </span>
```

Blok `col-actions` obejmij tym samym warunkiem `{% if item.is_virtual %}` co w Step 1.

W `index.html`, w `list-header`, dopisz nagłówek w tym samym miejscu kolejności:

```html
                <span class="list-col col-stage">Status</span>
```

- [ ] **Step 3: Karuzela — badge pod nazwą**

W `index.html`, w bloku `carousel-slide-content`, za `carousel-slide-name`:

```html
                        <span class="collection-badge collection-badge--{{ item.stage }}">{{ item.stage_label }}</span>
```

Zamień też otwierający `<div>` slajdu na wariant z warunkowym atrybutem:

```html
                <div class="carousel-slide"{% if not item.is_virtual %} data-item-id="{{ item.id }}"{% endif %}
                     data-dom-id="{{ item.dom_id }}">
```

Dzięki temu kliknięcie slajdu pozycji wirtualnej nie otwiera modala edycji — `collection.js:457`
odfiltrowuje je istniejącym warunkiem, bez zmian w JS.

- [ ] **Step 4: Filtr etapu i statystyki**

W `index.html`, obok `view-toggle`, dodaj filtr:

```html
            <div class="collection-filter" role="group" aria-label="Filtr pozycji">
                <button type="button" class="filter-btn {{ 'active' if filter_mode == 'all' }}" data-filter="all">Wszystko</button>
                <button type="button" class="filter-btn {{ 'active' if filter_mode == 'incoming' }}" data-filter="incoming">W drodze</button>
                <button type="button" class="filter-btn {{ 'active' if filter_mode == 'owned' }}" data-filter="owned">W kolekcji</button>
            </div>
```

W sekcji statystyk dopisz licznik pozycji w drodze obok istniejącego `total_items`:

```html
                {% if total_incoming %}
                <span class="stat-incoming">W drodze: {{ total_incoming }}</span>
                {% endif %}
```

- [ ] **Step 5: Linki paginacji przenoszą filtr**

W `index.html` w trzech miejscach (`prev_num`, `page_num`, `next_num`) dopisz `&filter={{ filter_mode }}` do każdego `href`, obok istniejących `view`, `sort`, `search`. Bez tego przejście na drugą stronę gubi filtr.

- [ ] **Step 6: Test badge'a w wyrenderowanej stronie**

Dopisz do `tests/test_collection_incoming.py`:

```python
def test_badge_etapu_widoczny_na_stronie(db, client, login, make_user, make_order, make_product):
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='w_drodze_polska', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection').get_data(as_text=True)
    assert 'W drodze do Polski' in html
    assert 'collection-badge--transit' in html


def test_pozycja_wirtualna_bez_przyciskow_edycji(db, client, login, make_user,
                                                  make_order, make_product):
    # Wirtualna pozycja nie ma wiersza w bazie — edycja i usuwanie nie mają czego dotknąć.
    u, p = make_user(profile_completed=True), make_product(name='Album NCT')
    o = make_order(u, status='oczekujace', order_type='on_hand')
    _pozycja(db, o, p)
    _potwierdzenie(db, o)

    login(u)
    html = client.get('/client/collection?filter=incoming').get_data(as_text=True)
    assert 'openDeleteModal' not in html
    assert 'btn-order-link' in html
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_collection_incoming.py -v`
Expected: PASS — łącznie z testami trasy z Task 5

- [ ] **Step 8: Commit**

```bash
git add templates/client/collection/ tests/test_collection_incoming.py
git commit -m "feat(kolekcja): etap pozycji widoczny w karuzeli, siatce i liscie"
```

---

### Task 7: Style, obsługa filtra i cache

**Files:**
- Modify: `static/css/pages/client/collection.css`
- Modify: `static/js/pages/client/collection.js`
- Modify: `static/sw.js:10` (`CACHE_VERSION`)

**Interfaces:**
- Consumes: klasy `collection-badge--<stage>`, `collection-filter`, `filter-btn[data-filter]` (Task 6)
- Produces: nic dla dalszych zadań (ostatnie)

- [ ] **Step 1: Style badge'ów — light i dark mode**

Dopisz na końcu `static/css/pages/client/collection.css`:

```css
/* ===== Badge etapu realizacji ===== */

.collection-badge {
    display: inline-block;
    padding: 3px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    line-height: 1.4;
    white-space: nowrap;
    border: 1px solid transparent;
}

.collection-badge--unpaid    { background: #fef3c7; color: #92400e; border-color: #fcd34d; }
.collection-badge--ordered   { background: #dbeafe; color: #1e40af; border-color: #93c5fd; }
.collection-badge--transit   { background: #ede9fe; color: #5b21b6; border-color: #c4b5fd; }
.collection-badge--warehouse { background: #e0e7ff; color: #3730a3; border-color: #a5b4fc; }
.collection-badge--shipped   { background: #cffafe; color: #155e75; border-color: #67e8f9; }
.collection-badge--owned     { background: #d1fae5; color: #065f46; border-color: #6ee7b7; }

[data-theme="dark"] .collection-badge {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(240, 147, 251, 0.2);
    backdrop-filter: blur(10px);
}

[data-theme="dark"] .collection-badge--unpaid    { color: #fbbf24; border-color: rgba(251, 191, 36, 0.35); }
[data-theme="dark"] .collection-badge--ordered   { color: #93c5fd; border-color: rgba(147, 197, 253, 0.3); }
[data-theme="dark"] .collection-badge--transit   { color: #c4b5fd; border-color: rgba(196, 181, 253, 0.3); }
[data-theme="dark"] .collection-badge--warehouse { color: #a5b4fc; border-color: rgba(165, 180, 252, 0.3); }
[data-theme="dark"] .collection-badge--shipped   { color: #67e8f9; border-color: rgba(103, 232, 249, 0.3); }
[data-theme="dark"] .collection-badge--owned     { color: #6ee7b7; border-color: rgba(110, 231, 183, 0.3); }

/* ===== Filtr etapu ===== */

.collection-filter {
    display: inline-flex;
    gap: 2px;
    padding: 2px;
    border-radius: 8px;
    background: #f3f4f6;
    border: 1px solid #e0e0e0;
}

.collection-filter .filter-btn {
    min-height: 44px;                  /* dotykowy cel na mobile */
    padding: 0 12px;
    border: none;
    border-radius: 6px;
    background: transparent;
    color: #6b7280;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
}

.collection-filter .filter-btn.active {
    background: #ffffff;
    color: #111827;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
}

[data-theme="dark"] .collection-filter {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
    backdrop-filter: blur(10px);
}

[data-theme="dark"] .collection-filter .filter-btn { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .collection-filter .filter-btn.active {
    background: rgba(240, 147, 251, 0.15);
    color: #ffffff;
    box-shadow: none;
}

.stat-incoming { color: #6b7280; }
[data-theme="dark"] .stat-incoming { color: rgba(255, 255, 255, 0.6); }

```

- [ ] **Step 1b: Siódma kolumna w gridzie listy**

Lista to CSS Grid, a szerokości kolumn są zadeklarowane w **dwóch** miejscach — `.list-header`
(ok. linii 645) i `.collection-row` (ok. linii 665). Oba mają dziś:

```css
    grid-template-columns: 48px minmax(120px, 1fr) 100px 100px 100px 80px;
```

Zamień **obie** deklaracje na siedmiokolumnową (nowa kolumna statusu za „Źródło"):

```css
    grid-template-columns: 48px minmax(120px, 1fr) 100px 140px 100px 100px 80px;
```

Rozjechanie się tych dwóch reguł oznacza nagłówek nietrafiający w kolumny wierszy — zmieniaj je razem.

Na wąskim ekranie (media query ok. linii 1110) grid schodzi do `48px 1fr auto` i chowa
`.col-source`, `.col-price`, `.col-date`. Statusu **nie chowamy** — to sedno tej zmiany.
Kładziemy go w drugim wierszu pod nazwą:

```css
@media (max-width: 768px) {
    .collection-row .col-stage {
        grid-column: 2;
        grid-row: 2;
    }
}
```

Jeśli w podglądzie badge nakłada się na inny element tego wiersza, sprawdź, co jeszcze zajmuje
`grid-row: 2` w `.collection-row`, i przesuń status do własnego wiersza zamiast chować kolumnę.

- [ ] **Step 2: Obsługa filtra w JS**

W `static/js/pages/client/collection.js`, w bloku inicjalizacji obok obsługi sortowania, dopisz:

```javascript
    // ---- Filtr etapu (Wszystko / W drodze / W kolekcji) ----
    document.querySelectorAll('.collection-filter .filter-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var url = new URL(window.location);
            url.searchParams.set('filter', this.getAttribute('data-filter'));
            url.searchParams.delete('page');          // filtr zmienia liczbę stron
            window.location.href = url.toString();
        });
    });
```

W funkcji `applyFilters()` zachowaj filtr przy zmianie wyszukiwania i sortowania — dopisz przed `window.location.href`:

```javascript
        var aktywnyFiltr = document.querySelector('.collection-filter .filter-btn.active');
        if (aktywnyFiltr) {
            url.searchParams.set('filter', aktywnyFiltr.getAttribute('data-filter'));
        }
```

- [ ] **Step 3: Bump CACHE_VERSION**

W `static/sw.js:10` podnieś wersję:

```javascript
const CACHE_VERSION = 'thunderorders-v25';
```

Bez tego klient z rozgrzanym cache dostanie stary JS i nowy filtr nie zadziała.

- [ ] **Step 4: Weryfikacja w przeglądarce**

Uruchom serwer dev i sprawdź na żywo — nie zgaduj, że działa:
- wszystkie trzy widoki pokazują badge etapu
- filtr przełącza listę i zostaje po zmianie sortowania oraz po przejściu na kolejną stronę
- dark mode: badge'y i filtr czytelne (przełącz motyw)
- szerokość mobilna: przyciski filtra mają 44px wysokości, lista nie rozjeżdża się poziomo

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -q`
Expected: PASS — bez regresji względem stanu sprzed planu

- [ ] **Step 6: Commit**

```bash
git add static/css/pages/client/collection.css static/js/pages/client/collection.js static/sw.js
git commit -m "feat(kolekcja): style etapow w obu motywach, filtr i bump cache"
```

---

## Po wdrożeniu

- Przełącz taska ClickUp [869f3nvfc](https://app.clickup.com/t/869f3nvfc) na `complete`
- **Nie pushuj bez zgody Konrada** — push do `main` uruchamia auto-deploy na produkcję
- Mobile API zostaje na starym zachowaniu (`include_incoming=False`). Włączenie pozycji w drodze w apce Flutter to osobny temat: pozycje bez `id` wymagają zmiany po stronie klienta mobilnego
