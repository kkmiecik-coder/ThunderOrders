# Lista nieodebranych zamówień

Data: 2026-09-02
Gałąź: `feat/lista-nieodebranych-zamowien`

## Problem

Towar dojeżdża z Korei, dostaje status pozwalający zamówić wysyłkę — i część klientów
po prostu nigdy nie klika „zamów wysyłkę". Ich rzeczy leżą w magazynie tygodniami.
Właścicielka nie ma dziś żadnego miejsca, w którym widziałaby, **kto** zalega ani
**czyje** są sztuki zostające na półce po rozesłaniu partii.

Informacja jest w bazie — nikt jej nie zestawia w jednym widoku.

## Ustalenia z właścicielką

- Potrzebne **oba** ujęcia: lista klientów (kto zalega) i lista produktów (czyje są te
  5 light sticków na półce).
- Przypomnienia **ręczne** — zaznacza osoby i wysyła. Automat świadomie odłożony:
  najpierw ma zobaczyć, czy przypominanie w ogóle działa na ludzi.
- Kanał: **mail + push + dzwoneczek**, tak jak reszta powiadomień w systemie.
- Na liście liczy się **wyłącznie** przypadek „towar gotowy, klient nie zamówił
  wysyłki". Niedopłaty i nieopłacone wysyłki to inne problemy — świadomie poza zakresem.
- Osobny ekran, nie filtr na istniejącej liście zamówień. Powód: lista zamówień myśli
  wierszami-zamówieniami, a tu potrzebne są wiersze-ludzie. Klient z trzema zaległymi
  paczkami ma być jednym wierszem, nie trzema.

## Definicja „nieodebrane"

Zamówienie jest nieodebrane, gdy:

1. jego status jest wśród `allowed_request_statuses()` (Settings
   `shipping_request_allowed_statuses`, domyślnie `['dostarczone_gom']`), **oraz**
2. nie istnieje dla niego wiersz w `shipping_request_orders`.

To **ta sama** definicja, na której opiera się `get_available_orders()`
w `modules/client/shipping_service.py` — czyli to, co klient widzi u siebie jako
„możesz zamówić wysyłkę". Dzięki temu ekran admina i strefa klienta nie mogą się
rozjechać, a zmiana ustawienia statusów przestawia oba naraz.

Anulowane zamówienia odpadają same — ich status nie jest w dozwolonych.

### Refaktor: jedno źródło warunku

Z `get_available_orders()` wydzielamy bazowe zapytanie:

```python
def unclaimed_orders_query():
    """Zamówienia gotowe do wysyłki, których klient nie wrzucił do żadnego zlecenia."""
```

`get_available_orders(user_id)` staje się tym zapytaniem zawężonym do jednego
użytkownika, a widok admina bierze je bez zawężenia. Kopiowanie warunku do modułu
admina byłoby drugim źródłem prawdy, które po pierwszej zmianie ustawień zacznie
kłamać.

Funkcja zostaje w `modules/client/shipping_service.py` mimo że woła ją admin —
przenoszenie serwisu do `modules/orders/` ruszałoby importy strefy klienta i API
mobilnego dla czysto kosmetycznego zysku. Wersja rozważana i odrzucona.

## Wiek zaległości („leży X dni")

Kolumna sortująca listę, więc potrzebuje daty wejścia zamówienia w gotowy status.
System takiej daty dziś nie trzyma.

Rozwiązanie dwutorowe — decyzja właścicielki po przedstawieniu wariantów:

1. **Nowa kolumna `Order.status_changed_at`** (DateTime, nullable) + migracja.
   Stemplowana **jednym** listenerem SQLAlchemy na zmianę `Order.status`, nie
   ręcznie w każdej trasie. Sprawdzone: zarówno pojedyncza zmiana statusu
   (`admin_update_status`), jak i hurtowa (`bulk_status_change`) przypisują
   `order.status` przez ORM, więc listener łapie obie — i każdą przyszłą ścieżkę,
   której dziś nie znamy. Ominąć go mogłyby tylko masowe `query.update()`;
   takich w kodzie nie ma.
2. **Fallback z `ActivityLog`** dla zamówień sprzed wdrożenia: ostatni wpis
   `action='order_status_change'`, `entity_type='order'`, `entity_id=order.id`,
   którego `new_value.status` odpowiada obecnemu statusowi. Jedno zapytanie
   zbiorcze dla całej listy (group by `entity_id`), nie po jednym na wiersz.

Wiek policzony z fallbacku jest w interfejsie oznaczony tyldą (`~120 dni`) —
właścicielka ma widzieć, której liczbie ufać co do dnia. Zamówienia bez obu źródeł
(brak kolumny i brak logu) sortują się jako najstarsze i pokazują `~ b.d.`; leżą
najdłużej, więc miejsce na górze listy jest właściwe.

Odrzucone: liczenie z `Order.updated_at`. To pole zmienia się przy każdej edycji
zamówienia, więc dopisanie notatki „odmłodziłoby" zaległość o pół roku — dokładnie
ten sam powód, dla którego `ShippingRequest.shipped_at` istnieje osobno.

## Ekran

- Trasa: `GET /admin/orders/nieodebrane` → `orders.admin_unclaimed`, `@admin_required`
- Szablon: `templates/admin/orders/unclaimed.html`
- Pozycja w `templates/components/sidebar_admin.html`, w sekcji zamówień —
  za `orders.admin_list`

Dane liczone po stronie serwera, jednym zapytaniem z `joinedload` na `user`,
`items` i `items.product`. Grupowanie w Pythonie, obie zakładki renderowane w tym
samym żądaniu; przełącznik zakładek jest czysto wizualny (bez przeładowania).

### Zakładka „Wg klientów" (domyślna)

Wiersz = użytkownik: nick, liczba zaległych zamówień, wiek najstarszego w dniach,
data ostatniego przypomnienia, checkbox. Sortowanie: najstarsze zaległe na górze —
najgorsi zalegacze pierwsi. Rozwinięcie wiersza pokazuje jego zamówienia
(numer, data statusu, pozycje).

### Zakładka „Wg produktów"

Wiersz = produkt: nazwa, suma `OrderItem.quantity`, liczba różnych klientów.
Grupowanie po `OrderItem.product_id`; pozycje własne (`is_custom`, `product_id`
NULL) grupowane po `custom_name` i wyrzucone do osobnej sekcji na dole, żeby nie
mieszały się z katalogiem. Rozwinięcie pokazuje, kto ma te sztuki.

## Przypomnienie

`POST /admin/orders/nieodebrane/przypomnij` → `orders.admin_unclaimed_remind`,
przyjmuje listę `user_id`, CSRF jak reszta panelu.

**Jeden mail na osobę**, ze wszystkimi jej zaległymi zamówieniami w treści — nie
jeden mail na zamówienie. Klient z trzema paczkami dostaje jedną wiadomość.

Wysyłka wzorowana na `EmailManager.notify_costs_added_bulk()`: `prepare_email()`
w pętli, potem jedno `send_email_batch()` — jedno połączenie SMTP na całą operację
zamiast jednego na klienta.

Elementy do dołożenia:

- `templates/emails/pickup_reminder.html` — mail z listą zaległych zamówień
  i linkiem do zamówienia wysyłki
- `EmailManager.notify_pickup_reminder_bulk(users_orders)` — respektuje
  `is_email_enabled('notify_pickup_reminder')`
- `PushManager.notify_pickup_reminder(user, orders)` — push + wpis w dzwoneczku,
  `notification_type='pickup_reminder'`
- `'pickup_reminder': 'przypomnienie o odbiorze'` w `EMAIL_TYPE_LABELS`
  (`modules/admin/models.py`) — żeby mail miał czytelną nazwę w historii wysyłek
- pozycja w ustawieniach maili (`/admin/orders/settings/email-notifications`),
  z możliwością wyłączenia jednym przełącznikiem

### Znacznik ostatniego przypomnienia

Nowa kolumna `Order.pickup_reminder_sent_at` (DateTime, nullable) + migracja
Alembic. Stemplowane są wszystkie zamówienia objęte wysłanym przypomnieniem, więc
data jest widoczna także w ujęciu produktowym.

Wzorzec przepisany z `ShippingRequest.delivery_reminder_sent_at` — kolumna zamiast
tabeli logu, bo interesuje nas wyłącznie „kiedy ostatnio", nie pełna historia.

Jeśli w zaznaczeniu jest ktoś, komu przypomnienie poszło w ciągu **7 dni**, przed
wysyłką pojawia się pytanie potwierdzające z listą tych osób. Ostrzeżenie, nie
blokada — właścicielka może mieć powód, żeby napisać drugi raz.

## Poza zakresem

- automatyczne przypomnienia po X dniach (świadomie odłożone do drugiego kroku)
- niedopłaty do zamówień i nieopłacone zlecenia wysyłki
- stronicowanie listy — dokładane, gdy lista urośnie na tyle, że zacznie przeszkadzać
- kafelek na dashboardzie — dodatek do tego ekranu, nie jego zamiennik

## Weryfikacja

`python -m pytest`, nowy plik `tests/test_nieodebrane_zamowienia.py`:

- zamówienie w dozwolonym statusie, bez zlecenia wysyłki → jest na liście
- to samo zamówienie po utworzeniu zlecenia WYS/... → znika z listy
- zamówienie anulowane → nie trafia na listę
- zmiana `shipping_request_allowed_statuses` przestawia zawartość listy
- zmiana statusu (pojedyncza i hurtowa) stempluje `status_changed_at`
- zamówienie bez `status_changed_at`, ale z wpisem w `ActivityLog` → wiek liczony
  z logu i oznaczony jako przybliżony
- zamówienie bez obu źródeł → sortuje się na górze listy, nie wywraca widoku
- dopisanie notatki do zamówienia NIE zmienia jego wieku zaległości
- lista admina i `get_available_orders()` dla tego samego klienta zwracają ten sam
  zbiór zamówień (ochrona przed rozjazdem obu widoków)
- grupowanie produktowe sumuje `quantity` i liczy klientów; pozycje własne lądują
  w osobnej grupie
- klient z trzema zaległymi zamówieniami dostaje **jeden** mail
- wysyłka stempluje `pickup_reminder_sent_at` na wszystkich objętych zamówieniach
- `notify_pickup_reminder` wyłączone w ustawieniach → mail nie wychodzi

Testy szablonów maili renderujemy w `app.test_request_context()` — globalny context
processor czyta `flask.session`, więc sam `app_context()` nie wystarcza.

Przeklikanie gotowego ekranu zostaje po stronie właścicielki: panel admina jest za
logowaniem, do którego nie mam hasła.
