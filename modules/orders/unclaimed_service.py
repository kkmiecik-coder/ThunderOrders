"""Dane ekranu „Nieodebrane" (projekt 2026-09-02).

Osobny moduł, bo `modules/orders/routes.py` ma już ponad 5000 linii — agregacja
i wysyłka przypomnień żyją tu, trasy zostają cienkie.
"""

import json

from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from modules.admin.models import ActivityLog
from modules.client.shipping_service import unclaimed_orders_query
from modules.orders.models import Order, OrderItem, get_local_now


def wiek_zaleglosci(orders):
    """Ile dni każde zamówienie leży w obecnym statusie.

    Zwraca {order_id: (dni, czy_dokladne)}. `czy_dokladne=False` znaczy, że data
    pochodzi z dziennika zmian, a nie z kolumny — interfejs pokazuje wtedy tyldę,
    żeby właścicielka wiedziała, której liczbie ufać co do dnia.
    `(None, False)` = zamówienie sprzed wdrożenia, którego zmiany statusu nikt nie
    zalogował; ekran sortuje takie na górę, bo leżą najdłużej.

    Dziennik czytany JEDNYM zapytaniem dla całej listy — po jednym na wiersz
    zrobiłoby z ekranu N+1 na tabeli, która rośnie z każdą akcją w systemie.
    """
    if not orders:
        return {}

    teraz = get_local_now()
    wynik = {}
    bez_kolumny = {}

    for o in orders:
        if o.status_changed_at is not None:
            wynik[o.id] = ((teraz - o.status_changed_at).days, True)
        else:
            bez_kolumny[o.id] = o.status

    if bez_kolumny:
        wpisy = ActivityLog.query.filter(
            ActivityLog.action == 'order_status_change',
            ActivityLog.entity_type == 'order',
            ActivityLog.entity_id.in_(bez_kolumny.keys()),
        ).order_by(desc(ActivityLog.created_at)).all()

        znalezione = set()
        for wpis in wpisy:
            if wpis.entity_id in znalezione:
                continue  # wpisy posortowane malejąco — pierwszy trafiony jest najnowszy
            try:
                dane = json.loads(wpis.new_value)
            except (TypeError, ValueError):
                continue
            if dane is None:
                continue
            if not isinstance(dane, dict):
                # `activity_log` to tabela współdzielona przez wielu piszących —
                # nie ma gwarancji, że `new_value` zawsze zdekoduje się do słownika.
                # Pojedynczy nietypowy wiersz (np. '[1,2,3]') ma zostać pominięty,
                # a nie wywalić AttributeError-em liczenie dla WSZYSTKICH zamówień.
                continue
            status_z_wpisu = dane.get('status')
            if status_z_wpisu != bez_kolumny[wpis.entity_id]:
                continue  # wpis o wejściu w inny status nie datuje obecnej zaległości
            znalezione.add(wpis.entity_id)
            wynik[wpis.entity_id] = ((teraz - wpis.created_at).days, False)

        for order_id in bez_kolumny:
            wynik.setdefault(order_id, (None, False))

    return wynik


def zbierz_nieodebrane():
    """Dane obu zakładek ekranu „Nieodebrane" — jedno przejście po zamówieniach.

    Zwraca {'klienci': [...], 'produkty': [...]}. Obie zakładki renderują się
    z jednego żądania, więc przełączanie ich jest czysto wizualne.
    """
    zamowienia = unclaimed_orders_query().options(
        joinedload(Order.user),
        joinedload(Order.items).joinedload(OrderItem.product),
    ).all()

    if not zamowienia:
        return {'klienci': [], 'produkty': []}

    wiek = wiek_zaleglosci(zamowienia)

    # --- zakładka „Wg klientów" ---
    wg_klienta = {}
    for o in zamowienia:
        wpis = wg_klienta.setdefault(o.user_id, {
            'user': o.user, 'zamowienia': [], 'dni': None, 'dokladne': True,
            'ostatnie_przypomnienie': None,
        })
        wpis['zamowienia'].append(o)

        dni, dokladne = wiek.get(o.id, (None, False))
        # Wiersz klienta pokazuje jego NAJSTARSZĄ zaległość — to ona decyduje,
        # jak pilnie trzeba mu przypomnieć.
        if dni is not None and (wpis['dni'] is None or dni > wpis['dni']):
            wpis['dni'] = dni
        if not dokladne:
            wpis['dokladne'] = False  # jedna niepewna data brudzi cały wiersz

        if o.pickup_reminder_sent_at is not None and (
            wpis['ostatnie_przypomnienie'] is None
            or o.pickup_reminder_sent_at > wpis['ostatnie_przypomnienie']
        ):
            wpis['ostatnie_przypomnienie'] = o.pickup_reminder_sent_at

    # Klient bez policzalnego wieku trafia na górę: skoro nie ma śladu po zmianie
    # statusu, leży od dawna. `-1` sortowałoby go na dół, stąd nieskończoność.
    klienci = sorted(
        wg_klienta.values(),
        key=lambda w: float('inf') if w['dni'] is None else w['dni'],
        reverse=True,
    )

    # --- zakładka „Wg produktów" ---
    wg_produktu = {}
    for o in zamowienia:
        for it in o.items:
            wlasny = it.product_id is None
            klucz = ('custom', it.custom_name or 'Bez nazwy') if wlasny else ('id', it.product_id)
            wpis = wg_produktu.setdefault(klucz, {
                'product_id': it.product_id,
                'nazwa': (it.custom_name or 'Bez nazwy') if wlasny
                         else (it.product.name if it.product else f'Produkt #{it.product_id}'),
                'sztuk': 0,
                'klienci': set(),
                'wlasny': wlasny,
            })
            wpis['sztuk'] += it.quantity or 0
            wpis['klienci'].add(o.user_id)

    produkty = [
        {'product_id': w['product_id'], 'nazwa': w['nazwa'], 'sztuk': w['sztuk'],
         'klientow': len(w['klienci']), 'wlasny': w['wlasny']}
        for w in wg_produktu.values()
    ]
    # Pozycje własne zawsze na końcu — nie mają karty w magazynie, więc mieszanie
    # ich z katalogiem tylko zaśmieca listę.
    produkty.sort(key=lambda p: (p['wlasny'], -p['sztuk']))

    return {'klienci': klienci, 'produkty': produkty}
