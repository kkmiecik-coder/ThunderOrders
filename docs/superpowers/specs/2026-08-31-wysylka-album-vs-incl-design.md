# Wysyłka KR liczona osobno dla całego albumu i dla samego incl

Zadanie ClickUp: [869erz1q0](https://app.clickup.com/t/869erz1q0) — „Wysyłka KR liczona osobno dla całego albumu i dla samego incl"
Data: 2026-08-31
Gałąź: `feat/wysylka-album-vs-incl`

## Problem

Przy zamówieniach exclusive klienci wybierają **na czacie**, czy chcą sprowadzić
cały album, czy tylko inclusions z niego. Album jedzie z Korei drożej niż samo incl —
ale system o tym wyborze nic nie wie.

Koszt Wysyłki KR wpisywany jest przy pozycji partii do Polski
(`PolandOrderItem.shipping_cost`, `modules/products/routes.py:4239`) dla całej linijki
naraz, a `_allocate_product_shipping_fifo` (`modules/products/routes.py:3910`) dzieli go
**po równo na sztuki**:

```python
per_unit = shipping / Decimal(qty)
slots.extend([per_unit] * qty)
```

Skutek: klient, który bierze cały album, płaci w etapie 2 dokładnie tyle samo, co
klient, który bierze samo incl. Realny koszt rozkłada się niesprawiedliwie.

## Ustalenia biznesowe

Potwierdzone z Karoliną przed projektowaniem:

- Wybór album/incl **nie istnieje dziś nigdzie w systemie** — tylko na czacie.
- Od proxy przychodzi **jedna kwota za paczkę**; podział na album/incl robi admin.
- Admin chce wpisywać **konkretne złotówki za sztukę** (album 45 zł, incl 12 zł),
  nie proporcje.
- Zdarza się, że **jeden klient w jednej pozycji bierze i album, i samo incl**
  (np. 2 szt. = 1 album + 1 incl) — więc potrzebna jest liczba sztuk, nie ptaszek.
- Oznaczanie odbywa się **w oknie partii do Polski** (tam, gdzie admin i tak wpisuje
  koszt), ale informacja zapisuje się **trwale przy pozycji zamówienia klienta**.
- Odrzucony pomysł: osobny produkt-dopłata do wysyłki. Powód w sekcji "Odrzucone".

## Dlaczego dane muszą siedzieć przy zamówieniu klienta

`_distribute_proxy_shipping_to_client_orders` (`modules/products/routes.py:4038`) jest
**idempotentna** — przy każdej nowej partii przelicza `proxy_shipping_cost` wszystkich
dotkniętych zamówień **od zera**, po wszystkich partiach danego produktu. To celowe
(chroni przed dublowaniem kosztów przy podziale produktu na kilka partii).

Konsekwencja: gdyby wybór album/incl żył tylko w oknie partii i nie był zapisany,
kolejna partia przeliczyłaby wcześniejsze kwoty bez tej wiedzy i by je rozjechała.

## Model danych

### `order_items.incl_only_quantity`

Nowa kolumna: `db.Column(db.Integer, nullable=False, default=0)`.

Ile sztuk z tej pozycji klient bierze **jako samo incl**. Reszta (`quantity -
incl_only_quantity`) to całe albumy.

Domyślnie `0` → wszystkie istniejące zamówienia zachowują się dokładnie jak dziś.

**Pozycje o zerowej ilości efektywnej** (niedomknięty set, `fulfilled_quantity = 0`)
zapis pozostawia **nietknięte** — zachowują swoje `incl_only_quantity`. Wartość nie
wpływa wtedy na żadną kwotę, bo `_order_product_quantities` przycina ją przez
`min(incl, efektywna)`. Gdyby ją zerować, wybór klienta przepadłby bezpowrotnie, a po
późniejszym domknięciu setu klient dostałby stawkę albumową za sztuki, które miały być
incl — bez ścieżki poprawy, skoro edycja utworzonej partii jest poza zakresem.

### `poland_order_items` — dwie stawki zamiast jednej kwoty

Nowe kolumny, obie `db.Column(db.Numeric(10, 2), nullable=True, default=None)`:

- `shipping_cost_album_per_unit` — stawka za sztukę-album
- `shipping_cost_incl_per_unit` — stawka za sztukę-incl

Istniejąca `shipping_cost` **zostaje** jako suma linijki (liczona z obu stawek i ilości)
— korzystają z niej podsumowania partii (`modules/products/routes.py:2650`,
`templates/admin/warehouse/macros/_stock_order_items.html:40`) i widok magazynu.

**Brak backfillu.** Gdy obie stawki są `NULL`, algorytm działa po staremu
(`shipping_cost / quantity` dla każdej sztuki). Stare partie liczą się bez zmian.

## Algorytm podziału

`_allocate_product_shipping_fifo` — zasada FIFO zostaje bez zmian (partie wg daty
utworzenia, sztuki klientów wg daty złożenia zamówienia). Zmienia się **cena slotu**:

1. Dla każdej partii budujemy sloty jak dziś, ale zamiast jednej stawki slot dostaje
   **parę stawek** (album, incl); przy `NULL` obie równe `shipping_cost / quantity`.
2. Idąc po zamówieniach klientów FIFO, dla pozycji o ilości `q` i `incl_only_quantity = i`
   konsumujemy `q` slotów: pierwsze `q - i` sztuk po stawce albumowej, kolejne `i`
   po stawce incl.
3. Sumę zaokrąglamy jak dziś: `total.quantize(Decimal('0.01'))`.

`_allocate_batch_units_to_orders` (rozbicie ilości do `PolandOrderItemOrder`) nie zmienia
logiki przydziału ani swojej sygnatury — jego rdzeń został wydzielony do
`_batch_allocation_for_range(product_id, batch_start, batch_end)`, z którego korzysta też
podgląd w oknie. Podsumowanie `4 szt. album / 6 szt. incl` okno liczy po swojej stronie,
z pól „samo incl".

### Częściowa realizacja setów

Efektywna ilość pozycji liczona jest przez `_client_item_qty`
(`modules/products/routes.py:3900`) — uwzględnia `fulfilled_quantity` i
`is_set_fulfilled`. `incl_only_quantity` musi być **przycięte do efektywnej ilości**:
`min(incl_only_quantity, _client_item_qty(item))`. Bez tego przy częściowo zrealizowanym
secie policzylibyśmy incl-e, których klient nie dostał.

## Interfejs — okno „Zamówienie do Polski"

`static/js/pages/admin/stock-orders.js`, modal `orderToPolandModal`.

Pod każdym produktem rozwija się lista klientów, którym te sztuki przypadły (z podglądu
przydziału FIFO), z polem liczbowym „samo incl":

```
Album XYZ — 10 szt.
  ├ Kasia N.      2 szt.   samo incl: [ 0 ] z 2
  ├ Ola W.        3 szt.   samo incl: [ 3 ] z 3
  ├ Marta K.      2 szt.   samo incl: [ 1 ] z 2      ← mieszane
  └ Ania P.       3 szt.   samo incl: [ 2 ] z 3

  cały album   4 szt.  ×  [ 45.00 ] zł  =  180.00 zł
  samo incl    6 szt.  ×  [ 12.00 ] zł  =   72.00 zł
                                 razem:    252.00 zł
```

- Ilości `4` i `6` przeliczają się na żywo z pól „samo incl".
- Po wpisaniu stawki albumu system **podpowiada** stawkę incl tak, żeby suma linijek
  zeszła się z kwotą paczki — jako placeholder do nadpisania, tym samym mechanizmem
  co dzisiejsze podpowiedzi (`calculateShippingCascade`,
  `static/js/pages/admin/stock-orders.js:276`).
- Licznik `shippingDifference` porównuje kwotę paczki z sumą linijek, ale dla pozycji
  z aktywnym wierszem stawek liczy linijkę **ze stawek** (`stawka_album × szt_album +
  stawka_incl × szt_incl`), a nie z pola „Wartość" — bo dokładnie tak liczy ją serwer.
  Inaczej admin widziałby „różnica 0", a zapisywałaby się inna kwota.
- Gdy w produkcie nikt nie bierze incl (`0` wszędzie), **cały blok stawek** się nie
  pokazuje — okno wygląda jak dotąd.

### Podgląd przydziału klientów

**Zrealizowane inaczej, niż zakładał projekt** (decyzja z wdrożenia): zamiast nowego
endpointu rozszerzony został istniejący POST `/admin/products/api/get-proxy-orders-details`,
z którego okno i tak korzysta przy otwarciu — jedno żądanie zamiast dwóch. Dla każdej
pozycji zwraca `clients`: listę `{order_id, order_number, client_name, quantity,
order_total_quantity, incl_only_quantity}`, wyliczoną przez `_preview_batch_allocation`
(ta sama zasada FIFO co `_allocate_batch_units_to_orders`, ale dla partii jeszcze
nieistniejącej w bazie). `quantity` to sztuki przypadające na tę partię,
`order_total_quantity` to sztuki klienta w całym zamówieniu — różnica między nimi
uruchamia ostrzeżenie ⚠ w oknie.

## Gdzie jeszcze to widać

- **Szczegóły zamówienia w adminie** (`templates/admin/orders/detail.html`) — przy
  pozycji plakietka „SAMO INCL" (przy mieszanej „SAMO INCL 1/2"), **tylko do odczytu**.
  Edycja tutaj byłaby myląca: nie ma ścieżki ponownego naliczenia kosztów już
  utworzonej partii, więc zmiana nic by nie przeliczyła.
- **Etap 2 „Wysyłka KR"** — bez zmian. `proxy_shipping_cost` to to samo pole co dotąd,
  więc terminy (`get_shipping_kr_deadline`), przypomnienia
  (`modules/orders/payment_overdue_service.py:16`) i maile
  (`utils/email_manager.py:683`) działają bez ruszania.
- **Panel klienta** (`templates/client/orders/detail.html:170`) — klient widzi przy
  pozycji plakietkę „SAMO INCL", tym samym wzorem co istniejące `size-badge` /
  `od-product-row__badge` (PEŁNY SET, GRATIS). Przy pozycji mieszanej plakietka mówi
  ile z ilu, np. „SAMO INCL 1/2". Klient tego nie edytuje — tylko podgląd.
- **Aplikacja mobilna** (`modules/api_mobile/orders_routes.py:131`) — pole
  `incl_only_quantity` dochodzi do odpowiedzi z pozycją zamówienia, obok
  `selected_size`, żeby apka mogła pokazać to samo.

## Walidacja

- `incl_only_quantity` z zakresu `0..quantity`; wartość spoza zakresu odrzucana.
- Stawki nie mogą być ujemne.
- Podpowiedziana stawka incl, gdyby wyszła ujemna (stawka albumu wyższa niż cała
  paczka), pokazuje się jako `0.00` z ostrzeżeniem — admin i tak widzi różnicę na dole.

## Testy (pytest)

1. Brak incl w ogóle → podział identyczny jak przed zmianą (regresja na starych danych).
2. Partia bez stawek (`NULL`) → stara logika `shipping_cost / quantity`.
3. Klient w całości na incl → dostaje stawkę incl × ilość.
4. Klient mieszany (2 szt. = 1 album + 1 incl) → suma dwóch różnych stawek.
5. Dwie partie tego samego produktu, FIFO → kwoty się nie dublują, przeliczenie od zera
   daje ten sam wynik co jednorazowe.
6. Częściowo zrealizowany set → `incl_only_quantity` przycięte do `_client_item_qty`.
7. Walidacja: `incl_only_quantity > quantity` odrzucone.
8. Render szczegółów zamówienia klienta: plakietka „SAMO INCL" pojawia się przy pozycji
   z `incl_only_quantity > 0` i znika przy `0` (test przez `app.test_request_context()`,
   nie `app.app_context()` — globalny context processor czyta `flask.session`).

## Odrzucone rozwiązania

**Osobny produkt-dopłata do wysyłki, dobierany przez klienta.** Klient dostawałby
w etapie 2 kwotę policzoną dalej po równo (za mało), a dopłatę płaciłby w etapie 1 —
czyli dwa razy w dwóch miejscach za jedną rzecz. Do tego kwota dopłaty musiałaby być
wymyślona z góry, zanim znany jest realny koszt od proxy, i część klientów by jej nie
dodała.

**Współczynnik proporcji zamiast złotówek** (album liczy się za 3 incl). Odrzucone na
życzenie — admin woli wpisywać konkretne stawki.

**Oznaczanie tylko w oknie partii, bez zapisu przy zamówieniu.** Niemożliwe technicznie
— patrz sekcja o idempotentnym przeliczaniu.

## Poza zakresem

- **Edycja kosztów wysyłki na już utworzonej partii.** W systemie nie istnieje dziś taki
  endpoint (jest tylko edycja cła/VAT, `/api/update-poland-customs-vat`), a partie do
  Polski dla tych exclusive dopiero powstaną — decyzja Karoliny z 2026-08-31. Do
  dorobienia osobnym zadaniem, gdyby okazało się potrzebne przy pomyłkach.
- **Na później:** wybór „cały album / samo incl" przez klienta przy składaniu zamówienia
  w ofercie, żeby nie przepisywać go z czatu. Naturalna druga część tego zadania —
  nie robimy jej teraz, bo nie ratuje exclusive już zebranych.
