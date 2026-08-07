# Jeden mail o wysyłce na paczkę zamiast na każde zamówienie

Zadanie ClickUp: [869efb233](https://app.clickup.com/t/869efb233)
Data: 2026-08-07
Gałąź: `feat/jeden-mail-o-wysylce-na-paczke`

## Problem

Przy oznaczaniu zlecenia wysyłki jako wysłane kod leci pętlą po zamówieniach
i dla każdego z osobna woła powiadomienie. Trzy zamówienia w jednym kartonie
= trzy maile i trzy pushe o tej samej przesyłce. Fizycznie klient dostaje
jedną paczkę, więc reszta to szum.

Ta sama pętla jest w dwóch miejscach:

1. `ship_shipping_request()` — `modules/orders/wms_utils.py:321`
   (panel w sesji WMS i lista zleceń)
2. `admin_update_shipping_request()` — `modules/orders/routes.py:3935`
   (dopisanie numeru przesyłki przy edycji zlecenia) — zadanie tego nie wymienia,
   ale robi dokładnie to samo

Trzecie i czwarte wywołanie (`routes.py:719`, `routes.py:1087`) dotyczą
numeru przesyłki dopisanego do **pojedynczego zamówienia**, poza kontekstem
paczki — tam jeden mail to jeden mail i nie ma czego łączyć.

## Cel

Jedna wiadomość na zlecenie wysyłki, w środku lista wszystkich zamówień
jadących w tej paczce, plus numer przesyłki i link do śledzenia.

## Decyzje

| Pytanie | Decyzja |
|---|---|
| Szablon przy jednym zamówieniu | Zawsze nowy szablon „paczka", także dla jednego zamówienia — jeden szablon do utrzymania |
| Mail o statusie vs. mail o numerze | Jeden wspólny szablon; blok ze śledzeniem pojawia się tylko, gdy numer jest. Rozróżnienie w temacie maila |
| Push | Jeden push na paczkę, prowadzi do listy zleceń wysyłki klienta |
| Zakres | Oba miejsca paczkowe (WMS + edycja zlecenia) |
| Gdzie mieszka kod | Nowa metoda paczkowa w `EmailManager` / `PushManager`, wzorem `notify_shipping_request_created` |
| Przełączniki w ustawieniach | Bez nowych — korzystamy z istniejących `notify_tracking_added` / `notify_status_change` |
| Push przy edycji zlecenia | Dokładamy (dziś go tam nie ma — niespójność) |

## Rozwiązanie

### Nowe komponenty

**`templates/emails/shipment_sent.html`** — szablon maila o wysłanej paczce.
Wzorowany układem na `shipping_request_created.html` (ten sam nagłówek z logo,
ta sama szerokość, ta sama stopka).

Zawartość:
- ikona 📦 i nagłówek „Twoja paczka jest w drodze"
- powitanie po imieniu
- zdanie o tym, że zamówienia jadą w jednej paczce, z numerem zlecenia
- lista numerów zamówień (same numery, bez dodatkowych danych)
- blok ze śledzeniem — kurier, numer przesyłki, przycisk „Śledź przesyłkę" —
  renderowany **warunkowo**, tylko gdy `tracking_number` jest ustawiony
- bez adresu dostawy (jest już w mailu o utworzeniu zlecenia)

**`utils/email_sender.py` → `send_shipment_sent_email(...)`**

Parametry: `user_email`, `user_name`, `request_number`, `order_numbers` (lista),
`tracking_number`, `courier_name`, `tracking_url`.

Temat zależny od obecności numeru:
- z numerem: `Numer przesyłki do Twojej paczki - {request_number} - ThunderOrders`
- bez numeru: `Twoja paczka została wysłana - {request_number} - ThunderOrders`

**`utils/email_manager.py` → `EmailManager.notify_shipment_sent(...)`**

Sygnatura: `notify_shipment_sent(shipping_request, *, tracking_number=None,
courier=None, courier_name=None, tracking_url=None)`.

Odpowiedzialności:
- sprawdzenie przełącznika: `notify_tracking_added` gdy numer jest,
  `notify_status_change` gdy go nie ma
- ustalenie adresu klienta: `shipping_request.user.email`, a gdy zlecenie nie ma
  użytkownika — `customer_email` pierwszego zamówienia (to i tak `user.email`,
  patrz `Order.customer_email`); imię jak w `notify_shipping_request_created`:
  `first_name or 'Kliencie'`
- wygenerowanie `tracking_url`, gdy nie podano, a jest kurier i numer
- zebranie `order_numbers` z `shipping_request.orders`
- wywołanie `send_shipment_sent_email`, log sukcesu/błędu

**`utils/push_manager.py` → `PushManager.notify_shipment_sent(...)`**

Wzorem `notify_shipping_status_change`:
- tytuł: `Wysyłka: {request_number}`
- treść z numerem: `{courier_name}: {tracking_number} — {n} zamówienia/ń`
- treść bez numeru: `Paczka wysłana — {n} zamówienia/ń`
- url: `client.shipping_requests_list`
- tag: `shipment-sent-{shipping_request.id}`
- typ: `shipping_updates`

### Zmiany w miejscach wywołania

**`modules/orders/wms_utils.py`** — pętla `for order in sr.orders` wysyłająca
powiadomienia znika. Zostają dotychczasowe zbiory (`new_shipment_order_ids`,
`changed_status_order_ids`) — służą teraz do decyzji na poziomie paczki:

- `new_shipment_order_ids` niepuste → jedno `notify_shipment_sent` **z numerem**
- inaczej, `changed_status_order_ids` niepuste (i `order_status` istnieje) →
  jedno `notify_shipment_sent` **bez numeru**
- inaczej → brak powiadomienia

Całość w jednym `try/except` — błąd powiadomienia trafia do logów i nie cofa
zapisanej wysyłki (commit jest wcześniej, tak jak dziś).

Pętla tworząca wpisy `OrderShipment` **zostaje bez zmian** — wpisy nadal
powstają per zamówienie, zmienia się tylko liczba wiadomości.

**`modules/orders/routes.py:3935`** — pętla tworząca `OrderShipment` zostaje,
znika z niej wywołanie `EmailManager.notify_tracking_added`. Po pętli jedno
`EmailManager.notify_shipment_sent` i jedno `PushManager.notify_shipment_sent`.

### Czego nie ruszamy

- `EmailManager.notify_tracking_added` / `notify_status_change` i ich
  odpowiedniki w `PushManager` — zostają nietknięte, używają ich pozostałe
  miejsca (pojedyncze zamówienia)
- mail ze zdjęciem paczki (`notify_packing_photo`) — naprawiony w 869edykjd
- mail o utworzeniu zlecenia (`notify_shipping_request_created`) — służy jako wzór
- statusy zamówień i zleceń — bez zmian
- baza danych — bez nowych kolumn, bez migracji

## Przypadki brzegowe

**Paczka mieszana** — część zamówień ma już wpis przesyłki, część nie.
Leci jeden mail z pełną listą. Klient zobaczy też zamówienia, o których już
wiedział, ale w kontekście „to wszystko jedzie razem" jest to poprawna
informacja.

**Ponowne oznaczenie wysłanej paczki** — `ship_shipping_request` i tak rzuca
`ShippingRequestAlreadyShipped`. Gdyby jednak żaden wpis nie powstał i żaden
status się nie zmienił, mail nie idzie.

**Zlecenie bez klienta** (`user_id` NULL po usunięciu konta) — metoda kończy
się cicho, tak jak istniejące metody push.

**Brak adresu e-mail** — log ostrzeżenia i wyjście, wzorem
`notify_shipping_request_created`.

**Zlecenie z jednym zamówieniem** — dostaje nowy szablon paczkowy z listą
jednoelementową. Świadoma zmiana wyglądu maila (decyzja wyżej).

## Testy

Nowy plik `tests/test_shipment_sent_notification.py`:

- paczka z 3 zamówieniami + numer przesyłki → dokładnie **jeden** mail
  i **jeden** push; mail zawiera wszystkie 3 numery zamówień
- ta sama paczka bez numeru → jeden mail, bez bloku ze śledzeniem
- paczka z 1 zamówieniem → jeden mail, lista jednoelementowa
- oznaczenie paczki, której zamówienia mają już wpisy przesyłki z tym numerem
  → **zero** maili
- dopisanie numeru przy edycji zlecenia (`routes.py:3935`) → jeden mail
  i jeden push
- zlecenie bez adresu e-mail → brak wysyłki, brak wyjątku

Aktualizacja `tests/test_wms_ship_and_reopen.py` — fixture `notifications`
podmienia dziś `notify_tracking_added` / `notify_status_change` per zamówienie.
Do podmiany na `notify_shipment_sent`. Pozostałe asercje tych testów
(statusy, wpisy przesyłki, cofanie do WMS) muszą przechodzić bez zmian.

Uruchomienie: `python -m pytest tests/ -q`

## Ryzyka

- Po wdrożeniu maile o wysyłce wyglądają inaczej także przy jednym zamówieniu —
  świadoma decyzja, ale warto zerknąć na pierwszą realną wysyłkę
- Renderowanie nowego szablonu warto sprawdzić testem renderowania,
  bo przeklikanie maila lokalnie jest ograniczone
