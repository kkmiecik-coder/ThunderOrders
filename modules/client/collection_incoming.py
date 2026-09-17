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
