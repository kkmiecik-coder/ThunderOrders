"""Przepisanie zamówienia (całego albo wybranych pozycji) na inną klientkę.

Spec: docs/superpowers/specs/2026-11-24-przepisz-zamowienie-design.md

Funkcje NIE commitują — robi to wywołujący (trasa), żeby całość była jedną
transakcją. log_activity commituje sam, więc trasa woła go dopiero po commicie.
"""
from dataclasses import dataclass, field

from extensions import db
from modules.orders.models import OrderComment

# Statusy, w których przepisanie nie ma sensu albo psułoby rozliczenia:
# zamknięte (anulowane/zwroty) oraz po wysyłce.
ZABLOKOWANE_STATUSY = ('anulowane', 'do_zwrotu', 'zwrocone', 'czesciowo_zwrocone',
                       'wyslane', 'dostarczone')

POLA_DANYCH_KLIENTKI = (
    'shipping_name', 'shipping_address', 'shipping_postal_code', 'shipping_city',
    'shipping_voivodeship', 'pickup_courier', 'pickup_point_id', 'pickup_address',
    'pickup_postal_code', 'pickup_city', 'delivery_method', 'custom_name',
)


class TransferError(Exception):
    """Przepisanie niemożliwe — komunikat po polsku, do pokazania adminowi."""


@dataclass
class WynikPrzepisania:
    zrodlo: object          # Order, z którego przepisano (przy całym = cel)
    cel: object             # Order nowej klientki
    poprzednia: object      # User — dotychczasowa właścicielka
    pozycje: list = field(default_factory=list)   # [(nazwa produktu, ilość)]
    wplata_poszla: bool = False
    cale: bool = False


def sprawdz_blokady(order):
    """Powód, dla którego zamówienia nie można przepisać, albo None."""
    if order.status in ZABLOKOWANE_STATUSY:
        return f'Zamówienia w statusie „{order.status_display_name}” nie można przepisać.'
    if order.is_in_shipping_request:
        return ('Zamówienie jest w zleceniu wysyłki — najpierw wyjmij je ze zlecenia, '
                'potem przepisz.')
    if order.wms_locked_at or order.wms_session_id:
        return 'Zamówienie jest właśnie pakowane w magazynie (WMS) — spróbuj po spakowaniu sesji.'
    return None


def _sprawdz_cel(order, nowa_klientka):
    if nowa_klientka is None or nowa_klientka.role != 'client':
        raise TransferError('Nie znaleziono klientki, na którą chcesz przepisać zamówienie.')
    if nowa_klientka.id == order.user_id:
        raise TransferError('To zamówienie już należy do tej klientki.')
    powod = sprawdz_blokady(order)
    if powod:
        raise TransferError(powod)


def _opis_klientki(user):
    return f'{user.full_name} ({user.email})'


def _komentarz(order, admin, tresc):
    db.session.add(OrderComment(order_id=order.id, user_id=admin.id, comment=tresc,
                                is_internal=True))


def _przenies_gift_cards(items, nowa_klientka):
    from modules.gift_cards.models import GiftAssignment
    ids = [i.id for i in items if i.id is not None]
    if not ids:
        return
    for przydzial in GiftAssignment.query.filter(GiftAssignment.order_item_id.in_(ids)).all():
        przydzial.user_id = nowa_klientka.id


def przepisz_cale_zamowienie(order, nowa_klientka, admin):
    """Zmiana klientki „na kopercie”: numer, data, kwoty i wpłaty zostają."""
    _sprawdz_cel(order, nowa_klientka)
    poprzednia = order.user

    order.user_id = nowa_klientka.id
    order.user = nowa_klientka
    for pole in POLA_DANYCH_KLIENTKI:
        setattr(order, pole, None)
    if order.notes:
        dopisek = f'Notatka poprzedniej klientki: {order.notes}'
        order.admin_notes = f'{order.admin_notes}\n{dopisek}' if order.admin_notes else dopisek
        order.notes = None

    for conf in order.payment_confirmations:
        if conf.proof_file:
            conf.proof_hidden_for_client = True

    _przenies_gift_cards(order.items, nowa_klientka)

    _komentarz(order, admin,
               f'Przepisano całe zamówienie z {_opis_klientki(poprzednia)} '
               f'na {_opis_klientki(nowa_klientka)}.')
    db.session.flush()

    return WynikPrzepisania(
        zrodlo=order, cel=order, poprzednia=poprzednia, cale=True,
        pozycje=[(i.product_name, i.quantity) for i in order.items],
    )
