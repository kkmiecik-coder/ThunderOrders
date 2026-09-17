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


# Zapora na konto z patologiczną liczbą zamówień — scalanie i sortowanie robimy
# w Pythonie, więc lista musi mieć sufit. Limit wchodzi w dwóch miejscach:
# `.limit()` na zapytaniu o zamówienia (chroni bazę i pamięć — nie ładujemy
# wszystkich zamówień z pozycjami/produktami naraz) oraz cięcie pętli po
# pozycjach (bo jedno zamówienie z ilością > 1 albo rozbiciem exclusive na
# sztuki potrafi wygenerować więcej pozycji niż zamówień). Przekroczenie
# logujemy: to sygnał, że warto wrócić do wariantu z UNION ALL opisanego w specu.
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

    def __init__(self, order_item, unit_index, unit_count, stage, image_row=None):
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
        # Zdjęcie z batch preloadu (`_preload_primary_images`) — NIE z `self.product.primary_image`,
        # bo `Product.images` jest lazy='dynamic' i to byłby N+1 przy renderowaniu listy.
        self._image_row = image_row

    @property
    def stage_label(self):
        return STAGE_LABELS.get(self.stage, STAGE_LABELS[STAGE_ORDERED])

    @property
    def image_url(self):
        """Zdjęcie produktu (z batch preloadu) albo placeholder — parytet z CollectionItem.image_url."""
        if self._image_row is not None:
            return f'/static/{self._image_row.path_compressed}'
        return PLACEHOLDER_IMAGE

    @property
    def has_real_image(self):
        """Czy jest prawdziwe zdjęcie (nie placeholder) — z batch preloadu.

        Celowo NIE czyta `self.product.primary_image` (to byłby N+1 z `Product.images`
        lazy='dynamic' — patrz komentarz przy `_image_row` w `__init__`). Parytet
        z `CollectionItem.has_real_image`, ale bez odpytywania relacji produktu.
        """
        return self._image_row is not None


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


def _preload_primary_images(product_ids):
    """Jedno zapytanie zamiast N — `Product.primary_image` robi własny SELECT
    na `images` (lazy='dynamic'), więc czytanie go w pętli po pozycjach byłoby N+1.

    Zwraca mapę `product_id -> ProductImage`, wybierając dla każdego produktu
    zdjęcie główne (`is_primary=True`), a w jego braku to o najmniejszym `id` —
    dokładnie tak samo jak `Product.primary_image`, którego gałąź fallback to
    `self.images.first()` na relacji bez `order_by` (czyli najmniejsze `id`).
    Celowo BEZ `sort_order`: to numer slotu z uploadu, nie kolejność wstawienia —
    sortowanie po nim dawałoby inny wynik niż oryginał dla produktu, który dostał
    pierwsze zdjęcie do slotu innego niż 1.
    """
    from modules.products.models import ProductImage

    if not product_ids:
        return {}
    image_by_product = {}
    rows = (
        ProductImage.query
        .filter(ProductImage.product_id.in_(product_ids))
        .order_by(ProductImage.product_id,
                  ProductImage.is_primary.desc(),
                  ProductImage.id.asc())
        .all()
    )
    for img in rows:
        image_by_product.setdefault(img.product_id, img)
    return image_by_product


def _load_qualifying_orders(user_id, limit, with_product):
    """Zamówienia użytkownika (bez wykluczonych statusów) gotowe do przetworzenia,
    z preloadem potwierdzeń płatności (`order._cached_payment_confirmations`).

    Dzielona baza dla `incoming_items` i `count_incoming_items` — ta druga nie
    potrzebuje `OrderItem.product` (nie buduje obiektów ani nie dobiera zdjęć),
    więc `with_product=False` pomija ten joinedload.
    """
    from sqlalchemy.orm import joinedload
    from modules.orders.models import Order, OrderItem, PaymentConfirmation

    items_option = joinedload(Order.items)
    if with_product:
        items_option = items_option.joinedload(OrderItem.product)

    orders = (
        Order.query
        .filter(Order.user_id == user_id, ~Order.status.in_(EXCLUDED_STATUSES))
        .options(items_option)
        .order_by(Order.created_at.desc())
        .limit(limit)          # zapora po stronie bazy — patrz komentarz przy MAX_INCOMING
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

    return orders


def _materialized_order_item_ids(user_id):
    """Id `OrderItem` już zmaterializowanych przez auto_add — wykluczamy po tym,
    a nie po statusie: gdyby materializacja padła, pozycja ma zostać widoczna."""
    from extensions import db
    from modules.client.models import CollectionItem

    return {
        row[0] for row in db.session.query(CollectionItem.order_item_id)
        .filter(CollectionItem.user_id == user_id,
                CollectionItem.order_item_id.isnot(None))
        .all()
    }


def incoming_items(user_id, limit=MAX_INCOMING):
    """Pozycje kolekcji wyliczone z zamówień użytkownika, najnowsze pierwsze."""
    from flask import current_app

    orders = _load_qualifying_orders(user_id, limit, with_product=True)
    if not orders:
        return []

    materialized = _materialized_order_item_ids(user_id)

    # Batch preload zdjęć głównych — patrz `_preload_primary_images`.
    product_ids = {
        order_item.product_id
        for order in orders
        for order_item in order.items
        if order_item.product_id is not None
    }
    image_by_product = _preload_primary_images(product_ids)

    result = []
    for order in orders:
        if not _order_qualifies(order):
            continue
        stage = stage_for_order(order)
        for order_item in order.items:
            if order_item.id in materialized:
                continue
            quantity = _effective_quantity(order_item)
            image_row = image_by_product.get(order_item.product_id)
            for unit_index in range(quantity):
                result.append(VirtualCollectionItem(order_item, unit_index, quantity, stage, image_row))
                if len(result) >= limit:
                    current_app.logger.warning(
                        'Kolekcja: użytkownik %s przekroczył limit %s pozycji w drodze — '
                        'lista ucięta. Rozważ przejście na UNION ALL.', user_id, limit)
                    return result
    return result


def count_incoming_items(user_id, limit=MAX_INCOMING):
    """Liczba pozycji, którą zwróciłoby `incoming_items(user_id)` — bez budowania
    obiektów `VirtualCollectionItem` i bez preloadu zdjęć.

    UWAGA: obecnie BEZ konsumenta w kodzie produkcyjnym. Miała służyć trasie
    kolekcji przy `filter=owned` (licznik „W drodze" bez budowania pełnej listy),
    ale `collection_service.list_items()` w tej gałęzi i tak musi zbudować pełną
    `incoming_items()` (żeby domieszać do „W kolekcji" pozycje ze
    `stage == STAGE_OWNED` — patrz M3), więc trasa liczy licznik z tego, co
    serwis już policzył (`pagination.incoming_total`), zamiast wołać coś
    osobno — drugie, niezależne przejście przez zamówienia w jednym żądaniu
    było regresją wydajnościową wykrytą w re-recenzji. Funkcja zostaje jako
    tania alternatywa dla przyszłych miejsc, którym wystarczy sama liczba bez
    budowania listy (i ma własny test parytetu z `incoming_items`). Te same
    reguły co `incoming_items`: kwalifikacja zamówienia (`_order_qualifies`),
    wykluczenie już zmaterializowanych pozycji i rozbicie na sztuki przy
    `quantity > 1` (`_effective_quantity`).
    """
    orders = _load_qualifying_orders(user_id, limit, with_product=False)
    if not orders:
        return 0

    materialized = _materialized_order_item_ids(user_id)

    total = 0
    for order in orders:
        if not _order_qualifies(order):
            continue
        for order_item in order.items:
            if order_item.id in materialized:
                continue
            for _ in range(_effective_quantity(order_item)):
                total += 1
                if total >= limit:
                    return total
    return total
