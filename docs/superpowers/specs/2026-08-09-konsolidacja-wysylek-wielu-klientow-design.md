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

Ustalone po audycie kodu (2026-08-09):

- Anulowane zamówienie **wypina się z paczki automatycznie** — inaczej trwale blokuje
  wysyłkę wszystkim uczestnikom.
- Przy zleceniu zbiorczym bez właściciela (usunięte konto) **nie wysyłamy maila w ogóle**;
  fallback na adres z pierwszego zamówienia jest wyłączony.
- Wdrożenie idzie **jednym planem, w całości** — żadnego okna, w którym konsolidacja
  działa, a zabezpieczenia jeszcze nie.
- **Skonsolidowane zlecenie anuluje wyłącznie admin.** Klient nie może wypisać się z paczki
  zbiorczej ani jej rozwiązać — to ustalenie między kilkoma osobami i magazynem.

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
| Zlecenie widoczne przy zamówieniu | Nowa właściwość `Order.client_shipping_request` | `Order.shipping_request` zwraca zlecenie zbiorcze (potrzebne WMS), więc widoki klienta pokazywałyby cudzy adres — rozdzielamy role zamiast łatać każdy szablon |
| Anulowane zamówienie | Wypinane z paczki automatycznie | Bramki gotowości wymagają kompletu zamówień; anulowane nigdy go nie osiągnie i zablokuje paczkę wszystkim |
| Mail przy zleceniu bez właściciela | Brak fallbacku dla zbiorczych | Fallback na `orders[0].customer_email` wysłałby obcej osobie listę zamówień wszystkich uczestników |
| Nowe klucze obce | Jawne `ondelete='SET NULL'` | Istniejące FK zleceń nie mają `ondelete`, więc kasowanie zlecenia biorącego udział w konsolidacji rzucałoby `IntegrityError` |

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

Migracja pisana ręcznie i sprawdzana przed `flask db upgrade`. Wszystkie trzy klucze obce
dostają jawne **`ondelete='SET NULL'`**. Istniejące FK zleceń
(`migrations/versions/8b9c0cbaf032_add_shipping_requests_system.py:62-63, 75-76`) zakładane
są bez `ondelete`, więc bez tego skasowanie zlecenia biorącego udział w konsolidacji
kończy się `IntegrityError` — a kasowanie zleceń jest w kodzie w kilku miejscach
(bulk-delete, anulowanie przez klienta w webie i mobile).

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

### Rozdzielenie ról `Order.shipping_request`

`Order.shipping_request` (`modules/orders/models.py:685`) zwraca zlecenie przez
`shipping_request_orders[0]`, więc po konsolidacji **zamówienie klienta źródłowego wskazuje
paczkę zbiorczą cudzego klienta**. Konsumenci tej właściwości dzielą się na dwie grupy
o sprzecznych potrzebach:

- **WMS potrzebuje zbiorczego** — grupowanie pakowania (`wms_packing.py:49, 101`), cofanie
  do sesji (`wms.py:490`), zwrot opakowania na stan (`wms_utils.py:401-406`).
- **Widoki klienta potrzebują zlecenia właściciela** — karta zamówienia
  (`templates/client/orders/detail.html:483, 502, 549`), lista zamówień, mapa śledzenia
  (`modules/orders/routes.py:1873-1875`), tooltip ikony (`models.py:832`).

Bez rozdzielenia klient źródłowy zobaczyłby przy własnym zamówieniu numery cudzych zamówień
oraz **pełny adres dostawy obcej osoby** — imię, nazwisko, ulicę i miasto. To dane osobowe,
więc traktujemy to jako blokujące.

```python
shipping_request         # bez zmian: zlecenie, w którym zamówienie fizycznie leży (zbiorcze)
client_shipping_request  # zlecenie właściciela: źródłowe, gdy zamówienie jest w konsolidacji
```

Wszystkie widoki klienta przechodzą na `client_shipping_request`. Właściwość zwraca zlecenie
wskazane przez `source_request_id`, a gdy go nie ma — to samo co `shipping_request`.

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

Anulowania klient nie ma w ogóle, dopóki zlecenie jest w konsolidacji — wyplątać go z paczki
może tylko admin. Przycisk jest ukryty, a endpoint odrzuca żądanie z wyjaśnieniem, w obu
ścieżkach (web i mobile).

Druga powierzchnia to **karta zamówienia** (`templates/client/orders/detail.html`), lista
zamówień i mapa śledzenia. Wszystkie przechodzą na `client_shipping_request`, żeby klient
źródłowy widział przy swoim zamówieniu własne zlecenie, a nie paczkę zbiorczą z cudzym
adresem — szczegóły w sekcji „Rozdzielenie ról `Order.shipping_request`”.

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

## Zabezpieczenia wymuszone audytem kodu

Audyt (9 agentów, 2026-08-09) znalazł miejsca, w których konsolidacja psuje istniejące
zachowanie. Poniższe punkty są **częścią zakresu**, nie listą życzeń.

### Puste zlecenie źródłowe kłamie o swoim stanie

Zlecenie źródłowe traci wszystkie `ShippingRequestOrder`, a kilka miejsc interpretuje pustą
kolekcję jako „wszystko gotowe”, bo `all([])` to `True`:

| Miejsce | Skutek bez zabezpieczenia |
|---|---|
| `wms_packing.py:53-57` | źródłowe samo wskakuje na `spakowane` bez fizycznego pakowania |
| `payment_confirmations.py:43-61` | źródłowe wskakuje na `oplacone` mimo braku wpłaty |
| `wms.py:865` (`_wms_lock_blocking_session`) | blokada „zlecenie w aktywnej sesji WMS” przestaje działać |
| `wms.py:885` | admin może „wysłać” puste zlecenie źródłowe z listy |
| `routes.py:3887` | auto-przejście po wycenie milczy (`any([])` to `False`) |

Każda z tych funkcji dostaje wczesny warunek: zlecenie z ustawionym `consolidated_into_id`
nie jest samodzielną paczką i nie podlega bramkom gotowości ani akcjom wysyłkowym.

### Eksport InPost wygenerowałby podwójne etykiety

`build_inpost_csv` odrzuca zlecenia tylko na podstawie gabarytu i w ogóle nie czyta zamówień
(`inpost_export.py:55-74`). Zlecenie źródłowe zachowuje własny adres i `parcel_size`, więc
trafiłoby do pliku jako pełnoprawny wiersz i nadałoby drugą fizyczną przesyłkę na tę samą
paczkę. Filtr `consolidated_into_id IS NULL` wchodzi w `admin_export_shipping_requests_inpost`
(`routes.py:4239`) — czyli w jedyną bramkę przed plikiem dla kuriera.

To samo dotyczy `shipping_requests_filtered_ids` (`wms.py:283`): po propagacji statusu filtr
„spakowane” zwracałby zbiorcze **i** wszystkie jego źródła, więc „zaznacz na wszystkich
stronach” + eksport dałoby N+1 przesyłek. Ta sama poprawka zamyka też podwójne maile
z `admin_bulk_status_shipping_requests` (`routes.py:4179`).

### Powiadomienia: cisza zamiast wycieku

`notify_shipment_sent` (`email_manager.py:1001`) i jego odpowiednik w `PushManager`
(`push_manager.py:777`) mają wczesny return na pustej liście zamówień. Sama propagacja
statusu na źródłowe **nie powiadomi więc nikogo** — klienci nie-wiodący nie dowiedzą się,
że paczka pojechała, a w logu zostanie tylko `INFO`.

Rozwiązanie opisane w sekcji „Powiadomienia”: dla zlecenia zbiorczego iterujemy po
uczestnikach. Konsekwencja dla testów: `tests/test_shipment_sent_notification.py:536`
(`test_email_skipped_when_no_orders`) i bliźniaczy test pusha opisują dokładnie to
zachowanie — trzeba je przepisać tak, by pilnowały pustego zlecenia **niebędącego**
źródłem konsolidacji.

Dotyczy to również:

- `notify_packing_photo` (`wms_packing.py:201`) — dziś mail ze zdjęciem trafia do właściciela
  przypadkowego zamówienia z grupy, a zdjęcie pokazuje karton z cudzymi produktami. Dla
  paczki zbiorczej rozsyłamy do wszystkich uczestników, z informacją, że karton jest wspólny.
- deep-linków w mailach i pushach (`push_manager.py:752`, `email_manager.py:902, 962, 1035`) —
  prowadzą do listy zleceń klienta, w której zlecenie zbiorcze jest niewidoczne. Link
  uczestnika musi prowadzić do jego **własnego** zlecenia źródłowego.
- `notify_shipping_request_created` (`email_manager.py:899`) — **nie** używamy jej do
  zlecenia zbiorczego. To jedyny szablon pokazujący kwoty; wysłany do wiodącego ujawniłby
  kwoty zamówień obcych osób.

### Anulowanie i kasowanie zleceń

- **Skonsolidowanego zlecenia klient nie anuluje — nigdy.** Paczka zbiorcza jest ustaleniem
  między kilkoma osobami, więc rozmontować ją może wyłącznie admin, wypinając zlecenie albo
  rozwiązując konsolidację. `can_cancel` zwraca `False` dla zlecenia zbiorczego **i** dla
  źródłowego, niezależnie od statusu, kosztu i trackingu. Blokada wchodzi po stronie serwera
  w obu ścieżkach: web (`modules/client/shipping.py:293`) i mobile
  (`modules/api_mobile/shipping_routes.py:200`) — ukrycie przycisku w szablonie niczego nie
  zamyka, bo endpoint mobilny przyjmuje dowolne `request_id` należące do użytkownika.
  Odrzucenie zwraca czytelny powód („zlecenie jest częścią paczki zbiorczej — skontaktuj się
  z obsługą”), a nie gołe 403. Po wypięciu przez admina zlecenie wraca pod zwykłe reguły
  `can_cancel`.
- Kasowanie zlecenia zbiorczego (bulk-delete, `routes.py:4002`) najpierw odpina źródła
  i zeruje `lead_source_request_id`, a dopiero potem kasuje rekord.
- Usunięcie konta klienta (`modules/auth/models.py:673`, `modules/admin/clients.py:522`)
  zeruje `user_id`. Dla zlecenia zbiorczego bez właściciela mail o wysyłce **nie wychodzi
  wcale** — fallback na `orders[0].customer_email` (`email_manager.py:1015`) wysłałby obcej
  osobie listę zamówień wszystkich uczestników.

### Anulowane zamówienie wypina się z paczki

Bramki gotowości wymagają kompletu zamówień: `all(o.status == 'spakowane' …)`
(`wms_packing.py:53`) oraz zatwierdzonego E4 dla każdego `ro.order_id`
(`payment_confirmations.py:43-51`). Anulowane zamówienie nigdy tego nie osiągnie, więc jedno
anulowanie zablokowałoby wysyłkę wszystkim uczestnikom paczki.

Anulowanie zamówienia należącego do konsolidacji usuwa jego powiązanie z paczką
i przelicza `total_shipping_cost` zlecenia zbiorczego. Gdy właściciel traci w ten sposób
wszystkie zamówienia, jego zlecenie źródłowe wypina się z konsolidacji.

### Konsolidacja zagnieżdżona

Nic w modelu nie broni ustawienia `consolidated_into_id` na zlecenie, które samo jest już
źródłem, ani cyklu A→B→A, ani wskazania na samego siebie. Propagacja idzie o jeden poziom,
więc druga warstwa zostałaby z nieaktualnym statusem, a rekurencja bez guardu zawiesiłaby
request. Walidacja przy konsolidacji odrzuca: zlecenie już będące źródłem, zlecenie zbiorcze
jako element scalany (poza trybem dopięcia) oraz każdy przypadek, w którym cel jest
jednocześnie źródłem.

### Pułapka przy samej implementacji

`ShippingRequest.request_orders` ma `cascade='all, delete-orphan'` (`models.py:1506`). Stary
`bulk-merge` przenosi wiersze SQL-owym `.update()` (`routes.py:4122`), a zaraz potem kasuje
zlecenie (`4128`) — działa **wyłącznie** dlatego, że nigdy nie dotyka `sr.request_orders`
przed UPDATE-em, więc kaskada doczytuje kolekcję leniwie i widzi pustkę.

Kod konsolidacji **musi** odczytać `sr.request_orders`, żeby ustawić `source_request_id`.
Powtórzenie tamtej sekwencji skasuje więc wiersze, które przed chwilą przeniósł. Przepinamy
przez ORM albo jawnie odświeżamy kolekcję przed kasowaniem. To samo dotyczy rozwiązywania
konsolidacji.

### Numer zlecenia

`generate_request_number` (`models.py:1615-1626`) czyta wiersz o najwyższym `id` i
inkrementuje, bez `SELECT FOR UPDATE`, przy kolumnie z `UNIQUE`. Dziś zlecenia tworzy tylko
klient; konsolidacja dokłada tworzenie po stronie admina, z natury równolegle do ruchu
klienckiego. Tworzenie zlecenia zbiorczego obsługuje `IntegrityError` na numerze i ponawia
generowanie.

### Koszt i termin płatności na zleceniu źródłowym

`calculated_shipping_cost` (`models.py:1594-1604`) sumuje po `request_orders`, więc na
zleceniu źródłowym zwróci `None` — klient widziałby „oczekuje na wycenę” mimo zapłaty.
Właściwość liczy się z `display_orders`.

`payment_deadline` i `parcel_size` nie są propagowane świadomie: termin E4 klienta liczy się
ze zlecenia, w którym leżą jego zamówienia (`models.py:1123-1127`), czyli ze zbiorczego —
i tak ma być, bo termin dotyczy tej jednej paczki.

`admin_update_shipping_request` (`routes.py:3862`) nie sprawdza, czy zamówienie z żądania
należy do edytowanego zlecenia. Dziś nieszkodliwe, po konsolidacji to jedyne miejsce, gdzie
admin ustawia kwotę E4 obcemu klientowi — dokładamy walidację przynależności.

## Zakres

W zakresie:

- migracja (3 kolumny z `ondelete`), właściwości modelu, helper propagacji,
- rozdzielenie `Order.shipping_request` / `Order.client_shipping_request` i przełączenie
  widoków klienta na tę drugą,
- pięć endpointów konsolidacji, usunięcie `bulk-merge`,
- modal konsolidacji i edycji (tworzenie + zarządzanie),
- badge i grupowanie zamówień w karcie zbiorczej,
- ukrycie zleceń źródłowych na liście WMS, w zaznaczaniu „na wszystkich stronach”
  i w eksporcie InPost + filtr widoku „scalone”,
- guardy chroniące puste zlecenia źródłowe przed bramkami gotowości i akcjami wysyłkowymi,
- panel klienta (web + mobile): filtr, badge, `display_orders`, blokada anulowania po
  stronie serwera,
- powiadomienia per uczestnik + nowy szablon o scaleniu + brak fallbacku adresata,
- auto-wypięcie anulowanego zamówienia z paczki,
- walidacja odrzucająca konsolidacje zagnieżdżone i cykle,
- obsługa kolizji numeru `WYS` przy tworzeniu zlecenia zbiorczego,
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
- eksport InPost dla paczki zbiorczej używa adresu wiodącego,
- eksport InPost **pomija** zlecenia źródłowe (test na podwójną etykietę),
- karta zamówienia klienta źródłowego nie pokazuje cudzego adresu ani cudzych numerów
  zamówień (`client_shipping_request`),
- puste zlecenie źródłowe nie wskakuje na `spakowane` ani `oplacone` przez `all([])`,
- anulowanie zamówienia wypina je z paczki i nie blokuje pakowania pozostałych,
- anulowanie zlecenia (web i mobile) jest odrzucane dla zbiorczego i źródłowego,
- zlecenie zbiorcze bez właściciela nie wysyła maila do nikogo,
- konsolidacja zagnieżdżona i cykl są odrzucane,
- przepięcie zamówień nie kasuje wierszy przez `delete-orphan` (test na pułapkę kaskady).

Na `bulk-merge` nie ma dziś **ani jednego** testu, więc każdy z powyższych punktów pisany
jest przed zmianą kodu — inaczej przepisujemy tę funkcję bez siatki bezpieczeństwa.

## Ryzyka

**Kompletność propagacji.** Audyt naliczył **osiem** niezależnych miejsc zapisujących status
lub tracking zlecenia: `routes.py:3837/3839/3841`, `routes.py:3887`, `routes.py:4179`,
`wms_utils.py:259-266`, `wms_utils.py:418-420` (cofanie do WMS), `wms_packing.py:57`
i `payment_confirmations.py:61`. Pominięcie któregokolwiek zostawia zlecenie źródłowe ze
starym statusem u klienta. Test pokrywa każdą ścieżkę osobno, łącznie z cofaniem —
propagacja musi działać w obie strony, nie tylko do przodu.

Osobna pułapka: `_check_sr_auto_oplacone` robi **własny** `db.session.commit()`
(`payment_confirmations.py:62`) w środku zatwierdzania płatności. Propagacja wpięta w to
miejsce musi zmieścić się w tej samej transakcji, inaczej zbiorcze i źródłowe rozjadą się
przy błędzie.

**Liczniki po stronie admina.** Zlecenie zbiorcze i źródłowe współistnieją, więc każde
`COUNT` po `ShippingRequest` policzy je podwójnie — m.in. `sr_total_count` na dashboardzie
WMS, statystyki wysyłki i liczniki na karcie klienta. Do przejrzenia razem z filtrem listy.

**Zdjęcie paczki.** Po wdrożeniu pakowania na poziomie zlecenia (spec z 2026-08-07) dane
paczki kopiują się na każde zamówienie, więc zdjęcie paczki zbiorczej dotyczy wszystkich
uczestników. Zdjęcie pokazuje karton z produktami wszystkich osób i może zawierać etykietę
z adresem adresata — treść maila musi to uprzedzać.

**Zmiana wiodącego po nadaniu przesyłki.** Edycja jest zablokowana po spakowaniu, ale
tracking bywa wpisywany wcześniej (`admin_update_shipping_request`). Zmiana wiodącego
przepisuje wtedy adres w bazie, choć etykieta u kuriera pozostaje stara. Modal ostrzega,
gdy zlecenie ma już numer przesyłki.

**Migracja danych historycznych.** Zlecenia scalone starym `bulk-merge` nie mają zapisanych
źródeł i nie da się ich odtworzyć. Zostają jak są — bez badge’a i bez uczestników. To
świadoma decyzja, nie luka.
