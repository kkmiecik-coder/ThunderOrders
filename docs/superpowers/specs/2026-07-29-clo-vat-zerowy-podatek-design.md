# Cło/VAT: zerowy podatek i rozróżnienie „nieustalone" — projekt

Data: 2026-07-29
Gałąź: `feat/clo-vat-zerowy-podatek`

## Problem

Część zamówień nie ma cła/VAT, ale system nie potrafi tego zapisać.

Dziś kolumna stawki cła zawsze zawiera liczbę (domyślnie `0.00`), a `0` jest
w kodzie traktowane jak „nic nie wpisano", nie jak „ustalono: bez podatku".
Wynikają z tego trzy konkretne wady:

1. **Wpisanie 0% nie działa.** W `update_poland_customs_vat()`
   (`modules/products/routes.py:4066`) produkt trafia do dystrybucji tylko gdy
   `percentage > 0`; to samo filtrowanie jest w
   `_distribute_customs_vat_to_client_orders()` (`routes.py:3737`) oraz
   wcześniejszy `return` przy pustym słowniku (`routes.py:3719`).
   Skutek: gdy najpierw naliczono np. 23%, a potem poprawiono na 0%,
   **kwota na zamówieniu klienta nie zostaje wyzerowana** — zostaje stara.

2. **Zamówienie bez cła nigdy nie staje się „w pełni opłacone".**
   `get_confirmation_orders()`
   (`modules/client/payment_confirmation_service.py:209-210`) wymaga, by etap E3
   miał status `approved`. Przy zerowej kwocie klient nie może wgrać
   potwierdzenia (`Order.can_upload_stage_3`, `modules/orders/models.py:946`),
   więc status na zawsze zostaje `none`. Zamówienie wisi bezterminowo w zakładce
   „do zapłaty" i nie trafia ani do opłaconych, ani do archiwum.

3. **Klient widzi mylący stan.** Wiersz „Cło/VAT — 0.00 zł — Zablokowane"
   (`templates/client/payment_confirmations/list.html:104-209`) sugeruje kwotę
   zero, choć realnie znaczy „jeszcze nie policzono".

## Stan danych na produkcji (sprawdzone 2026-07-29)

Odczyt z bazy produkcyjnej potwierdził, że dzisiejsze zera są jednoznaczne:

| Paczki do Polski | Pozycji | Stawka `0` | Stawka `> 0` |
|---|---|---|---|
| 6 paczek z zapisanym terminem cła (modal zapisany) | 38 | 0 | 38 |
| 7 paczek bez terminu cła (modal nigdy nie zapisany) | 50 | 50 | 0 |

Korelacja jest stuprocentowa: **każde istniejące zero oznacza „nie ustalono"**,
ani jedno nie oznacza „ustalono, wyszło zero" — co wynika wprost z filtra
`percentage > 0` opisanego w punkcie 1.

Zamówienia klientów: `customs_vat_sale_cost = 0.00` — 2096 szt.,
`> 0` — 126 szt., `NULL` — 0 szt.

Wszystkie 88 pozycji paczek mają `poland_order_items.order_id = NULL` — pole
istnieje, ale nie jest wypełniane w żadnym z miejsc tworzenia
(`routes.py:2748`, `:2831`, `:2913`), więc `routes.py:3867` przepisuje pustkę.
Powiązanie pozycji paczki z zamówieniem klienta jest dziś wyliczane w locie
metodą FIFO (`_allocate_product_shipping_fifo`, `routes.py:3591`).

## Zakres

Etap 1 — rozróżnienie „nieustalone / bez podatku / z podatkiem" oraz poprawne
zerowanie. Obejmuje panel admina, konto klienta, blokadę zlecenia wysyłki,
migrację danych i API mobilne.

**Poza zakresem (Etap 2, osobny spec):** przeniesienie naliczania cła z modelu
„per produkt" na „per paczka" (mechanizmem FIFO, analogicznie do wysyłki KR).
Potrzebne tylko dla przypadków, gdy ten sam produkt jedzie w dwóch paczkach
i w jednej ma cło, a w drugiej nie. Wg właścicielki dotyczy to ok. 1% sytuacji.

## Model danych — trzy stany

| Wartość | Znaczenie |
|---|---|
| `NULL` | podatek jeszcze nie ustalony |
| `0` | podatek ustalony i wynosi zero — zamówienie bez cła |
| `> 0` | podatek ustalony i doliczany |

Kolumny zmieniane na `nullable=True, default=None` (dziś `default=0.00`):

- `PolandOrderItem.customs_vat_percentage` — `modules/products/models.py:446`
- `PolandOrderItem.customs_vat_amount` — `modules/products/models.py:447`
- `Order.customs_vat_sale_cost` — `modules/orders/models.py:181`

## Zachowanie (uzgodnione z właścicielką)

### Modal Cło/VAT (admin)

1. W `#customsVatGlobalSection`
   (`templates/admin/warehouse/stock_orders.html:757-810`) dochodzi
   **jeden przełącznik dla całego modala**, wyrównany do prawej krawędzi sekcji,
   pod przyciskiem „Zastosuj".
2. Stan domyślny: **„Zamówienie z cłem/VAT"** — modal działa dokładnie jak dziś.
3. Po przestawieniu na **„Bez cła/VAT"**:
   - wszystkie pola `%` (globalne i per pozycja) zostają **zablokowane**
     (`disabled`) i wyczyszczone do `0`,
   - kolumna „Kwota Cło/VAT" pokazuje `0.00 zł`, suma `0.00 zł`,
   - **pole terminu płatności znika i przestaje być wymagane** — dziś jest
     obowiązkowe zarówno po stronie serwera (`routes.py:4035-4036`), jak i
     w walidacji JS (`static/js/pages/admin/stock-orders.js:1116-1131`).
4. Przełącznik działa na wszystkie paczki widoczne w modalu naraz — spójnie
   z istniejącym polem „Zastosuj % do wszystkich produktów" i z faktem, że
   w Etapie 1 cło nadal liczy się per produkt.
5. Styl przełącznika w `static/css/pages/admin/stock-orders.css` obok
   istniejących reguł `.customs-vat-*` (od `:2321`), z wariantem ciemnym
   przy `[data-theme="dark"]` (od `:2488`).

### Zapis i propagacja

6. Zapis modala z przełącznikiem w pozycji „bez cła" zapisuje **`0`**
   (nie `NULL`) w `customs_vat_percentage` i `customs_vat_amount` wszystkich
   pozycji objętych modalem. To jest zapis decyzji.
7. Znikają filtry `percentage > 0` w `routes.py:4066` i `routes.py:3737` oraz
   wczesny `return` w `routes.py:3719` — stawka `0` musi przechodzić przez
   dystrybucję tak samo jak stawka dodatnia.
8. `_distribute_customs_vat_to_client_orders()` ustawia
   `order.customs_vat_sale_cost = 0` dla zamówień zawierających produkty ze
   stawką `0`. Dotychczasowa flaga `has_match` musi uznawać dopasowanie także
   przy stawce zerowej.
9. Zamówienia i pozycje nietknięte modalem zachowują `NULL`.
10. Przy zapisie „bez cła" `PolandOrder.customs_payment_deadline` jest
    **czyszczony do `NULL`** — nie ma płatności, więc nie ma terminu. Dotyczy to
    także paczek, które wcześniej miały ustawiony termin przy stawce dodatniej.
    `PolandOrder.customs_cost` przeliczy się wtedy do `0`, a `total_amount`
    odpowiednio zmaleje (istniejąca logika `routes.py:4082-4091`, bez zmian).
11. `Order.get_customs_vat_deadline()` (`modules/orders/models.py:981-987`)
    zwróci wtedy `None` — widok klienta musi to znieść bez błędu
    (sekcja terminu w `templates/client/payment_confirmations/list.html:178-209`).

### Blokada wyzerowania opłaconego cła

12. Przed zapisem endpoint sprawdza, które zamówienia klientów zostałyby
    wyzerowane (`customs_vat_sale_cost > 0` → `0`).
13. Jeśli którekolwiek z nich ma `stage_3_status` równy **`approved` lub
    `pending`**, zapis jest **odrzucany** (HTTP 409) z komunikatem
    wymieniającym numery tych zamówień. Status `pending` jest objęty blokadą,
    bo wgrane potwierdzenie oznacza, że przelew najpewniej już wyszedł.
14. Komunikat ma nazywać przyczynę wprost, np.: „Nie można wyzerować Cła/VAT —
    zamówienia ZAM/00123, ZAM/00124 mają już opłacony ten etap."
15. Sprawdzenie jest **całościowe**: odrzucenie dotyczy całego zapisu modala,
    nie pojedynczych pozycji — nic nie zostaje zapisane częściowo.

### Konto klienta

16. Rubryka „Cło/VAT" (`templates/client/payment_confirmations/list.html`)
    zachowuje się zależnie od stanu:

| Kwota | Co widzi klient | Czy blokuje „w pełni opłacone" |
|---|---|---|
| `> 0` | „Do zapłaty" → po wgraniu i akceptacji „Opłacone" | tak |
| `0` | **wiersz w ogóle się nie pojawia** — nie ma czego opłacać | **nie** |
| `NULL` | „Zablokowane" — **bez zmian wobec dziś** | tak |

17. Przy kwocie `0` etap E3 jest **strukturalnie nieobecny** — dokładnie tak,
    jak dziś dla zamówień `on_hand`. Realizuje to jeden warunek dopisany do
    `order_stage_keys()` (`payment_confirmation_service.py:22-29`), które jest
    kanonicznym źródłem prawdy o obecności etapów (używa go zarówno widok
    webowy, jak i walidacja bulk uploadu, jak i API mobilne):

```python
if order.order_type != 'on_hand' and order.customs_vat_sale_cost != 0:
    keys.add('customs_vat')
```

   Uwaga: warunek musi odróżniać `0` od `NULL` — przy `NULL` etap zostaje
   obecny (stan „nieustalone" nadal blokuje i pokazuje „Zablokowane").

18. Konsekwencje wynikające z pkt 17, bez dodatkowej logiki:
    - **brak opcji opłacenia** — klient nie ma jak wgrać potwierdzenia
      (`validate_bulk_upload()` odrzuci taką próbę kodem `stage_not_applicable`,
      `payment_confirmation_service.py:67-72`),
    - **brak maili i powiadomień** o tym etapie,
    - `get_confirmation_orders()` (`payment_confirmation_service.py:204-227`)
      nie doda `stage_3_status` do listy sprawdzanych statusów, więc zamówienie
      normalnie trafi do opłaconych, a po trzech dniach do archiwum.
19. Miejsca do doprowadzenia do parytetu z pkt 17:
    - `templates/client/payment_confirmations/list.html` — pominięcie sekcji E3
      oraz atrybutów `data-stage3-*` i `data-customs-vat-amount`,
    - `static/js/pages/client/payment-confirmations.js` — pominięcie etapu
      w budowie kart i w mapowaniu kwot (`:574`),
    - `modules/api_mobile/orders_routes.py:92-168` — `_serialize_payment_stages()`
      nie zwraca etapu E3,
    - `get_confirmation_orders()` — warunek `order.order_type != 'on_hand'`
      (`:209-210`) zastąpiony wywołaniem `order_stage_keys()`, żeby reguła
      obecności etapów istniała w kodzie **tylko raz**.
20. `can_upload_stage_3` pozostaje bez zmian merytorycznych (kwota `0` i `NULL`
    dalej blokują wgranie); dochodzi wyłącznie obsługa wartości `NULL`.

### Zlecenie wysyłki

21. `Order.is_customs_vat_settled` (`modules/orders/models.py:959-971`)
    przyjmuje nową logikę:
    - `order_type == 'on_hand'` → `True` (bez zmian),
    - `customs_vat_sale_cost IS NULL` → **`False`** (nowość — blokuje),
    - `== 0` → `True`,
    - `> 0` → `True` tylko gdy `stage_3_status == 'approved'`.
22. **To jest zmiana dzisiejszego zachowania:** dopóki cło dla paczki nie
    zostanie zapisane (choćby zerowe), klienci z tej paczki nie zlecą wysyłki.
    Modal Cło/VAT staje się krokiem obowiązkowym. Świadoma decyzja właścicielki;
    ostrzeżeń ani liczników w panelu admina **nie dodajemy**.
23. `shipping_service.py:164-166` rozdziela dziś jeden kod błędu na dwa:
    - `customs_vat_unpaid` — kwota `> 0`, nieopłacona (komunikat jak dziś:
      „Najpierw opłać Cło/VAT dla wybranych zamówień."),
    - `customs_vat_not_set` — kwota `NULL`, komunikat w rodzaju
      „Trwa ustalanie Cła/VAT — wysyłkę zlecisz, gdy będzie gotowe."
    Komunikat „opłać" przy nieustalonym cle byłby mylący: klient nie ma czego
    opłacić i zacznie pytać obsługę.
24. Nowy kod obsługują: `modules/client/shipping.py:254` oraz mapy
    w `modules/api_mobile/shipping_routes.py:141,149,153`.

### Powiadomienia

25. Przy zejściu kwoty do zera **nie wysyłamy nic** — ani maila, ani push.
    Obecny warunek `costs['new'] > 0 and costs['new'] != costs['old']`
    (`routes.py:3778`) już to zapewnia i **pozostaje bez zmian**.
    Ryzyko „klient zapłaci za coś, co anulowano" jest ograniczone blokadą
    z punktu 13 — cła opłaconego lub oczekującego nie da się wyzerować.
26. Zamówienie z cłem `0` nie ma etapu E3 (pkt 17), więc nie trafi też do
    przypomnień o płatnościach ani do żadnego zestawienia „do zapłaty".

## Migracja danych

Jedna migracja Alembic, uruchamiana najpierw lokalnie, po wdrożeniu na
produkcji (kolejność ustalona: praca lokalnie → migracja lokalnie → push →
migracja na serwerze). Przed uruchomieniem na produkcji — kopia bazy.

**Krok w przód:**
1. `ALTER` trzech kolumn na `nullable`, `server_default` usunięty.
2. `UPDATE poland_order_items SET customs_vat_percentage = NULL,
   customs_vat_amount = NULL WHERE customs_vat_percentage = 0` (dot. 50 pozycji).
3. `UPDATE orders SET customs_vat_sale_cost = NULL
   WHERE customs_vat_sale_cost = 0` (dot. 2096 zamówień).

Zamiana wszystkich zer na `NULL` jest bezpieczna, bo — jak wykazano wyżej —
dziś żadne zero nie może oznaczać ustalonego braku podatku.

**Krok wstecz:** `UPDATE ... SET <kolumna> = 0 WHERE <kolumna> IS NULL`,
następnie przywrócenie `NOT NULL`/`default 0.00`. Rozróżnienie stanów przepada,
co jest nieuniknione — stan sprzed migracji go nie zawierał.

## Pliki do zmiany

**Backend**
- `modules/products/models.py` — 2 kolumny nullable
- `modules/orders/models.py` — kolumna nullable; `customs_vat_total`,
  `can_upload_stage_3`, `is_customs_vat_settled`, `total_to_pay`,
  `payment_icon_state`, `payment_badge` — obsługa `NULL`; nowa właściwość
  rozróżniająca „ustalone zero" od „nieustalone"
- `modules/products/routes.py` — `update_poland_customs_vat()` (przełącznik,
  warunkowy termin, blokada z pkt 12-15), `_distribute_customs_vat_to_client_orders()`
- `modules/client/payment_confirmation_service.py` — `order_stage_keys()`
  (kluczowa zmiana, pkt 17), `stage_amount()`, `get_confirmation_orders()`
- `modules/client/shipping_service.py` + `modules/client/shipping.py` — nowy kod błędu
- `modules/api_mobile/shipping_routes.py`, `modules/api_mobile/orders_routes.py` — parytet
- `migrations/versions/<rev>_clo_vat_nullable.py` — nowa migracja

**Frontend**
- `templates/admin/warehouse/stock_orders.html` — przełącznik w modalu
- `static/js/pages/admin/stock-orders.js` — logika przełącznika, blokowanie pól,
  warunkowa walidacja terminu, obsługa odpowiedzi 409
- `static/css/pages/admin/stock-orders.css` — styl przełącznika, jasny i ciemny
- `templates/client/payment_confirmations/list.html` — trzeci stan rubryki E3
- `static/js/pages/client/payment-confirmations.js` — parytet kwot i statusów

## Testy

Nowy plik `tests/test_customs_vat_zero.py`:
- zapis modala z przełącznikiem „bez cła" zapisuje `0`, nie `NULL`
- stawka `0` zeruje `customs_vat_sale_cost` na zamówieniach klientów
  (test wprost na scenariuszu 23% → 0%)
- `order_stage_keys()` **nie zawiera** `customs_vat` przy kwocie `0`,
  ale **zawiera** przy `NULL` i przy kwocie dodatniej
- próba wgrania potwierdzenia E3 dla zamówienia z cłem `0` kończy się kodem
  `stage_not_applicable` (web i API mobilne)
- `_serialize_payment_stages()` nie zwraca etapu E3 przy kwocie `0`
- zamówienie z cłem `0` przechodzi do „w pełni opłacone" po opłaceniu
  pozostałych etapów
- `is_customs_vat_settled`: `NULL` → `False`, `0` → `True`,
  `> 0` bez akceptacji → `False`
- próba wyzerowania przy `stage_3_status` `approved` → 409
- próba wyzerowania przy `stage_3_status` `pending` → 409
- zejście kwoty do zera nie wywołuje powiadomień

Regresja w istniejących: `tests/test_cost_notifications_bulk.py`,
`tests/test_shipping_service.py`, `tests/test_payment_confirmation_service.py`,
`tests/test_mobile_api_orders.py`.

Uruchamianie: `python -m pytest`.

## Otwarte kwestie

Brak — wszystkie decyzje projektowe rozstrzygnięte z właścicielką.
