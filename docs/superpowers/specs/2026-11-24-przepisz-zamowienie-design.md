# Przepisanie zamówienia na inną klientkę — projekt

Data: 2026-11-24 · Gałąź: `feat/przepisz-zamowienie` · Decyzje: Karolina (właścicielka), przez sesję koordynującą.

## Po co

Karolina: „najczęściej to ktoś dla kogoś brał kartę lub się dogadał z kimś że bierze tą kartę”.
Klientka A (Ania) ma w zamówieniu kartę (photocard itp.), która w praktyce należy do klientki B (Basi):
albo Ania zamówiła ją dla Basi, albo Basia ją od Ani przejęła. Dziś admin nie ma jak tego odzwierciedlić
w systemie. Czasem trzeba przepisać całe zamówienie, częściej pojedyncze pozycje.

## Cele

- W panelu admina, na stronie zamówienia: przycisk „Przepisz na inną klientkę”.
- Dwa tryby: **całe zamówienie** albo **wybrane pozycje** (z możliwością przeniesienia części sztuk pozycji).
- Przepisanie nie może przesunąć nikomu innemu miejsca w kolejce FIFO do partii z Korei.
- Pieniądze i koszty liczą się poprawnie u obu klientek.

## Nie-cele

- Klientki nie przepisują same (tylko admin/mod).
- Brak cofania jednym kliknięciem (odwrotność = przepisać z powrotem).
- Nie naprawiamy tu błędu pustych `poland_order_item_orders` dla PRX/PL/12+ (osobne zadanie);
  kod musi działać także przy pustych powiązaniach.

## Anty-cele (porażka mimo że „działa”)

- Inne klientki dostają nagle sztuki z innej partii / inne koszty E2 (przetasowana kolejka).
- Suma pieniędzy się „rozjeżdża” (kwota znika albo jest liczona podwójnie).
- Basia widzi dane Ani (adres, dowód przelewu z danymi bankowymi).

## Decyzje Karoliny

1. **Wpłaty przy przepisaniu pozycji: opcja C.** W okienku przełącznik „Wpłata idzie razem z kartą”
   (domyślnie zaznaczony):
   - zaznaczony (A): opłacona część kwoty przypadająca na kartę przechodzi do Basi (etapy E1, E2, E3);
     dziewczyny rozliczają się między sobą;
   - odznaczony (B): wpłata zostaje u Ani (Ania ma nadpłatę do zwrotu/zaliczenia — admin robi to jak dziś),
     Basia płaci od nowa.
   Koszt wysyłki z Korei (E2) i cło (E3) przypadające na kartę przechodzą zawsze; przełącznik decyduje
   tylko o tym, czy przechodzi też *wpłata* za nie.
2. **Gdzie ląduje karta: wersja 1.** Zawsze nowe, osobne zamówienie Basi: nowy numer (`{PREFIX}/{ID}`
   jak zwykle), **data złożenia przejęta od Ani**, ten sam typ, strona sprzedaży, liczba etapów i status.
3. **Część sztuk:** jeśli Ania ma 2 sztuki tej samej karty, można przepisać 1.
4. **Całe zamówienie = zmiana klientki na kopercie:** numer, data, wpłaty, koszty zostają; zmienia się
   właścicielka. Przełącznika wpłat w tym trybie nie ma.
5. **Gift cards (przydziały z kampanii)** przypisane do pozycji przechodzą na Basię razem z pozycją.
6. **Powiadomienia: wersja b.** Pole „Powiadom klientki”, domyślnie zaznaczone. Basia: mail + push
   „Dodano dla Ciebie zamówienie … (przepisane od innej klientki)”; Ania: „Karta X została przepisana
   na inną osobę” — bez danych Basi.
7. **Blokady:** nie da się przepisać zamówienia w zleceniu wysyłki; anulowanego/zwróconego; pakowanego
   w WMS.
8. **Historia:** wpis w historii obu zamówień — kto, kiedy, co, na kogo, czy wpłata poszła za kartą.

## Podejścia (rozważone)

Sposób techniczny (decyzja wykonawcy — Karolina mówi o efektach, nie o „jak”):

- **Wybrane: serwis domenowy + endpoint + modal.** Funkcja `przepisz_zamowienie(...)` w nowym module
  `modules/orders/transfer.py` (cała logika, jedna transakcja), cienka trasa POST w `routes.py`,
  modal w `templates/admin/orders/detail.html`. Testowalne bez UI.
- Odrzucone: przeliczanie kosztów E2/E3 przez istniejące `_distribute_*` dla wszystkich zamówień —
  nadpisałoby ręczne korekty innym klientkom (anty-cel). Liczymy tylko udział A↔B.
- Odrzucone: dopinanie do istniejącego zamówienia Basi (Karolina wybrała wersję 1).

## Projekt

### Kolejka FIFO — kotwica (mój wybór, konieczny dla decyzji 2)

`orders.created_at` to w MariaDB `DATETIME` z dokładnością do sekundy; przy sprzedaży LIVE wiele
zamówień ma tę samą sekundę, a remis rozstrzyga `id`. Nowe zamówienie Basi z datą Ani dostałoby
największe `id`, więc stanęłoby za wszystkimi zamówieniami z tej sekundy — przesuwając je w kolejce.

Rozwiązanie: nowa kolumna `orders.fifo_anchor_order_id` (INT NULL, FK → orders.id, `ON DELETE SET NULL`,
indeks). Zamówienie Basi dostaje `fifo_anchor_order_id = A.id` (albo kotwicę A, jeśli A sama jest
przepisana — łańcuch). Klucz kolejki: `(created_at, COALESCE(fifo_anchor_order_id, id), id)`.
Pomocnik `fifo_order_by()` w `modules/orders/models.py`, użyty w:
`_allocate_product_shipping_fifo` i `_batch_allocation_for_range` (`modules/products/routes.py`) oraz
w liczeniu przydziałów setów przy zamknięciu sprzedaży (`utils/offer_closure.py`, pierwsze zapytanie,
dziś tylko `created_at`). Dla zamówień bez kotwicy kolejność identyczna jak dotąd.

### Dowody przelewu (mój wybór — prywatność)

Nowa kolumna `payment_confirmations.proof_hidden_for_client` (BOOL NOT NULL default 0). Przy przepisaniu
całego zamówienia ustawiana na wszystkich potwierdzeniach z plikiem. Klientka nie widzi takiego pliku
(lista potwierdzeń w panelu klienta, API mobilne, `serve_payment_proof` → 403 dla klienta); admin widzi.
Przy przepisaniu pozycji nowe potwierdzenia Basi powstają bez pliku (`proof_file = NULL`).

### Tryb „całe zamówienie”

- `order.user_id = B`.
- Dane Ani zdejmowane z zamówienia: adres i punkt odbioru (`shipping_*`, `pickup_*`), `delivery_method`,
  `custom_name`. Notatka klientki (`notes`) przenoszona do `admin_notes` z dopiskiem
  „Notatka poprzedniej klientki: …”, potem `notes = NULL`.
- `GiftAssignment.user_id = B` dla pozycji zamówienia; `CollectionItem` nie ruszamy (powstają po
  dostarczeniu — a dostarczone są zablokowane).
- Dowody: `proof_hidden_for_client = True`.
- Kwoty, wpłaty, data, numer, kotwica bez zmian.

### Tryb „wybrane pozycje”

Wejście: lista `{item_id, quantity}`. Walidacja:
- co najmniej jedna pozycja; nie wolno wybrać *wszystkiego* (wtedy → tryb „całe zamówienie”);
- `1 ≤ quantity ≤ item.quantity`;
- część sztuk (`quantity < item.quantity`) tylko dla pozycji „prostej”: `fulfilled_quantity` NULL
  lub równe `quantity`, `is_set_fulfilled` nie False, `incl_only_quantity == 0`, `picked_quantity == 0`,
  brak przydziałów gift cards. Pozostałe pozycje — tylko w całości (mój wybór: inaczej nie da się
  jednoznacznie powiedzieć, które sztuki są zrealizowane/incl/z gift card).
- z przełącznikiem A: żaden etap Ani nie może mieć potwierdzenia „oczekuje” (najpierw zatwierdź
  lub odrzuć — inaczej nie wiadomo, ile wpłaty przenieść).

Kroki (jedna transakcja):
1. Nowe zamówienie B: placeholder numeru → flush → `assign_order_number(B, A.order_type)`;
   `user_id=B`, `order_type`, `status`, `offer_page_id`, `offer_page_name`, `payment_stages` z A;
   `created_at = A.created_at`; `fifo_anchor_order_id = A.fifo_anchor_order_id or A.id`;
   `created_by_admin_id = current_user`; adres pusty; kwoty 0.
2. Pozycje: całość → `item.order_id = B.id`; część → A.quantity −= k (total przeliczony),
   nowa pozycja B z k sztukami i tymi samymi polami produktu/ceny/rozmiaru/setu/bonusu, `total = price × k`.
   Gift assignments pozycji przeniesionej w całości → `user_id = B`.
3. Udziały (liczone *przed* zmianami, do porównania po):
   - **E1** = suma `total` przeniesionych sztuk (`price × k` lub `item.total` całej pozycji).
   - **E2** (tylko `payment_stages == 4`, tylko zamówienia ze strony sprzedaży) = dla każdego
     przeniesionego produktu: `alloc_przed[A] − alloc_po[A]` z `_allocate_product_shipping_fifo(pid)`
     (po flushu pozycji i B, z kotwicą); przycięte do `[0, A.proxy_shipping_cost]`.
     `A.proxy_shipping_cost −= E2`, `B.proxy_shipping_cost = E2` (suma zachowana; ręczne korekty innych
     zamówień nietknięte).
   - **E3** (gdy `A.customs_vat_sale_cost` nie jest NULL i typ ≠ on_hand) = dla przeniesionych sztuk
     `price × efektywna_ilość × stawka / 100` (stawka = `customs_vat_percentage` z najnowszej
     nieanulowanej partii tego produktu; brak stawki → 0), zaokrąglone do grosza, przycięte do
     `[0, A.customs_vat_sale_cost]`. `A −= E3`, `B = E3`. Gdy u A NULL → u B NULL.
   - `A.recalculate_total_amount()`, `B.recalculate_total_amount()`.
4. Wpłaty (tylko przełącznik A): dla etapów `product`/`korean_shipping`/`customs_vat` z zatwierdzonym
   potwierdzeniem u A: `ruch = min(udział_etapu, conf.amount)`; `conf.amount −= ruch`;
   `A.paid_amount −= ruch`; u B nowe `PaymentConfirmation(status='approved', amount=ruch,
   payment_stage=…, payment_method_id=conf.payment_method_id, proof_file=None,
   uploaded_at=conf.uploaded_at)`; `B.paid_amount += ruch`. Przełącznik B: nic nie przenosimy.
5. Powiązania z partiami (`poland_order_item_orders`): dla każdego przeniesionego produktu przenieś
   do B tyle sztuk z wierszy A (od najpóźniejszej partii — sztuki A są na końcu jej zakresu, a B stoi
   tuż za A), zmniejszając/usuwając wiersze A. Gdy powiązań brak (błąd PRX/PL/12+) — nic nie robimy.
   Kolumny legacy `poland_order_items.order_id` / `proxy_order_items.order_id` bez zmian.
6. Historia: `OrderComment(is_internal=True)` w obu zamówieniach + `log_activity(action='order_transferred')`.
7. Commit; po commicie powiadomienia (jeśli zaznaczone) — błąd wysyłki nie cofa przepisania.

### Blokady (oba tryby)

- zamówienie w zleceniu wysyłki (`is_in_shipping_request`);
- status w `anulowane`, `do_zwrotu`, `zwrocone`, `czesciowo_zwrocone`, oraz `wyslane`, `dostarczone`
  (mój dodatek — po wysyłce przepisanie nie ma sensu, a dostarczone mają już kolekcję klientki);
- zamówienie zablokowane w WMS (`wms_locked_at` lub `wms_session_id`);
- klientka docelowa = obecna; docelowy użytkownik nie istnieje albo nie ma roli `client`.

### Powiadomienia

- Basia: mail + push (nowe metody `EmailManager.notify_order_transferred_to` /
  `PushManager.notify_order_transferred_to`), link do nowego (lub całego) zamówienia, lista pozycji,
  kwota do zapłaty.
- Ania: mail + push „Pozycja X z zamówienia … została przepisana na inną osobę” (przy całym zamówieniu:
  „Zamówienie … zostało przepisane na inną osobę”). Bez danych Basi.
- Szablony maili w stylu istniejących (`templates/emails/`), przełącznik w ustawieniach maili
  jak inne powiadomienia (klucz `order_transferred`, domyślnie włączony).

### UI (admin)

- `templates/admin/orders/detail.html`: przycisk „Przepisz na inną klientkę” (ukryty/wyłączony z
  podpowiedzią, gdy blokada).
- Modal (style wyłącznie w `static/css/components/modals.css`, jasny + ciemny, cele 44px):
  1. wybór klientki — istniejące wyszukiwanie `/api/clients/search`;
  2. tryb: „Całe zamówienie” / „Wybrane pozycje” — przy pozycjach checkbox + pole ilości
     (zablokowane na pełnej ilości dla pozycji nie-prostych);
  3. „Wpłata idzie razem z kartą” (tylko tryb pozycji, domyślnie ✓);
  4. „Powiadom klientki” (domyślnie ✓);
  5. „Przepisz” → POST JSON z CSRF → toast + przekierowanie do zamówienia Basi (tryb pozycji) albo
     odświeżenie (całe).
- Trasa: `POST /admin/orders/<id>/transfer`, `@role_required('admin', 'mod')`, odpowiedź JSON.

### Statystyki / osiągnięcia / limity

- Osiągnięcia liczą się na żywo z `orders.user_id` — nic do robienia; już przyznane zostają.
- Limit sprzedaży strony (`set_max_per_product`) jest globalny — liczba sztuk się nie zmienia.

## Testy (TDD, `tests/test_order_transfer.py`)

- całe zamówienie: zmienia user_id, czyści adres/notatkę, ukrywa dowody, gift assignments → B;
- pozycja w całości / część sztuk: kwoty E1 u A i B, suma zachowana;
- E2: dwie partie i kilka zamówień z tą samą sekundą — przydziały innych zamówień identyczne przed i po;
- E3: udział wg stawki, NULL zostaje NULL;
- wpłaty przełącznik A vs B; blokada przy oczekującym potwierdzeniu;
- powiązania `poland_order_item_orders` przeniesione / brak powiązań nie wywala;
- blokady (zlecenie wysyłki, status, WMS, wszystko zaznaczone, ilość poza zakresem, pozycja nie-prosta);
- kotwica FIFO w `_batch_allocation_for_range` i `_allocate_product_shipping_fifo`;
- trasa: 403 dla klienta, JSON sukcesu, powiadomienia wołane tylko z flagą;
- klient nie widzi ukrytego dowodu (`serve_payment_proof` 403).

## Zostawione wykonawcy

Teksty maili/pushy, dokładny wygląd modala, nazwy funkcji pomocniczych.
