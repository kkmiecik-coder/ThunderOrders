# Konsolidacja wysyłek wielu klientów w jedną paczkę

Zadanie ClickUp: [869eckz7u](https://app.clickup.com/t/869eckz7u) — „konsolidacja wysyłek dwóch innych osób"
Data: 2026-08-09
Gałąź: `feat/konsolidacja-wysylek-wielu-klientow`

## Problem

Klientki zamawiają razem — jedna odbiera paczkę dla obu, żeby podzielić koszt wysyłki.
System tego nie potrafi: scalanie zleceń wysyłki (`bulk-merge`, `modules/orders/routes.py:4087`)
twardo odrzuca zlecenia różnych klientów:

```python
user_ids = set(sr.user_id for sr in shipping_requests)
if len(user_ids) > 1:
    return jsonify({'error': 'Zaznaczone zlecenia pochodzą od różnych klientów'}), 400
```

Front blokuje to samo (`allSelectedFromSameClient()`, `static/js/pages/admin/shipping-requests.js:100`).
W efekcie admin wysyła dwie paczki tam, gdzie wystarczyłaby jedna, albo obchodzi system ręcznie.

Obecne scalanie ma też drugą wadę: zabiera numer najstarszego zlecenia i kasuje pozostałe,
więc po scaleniu nie widać, że paczka powstała z kilku zleceń, ani z których.

## Ustalenia biznesowe

Potwierdzone z Konradem przed projektowaniem:

- Klient, który nie jest adresatem, **zachowuje swoje zlecenie** w panelu (web i mobile),
  oznaczone jako wysyłka zbiorcza, ze wspólnym numerem śledzenia.
- **Jeden wspólny flow** — modal konsolidacji obsługuje zarówno różnych klientów, jak
  i kilka zleceń tego samego klienta. Stary `bulk-merge` znika.
- Adres, adresat i kontakt pochodzą z **jednego** zlecenia wiodącego (to ta osoba
  odbiera paczkę, więc kurier ma jej telefon).
- Koszt wysyłki rozliczamy **bez zmian** — admin wpisuje kwotę per zamówienie
  w istniejącym modalu „Dodaj koszty". Żadnego automatycznego dzielenia.
- Edycja konsolidacji obejmuje: zmianę wiodącego, dopięcie zlecenia, wypięcie zlecenia
  i rozwiązanie całości — **do momentu spakowania** paczki.
- Powiadomienia (mail + push) idą do **każdego** uczestnika, plus osobne powiadomienie
  w chwili samego scalenia.
- Karta zbiorcza pokazuje **zamówienia i produkty ze wszystkich zleceń**, pogrupowane
  po właścicielu.

## Decyzje

| Pytanie | Decyzja | Dlaczego |
|---|---|---|
| Model konsolidacji | Nowy `ShippingRequest` z nowym numerem; źródłowe zostają | Pipeline WMS w ~70 miejscach zakłada, że jednostką pakowania jest `ShippingRequest` — konsolidacja jako SR dziedziczy sesje WMS, pakowanie, eksport InPost, tracking i modal kosztów bez zmian |
| Osobna encja `ShipmentConsolidation` | Odrzucona | Wymagałaby przepisania całego WMS, panelu klienta i API mobilnego bez korzyści dla użytkownika |
| Flaga `is_consolidation` w bazie | Bez niej | Zlecenie jest zbiorcze wtedy i tylko wtedy, gdy ma podpięte źródła — jedno źródło prawdy |
| Adres zbiorczego | Kopiowany z wiodącego | Tak samo jak SR kopiuje dziś adres z `ShippingAddress`; eksport InPost i etykiety działają bez zmian |
| Status i tracking | Kopiowane na źródłowe, nie czytane przez property | Panel klienta, mobile i statystyki filtrują po `status` w SQL — property byłoby dla nich niewidoczne |
| Statusy finansowe | Zostają indywidualne na źródłowych | Każdy klient płaci za swoje zamówienia; propagacja w dół cofnęłaby opłacone zlecenie do „czeka na opłacenie” |
| Zlecenie zbiorcze w panelu klienta | Ukryte | Ma `user_id` wiodącego, więc bez tego wiodący zobaczyłby zamówienia obcej osoby |
| Treść maili o paczce | Budowana per uczestnik | `notify_shipment_sent` wymienia wszystkie zamówienia zlecenia — dla paczki zbiorczej ujawniłoby to numery cudzych zamówień |
| Wejście w edycję | Ten sam modal w trybie edycji | Jeden komponent i jeden zestaw styli zamiast czterech osobnych dialogów |
| Układ zamówień w karcie | Grupowanie po kliencie | Nagłówki grup zastępują osobną sekcję „Uczestnicy”; pakujący widzi, czyje rzeczy wkłada do kartonu |

## Model danych

### Migracja

`shipping_requests`:

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `consolidated_into_id` | INT NULL, FK → `shipping_requests.id` | Na zleceniu **źródłowym**: wskazuje paczkę zbiorczą |
| `lead_source_request_id` | INT NULL, FK → `shipping_requests.id` | Na zleceniu **zbiorczym**: które źródło jest wiodące |

`shipping_request_orders`:

| Kolumna | Typ | Znaczenie |
|---|---|---|
| `source_request_id` | INT NULL, FK → `shipping_requests.id` | Z którego zlecenia przyszło zamówienie; NULL = było tu od początku |

Bez `source_request_id` wypięcie i rozwiązanie konsolidacji nie wiedzą, dokąd zwrócić
zamówienia — zwłaszcza gdy jeden klient wrzucił do paczki dwa własne zlecenia.

Numer zlecenia zbiorczego powstaje przez istniejące `ShippingRequest.generate_request_number()`,
czyli jest kolejnym numerem w serii `WYS/000000` — bez osobnego formatu dla paczek zbiorczych.
Rozpoznawalność zapewnia badge, nie numer.

Migracja pisana ręcznie i sprawdzana przed `flask db upgrade`. Klucze obce wskazują na tę
samą tabelę, więc kolejność operacji przy kasowaniu ma znaczenie — patrz „Ryzyka”.

### Właściwości modelu

```python
is_consolidation          # bool(self.consolidated_sources)
is_consolidated_source    # self.consolidated_into_id is not None
consolidation_participants  # [(user, source_sr, orders)] — pogrupowane, dla karty i maili
display_orders            # źródłowe: zamówienia z konsolidacji po source_request_id; inaczej self.orders
can_cancel                # dodatkowo False, gdy consolidated_into_id jest ustawione
```

`consolidation_participants` jest jedynym miejscem, które grupuje zamówienia po właścicielu —
korzystają z niego karta, modal, mail o wysyłce i push.

## Reguły

### Wejście w konsolidację

Wymagane:

- co najmniej 2 zlecenia,
- żadne nie jest już wpięte w inną konsolidację (`consolidated_into_id IS NULL`),
- żadne nie ma statusu `wyslane` ani `dostarczone`,
- żadne nie wisi w aktywnej sesji WMS — ta sama kontrola, którą robi bulk-delete
  (`modules/orders/routes.py:3990`).

Warunek „ten sam klient” znika, razem z `allSelectedFromSameClient()`.

Gdy w zaznaczeniu jest **jedno** zlecenie zbiorcze, modal przechodzi w tryb „dopnij do
istniejącej paczki”. Przy dwóch zbiorczych odmawiamy — łączenie paczek zbiorczych nie ma
uzasadnienia biznesowego i mnoży przypadki brzegowe.

### Statusy — dwa kierunki

**Finanse płyną w górę.** Statusy `czeka_na_wycene` / `czeka_na_oplacenie` / `oplacone`
zostają indywidualne na zleceniach źródłowych, bo każdy klient płaci za swoje zamówienia
osobno (etap E4, `Order.shipping_cost`). Status zlecenia zbiorczego to **najmniej
zaawansowany** status źródeł, liczony po `ShippingRequestStatus.sort_order` i przeliczany,
gdy któryś uczestnik zapłaci.

**Logistyka płynie w dół.** Statusy `spakowane` / `wyslane` / `dostarczone` oraz
`tracking_number` i `courier` kopiują się ze zlecenia zbiorczego na wszystkie źródłowe —
opisują jedną fizyczną paczkę.

Efekt uboczny jest korzystny: WMS blokuje już dziś wysyłkę zleceń w statusach
`czeka_na_wycene` / `czeka_na_oplacenie` (`UNPAID_SR_STATUSES`, `modules/orders/wms_utils.py:215`),
więc paczka zbiorcza sama z siebie nie pojedzie, dopóki nie zapłacą wszyscy. Zero nowej
logiki blokującej.

Propagacja mieszka w jednym helperze `sync_consolidation_sources(sr)`, wołanym wszędzie tam,
gdzie zmienia się status lub tracking zlecenia — wzorem istniejącego
`_sync_order_statuses_from_shipping_request` (`modules/orders/routes.py:3776`).

### Wypięcie i rozwiązanie

Zamówienia wracają dokładnie do zleceń wskazanych przez `source_request_id`. Zlecenie
źródłowe traci `consolidated_into_id` i wraca do samodzielnego życia ze swoim statusem
finansowym. Gdy po wypięciu w paczce zostaje jeden uczestnik, konsolidacja **rozwiązuje się
sama** — zbiorcza paczka z jednym zleceniem to zbędna warstwa.

Rozwiązanie całości zwraca wszystkie zamówienia i kasuje zlecenie zbiorcze.

### Granica edycji

Wszystkie operacje edycyjne (zmiana wiodącego, dopięcie, wypięcie, rozwiązanie) są dostępne,
dopóki zlecenie zbiorcze nie ma statusu `spakowane` i nie jest w aktywnej sesji WMS. Po
spakowaniu skład paczki odpowiada temu, co fizycznie leży w kartonie — zmiana w systemie
byłaby kłamstwem wobec magazynu.

## Endpointy

Wszystkie `@login_required`, `@role_required('admin', 'mod')`, CSRF, `log_activity`.

| Metoda | Ścieżka | Rola |
|---|---|---|
| GET | `/admin/orders/shipping-requests/consolidation-preview?ids=` | dane do modalu: zlecenia, klienci, pełne adresy, powody blokady |
| POST | `/admin/orders/shipping-requests/consolidate` | utworzenie paczki zbiorczej lub dopięcie do istniejącej |
| POST | `/admin/orders/shipping-requests/<id>/consolidation/lead` | zmiana wiodącego (przepisuje adres, kontakt, `user_id`) |
| POST | `/admin/orders/shipping-requests/<id>/consolidation/detach` | wypięcie jednego zlecenia |
| POST | `/admin/orders/shipping-requests/<id>/consolidation/dissolve` | rozwiązanie konsolidacji |

Modal karmi się osobnym `preview`, a nie danymi z kart — karty nie mają kompletu adresów,
a stan mógł się zmienić od załadowania strony.

Endpoint `bulk-merge` i jego obsługa w JS zostają usunięte.

## Interfejs

### Modal konsolidacji

Lista zaznaczonych zleceń: numer, klient z awatarem, skrócony adres, status, liczba zamówień.
Przy każdym wierszu radio „wiodące”. Pod listą podgląd paczki po scaleniu — adresat, adres,
kontakt, zawartość — przeliczany na żywo przy zmianie wiodącego.

Ostrzeżenia pojawiają się warunkowo:

- gdy statusy się różnią: „paczka dostanie status X — najmniej zaawansowany ze scalanych”,
- gdy któreś zlecenie jest w aktywnej sesji WMS albo już wysłane (wtedy przycisk zablokowany).

W trybie edycji ten sam modal pokazuje zlecenia już wpięte, ikonę wypięcia przy każdym
wierszu oraz przyciski „Dopnij zlecenie” i „Rozwiąż”. Wejście przez przycisk „Zarządzaj
paczką” w stopce karty zbiorczej.

Style modalu trafiają do `static/css/components/modals.css` (light + dark), zgodnie z regułą
projektu, że wszystkie style modali mieszkają w jednym pliku.

### Karta zlecenia

Layout karty pozostaje bez zmian. Dochodzą dwie rzeczy:

1. **Badge w nagłówku** — „zbiorcza · N zleceń”, półprzezroczysta biel na istniejącym
   gradiencie, pod numerem zlecenia, żeby nie konkurowała z pigułką statusu.
2. **Grupowanie zamówień po właścicielu** w sekcji `sr-orders-compact`: nagłówek grupy
   (awatar, imię, numer zlecenia źródłowego), pod nim zamówienia z rozwijanymi produktami
   dokładnie jak dziś. Nagłówki grup zastępują osobną sekcję uczestników.

Limit trzech widocznych zamówień z commita `e71d50d` zostaje — liczony łącznie, niezależnie
od liczby grup, żeby karta zbiorcza nie rozjechała siatki.

Adresat oznaczony podpisem „adresat paczki” przy nazwisku wiodącego.

Style: `static/css/pages/admin/shipping-requests-list.css`, oba tryby.

### Lista WMS

Zlecenia źródłowe znikają z domyślnej listy (admin widzi jedną paczkę zamiast czterech
pozycji). Dochodzi filtr widoku „scalone”, gdy trzeba je odszukać — **nie** nowy status
w `shipping_request_statuses`: zlecenie źródłowe zachowuje swój status finansowy, a bycie
częścią paczki wynika z `consolidated_into_id`. Zapytanie listy
(`build_shipping_requests_query`, `modules/orders/wms.py:245`) dostaje warunek
`consolidated_into_id IS NULL` oraz `selectinload` na źródła i ich użytkowników, żeby karta
nie generowała N+1.

## Panel klienta

Listy zleceń (`modules/client/shipping.py:116`, `modules/api_mobile/shipping_routes.py:132`)
dostają filtr wykluczający zlecenia zbiorcze. Bez tego klient wiodący zobaczyłby paczkę
zbiorczą z zamówieniami obcej osoby.

Zlecenie źródłowe pokazuje klientowi:

- badge „wysyłka zbiorcza”,
- zdanie „paczka jedzie na adres: <imię i pierwsza litera nazwiska adresata>”,
- wspólny numer śledzenia,
- **wyłącznie własne** zamówienia, przez `display_orders`.

Anulowanie zlecenia wpiętego w konsolidację jest zablokowane (`can_cancel`).

## Powiadomienia

### Przeciek danych do naprawienia po drodze

`EmailManager.notify_shipment_sent` (`utils/email_manager.py:973`) buduje mail z pełnej listy
`shipping_request.orders` i wysyła go do `sr.user`. Dla paczki zbiorczej oznaczałoby to, że
klient wiodący dostaje w mailu numery zamówień drugiej osoby.

Rozwiązanie: gdy zlecenie jest zbiorcze, powiadomienie leci **w pętli po uczestnikach**,
każdemu z jego własną listą zamówień (`consolidation_participants`). Zamiast adresu dostawy
mail uczestnika niebędącego adresatem zawiera zdanie, że paczka jedzie na adres innej osoby —
inaczej ktoś będzie czekał pod własnymi drzwiami.

To samo dotyczy `PushManager.notify_shipment_sent` i `notify_shipping_status_change`.

### Nowe powiadomienie o scaleniu

W chwili konsolidacji każdy uczestnik dostaje mail i push: „Twoja wysyłka została połączona
z paczką zbiorczą wysyłaną do <imię>”. Nowy szablon `templates/emails/shipment_consolidated.html`,
wzorowany na `shipment_sent.html` (ten sam nagłówek, szerokość i stopka), plus metody
w `EmailManager` i `PushManager`.

Maile idą przez `send_email_batch` — Hostinger limituje uwierzytelnienia per IP i wysyłka
w pętli po jednym połączeniu potrafi się wyłożyć.

Przełączniki: korzystamy z istniejących kluczy (`notify_status_change`, `notify_tracking_added`),
bez dokładania nowych — nowy klucz startowałby jako włączony i po cichu zmieniłby to, co
sklep wysyła.

## Zakres

W zakresie:

- migracja (3 kolumny), właściwości modelu, helper propagacji,
- pięć endpointów konsolidacji, usunięcie `bulk-merge`,
- modal konsolidacji i edycji (tworzenie + zarządzanie),
- badge i grupowanie zamówień w karcie zbiorczej,
- ukrycie zleceń źródłowych na liście WMS + filtr „scalone”,
- panel klienta (web + mobile): filtr, badge, `display_orders`, blokada anulowania,
- powiadomienia per uczestnik + nowy szablon o scaleniu,
- testy.

Poza zakresem:

- automatyczne dzielenie kosztu wysyłki między klientów,
- konsolidacja inicjowana przez klienta,
- łączenie dwóch paczek zbiorczych,
- podział jednego zlecenia na kilka paczek (spec z 2026-08-07 ustala: jedno zlecenie = jedna paczka).

## Testy

`python -m pytest` (gołe `pytest` pada na `No module named 'app'`).

- konsolidacja zleceń dwóch różnych klientów tworzy nowy numer i przenosi wszystkie zamówienia,
- status zbiorczego = najmniej zaawansowany ze źródeł,
- opłacenie przez jednego uczestnika podnosi status zbiorczego dopiero, gdy zapłacą wszyscy,
- `wyslane` na zbiorczym propaguje status i tracking na wszystkie źródłowe,
- opłacone zlecenie źródłowe **nie** cofa się przy konsolidacji ze zleceniem nieopłaconym,
- wypięcie i rozwiązanie zwracają zamówienia zgodnie z `source_request_id`,
- wypięcie przedostatniego uczestnika rozwiązuje konsolidację automatycznie,
- panel klienta wiodącego nie zawiera zlecenia zbiorczego (web i mobile),
- klient źródłowy widzi wyłącznie własne zamówienia,
- mail o wysyłce nie zawiera numerów zamówień innego uczestnika,
- blokady: aktywna sesja WMS, zlecenie wysłane, podwójna konsolidacja, edycja po spakowaniu,
- eksport InPost dla paczki zbiorczej używa adresu wiodącego.

## Ryzyka

**Klucze obce na tę samą tabelę.** Przy kasowaniu zlecenia zbiorczego trzeba najpierw odpiąć
źródła (`consolidated_into_id = NULL`) i wyzerować `lead_source_request_id`, inaczej MariaDB
odrzuci `DELETE`. Dotyczy każdego miejsca robiącego `db.session.delete(ShippingRequest)` —
w tym bulk-delete i anulowania zleceń.

**Kompletność propagacji.** Status zlecenia zmienia się w kilku miejscach (bulk-status,
`ship_shipping_request`, pakowanie, edycja zlecenia). Pominięcie któregokolwiek zostawi
zlecenie źródłowe ze starym statusem u klienta. Test pokrywa każdą ze ścieżek osobno.

**Liczniki po stronie admina.** Zlecenie zbiorcze i źródłowe współistnieją, więc każde
`COUNT` po `ShippingRequest` policzy je podwójnie (m.in. `sr_total_count` i statystyki
klienta). Wymaga przejrzenia razem z filtrem listy.

**Zdjęcie paczki.** Po wdrożeniu pakowania na poziomie zlecenia (spec z 2026-08-07) dane
paczki kopiują się na każde zamówienie, więc zdjęcie paczki zbiorczej trafi do obu klientów.
To ta sama paczka, więc jest to poprawne — ale zdjęcie może pokazywać etykietę z adresem
adresata, o czym warto pamiętać przy treści maila.
