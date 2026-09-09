# Podział partii w zakładce Polska

Data: 2026-09-09
Status: zatwierdzony projekt, przed planem wdrożenia
ClickUp: https://app.clickup.com/t/869ezbu3c

## Problem

Do jednej partii w zakładce Polska trafiły pozycje, które nie jadą razem — część
towaru jest już na miejscu, część jeszcze nie dotarła. Status
(`zamowione` / `urzad_celny` / `dostarczone_gom` / `anulowane`) jest wspólny dla
całej partii, więc przestawienie go na „Dostarczone GOM" wywołuje
`_update_client_orders_on_gom_delivery()` (`modules/products/routes.py:3646`) i wysyła
maile również klientom, których towaru fizycznie nie ma.

Dziś nie ma czym tego rozdzielić. Partia obsługuje wyłącznie: zmianę statusu
(`modules/products/routes.py:3621`), edycję Cła/VAT (`modules/products/routes.py:4730`),
archiwizację (`modules/products/routes.py:3740`) i usunięcie
(`modules/products/routes.py:3672`). Nie istnieje endpoint wyjmujący pojedynczą
pozycję ani przenoszący ją do innej partii.

Obejścia są złe:

- **Usunięcie i założenie od nowa** — działa (produkty wracają na listę „Do
  zamówienia", bo `already_ordered` liczy się z nieanulowanych `ProxyOrder`,
  `modules/products/routes.py:2402`), ale kasuje historię partii i przy niezerowej
  wysyłce zostawia klientom naliczone koszty (patrz „Znalezione przy okazji").
- **Status „Anulowane"** — nie pomaga wcale: zmienia tylko `PolandOrder.status`,
  nie rusza `ProxyOrder.status`, więc produkty nie wracają na listę „Do zamówienia"
  i zapotrzebowanie zostaje zablokowane.

## Zakres

Podział partii **całymi pozycjami**: zaznaczone `PolandOrderItem` przechodzą w
komplecie do nowej partii, reszta zostaje w oryginalnej.

Poza zakresem:

- **dzielenie pojedynczej pozycji po sztukach** (np. 30 z 66 szt.) — wymaga
  przeliczenia `PolandOrderItemOrder`, stawek za sztukę i kwot cła; jeśli taka
  potrzeba realnie wystąpi, będzie osobnym projektem,
- łączenie partii z powrotem,
- zmiany w naliczaniu kosztów klientom, w powiadomieniach i w statusach zamówień
  klientów,
- zakładka Proxy — dzielimy wyłącznie partie Polska.

## Rozwiązanie

### Przebieg

Admin klika nożyczki przy partii → okno z listą pozycji i checkboxami →
zaznacza pozycje → koryguje proponowane kwoty ewidencyjne → „Podziel" →
powstaje nowa partia z zaznaczonymi pozycjami.

### Warstwa danych

Podział wykonuje się w jednej transakcji. Kolejno:

1. **Nowa `PolandOrder`** z numerem z istniejącego generatora: `generate_poland_order_number()`
   dla oryginału `PL/…`, `generate_proxy_to_poland_number()` dla `PRX/PL/…`
   (`modules/products/routes.py:3847`, `:3851`). Dziedziczy po oryginale:

   | Pole | Wartość | Powód |
   |---|---|---|
   | `status` | jak oryginał | obie części są w tym samym stanie w chwili podziału |
   | `created_at` | **jak oryginał** | kolejka FIFO, patrz niżej |
   | `payment_deadline` | jak oryginał | `Order.get_shipping_kr_deadline()` czyta termin z partii (`modules/orders/models.py:1244`) |
   | `customs_payment_deadline` | jak oryginał | `Order.get_customs_vat_deadline()` (`modules/orders/models.py:1258`) |
   | `tracking_number` | pusty | druga przesyłka ma własny numer |
   | `notes`, `admin_notes` | puste | notatki opisują oryginał |
   | `is_archived` | `False` | nowa partia jest aktywna |

2. **Nowy `ProxyOrder`** — kopia rodzica oryginału (ten sam `order_type`, `supplier_id`,
   `status`), z numerem z odpowiedniego generatora. Do niego przenoszone są
   `ProxyOrderItem` odpowiadające przenoszonym pozycjom.

   Wspólny rodzic jest wykluczony: `ProxyOrder.poland_orders` ma
   `cascade='all, delete-orphan'` (`modules/products/models.py:351`), a
   `delete_poland_order` kasuje rodzica dla typu `polska`
   (`modules/products/routes.py:3703`) — usunięcie jednej z podzielonych partii
   skasowałoby po cichu drugą.

   Przeniesienie (a nie skopiowanie) `ProxyOrderItem` utrzymuje poprawność
   `already_ordered` w „Do zamówienia": zapytanie grupuje po
   `(product_id, order_type)` po wszystkich nieanulowanych `ProxyOrder`
   (`modules/products/routes.py:2403`), więc suma sztuk nie zmienia się.

3. **Przeniesienie pozycji** — zaznaczonym `PolandOrderItem` zmienia się
   `poland_order_id` na nową partię, a `proxy_order_item_id` wskazuje na
   przeniesiony `ProxyOrderItem`. Bez zmian zostają: `quantity`, `shipping_cost`,
   `shipping_cost_album_per_unit`, `shipping_cost_incl_per_unit`,
   `customs_vat_percentage`, `customs_vat_amount`, `selected_size`.

   Wiersze `PolandOrderItemOrder` wiszą na `poland_order_item_id`, więc przypisanie
   sztuk do konkretnych zamówień klientów jedzie razem z pozycją bez żadnej
   ingerencji.

4. **Kwoty ewidencyjne** — `shipping_cost` i `customs_cost` obu partii ustawiane na
   wartości przysłane z okna (propozycja proporcjonalna do sztuk, edytowalna przez
   admina).

5. **Przeliczenie sum** — `total_amount` obu partii liczone tym samym wzorem, co w
   edycji Cła/VAT: `wartość zakupu pozycji + shipping_cost + customs_cost`
   (`modules/products/routes.py:4823`). Wzór trafia do wspólnego helpera
   `_przelicz_sumy_partii(poland_order)` używanego przez oba miejsca.

6. **Wpis do dziennika** — `log_activity(action='poland_order_split', entity_type='poland_order')`
   z numerem oryginału, numerem nowej partii, listą przeniesionych pozycji
   (id, produkt, ilość) i kwotami obu partii.

### Dziedziczenie `created_at` — dlaczego to jest krytyczne

`_allocate_product_shipping_fifo` (`modules/products/routes.py:4020`) ustawia partie
w kolejce po `PolandOrder.created_at, PolandOrder.id` i przydziela do nich sztuki
klientów według daty złożenia zamówienia. To samo robi
`_allocate_batch_units_to_orders` (`modules/products/routes.py:4141`) przy wypełnianiu
`PolandOrderItemOrder`.

Gdyby nowa partia dostała bieżącą datę, przesunęłaby się na koniec kolejki. Sam
podział niczego by nie zmienił (nie wywołuje przeliczeń), ale **następne**
uruchomienie `_distribute_proxy_shipping_to_client_orders` — np. przy zakładaniu
kolejnej partii z tym samym produktem — przetasowałoby sztuki między partiami,
zmieniło kwoty klientom i wywołało maile z `_notify_distributed_costs`.

Dziedziczenie `created_at` zachowuje pozycję w kolejce. Rozróżnienie obu partii przy
identycznym `created_at` daje `PolandOrder.id` (nowa jest wyższa, więc stoi tuż za
oryginałem) — to samo kryterium, którego zapytania już używają. Moment podziału jest
odczytywalny z `updated_at` i z dziennika aktywności.

### Czego podział celowo nie wywołuje

Podział **nie** woła `_distribute_proxy_shipping_to_client_orders`,
`_distribute_customs_vat_to_client_orders`, `_update_client_orders_on_polska_ordered`
ani `_notify_distributed_costs`. Stawki za sztukę i kwoty cła jadą razem z pozycjami,
a `Order.proxy_shipping_cost` i `Order.customs_vat_sale_cost` są wartościami
zapisanymi na zamówieniu — nietkniętymi. Powiadomienia i tak wychodzą wyłącznie przy
zmianie kwoty (`modules/products/routes.py:4343`), ale nie polegamy na tym: mechanizm
nie jest w ogóle uruchamiany.

### Endpointy

Oba w `modules/products/routes.py`, `@role_required('admin')` (jak usuwanie — mod ma
dostęp do statusu i cła, ale nie do zmian strukturalnych).

**`GET /admin/products/api/poland-orders/<int:id>/split-preview`**

Zwraca JSON do wypełnienia okna: numer i status partii, pozycje
(`id`, nazwa produktu, `selected_size`, `quantity`, wartość zakupu) oraz bieżące
`shipping_cost` i `customs_cost`. Osobny endpoint JSON, bo istniejący
`stock_order_items` (`modules/products/routes.py:2663`) zwraca fragment HTML listy.

**`POST /admin/products/api/poland-orders/<int:id>/split`**

```json
{
  "item_ids": [12, 13, 14],
  "shipping_cost_stara": "0.00",
  "shipping_cost_nowa": "0.00",
  "customs_cost_stara": "0.00",
  "customs_cost_nowa": "0.00"
}
```

Odpowiedź: `{"success": true, "nowy_numer": "PL/12", "nowa_partia_id": 42}`.

Walidacje (każda kończy się `rollback` i czytelnym komunikatem po polsku):

| Sytuacja | Kod | Komunikat |
|---|---|---|
| `item_ids` puste | 400 | „Zaznacz przynajmniej jedną pozycję do wydzielenia." |
| zaznaczono wszystkie pozycje | 400 | „W partii musi zostać przynajmniej jedna pozycja." |
| któreś `id` nie należy do tej partii | 409 | „Te pozycje nie są już w tej partii — odśwież stronę." |
| partia anulowana | 400 | „Nie można dzielić anulowanej partii." |
| kwota ujemna lub nieliczbowa | 400 | „Nieprawidłowa kwota." |

Warunek 409 obsługuje podwójne kliknięcie i równoległą pracę dwóch osób: pozycje
sprawdzane są po `poland_order_id` w tej samej transakcji, więc drugie żądanie nie
przeniesie niczego po raz drugi.

### Warstwa widoku

- **`templates/admin/warehouse/stock_orders.html`** — w kolumnie akcji wiersza partii
  (obok przycisku usuwania, `:431`) przycisk z ikoną nożyczek,
  `title="Podziel partię"`, widoczny dla `current_user.role == 'admin'` i tylko gdy
  `order.status != 'anulowane'`. Nowe okno `#splitPolandOrderModal` zbudowane na
  istniejących klasach `modal-overlay` / `modal modal-lg`, wzorowane na
  `#customsVatModal` (`:702`).
- **`static/js/pages/admin/stock-orders.js`** — `openSplitPolandOrderModal(orderId)`
  (pobiera podgląd, renderuje listę), licznik „zostaje / idzie" przeliczany przy
  każdym kliknięciu checkboxa, automatyczne wyliczanie proponowanego podziału kwot
  po sztukach przy zmianie zaznaczenia (tylko dopóki admin nie tknie pola ręcznie),
  `confirm()` z podsumowaniem i informacją „Kwoty u klientów nie zmienią się i nie
  pójdą żadne maile", `fetch` z `X-CSRFToken` przez `getCsrfToken()`, `showToast`,
  `window.location.reload()` — dokładnie wzorzec `_deleteOrder`
  (`static/js/pages/admin/stock-orders.js:1731`).
- **CSS** — style okna w `static/css/components/modals.css`, wariant jasny i ciemny.
  Ostrzeżenie o niezgodnej sumie („Suma obu partii to X, przed podziałem było Y")
  jest informacją, nie blokadą — bywa, że doszedł realny koszt.

## Testy

Nowy plik `tests/test_poland_order_split.py`, wzorowany na
`tests/test_poland_order_item_allocation.py` i `tests/test_proxy_shipping_distribution.py`.

1. **Kwoty klientów bez zmian** — `Order.proxy_shipping_cost` i
   `Order.customs_vat_sale_cost` wszystkich zamówień identyczne przed i po podziale.
2. **Brak powiadomień** — `EmailManager.notify_costs_added_bulk` i
   `PushManager.notify_cost_added` niewywołane (mock).
3. **FIFO nietknięte** — po podziale wymuszone
   `_distribute_proxy_shipping_to_client_orders` daje te same kwoty, co przed;
   test przechodzi tylko przy odziedziczonym `created_at`.
4. **Terminy płatności** — `get_shipping_kr_deadline()` i `get_customs_vat_deadline()`
   klienta z przeniesioną pozycją zwracają te same daty.
5. **Niezależność partii** — usunięcie nowej partii przez `delete_poland_order`
   zostawia oryginał i jego pozycje nietknięte; to samo w drugą stronę.
6. **Przypisania sztuk** — `PolandOrderItemOrder` przeniesionych pozycji wskazują na
   te same zamówienia i te same ilości.
7. **„Do zamówienia" bez zmian** — `get_products_to_order()` zwraca to samo przed i
   po podziale (dowód, że przeniesienie `ProxyOrderItem` nie rozjechało
   `already_ordered`).
8. **Sumy partii** — `total_amount` obu partii zgadza się z wzorem, a wartość
   produktów obu partii sumuje się do wartości sprzed podziału.
9. **Walidacje** — pusta lista, wszystkie pozycje, obce `id`, partia anulowana,
   kwota ujemna; każda zwraca właściwy kod i nie zmienia bazy.
10. **Uprawnienia** — mod i klient dostają odmowę, admin przechodzi.

## Znalezione przy okazji (osobne zadanie, poza tym projektem)

`delete_poland_order` (`modules/products/routes.py:3679`) zeruje klientom
`proxy_shipping_cost` i `customs_vat_sale_cost` przechodząc po
`PolandOrderItem.order_id`. To pole jest legacy i nigdy nie jest wypełniane —
`ProxyOrderItem` nie powstaje z `order_id` (`modules/products/routes.py:3050`,
`:3133`, `:3215`), a prawdziwe powiązanie idzie przez `PolandOrderItemOrder`
(`modules/products/models.py:470`). W efekcie pętla nigdy nic nie zeruje: po
usunięciu partii z niezerową wysyłką klient zostaje z kosztem za paczkę, której
już nie ma w systemie.

Nie naprawiamy tego tutaj — podział partii jest właśnie po to, żeby nie musieć
kasować. Do zgłoszenia osobno.
