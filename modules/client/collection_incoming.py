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
