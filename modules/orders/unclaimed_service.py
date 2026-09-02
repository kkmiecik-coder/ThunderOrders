"""Dane ekranu „Nieodebrane" (projekt 2026-09-02).

Osobny moduł, bo `modules/orders/routes.py` ma już ponad 5000 linii — agregacja
i wysyłka przypomnień żyją tu, trasy zostają cienkie.
"""

import json

from sqlalchemy import desc

from modules.admin.models import ActivityLog
from modules.orders.models import get_local_now


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
