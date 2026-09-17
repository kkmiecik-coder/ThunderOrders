# Moja kolekcja — produkty zamówione i opłacone

**Data:** 2026-09-17
**ClickUp:** [869f3nvfc](https://app.clickup.com/t/869f3nvfc) (Web → Panel klienta)

## Problem

Feedback od Karoliny: klienci z trudem korzystają z zakładki „Moje zamówienia", żeby sprawdzić,
co faktycznie mają zamówione. Zamówienie grupuje pozycje po transakcji, a klient myśli
kategoriami „co mam", nie „co kupiłem i kiedy".

„Moja kolekcja" dziś pokazuje wyłącznie rzeczy **dostarczone** — `auto_add_order_to_collection`
materializuje pozycje zamówienia do `collection_items` dopiero przy statusie `dostarczone`
(`modules/client/collection_utils.py`, wołane z `orders/routes.py` i `wms_utils.py`).
Wszystko, co jest w drodze, jest dla klienta niewidoczne w tym miejscu.

## Cel

Kolekcja pokazuje **wszystko, co klient posiada lub ma w realizacji**, z czytelnym statusem
każdej pozycji — tak, żeby „Moje zamówienia" przestały być jedynym miejscem, gdzie widać stan rzeczy.

## Decyzje projektowe

Rozstrzygnięte z Konradem przed projektem:

| Decyzja | Wybór | Powód |
|---|---|---|
| Model danych | **Warstwa odczytu** (pozycje wirtualne) | Zero migracji, anulowanie zamówienia samo usuwa pozycję, brak ryzyka rozjazdu statusu i kasowania zdjęć klienta |
| Exclusive przed opłaceniem | **Widoczny od `oczekujace`, z osobnym badge** | Przy exclusive momentem „mam to" jest przydział; badge „Do opłacenia" działa jako bodziec do zapłaty |
| Granulacja statusu | **6 etapów** zamiast 8 statusów | Klient czyta jednym rzutem oka; statusy techniczne (`dostarczone_gom`, `dostarczone_proxy`) nie wyciekają do panelu klienta |
| Układ | **Jedna lista + filtr** | Realizuje cel Karoliny — wszystko w jednym miejscu; nie komplikuje paginacji ani karuzeli |
| Publiczna kolekcja | **Bez zmian** | To wizytówka kolekcji, nie lista zakupów w toku; pozycje wirtualne nie mają flagi `is_public`, więc klient nie mógłby ich ukryć pojedynczo |

## Architektura

### Nowy moduł: `modules/client/collection_incoming.py`

Buduje listę obiektów `VirtualCollectionItem` — lekkich, niezapisywanych w bazie, o **tym samym
interfejsie** co `CollectionItem`, dzięki czemu wszystkie trzy istniejące widoki renderują je
bez przepisywania szablonów.

Pola zgodne z `CollectionItem`:

| Pole | Źródło |
|---|---|
| `name` | `order_item.product_name` (+ sufiks `(n/N)` przy ilości > 1) |
| `market_price` | `order_item.price` — parytet z `auto_add` |
| `created_at` | `order.created_at` (data zakupu = „data dodania" w sortowaniu) |
| `image_url`, `primary_image`, `product`, `product_id` | z powiązanego `Product` |
| `is_from_order` | zawsze `True` |

Pola nowe:

| Pole | Znaczenie |
|---|---|
| `is_virtual` | `True` — szablony po tym rozpoznają brak akcji Edytuj/Usuń |
| `id` | `None` (brak wiersza w bazie) |
| `dom_id` | `oi-<order_item_id>-<n>` — stabilny identyfikator dla DOM |
| `stage`, `stage_label` | etap (patrz niżej) |
| `order` | zamówienie źródłowe — dla linku „Zobacz zamówienie" |

`CollectionItem` dostaje dopełniające właściwości `is_virtual = False`, `dom_id`, `stage = 'owned'`,
`stage_label`, żeby szablony traktowały oba rodzaje pozycji jednolicie.

### Zmiana w `collection_service.list_items()`

Nowy parametr `include_incoming` (domyślnie `False`) i `stage_filter`. Gdy włączony — scala
pozycje zmaterializowane z wirtualnymi, sortuje wspólnie i tnie na strony.

## Kwalifikacja pozycji

Pozycja zamówienia staje się wirtualną pozycją kolekcji, gdy spełnia **wszystkie** warunki:

1. **Typ zamówienia:**
   - `exclusive` → status `oczekujace` lub dalszy (płatność nie jest wymagana)
   - `on_hand`, `pre_order` → `product_payment_status == 'approved'` (E1 zatwierdzone), niezależnie od statusu
2. **Status zamówienia** nie należy do: `anulowane`, `do_zwrotu`, `zwrocone`, `czesciowo_zwrocone`
3. **Pozycja:** `is_set_fulfilled is not False` oraz `fulfilled_quantity ?? quantity > 0`
4. **Brak duplikatu:** nie istnieje `CollectionItem` z tym `order_item_id`

### Dlaczego kryteria różnią się między typami

Exclusive startuje jako `nowe` (`modules/offers/place_order.py`) i wchodzi w `oczekujace` przy
domykaniu oferty. Płatność E1 dla exclusive staje się dostępna **dopiero po** `is_fully_closed`
(`Order.can_upload_product_payment`), czyli już po wejściu w `oczekujace` — dlatego kryterium
statusowe, a nie płatnicze.

Pre-order i on-hand działają odwrotnie: klient płaci od razu po złożeniu, więc zamówienie
**opłacone, ale wciąż w statusie `nowe`** jest realnym zamówieniem w produkcji (tak samo
kwalifikuje je `get_products_to_order` w `modules/products/routes.py`). Dla nich kryterium
to płatność, nie status.

### Ilość większa niż 1

Osobna pozycja na każdą sztukę, nazwa z sufiksem `(1/2)`, `(2/2)` — parytet z `auto_add`
(K-pop = egzemplarze traktowane osobno).

## Etapy statusu

| Etap | Statusy zamówienia | Etykieta dla klienta |
|---|---|---|
| `unpaid` | exclusive z niezatwierdzonym E1 | Do opłacenia |
| `ordered` | `nowe`, `oczekujace`, `dostarczone_proxy` | Zamówione |
| `transit` | `w_drodze_polska`, `urzad_celny` | W drodze do Polski |
| `warehouse` | `dostarczone_gom`, `spakowane` | Gotowe do wysyłki |
| `shipped` | `wyslane` | Wysłane |
| `owned` | `dostarczone` (pozycje zmaterializowane) | W kolekcji |

Mapowanie trzymamy w **jednym słowniku** w `collection_incoming.py`. `wyslane` dostaje własny
etap, bo dla klienta to inny moment niż „leży u nas w magazynie" — paczka jest już w drodze
do niego i to najczęstszy powód zaglądania w tę zakładkę.

Statusy spoza mapy (dodane w przyszłości z panelu ustawień) trafiają do `ordered` jako
bezpieczny domyślny etap — kolekcja nie może się wywalić przez nowy slug w słowniku statusów.

## Interfejs użytkownika

Wszystkie trzy widoki iterują po tej samej liście `items` i korzystają z tego samego zestawu pól,
więc zmiany są punktowe:

- **Siatka** (`_item_card.html`) — badge etapu w rogu zdjęcia, obok istniejącego „Z zamówienia"
- **Lista** (`_item_row.html`) — nowa kolumna **Status**; kolumna „Źródło" zostaje bez zmian
- **Karuzela** (`index.html`) — badge pod nazwą slajdu
- **Filtr** obok sortowania: `Wszystko / W drodze / W kolekcji`, parametr `?filter=`,
  przenoszony w linkach paginacji razem z `view`, `sort`, `search`
- **Akcje** — pozycje wirtualne nie mają Edytuj/Usuń; w ich miejsce link „Zobacz zamówienie"
  prowadzący do szczegółów zamówienia
- **Statystyki** u góry rozbite: „W kolekcji: X" oraz „W drodze: Y"

### CSS

Nowe klasy badge'y etapów w `static/css/pages/client/collection.css`, obowiązkowo w wariancie
light i dark (`[data-theme="dark"]`, paleta glassmorphism). Bez stylów inline w HTML.

## Paginacja i wydajność

Wirtualnych pozycji nie da się paginować w SQL razem z tabelą kolekcji. Rozwiązanie:

1. Zapytanie o `CollectionItem` użytkownika (bez `paginate`)
2. Zapytanie o kwalifikujące się `OrderItem` z `joinedload` zamówienia, produktu i potwierdzeń płatności
3. Scalenie, wspólne sortowanie (te same 4 sorty co dziś) i ręczne cięcie na strony przez obiekt
   zgodny z interfejsem `Pagination` (`items`, `page`, `pages`, `has_prev`, `has_next`,
   `prev_num`, `next_num`, `iter_pages`) — szablon paginacji zostaje bez zmian

Przy realnych wolumenach (setki pozycji na klienta) koszt to kilka milisekund. Odrzucona
alternatywa: `UNION ALL` na wyrównanych kolumnach — szybsza, ale rozdziela logikę kwalifikacji
między SQL i Pythona, co przy tych regułach (różne kryteria per typ zamówienia, potwierdzenia
płatności) szybko staje się nieutrzymywalne.

Zabezpieczenie: limit 2000 najnowszych pozycji wirtualnych, żeby konto z patologiczną liczbą
zamówień nie zabiło strony. Przekroczenie limitu logujemy ostrzeżeniem — to sygnał, że warto
wrócić do wariantu z `UNION ALL`.

## Zasięg zmian

| Obszar | Zmiana |
|---|---|
| `modules/client/collection_incoming.py` | **nowy** — budowanie pozycji wirtualnych, mapowanie etapów |
| `modules/client/collection_service.py` | `list_items(include_incoming, stage_filter)` + scalanie i paginacja |
| `modules/client/collection.py` | trasa `collection_list` — nowy parametr filtra, rozbite statystyki |
| `modules/client/models.py` | `CollectionItem`: `is_virtual`, `dom_id`, `stage`, `stage_label` |
| `templates/client/collection/` | `index.html`, `_item_card.html`, `_item_row.html` |
| `static/css/pages/client/collection.css` | badge'y etapów, light + dark |
| `static/js/pages/client/collection.js` | obsługa filtra |

Bez zmian: `auto_add_order_to_collection`, publiczna kolekcja, osiągnięcia, mobile API,
migracje bazy (nie ma żadnej).

## Ryzyka i ich obsługa

| Ryzyko | Obsługa |
|---|---|
| Duplikaty przy dostarczeniu | Wykluczanie po `order_item_id`, a nie po statusie — pozycja pozostaje widoczna nawet gdyby materializacja padła, i nigdy nie pokaże się dwa razy |
| Mobile API dostaje wirtualne „za darmo" | `include_incoming` domyślnie wyłączone; apka Flutter parsuje `id` jako wymagane, więc wirtualne pozycje bez `id` mogłyby wywalić listę. Mobile dostanie je dopiero po jawnej zmianie po stronie apki |
| Znikająca pozycja po anulowaniu | Świadomie zaakceptowane — pozycja wirtualna nie ma własnych danych klienta (zdjęć, notatek), więc nie ma czego stracić |
| Nowy status w słowniku | Nieznane slugi mapują się na `ordered`, nie wywalają widoku |
| Cache Service Workera | Bump `CACHE_VERSION` w `sw.js` razem ze zmianami JS/CSS |

## Testy

Nowy plik `tests/test_collection_incoming.py` (uruchamiany przez `python -m pytest`):

- kwalifikacja per typ: exclusive od `oczekujace` bez płatności; on-hand i pre-order tylko z E1 approved
- pre-order opłacony w statusie `nowe` **jest** widoczny
- wykluczenia: anulowane, zwroty, `is_set_fulfilled=False`, `fulfilled_quantity=0`
- brak duplikatu, gdy pozycja została już zmaterializowana
- ilość > 1 → osobne pozycje z sufiksem
- mapowanie statusów na etapy, w tym rozdział `spakowane` → `warehouse` a `wyslane` → `shipped`
- nieznany slug statusu → `ordered`
- filtr `w drodze` / `w kolekcji` / `wszystko`
- paginacja mieszanej listy: liczba stron, kolejność przy każdym z 4 sortów
- brak regresji: `include_incoming=False` zwraca dokładnie to, co dziś (parytet dla mobile API)

## Poza zakresem

- **Publiczna kolekcja** — bez zmian
- **Mobile API E8** — wirtualne pozycje tylko za jawną flagą, po stronie apki osobna robota
- **Dług zastany:** `_item_card.html` i `_item_row.html` mają `onclick="openDeleteModal({{ item.id }}, '{{ item.name|e }}')"` — nazwa z apostrofem wywala JS (`escapeHtml` nie escapuje apostrofów). Nie dotyczy pozycji wirtualnych, bo te nie mają przycisków akcji. Do naprawy osobno, przez event delegation
