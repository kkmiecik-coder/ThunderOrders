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


# ------------------------------------------------------------------ wybrane pozycje

# Pola pozycji kopiowane do nowej pozycji przy przepisaniu części sztuk.
POLA_POZYCJI = (
    'product_id', 'custom_name', 'custom_sku', 'is_custom', 'is_full_set', 'selected_size',
    'price', 'wms_status', 'is_set_fulfilled', 'set_section_id', 'set_number', 'is_bonus',
    'bonus_source_section_id',
)

ETAPY_PRZENOSZONE = ('product', 'korean_shipping', 'customs_vat')


def _ma_gift_cards(item):
    from modules.gift_cards.models import GiftAssignment
    return GiftAssignment.query.filter_by(order_item_id=item.id).first() is not None


def czy_pozycja_prosta(item):
    """Czy z pozycji można przepisać część sztuk.

    Tylko gdy wszystkie sztuki są „takie same”: bez częściowej realizacji, bez
    samych incl-i, bez zebranych w magazynie sztuk i bez przydziałów gift cards —
    inaczej nie wiadomo, które sztuki przechodzą.
    """
    if item.is_set_fulfilled is False:
        return False
    if item.fulfilled_quantity is not None and item.fulfilled_quantity != item.quantity:
        return False
    if (item.incl_only_quantity or 0) > 0 or (item.picked_quantity or 0) > 0:
        return False
    return not _ma_gift_cards(item)


def _waliduj_wybor(order, wybor):
    """Zwraca [(item, ilosc)] albo rzuca TransferError."""
    if not wybor:
        raise TransferError('Zaznacz przynajmniej jedną pozycję do przepisania.')
    pozycje = {i.id: i for i in order.items}
    wynik, widziane = [], set()
    for item_id, ilosc in wybor:
        item = pozycje.get(item_id)
        if item is None or item_id in widziane:
            raise TransferError('Wybrana pozycja nie należy do tego zamówienia.')
        widziane.add(item_id)
        if not isinstance(ilosc, int) or ilosc < 1 or ilosc > item.quantity:
            raise TransferError(
                f'Nieprawidłowa ilość dla „{item.product_name}” (można od 1 do {item.quantity}).')
        if ilosc < item.quantity and not czy_pozycja_prosta(item):
            raise TransferError(
                f'Z pozycji „{item.product_name}” można przepisać tylko całą pozycję '
                f'({item.quantity} szt.) — to set, gift card albo częściowa realizacja.')
        wynik.append((item, ilosc))
    if len(wynik) == len(pozycje) and all(ilosc == item.quantity for item, ilosc in wynik):
        raise TransferError('Zaznaczono wszystko — użyj opcji „Całe zamówienie”.')
    return wynik


def _sprawdz_oczekujace_wplaty(order):
    for conf in order.payment_confirmations:
        if conf.payment_stage in ETAPY_PRZENOSZONE and conf.status == 'pending':
            raise TransferError(
                f'Klientka ma wpłatę „{conf.stage_display_name}”, która czeka na sprawdzenie. '
                'Zatwierdź ją albo odrzuć, zanim przepiszesz kartę razem z wpłatą.')


def _nowe_zamowienie(order, nowa_klientka, admin):
    from modules.orders.models import Order
    from modules.orders.utils import assign_order_number, order_number_placeholder

    nowe = Order(
        order_number=order_number_placeholder(),
        user_id=nowa_klientka.id,
        order_type=order.order_type,
        status=order.status,
        offer_page_id=order.offer_page_id,
        offer_page_name=order.offer_page_name,
        payment_stages=order.payment_stages,
        created_by_admin_id=admin.id,
        fifo_anchor_order_id=order.fifo_anchor_order_id or order.id,
        total_amount=0,
        paid_amount=0,
        shipping_cost=0,
        proxy_shipping_cost=0,
        customs_vat_sale_cost=None,
    )
    nowe.created_at = order.created_at
    db.session.add(nowe)
    db.session.flush()
    assign_order_number(nowe, order.order_type or 'on_hand')
    return nowe


def _przenies_pozycje(wybrane, nowe):
    """Przenosi sztuki do zamówienia `nowe`. Zwraca [(pozycja_docelowa, ilosc, kwota_e1)]."""
    from decimal import Decimal
    from modules.orders.models import OrderItem

    przeniesione = []
    for item, ilosc in wybrane:
        if ilosc == item.quantity:
            kwota = Decimal(str(item.total or 0))
            item.order_id = nowe.id
            item.order = nowe
            przeniesione.append((item, ilosc, kwota))
            continue
        cena = Decimal(str(item.price))
        nowa = OrderItem(order_id=nowe.id, quantity=ilosc, total=cena * ilosc,
                         **{pole: getattr(item, pole) for pole in POLA_POZYCJI})
        item.quantity -= ilosc
        item.total = cena * item.quantity
        db.session.add(nowa)
        przeniesione.append((nowa, ilosc, cena * ilosc))
    db.session.flush()
    return przeniesione


def przepisz_pozycje(order, nowa_klientka, admin, wybor, wplata_za_karta):
    """Przenosi wybrane sztuki do NOWEGO zamówienia nowej klientki.

    wybor: [(order_item_id, ilosc)]. Nowe zamówienie przejmuje datę i miejsce
    w kolejce FIFO oryginału (kotwica). wplata_za_karta=True przenosi opłaconą
    część kwoty; False zostawia wpłatę u dotychczasowej klientki.
    """
    _sprawdz_cel(order, nowa_klientka)
    wybrane = _waliduj_wybor(order, wybor)
    if wplata_za_karta:
        _sprawdz_oczekujace_wplaty(order)
    poprzednia = order.user

    nowe = _nowe_zamowienie(order, nowa_klientka, admin)
    przeniesione = _przenies_pozycje(wybrane, nowe)
    _przenies_gift_cards([poz for poz, _, _ in przeniesione], nowa_klientka)

    db.session.expire(order, ['items'])
    order.recalculate_total_amount()
    nowe.recalculate_total_amount()

    pozycje = [(poz.product_name, ilosc) for poz, ilosc, _ in przeniesione]
    opis_pozycji = ', '.join(f'{nazwa} ×{ilosc}' for nazwa, ilosc in pozycje)
    opis_wplaty = ('wpłata poszła razem z kartą' if wplata_za_karta
                   else 'wpłata została u poprzedniej klientki')
    tresc = (f'Przepisano z {order.order_number} ({_opis_klientki(poprzednia)}) '
             f'do {nowe.order_number} ({_opis_klientki(nowa_klientka)}): {opis_pozycji}; '
             f'{opis_wplaty}.')
    _komentarz(order, admin, tresc)
    _komentarz(nowe, admin, tresc)
    db.session.flush()

    return WynikPrzepisania(zrodlo=order, cel=nowe, poprzednia=poprzednia, pozycje=pozycje,
                            wplata_poszla=bool(wplata_za_karta), cale=False)
