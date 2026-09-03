"""Dane ekranu „Nieodebrane" (projekt 2026-09-02).

Osobny moduł, bo `modules/orders/routes.py` ma już ponad 5000 linii — agregacja
i wysyłka przypomnień żyją tu, trasy zostają cienkie.
"""

import json

from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from extensions import db
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
        # Dwie akcje wpisują zmianę statusu zamówienia do dziennika: ręczna/hurtowa
        # zmiana w panelu loguje 'order_status_change' (routes.py), a GŁÓWNA,
        # automatyczna droga wejścia w status (towar dojechał i pokrył zamówienia,
        # `_apply_coverage_status_update` w modules/products/routes.py) loguje
        # 'order_status_auto_updated' — inny action, ten sam kształt new_value
        # ({'status': ...} przez json.dumps). Pominięcie drugiej akcji zostawiałoby
        # fallback ślepym na zdecydowaną większość zaległości sprzed wdrożenia tej
        # kolumny, bo to właśnie ta droga najczęściej wprowadza zamówienia w status
        # „nieodebrane". (Trzecia droga, `reopen_orders_for_wms`, w ogóle nie loguje
        # activity_log na poziomie zamówienia — dla niej fallback i tak zwróci
        # (None, False), czyli „wiek nieznany", co jest bezpieczne: patrz P2.)
        wpisy = ActivityLog.query.filter(
            ActivityLog.action.in_(('order_status_change', 'order_status_auto_updated')),
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
            'ostatnie_przypomnienie': None, 'ma_nieznany_wiek': False,
        })
        wpis['zamowienia'].append(o)

        dni, dokladne = wiek.get(o.id, (None, False))
        # Wiersz klienta pokazuje jego NAJSTARSZĄ ZNANĄ zaległość — to ona
        # decyduje, jak pilnie trzeba mu przypomnieć. Ale samo `dni` nie
        # wystarcza do sortowania: klient z jednym zamówieniem bez daty (może
        # leżeć 400 dni) i jednym sprzed 10 dni pokazałby tu „10 dni" i wylądował
        # nisko na liście, mimo że realnie może zalegać najdłużej ze wszystkich.
        # `ma_nieznany_wiek` pamięta, że część zamówień tego klienta nie ma
        # policzalnego wieku — klucz sortowania (niżej) wysyła taki wiersz na
        # górę niezależnie od tego, co pokazuje `dni`.
        if dni is None:
            # Zamówienie bez policzalnego wieku nie mówi nic o PRECYZJI liczby,
            # którą pokażemy (`wpis['dni']` bierze się z INNYCH zamówień tego
            # klienta) — to osobna informacja, sygnalizowana w szablonie przez
            # „+?", nie przez tyldę. Stąd `dokladne` (zawsze False dla takiego
            # wpisu w `wiek_zaleglosci`) NIE ma tu brudzić `wpis['dokladne']`.
            wpis['ma_nieznany_wiek'] = True
        else:
            if wpis['dni'] is None or dni > wpis['dni']:
                wpis['dni'] = dni
            if not dokladne:
                wpis['dokladne'] = False  # jedna niepewna data spośród ZNANYCH brudzi cały wiersz

        if o.pickup_reminder_sent_at is not None and (
            wpis['ostatnie_przypomnienie'] is None
            or o.pickup_reminder_sent_at > wpis['ostatnie_przypomnienie']
        ):
            wpis['ostatnie_przypomnienie'] = o.pickup_reminder_sent_at

    # Klient, u którego CHOĆBY JEDNO zamówienie ma nieznany wiek, trafia na górę —
    # niezależnie od tego, ile pokazuje `dni` dla jego znanych zaległości. Wiek
    # nieznany może w rzeczywistości być największy ze wszystkich (zamówienie
    # sprzed wdrożenia kolumny, bez wpisu w dzienniku), więc pokazywanie tu
    # najmłodszej znanej daty i sortowanie po niej chowałoby najgorszych
    # zalegaczy na dole listy. `-1` sortowałoby na dół, stąd nieskończoność.
    klienci = sorted(
        wg_klienta.values(),
        key=lambda w: float('inf') if (w['ma_nieznany_wiek'] or w['dni'] is None) else w['dni'],
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
                # user_id -> wpis klienta tego produktu. Osobna mapa od `klienci` (set,
                # tylko do liczenia `klientow`) — ten sam klient z tym produktem w dwóch
                # zamówieniach ma dać JEDNĄ pozycję z sumą sztuk, nie dwie.
                'klienci_wg_id': {},
                'wlasny': wlasny,
            })
            wpis['sztuk'] += it.quantity or 0
            wpis['klienci'].add(o.user_id)
            klient_wpis = wpis['klienci_wg_id'].setdefault(
                o.user_id, {'user': o.user, 'sztuk': 0}
            )
            klient_wpis['sztuk'] += it.quantity or 0

    produkty = [
        {'product_id': w['product_id'], 'nazwa': w['nazwa'], 'sztuk': w['sztuk'],
         'klientow': len(w['klienci']), 'wlasny': w['wlasny'],
         # Rozwinięcie wiersza produktu pokazuje „czyje są te sztuki" — malejąco po
         # liczbie sztuk, bo właścicielka najpierw chce wiedzieć, kto ma najwięcej.
         'lista_klientow': sorted(
             w['klienci_wg_id'].values(), key=lambda k: k['sztuk'], reverse=True
         )}
        for w in wg_produktu.values()
    ]
    # Pozycje własne zawsze na końcu — nie mają karty w magazynie, więc mieszanie
    # ich z katalogiem tylko zaśmieca listę.
    produkty.sort(key=lambda p: (p['wlasny'], -p['sztuk']))

    return {'klienci': klienci, 'produkty': produkty}


def wyslij_przypomnienia(user_ids):
    """Wysyła przypomnienia o odbiorze do wskazanych klientów.

    Zaległości pobierane są tu na nowo, a nie przyjmowane z przeglądarki: między
    wyrenderowaniem ekranu a kliknięciem przycisku klient mógł już zamówić wysyłkę
    i przypominanie mu o tym byłoby wpadką.

    Przypomnienie idzie TRZEMA kanałami: mail, push i dzwoneczek w centrum
    powiadomień. Mail ma własny przełącznik (`notify_pickup_reminder` w ustawieniach)
    i może pominąć pojedynczego klienta bez adresu e-mail — to nie może gasić
    pozostałych dwóch kanałów. Push ma własną, niezależną kontrolę per użytkownik
    (`NotificationPreference.shipping_updates`, sprawdzaną wewnątrz `PushManager`),
    więc nie potrzebuje bramki od maila. Dlatego stemplowanie `pickup_reminder_sent_at`
    i wywołanie pusha idą do KAŻDEGO klienta z realną zaległością, niezależnie od
    tego, czy i ile maili faktycznie poszło.

    Returns:
        dict: {'wyslane': int, 'maile': int, 'bez_maila': int,
               'mail_wylaczony': bool, 'pominieci': [str]}
            - 'wyslane': liczba klientów, do których poszło przypomnienie (czyli
              tych z realną zaległością) — to ta liczba trafia do komunikatu
              na ekranie;
            - 'maile': liczba zakolejkowanych wiadomości e-mail (może być 0 przy
              wyłączonym przełączniku albo gdy nikt z zaznaczonych nie ma adresu —
              to nie znaczy, że 'wyslane' też jest 0);
            - 'bez_maila': liczba klientów spośród 'wyslane', którzy nie mają
              zapisanego adresu e-mail — bez tego `maile < wyslane` milczy o
              przyczynie i właścicielka myśli, że mail poszedł do wszystkich;
            - 'mail_wylaczony': czy przełącznik „Przypomnienie o odbiorze" jest
              wyłączony w ustawieniach — odróżnia to od samego braku adresów,
              bo `maile == 0` ma dwa zupełnie inne wytłumaczenia;
            - 'pominieci': identyfikatory klientów, którzy w międzyczasie przestali
              zalegać.
    """
    from utils.email_manager import EmailManager
    from utils.push_manager import PushManager

    if not user_ids:
        return {'wyslane': 0, 'maile': 0, 'bez_maila': 0,
                'mail_wylaczony': False, 'pominieci': []}

    zamowienia = unclaimed_orders_query().filter(
        Order.user_id.in_(user_ids)
    ).options(
        joinedload(Order.user),
        joinedload(Order.items).joinedload(OrderItem.product),
    ).all()

    wg_klienta = {}
    for o in zamowienia:
        wg_klienta.setdefault(o.user_id, {'user': o.user, 'zamowienia': []})
        wg_klienta[o.user_id]['zamowienia'].append(o)

    pominieci = [str(uid) for uid in user_ids if uid not in wg_klienta]
    if not wg_klienta:
        return {'wyslane': 0, 'maile': 0, 'bez_maila': 0,
                'mail_wylaczony': False, 'pominieci': pominieci}

    mail_wylaczony = not EmailManager.is_email_enabled('notify_pickup_reminder')
    bez_maila = sum(1 for w in wg_klienta.values() if not getattr(w['user'], 'email', None))

    # Stempel NAJPIERW, powiadomienia PO commicie: `send_email_batch` (jak i wątek
    # pusha) startuje natychmiast, więc gdyby mail/push poszły przed commitem,
    # a commit padł, klient dostałby wiadomość bez zapisanego stempla — przy
    # następnym kliknięciu ostrzeżenie o 7 dniach by nie zadziałało i ta sama
    # osoba dostałaby drugie przypomnienie.
    teraz = get_local_now()
    for w in wg_klienta.values():
        for o in w['zamowienia']:
            o.pickup_reminder_sent_at = teraz
    db.session.commit()

    # Mail podlega swojemu przełącznikowi (i pomija pojedynczych klientów bez
    # adresu) — licznik zakolejkowanych wiadomości jest osobny od tego, ilu
    # klientów faktycznie dostało przypomnienie.
    maile = EmailManager.notify_pickup_reminder_bulk(
        [(w['user'], w['zamowienia']) for w in wg_klienta.values()]
    )

    # Push: JEDEN wątek tła na całą operację, nie jeden na klienta — patrz
    # docstring `PushManager.notify_pickup_reminder_bulk`. Ekran nie ma
    # paginacji i ma „Zaznacz wszystkich", więc pętla `_fire_and_forget` po
    # kliencie odpalałaby przy większej zaległości dziesiątki wątków OS naraz.
    PushManager.notify_pickup_reminder_bulk(
        [(user_id, len(w['zamowienia'])) for user_id, w in wg_klienta.items()]
    )

    return {
        'wyslane': len(wg_klienta), 'maile': maile, 'bez_maila': bez_maila,
        'mail_wylaczony': mail_wylaczony, 'pominieci': pominieci,
    }
