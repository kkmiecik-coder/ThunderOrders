"""Uzupełnia powiązania partii do Polski z zamówieniami klientów (poland_order_item_orders).

Po co: od PRX/PL/12 (2026-08-14) przydział FIFO przy tworzeniu partii liczył partię
jako „wcześniejszą od samej siebie" (MariaDB obcina mikrosekundy), więc powiązania
prawie nie powstawały, a te nieliczne wskazywały złe sztuki. Bez powiązań zamówienia
nie widzą terminów E2 (wysyłka z Korei) i E3 (cło/VAT).

Co robi: dla każdej nieanulowanej partii utworzonej od `--od` (domyślnie 2026-08-08,
czyli po jednorazowym uzupełnieniu z 2026-08-07) liczy przydział tą samą funkcją
co aplikacja (`_allocate_batch_units_to_orders`) i doprowadza powiązania do zgodności:
  • brakujące — dodaje,
  • z inną ilością — poprawia ilość,
  • wskazujące zamówienie spoza przydziału FIFO — usuwa.
Partii sprzed `--od` nie dotyka (ich powiązania mają historyczne płatności).

Idempotentny: drugie uruchomienie po --apply nic nie zmienia.

Uruchomienie (z katalogu aplikacji, PO zrobieniu kopii bazy mysqldump):
    venv/bin/python scripts/backfill_poland_order_links.py              # tryb próbny
    venv/bin/python scripts/backfill_poland_order_links.py --apply      # zapis
Opcje: --od RRRR-MM-DD, --partia PRX/PL/55 (można kilka razy).
"""
import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

DOMYSLNIE_OD = datetime(2026, 8, 8, tzinfo=timezone.utc)

# Etapy, których termin pochodzi z partii do Polski (przez powiązania).
_ETAPY_Z_PARTII = {
    'shipping_kr': 'payment_deadline',
    'customs_vat': 'customs_payment_deadline',
}


@dataclass
class Zmiana:
    rodzaj: str            # 'dodaj' | 'popraw' | 'usun'
    partia: str            # numer PolandOrder
    poland_order_item_id: int
    order_id: int
    order_number: str
    product_id: int
    ilosc: int             # docelowa ilość (dla 'usun' — ilość usuwana)
    ilosc_byla: int = 0


@dataclass
class Plan:
    zmiany: list = field(default_factory=list)
    partie: int = 0
    pozycje: int = 0
    # order_id -> lista {'stage', 'deadline', 'amount'} — etapy, które PO uzupełnieniu
    # od razu są po terminie i nieopłacone
    od_razu_zalegle: dict = field(default_factory=dict)

    def policz(self, rodzaj):
        return sum(1 for z in self.zmiany if z.rodzaj == rodzaj)


def zaplanuj(od=DOMYSLNIE_OD, numery_partii=None, now=None):
    """Liczy zmiany bez zapisu do bazy. Zwraca `Plan`."""
    from modules.orders.models import Order
    from modules.orders.payment_overdue_service import STAGE_DEFINITIONS
    from modules.products.models import PolandOrder, PolandOrderItem, PolandOrderItemOrder
    from modules.products.routes import _allocate_batch_units_to_orders
    from utils.timeutil import utcnow

    now = now or utcnow()
    plan = Plan()

    zapytanie = (
        PolandOrderItem.query
        .join(PolandOrder, PolandOrderItem.poland_order_id == PolandOrder.id)
        .filter(PolandOrder.status != 'anulowane', PolandOrder.created_at >= od)
    )
    if numery_partii:
        zapytanie = zapytanie.filter(PolandOrder.order_number.in_(numery_partii))
    pozycje = zapytanie.order_by(
        PolandOrder.created_at.asc(), PolandOrder.id.asc(), PolandOrderItem.id.asc()
    ).all()

    plan.pozycje = len(pozycje)
    plan.partie = len({p.poland_order_id for p in pozycje})

    # Docelowe partie każdego dotkniętego zamówienia — do policzenia terminów po zmianie.
    docelowe_partie = defaultdict(set)   # order_id -> {PolandOrder}
    usuwane = defaultdict(set)           # order_id -> {poland_order_item_id}
    dotkniete = set()

    for pozycja in pozycje:
        partia = pozycja.poland_order
        oczekiwane = dict(_allocate_batch_units_to_orders(pozycja))
        istniejace = {
            l.order_id: l for l in
            PolandOrderItemOrder.query.filter_by(poland_order_item_id=pozycja.id).all()
        }

        for order_id, ilosc in oczekiwane.items():
            docelowe_partie[order_id].add(partia)
            link = istniejace.get(order_id)
            if link is None:
                rodzaj, byla = 'dodaj', 0
            elif link.quantity != ilosc:
                rodzaj, byla = 'popraw', link.quantity
            else:
                continue
            dotkniete.add(order_id)
            plan.zmiany.append(Zmiana(rodzaj, partia.order_number, pozycja.id, order_id,
                                      '', pozycja.product_id, ilosc, byla))

        for order_id, link in istniejace.items():
            if order_id in oczekiwane:
                continue
            usuwane[order_id].add(pozycja.id)
            dotkniete.add(order_id)
            plan.zmiany.append(Zmiana('usun', partia.order_number, pozycja.id, order_id,
                                      '', pozycja.product_id, link.quantity, link.quantity))

    zamowienia = {o.id: o for o in Order.query.filter(Order.id.in_(dotkniete)).all()} if dotkniete else {}
    for z in plan.zmiany:
        z.order_number = zamowienia[z.order_id].order_number if z.order_id in zamowienia else '?'

    # Terminy E2/E3 po uzupełnieniu: najwcześniejszy termin spośród partii, z którymi
    # zamówienie będzie powiązane (te same zasady co Order.get_shipping_kr_deadline:
    # nieanulowane partie, najwcześniejszy termin).
    for order_id in dotkniete:
        order = zamowienia.get(order_id)
        if order is None:
            continue
        partie = set(docelowe_partie.get(order_id, set()))
        # Powiązania spoza zakresu skryptu zostają — też dają terminy.
        for link in PolandOrderItemOrder.query.filter_by(order_id=order_id).all():
            if link.poland_order_item_id in usuwane[order_id]:
                continue
            p = link.poland_order_item.poland_order
            if p.status != 'anulowane':
                partie.add(p)

        zalegle = []
        for stage, kolumna in _ETAPY_Z_PARTII.items():
            definicja = STAGE_DEFINITIONS[stage]
            if not definicja['applies'](order):
                continue
            if definicja['status'](order) in ('pending', 'approved'):
                continue
            kwota = definicja['amount'](order)
            if not kwota or kwota <= 0:
                continue
            terminy = [getattr(p, kolumna) for p in partie if getattr(p, kolumna) is not None]
            if not terminy:
                continue
            termin = min(terminy)
            if termin < now:
                zalegle.append({'stage': stage, 'deadline': termin, 'amount': kwota})
        if zalegle:
            plan.od_razu_zalegle[order_id] = zalegle

    return plan


def zastosuj(plan):
    """Zapisuje zmiany z planu w jednej transakcji."""
    from extensions import db
    from modules.products.models import PolandOrderItemOrder

    for z in plan.zmiany:
        link = PolandOrderItemOrder.query.filter_by(
            poland_order_item_id=z.poland_order_item_id, order_id=z.order_id
        ).first()
        if z.rodzaj == 'dodaj' and link is None:
            db.session.add(PolandOrderItemOrder(
                poland_order_item_id=z.poland_order_item_id, order_id=z.order_id, quantity=z.ilosc,
            ))
        elif z.rodzaj == 'popraw' and link is not None:
            link.quantity = z.ilosc
        elif z.rodzaj == 'usun' and link is not None:
            db.session.delete(link)
    db.session.commit()


def wypisz(plan, out=print):
    etykiety = {'dodaj': 'DODAJ ', 'popraw': 'POPRAW', 'usun': 'USUŃ  '}
    for z in plan.zmiany:
        ilosc = f'{z.ilosc_byla} -> {z.ilosc}' if z.rodzaj == 'popraw' else str(z.ilosc)
        out(f'{etykiety[z.rodzaj]} {z.partia:<12} pozycja={z.poland_order_item_id:<6} '
            f'zamówienie={z.order_number} (id {z.order_id}) produkt={z.product_id} ilość={ilosc}')

    out('')
    out(f'Partie w zakresie: {plan.partie}, pozycje: {plan.pozycje}')
    out(f'Do dodania: {plan.policz("dodaj")}, do poprawy: {plan.policz("popraw")}, '
        f'do usunięcia: {plan.policz("usun")}')
    out(f'Zamówienia z nowymi/zmienionymi powiązaniami: {len({z.order_id for z in plan.zmiany})}')

    if plan.od_razu_zalegle:
        suma = sum(e['amount'] for etapy in plan.od_razu_zalegle.values() for e in etapy)
        out(f'UWAGA: po uzupełnieniu od razu po terminie (nieopłacone) będzie '
            f'{len(plan.od_razu_zalegle)} zamówień, łącznie {suma:.2f} zł '
            f'(E2+E3). Cron przypomnień wyśle im maile/push przy najbliższym przebiegu.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='zapisz zmiany (bez tego: tryb próbny)')
    parser.add_argument('--od', default=DOMYSLNIE_OD.strftime('%Y-%m-%d'),
                        help='tylko partie utworzone od tej daty (UTC), domyślnie 2026-08-08')
    parser.add_argument('--partia', action='append', help='tylko podane partie, np. PRX/PL/55')
    args = parser.parse_args(argv)

    od = datetime.strptime(args.od, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import create_app

    app = create_app()
    with app.app_context():
        plan = zaplanuj(od=od, numery_partii=args.partia)
        wypisz(plan)
        if not args.apply:
            print('\nTRYB PRÓBNY — nic nie zapisano. Zapis: dodaj --apply.')
            return 0
        if not plan.zmiany:
            print('\nNic do zapisania.')
            return 0
        zastosuj(plan)
        print(f'\nZAPISANO {len(plan.zmiany)} zmian.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
