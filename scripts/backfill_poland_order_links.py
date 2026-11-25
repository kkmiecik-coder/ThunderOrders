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

`--nowy-termin "RRRR-MM-DD GG:MM"` (czas polski): partiom w zakresie, których termin
E2 (`payment_deadline`) albo E3 (`customs_payment_deadline`) JUŻ MINĄŁ, ustawia ten
termin. Terminów pustych (NULL) i przyszłych nie rusza. Dzięki temu klientki nie
dostają zaległości za terminy, których nie widziały, tylko normalne przypomnienia
przed nowym terminem.

Idempotentny: drugie uruchomienie po --apply nic nie zmienia.

Uruchomienie (z katalogu aplikacji, PO zrobieniu kopii bazy mysqldump):
    venv/bin/python scripts/backfill_poland_order_links.py --nowy-termin "2026-12-02 23:59"          # próba
    venv/bin/python scripts/backfill_poland_order_links.py --nowy-termin "2026-12-02 23:59" --apply  # zapis
Inne opcje: --od RRRR-MM-DD, --partia PRX/PL/55 (można kilka razy).
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
_NAZWY_POL = {'payment_deadline': 'E2 (wysyłka KR)', 'customs_payment_deadline': 'E3 (cło/VAT)'}


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
class ZmianaTerminu:
    poland_order_id: int
    partia: str
    pole: str              # 'payment_deadline' | 'customs_payment_deadline'
    stary: datetime
    nowy: datetime


@dataclass
class Plan:
    zmiany: list = field(default_factory=list)
    zmiany_terminow: list = field(default_factory=list)
    partie: int = 0
    pozycje: int = 0
    # order_id -> lista {'stage', 'deadline', 'amount'} — etapy, które PO uzupełnieniu
    # od razu są po terminie i nieopłacone (dostaną zaległość i przypomnienia od razu)
    od_razu_zalegle: dict = field(default_factory=dict)
    # order_id -> lista {'stage', 'deadline', 'amount'} — etapy nieopłacone z terminem
    # w przyszłości (dostaną zwykłe przypomnienia przed terminem)
    przypomnienia: dict = field(default_factory=dict)
    # order_id -> user_id dla zamówień z dwóch słowników wyżej
    klientki: dict = field(default_factory=dict)
    # (order_id, stage) -> lista godzin reguł, których przypomnienie NIE pójdzie, bo
    # w payment_reminder_logs jest już wpis z dawnego terminu tego etapu
    zablokowane_logami: dict = field(default_factory=dict)

    def policz(self, rodzaj):
        return sum(1 for z in self.zmiany if z.rodzaj == rodzaj)


def zaplanuj(od=DOMYSLNIE_OD, numery_partii=None, now=None, nowy_termin=None):
    """Liczy zmiany bez zapisu do bazy. Zwraca `Plan`."""
    from modules.offers.reminder_models import PaymentReminderConfig, PaymentReminderLog
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
    partie_w_zakresie = {}
    for p in pozycje:
        partie_w_zakresie.setdefault(p.poland_order_id, p.poland_order)
    plan.partie = len(partie_w_zakresie)

    # --- nowe terminy (tylko minione, tylko w zakresie) -------------------------
    nowe_terminy = {}  # (poland_order_id, pole) -> nowy termin
    if nowy_termin is not None:
        for partia in partie_w_zakresie.values():
            for pole in _ETAPY_Z_PARTII.values():
                stary = getattr(partia, pole)
                if stary is not None and stary < now:
                    nowe_terminy[(partia.id, pole)] = nowy_termin
                    plan.zmiany_terminow.append(
                        ZmianaTerminu(partia.id, partia.order_number, pole, stary, nowy_termin))

    def termin(partia, pole):
        return nowe_terminy.get((partia.id, pole), getattr(partia, pole))

    # --- powiązania ---------------------------------------------------------------
    docelowe_partie = defaultdict(set)   # order_id -> {PolandOrder}
    usuwane = defaultdict(set)           # order_id -> {poland_order_item_id}
    dotkniete = set()                    # zamówienia, których powiązania się zmienią

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

    # Raport terminów obejmuje wszystkie zamówienia powiązane z partiami z zakresu
    # PO uzupełnieniu (także te, którym zmienia się tylko termin partii).
    raportowane = set(docelowe_partie) | dotkniete
    zamowienia = ({o.id: o for o in Order.query.filter(Order.id.in_(raportowane)).all()}
                  if raportowane else {})
    for z in plan.zmiany:
        z.order_number = zamowienia[z.order_id].order_number if z.order_id in zamowienia else '?'

    reguly_przed_terminem = PaymentReminderConfig.query.filter_by(
        enabled=True, reminder_type='before_deadline').all()

    # Terminy E2/E3 po uzupełnieniu: najwcześniejszy termin spośród nieanulowanych
    # partii, z którymi zamówienie będzie powiązane (zasada Order.get_shipping_kr_deadline).
    for order_id in raportowane:
        order = zamowienia.get(order_id)
        if order is None or order.status == 'anulowane':
            continue
        partie = set(docelowe_partie.get(order_id, set()))
        # Powiązania spoza zakresu skryptu zostają — też dają terminy.
        for link in PolandOrderItemOrder.query.filter_by(order_id=order_id).all():
            if link.poland_order_item_id in usuwane[order_id]:
                continue
            p = link.poland_order_item.poland_order
            if p.status != 'anulowane':
                partie.add(p)

        for stage, pole in _ETAPY_Z_PARTII.items():
            definicja = STAGE_DEFINITIONS[stage]
            if not definicja['applies'](order):
                continue
            if definicja['status'](order) in ('pending', 'approved'):
                continue
            kwota = definicja['amount'](order)
            if not kwota or kwota <= 0:
                continue
            terminy = [termin(p, pole) for p in partie if termin(p, pole) is not None]
            if not terminy:
                continue
            najwczesniejszy = min(terminy)
            wpis = {'stage': stage, 'deadline': najwczesniejszy, 'amount': kwota}
            cel = plan.od_razu_zalegle if najwczesniejszy < now else plan.przypomnienia
            cel.setdefault(order_id, []).append(wpis)
            plan.klientki[order_id] = order.user_id

            zablokowane = [
                r.hours for r in reguly_przed_terminem
                if PaymentReminderLog.query.filter_by(
                    order_id=order_id, config_id=r.id, stage=stage).first() is not None
            ]
            if zablokowane:
                plan.zablokowane_logami[(order_id, stage)] = sorted(zablokowane)

    return plan


def zastosuj(plan):
    """Zapisuje zmiany z planu w jednej transakcji."""
    from extensions import db
    from modules.products.models import PolandOrder, PolandOrderItemOrder

    for t in plan.zmiany_terminow:
        partia = db.session.get(PolandOrder, t.poland_order_id)
        # Tylko jeśli termin nadal jest ten stary — bezpieczne przy ponownym / spóźnionym
        # uruchomieniu (nie nadpisze terminu, który ktoś w międzyczasie zmienił).
        if partia is not None and getattr(partia, t.pole) == t.stary:
            setattr(partia, t.pole, t.nowy)

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


def _pl(dt):
    from utils.timeutil import to_pl
    return to_pl(dt).strftime('%d.%m.%Y %H:%M')


def _podsumuj_etapy(slownik, plan):
    zamowienia = set(slownik)
    klientki = {plan.klientki[o] for o in zamowienia}
    kwota = sum(e['amount'] for etapy in slownik.values() for e in etapy)
    return len(zamowienia), len(klientki), kwota


def wypisz(plan, out=print):
    etykiety = {'dodaj': 'DODAJ ', 'popraw': 'POPRAW', 'usun': 'USUŃ  '}
    for z in plan.zmiany:
        ilosc = f'{z.ilosc_byla} -> {z.ilosc}' if z.rodzaj == 'popraw' else str(z.ilosc)
        out(f'{etykiety[z.rodzaj]} {z.partia:<12} pozycja={z.poland_order_item_id:<6} '
            f'zamówienie={z.order_number} (id {z.order_id}) produkt={z.product_id} ilość={ilosc}')

    if plan.zmiany_terminow:
        out('')
        out('NOWE TERMINY (czas polski):')
        for t in plan.zmiany_terminow:
            out(f'TERMIN {t.partia:<12} {_NAZWY_POL[t.pole]:<16} {_pl(t.stary)} -> {_pl(t.nowy)}')

    out('')
    out(f'Partie w zakresie: {plan.partie}, pozycje: {plan.pozycje}')
    out(f'Powiązania — do dodania: {plan.policz("dodaj")}, do poprawy: {plan.policz("popraw")}, '
        f'do usunięcia: {plan.policz("usun")}')
    out(f'Zamówienia z nowymi/zmienionymi powiązaniami: {len({z.order_id for z in plan.zmiany})}')
    out(f'Terminy do zmiany: {len(plan.zmiany_terminow)} '
        f'(w {len({t.poland_order_id for t in plan.zmiany_terminow})} partiach)')

    if plan.przypomnienia:
        zam, kl, kwota = _podsumuj_etapy(plan.przypomnienia, plan)
        for stage, nazwa in (('shipping_kr', 'E2'), ('customs_vat', 'E3')):
            n = sum(1 for etapy in plan.przypomnienia.values() for e in etapy if e['stage'] == stage)
            s = sum(e['amount'] for etapy in plan.przypomnienia.values() for e in etapy if e['stage'] == stage)
            out(f'  {nazwa}: {n} zamówień, {s:.2f} zł')
        out(f'Przypomnienia przed terminem dostanie: {zam} zamówień, {kl} klientek, '
            f'łącznie {kwota:.2f} zł nieopłacone.')
    else:
        out('Przypomnienia przed terminem: nikt (brak nieopłaconych etapów z terminem w przyszłości).')

    if plan.od_razu_zalegle:
        zam, kl, kwota = _podsumuj_etapy(plan.od_razu_zalegle, plan)
        out(f'UWAGA: od razu PO TERMINIE (nieopłacone) będzie {zam} zamówień, {kl} klientek, '
            f'łącznie {kwota:.2f} zł (E2+E3). Cron przypomnień wyśle im maile/push przy '
            f'najbliższym przebiegu.')
    else:
        out('Od razu po terminie: 0 zamówień.')

    if plan.zablokowane_logami:
        out(f'UWAGA: {len(plan.zablokowane_logami)} etapów ma w payment_reminder_logs wpisy z dawnych '
            f'terminów — te przypomnienia NIE pójdą:')
        for (order_id, stage), godziny in sorted(plan.zablokowane_logami.items()):
            out(f'  zamówienie id {order_id} {stage}: reguły {godziny} h')
    else:
        out('Stare wpisy w payment_reminder_logs niczego nie blokują.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--apply', action='store_true', help='zapisz zmiany (bez tego: tryb próbny)')
    parser.add_argument('--od', default=DOMYSLNIE_OD.strftime('%Y-%m-%d'),
                        help='tylko partie utworzone od tej daty (UTC), domyślnie 2026-08-08')
    parser.add_argument('--partia', action='append', help='tylko podane partie, np. PRX/PL/55')
    parser.add_argument('--nowy-termin', help='„RRRR-MM-DD GG:MM" czasu polskiego — nowy termin '
                                              'dla minionych E2/E3 partii w zakresie')
    args = parser.parse_args(argv)

    od = datetime.strptime(args.od, '%Y-%m-%d').replace(tzinfo=timezone.utc)

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import create_app
    from utils.timeutil import pl_input_to_utc, utcnow

    nowy_termin = None
    if args.nowy_termin:
        nowy_termin = pl_input_to_utc(datetime.strptime(args.nowy_termin, '%Y-%m-%d %H:%M'))
        if nowy_termin <= utcnow():
            parser.error('--nowy-termin musi być w przyszłości')

    app = create_app()
    with app.app_context():
        plan = zaplanuj(od=od, numery_partii=args.partia, nowy_termin=nowy_termin)
        wypisz(plan)
        if not args.apply:
            print('\nTRYB PRÓBNY — nic nie zapisano. Zapis: dodaj --apply.')
            return 0
        if not plan.zmiany and not plan.zmiany_terminow:
            print('\nNic do zapisania.')
            return 0
        zastosuj(plan)
        print(f'\nZAPISANO: {len(plan.zmiany)} zmian powiązań, {len(plan.zmiany_terminow)} terminów.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
