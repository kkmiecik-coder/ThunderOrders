# Pakowanie na poziomie zlecenia wysyłki (jedna paczka = jedno zlecenie)

Data: 2026-08-07
Gałąź: `feature/wms-pakowanie-na-zlecenie`
Zadanie ClickUp: [869edykjd](https://app.clickup.com/t/869edykjd) — „wybór formy pakowania przy kilku zamówieniach w jednej paczce"

## Problem

W sesji WMS pakowanie jest dziś czynnością **na zamówieniu**, a nie na paczce. Po zebraniu
każdego zamówienia pojawia się panel „Pakowanie" (`templates/admin/orders/wms.html:268`),
w którym trzeba wybrać opakowanie, podać wagę i kliknąć „Potwierdź pakowanie"
(`static/js/pages/admin/wms.js:1164` → `modules/orders/wms.py:795`).

W rzeczywistości wszystkie zamówienia z jednego zlecenia wysyłki (`ShippingRequest`) lądują
w **jednym** kartonie. Stąd trzy konkretne szkody:

1. **Zbędna praca.** Przy zleceniu z 3 zamówieniami admin 3 razy wybiera to samo opakowanie,
   3 razy podaje wagę i 3 razy klika „Potwierdź pakowanie".
2. **Rozjazd stanu opakowań.** `wms_pack_order()` (`modules/orders/wms.py:859-865`) i
   `handle_mark_order_packed()` (`modules/orders/wms_events.py:301-307`) odejmują jedno
   opakowanie **za każde zamówienie**. Zlecenie z 3 zamówieniami zdejmuje ze stanu 3 kartony,
   choć zużyty został jeden.
3. **Zdublowane maile.** `EmailManager.notify_packing_photo(order)` leci raz na zamówienie
   (`modules/orders/wms.py:882-887`), więc klient dostaje 3 maile z tym samym zdjęciem paczki.

Do tego opakowanie jest już raz wybierane wcześniej — przy wycenie zlecenia
(`ShippingRequest.packaging_material_id`, `modules/orders/models.py:1447`, ustawiane w
`modules/orders/routes.py:3816`). W WMS wybiera się je po raz drugi, ręcznie, bez podpowiedzi.

## Ustalenia biznesowe

Potwierdzone z właścicielką przed projektowaniem:

- Jedno zlecenie wysyłki = **zawsze jedna paczka**. Podział na kilka paczek nie występuje
  i nie jest w zakresie.
- Do WMS trafiają **wyłącznie** zamówienia wchodzące w skład zleceń wysyłki. Ścieżka
  „zamówienie luzem, bez zlecenia" nie jest używana.
- Opakowanie, waga **i zdjęcie** paczki mają być podawane raz, na końcu zlecenia.
- Dane paczki (opakowanie, waga, zdjęcie) zapisujemy **kopiując je na każde zamówienie**
  z paczki. Bez migracji bazy — historia zamówienia (`templates/admin/orders/detail.html:1402`)
  i mail ze zdjęciem czytają je z zamówienia i mają działać bez zmian.

## Zakres

W zakresie:

- panel pakowania przenoszony z poziomu zamówienia na poziom zlecenia wysyłki — desktop
  (`templates/admin/orders/wms.html`, `static/js/pages/admin/wms.js`) i telefon
  (`templates/admin/orders/wms_mobile.html`, `static/js/pages/admin/wms-mobile.js`)
- nowy endpoint pakujący całą grupę zamówień jednego zlecenia + odpowiednik po WebSocket
  dla telefonu
- podpowiedź opakowania z wyceny zlecenia (`ShippingRequest.packaging_material_id`)
  i zapis wybranego opakowania z powrotem na zlecenie
- zdjęcie paczki robione raz na zlecenie
- jedno odjęcie opakowania ze stanu i jeden mail na paczkę
- korekta zwrotu opakowania na stan przy powrocie zlecenia do WMS
  (`reopen_orders_for_wms()`, `modules/orders/wms_utils.py:361`)

Poza zakresem:

- podział zlecenia na kilka paczek
- pakowanie zamówień spoza zlecenia wysyłki
- zmiany w panelu wysyłki (kurier / tracking / koszt) — zostaje jak jest
- zmiany w kompletowaniu (zbieraniu) pozycji

## Rozwiązanie

### Przepływ w interfejsie

Kompletowanie pozycji nie zmienia się. Zmienia się moment po skompletowaniu.

**Desktop.** Sekcja `#wmsPackAction` przestaje być panelem zamówienia i staje się panelem
zlecenia. Warunek pokazania: **wszystkie zamówienia danego zlecenia obecne w tej sesji** mają
`is_picked == true` i żadne z nich nie jest jeszcze spakowane. Panel zawiera:

- nagłówek: numer zlecenia, klient, liczba pakowanych zamówień
- sugestie opakowań + lista ręczna, z wartością wstępnie ustawioną na
  `ShippingRequest.packaging_material_id` (jeśli ustawione)
- jedno pole wagi paczki
- jedną miniaturkę zdjęcia paczki
- checkbox „Wyślij zdjęcie do klienta"
- przycisk **„Spakuj zlecenie"**

Po udanym zapisie panel znika, a na jego miejsce wchodzi istniejący panel wysyłki
(`showShippingPanel()`, `static/js/pages/admin/wms.js:1575`) — bez zmian w jego działaniu.

Gdy sesja obejmuje kilka zleceń, panele pojawiają się kolejno, po jednym na zlecenie.

**Telefon.** `#wmsMPackSection` (`templates/admin/orders/wms_mobile.html:70`) zmienia się
analogicznie: pokazuje się raz na zlecenie, zdjęcie robione jest raz, przycisk
`#wmsMPackBtn` pakuje całe zlecenie.

### Sugestie opakowań

`suggest_packaging(order)` (`modules/orders/wms_utils.py`) liczy dopasowanie dla jednego
zamówienia. Dla panelu zlecenia sugestie liczymy dla **sumy** zamówień z paczki: łączna waga
i łączna objętość zawartości. Nowa funkcja `suggest_packaging_for_orders(orders)` w
`wms_utils.py`; dotychczasowa `suggest_packaging(order)` zostaje jako cienkie opakowanie na
nową (`suggest_packaging_for_orders([order])`), żeby istniejące endpointy
`/api/orders/wms/suggest-packaging/...` dalej działały.

### Zapis

Nowy endpoint `POST /admin/orders/wms/<session_id>/pack-shipping-request` przyjmuje
`shipping_request_id`, `packaging_material_id`, `total_package_weight`, `send_email`.
Logika w jednej funkcji `pack_shipping_request_group()` w `modules/orders/wms.py`, wołanej
też przez handler WebSocket `mark_shipping_request_packed` w `wms_events.py` — telefon i
desktop nie mogą mieć dwóch różnych implementacji.

Kroki:

1. Ustal grupę: zamówienia tego zlecenia należące do tej sesji WMS, jeszcze niespakowane.
   Pusta grupa → błąd 400.
2. Odrzuć żądanie, jeśli którekolwiek z tych zamówień nie jest w pełni zebrane.
3. Dla każdego zamówienia w grupie: `status = 'spakowane'`, `packed_at`, `packed_by`,
   `packaging_material_id`, `total_package_weight`, zwolnienie blokady WMS,
   `WmsSessionOrder.packing_completed_at`.
4. **Raz na grupę:** `quantity_in_stock -= 1` na wybranym materiale + ewentualne ostrzeżenie
   o niskim stanie.
5. **Raz na grupę:** `ShippingRequest.packaging_material_id` = wybrany materiał (żeby wycena
   i rzeczywistość się zgadzały).
6. Wpis do dziennika aktywności — jeden, na zlecenie, z listą spakowanych zamówień.
7. `_update_sr_after_packing()` (`modules/orders/wms.py:241`) wołane raz — bez zmian
   w środku, dalej sprawdza, czy **wszystkie** zamówienia zlecenia są spakowane.
8. **Raz na grupę:** jeśli `send_email` i istnieje zdjęcie paczki —
   `EmailManager.notify_packing_photo()` + `PushManager.notify_packing_photo()`.

Odpowiedź zwraca listę spakowanych zamówień, postęp sesji i `shipping_request` — czyli to,
czego już dziś oczekuje front (`handleOrderPacked`, `static/js/pages/admin/wms.js:380`).
Dotychczasowe zdarzenie WebSocket `order_packed` zastępuje nowe `shipping_request_packed`
z listą spakowanych zamówień; oba klienty (desktop + telefon) aktualizują stan z tej listy.

### Zdjęcie paczki

`wms_upload_packing_photo()` (`modules/orders/wms.py:1332`) zapisuje zdjęcie na zamówieniu.
Zostaje bez zmian, ale front wysyła je dla **pierwszego** zamówienia z grupy, a
`pack_shipping_request_group()` po zapisaniu kopiuje `packing_photo` na pozostałe zamówienia
grupy. Dzięki temu każde zamówienie ma w historii zdjęcie swojej paczki, a mail wychodzi raz.

### Korekta zwrotu opakowania przy powrocie do WMS

`reopen_orders_for_wms()` (`modules/orders/wms_utils.py:376-388`) oddaje dziś na stan
**jedno opakowanie za każde zamówienie**. Przy pakowaniu raz na paczkę oznaczałoby to
przyrost stanu z powietrza (odjęte 1, zwrócone 3).

Zmiana: zwrot liczony raz na paczkę. Zamówienia grupujemy po `order.shipping_request_id`
i dla każdej grupy zwracamy `+1` na materiał wskazany przez to zlecenie, po czym czyścimy
`packaging_material_id` na wszystkich zamówieniach grupy. Zamówienia bez zlecenia (dane
historyczne) traktujemy po staremu — jedno zamówienie, jeden zwrot.

## Obsługa błędów

- **Nie wszystkie zamówienia zlecenia skompletowane** → panel się nie pokazuje; jeśli żądanie
  przyjdzie mimo to (np. z drugiej karty), endpoint zwraca 400 z komunikatem.
- **Zlecenie już spakowane / grupa pusta** → 400 „Zlecenie jest już spakowane".
- **Materiał opakowaniowy skasowany między wyceną a pakowaniem** → traktowany jak brak wyboru;
  pakowanie przechodzi bez odjęcia stanu, w odpowiedzi ostrzeżenie.
- **Błąd wysyłki maila** → logowany, nie przerywa pakowania (jak dziś).
- **Część zamówień zlecenia poza sesją** → pakujemy wyłącznie te z sesji; zlecenie dostaje
  status „spakowane" dopiero, gdy `_update_sr_after_packing()` zobaczy komplet.

## Testy

Nowy plik `tests/test_wms_pack_shipping_request.py`:

1. Zlecenie z 3 zamówieniami, wszystkie w sesji i skompletowane → jedno wywołanie
   `pack-shipping-request` → wszystkie 3 mają status `spakowane`, `quantity_in_stock` spadł
   **o 1**, `notify_packing_photo` wywołane **raz**, `ShippingRequest.status == 'spakowane'`.
2. To samo zlecenie przez `reopen_orders_for_wms()` → `quantity_in_stock` wraca do wartości
   sprzed pakowania (**+1**, nie +3), `packaging_material_id` wyczyszczone na wszystkich
   zamówieniach. Regresja na pułapkę opisaną wyżej.
3. Zlecenie z 3 zamówieniami, w sesji tylko 2 → pakują się 2, `ShippingRequest.status`
   **nie** zmienia się na `spakowane`.
4. Zamówienie w grupie niekompletnie zebrane → endpoint zwraca 400, nic się nie zapisuje.
5. `ShippingRequest.packaging_material_id` po spakowaniu innym materiałem niż z wyceny →
   zaktualizowane na faktycznie użyty.
6. `suggest_packaging_for_orders()` dla dwóch zamówień → sugeruje po sumie wagi i objętości;
   `suggest_packaging(order)` dla jednego zamówienia zwraca to samo co przed zmianą.

Istniejący `tests/test_wms_ship_and_reopen.py` musi przechodzić bez modyfikacji poza
dostosowaniem do zwrotu opakowania raz na paczkę.

Uruchomienie: `python -m pytest tests/ -q`
