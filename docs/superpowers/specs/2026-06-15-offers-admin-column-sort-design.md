# Sortowanie listy `/admin/offers` przez klik w nagłówki kolumn

**Data:** 2026-06-15
**Strona:** `/admin/offers` (lista stron sprzedaży, po podziale na zakładki Bieżące/Zamknięte)
**Typ zmiany:** Czysto front-end (HTML/Jinja makra + JS + CSS). **Bez zmian w bazie / route / Pythonie.**

## Cel

Umożliwić sortowanie listy stron sprzedaży po kliknięciu w nagłówek kolumny (rosnąco/malejąco), działające także na widoku mobilnym (karty) przez dedykowany kontroler.

## Decyzje (ustalone z użytkownikiem)

1. **Mechanizm: client-side (JS).** Klik natychmiast przestawia węzły w DOM, bez przeładowania. Zachowuje aktywną zakładkę, wpisaną frazę wyszukiwarki i zaznaczenia bulk. Sortuje niezależnie w obrębie aktywnej zakładki. (Konwencja listy klientów jest server-side, ale strona ofert jest w całości client-side — zakładki, wyszukiwarka, bulk — bez paginacji, więc client-side pasuje lepiej i nie psuje tych mechanizmów.)
2. **Sortowalne kolumny:** Nazwa, Typ, Typ wysyłki, Status, Utworzono, Rozpoczęcie, Zakończenie, Termin płatności. **Bez** kolumny Akcje i checkboxa.
3. **Cykl klików:** toggle — 1. klik rosnąco, każdy kolejny odwraca kierunek. Brak „powrotu do domyślnego" przez klik.
4. **Mobile:** sortowanie działa też na kartach, przez kontroler (dropdown pól + przycisk kierunku) nad kartami, bo karty nie mają nagłówków.
5. **Sortowanie po statusie** używa priorytetu (active → paused → scheduled → draft → ended), nie alfabetu etykiet.
6. **Stan sortowania:** per zakładka, efemeryczny — reset po przeładowaniu (F5) do domyślnego porządku status+data. Brak persystencji między sesjami.

## Stan istniejący (reuse)

- Klasy wskaźnika sortowania `.sortable`, `.sorted-asc::after` (↑), `.sorted-desc::after` (↓) istnieją w `static/css/pages/admin/clients-list.css` (akcent `#FF8500` light, dark w liniach ~1025-1030). Ten plik **nie** jest ładowany na stronie ofert — trzeba dodać równoważne reguły do `offer-list.css` (light + dark).
- Konwencja listy klientów: `<th class="sortable {% if sort_by==... %}sorted-{{sort_dir}}{% endif %}" onclick="sortBy(...)">` — server-side. Tu robimy odpowiednik client-side bez inline `onclick`.
- Makra `offer_table(pages, tab_id)` i `offer_mobile_cards(pages)` w `templates/admin/offers/_list_items.html` renderują wiersze tabeli i karty (po podziale na zakładki).
- `offer-list.js` ma już `initializeOfferTabs()` (zakładki) i `initializeBulkActions()`; wyszukiwarka filtruje `[data-search-name]` przez `.is-hidden`.

## Architektura

### A. Atrybuty `data-sort-*` na korzeniu wiersza i karty — `_list_items.html`

Aby jeden silnik sortował jednolicie tabelę i karty, na **korzeniu** każdego `<tr>` (makro `offer_table`) oraz każdej `.offer-card` (makro `offer_mobile_cards`) dodać identyczny komplet atrybutów z obiektu `page`:

| Atrybut | Wartość (Jinja) | Typ sortowania |
|---|---|---|
| `data-sort-name` | `{{ page.name }}` | text |
| `data-sort-ptype` | `{{ page.page_type }}` (exclusive/preorder) | text |
| `data-sort-shipping` | `{{ 'proxy' if page.payment_stages == 4 else 'polska' }}` | text |
| `data-sort-status` | `{{ page.status }}` (surowy, np. `active`) | status |
| `data-sort-created` | `{{ page.created_at.isoformat() if page.created_at else '' }}` | date |
| `data-sort-starts` | `{{ page.starts_at.isoformat() if page.starts_at else '' }}` | date |
| `data-sort-ends` | `{{ page.ends_at.isoformat() if page.ends_at else '' }}` | date |
| `data-sort-deadline` | `{{ page.payment_deadline.isoformat() if page.payment_deadline else '' }}` | date |

Daty jako ISO (`YYYY-MM-DDTHH:MM:SS`) sortują się leksykograficznie poprawnie. Puste (`''`) zawsze na końcu, niezależnie od kierunku.

> Uwaga implementacyjna: `<tr>` i `.offer-card` to korzenie pętli wewnątrz makr — atrybuty dodać do tych elementów (nie do pojedynczych komórek), żeby JS czytał je jednolicie z obu widoków.

### B. Nagłówki tabeli — makro `offer_table`

Każdy sortowalny `<th>` dostaje: klasę `sortable`, `data-sort-key` (`name`/`ptype`/`shipping`/`status`/`created`/`starts`/`ends`/`deadline`) i `data-sort-type` (`text`/`status`/`date`). Bez inline `onclick` — listenery podpina JS (separacja CSS/JS od HTML wg CLAUDE.md). Kolumny checkbox i Akcje pozostają bez zmian.

Mapowanie kolumn → klucz/typ:
- Nazwa → `name`/text
- Typ → `ptype`/text
- Typ wysyłki → `shipping`/text
- Status → `status`/status
- Utworzono → `created`/date
- Rozpoczęcie → `starts`/date
- Zakończenie → `ends`/date
- Termin płatności → `deadline`/date

### C. Kontroler mobilny — makro `offer_mobile_cards`

Nad `<div class="offer-cards-mobile">` dodać kontroler (widoczny tylko mobile przez CSS), np.:

```html
<div class="offer-sort-mobile">
    <select class="offer-sort-select" aria-label="Sortuj strony">
        <option value="" disabled selected>Sortuj wg…</option>
        <option value="name|text">Nazwa</option>
        <option value="ptype|text">Typ</option>
        <option value="shipping|text">Typ wysyłki</option>
        <option value="status|status">Status</option>
        <option value="created|date">Utworzono</option>
        <option value="starts|date">Rozpoczęcie</option>
        <option value="ends|date">Zakończenie</option>
        <option value="deadline|date">Termin płatności</option>
    </select>
    <button type="button" class="offer-sort-dir" aria-label="Kierunek sortowania" disabled>↑</button>
</div>
```

`value="klucz|typ"` przenosi i klucz, i typ sortowania. Przycisk kierunku domyślnie nieaktywny do czasu wyboru pola. Każda zakładka renderuje własny kontroler (niezależny stan). Touch target przycisku ≥ 44px (zgodnie z wytyczną mobilną projektu).

### D. Silnik sortujący — `initializeOfferSort()` w `offer-list.js`

Nowa funkcja wywoływana w `DOMContentLoaded` (obok `initializeOfferTabs`, `initializeBulkActions`).

- **Mapa priorytetu statusów** (stała w JS): `{active:0, paused:1, scheduled:2, draft:3, ended:4}`.
- **Komparator** wg typu:
  - `text`: porównanie case-insensitive (`localeCompare` na małych literach).
  - `date`: ISO string; pusty `''` zawsze na końcu (w obu kierunkach), pozostałe rosnąco/malejąco wg porównania stringów.
  - `status`: po wartości z mapy priorytetu (nieznany status → na koniec).
- **`applySort(panel, key, type, dir)`**:
  1. W danym panelu (`.offer-tab-panel`) pobiera wiersze z `tbody` i karty z `.offer-cards-mobile`.
  2. Sortuje obie kolekcje tym samym komparatorem (klucz `data-sort-${key}`), reorderuje węzły w DOM (`appendChild` w nowej kolejności).
  3. Ustawia klasę `.sorted-asc`/`.sorted-desc` na aktywnym `<th>` (czyści z pozostałych `<th>` w tej tabeli) i synchronizuje kontroler mobilny (`select.value`, strzałka i stan `disabled` przycisku).
- **Klik w nagłówek**: jeśli kolumna już aktywna → odwróć kierunek; w przeciwnym razie ustaw `asc`. Wywołaj `applySort` dla panelu, w którym jest dany `<th>`.
- **Kontroler mobilny**: zmiana `<select>` → `applySort` z kierunkiem bieżącym (domyślnie `asc` przy pierwszym wyborze); klik przycisku kierunku → odwróć i ponów `applySort`.
- **Stan per panel, efemeryczny**: trzymany w atrybutach na elemencie panelu (np. `data-sort-key`, `data-sort-dir`) lub w zmiennych zakresu; reset następuje naturalnie przy przeładowaniu (serwer renderuje domyślny porządek).

### E. Współpraca z istniejącymi mechanizmami (bez zmian w nich)

- **Wyszukiwarka**: sortowanie reorderuje także wiersze ukryte klasą `.is-hidden`; klasa zostaje na węźle, więc filtr nadal działa po posortowaniu.
- **Bulk-select**: stan `checked` i podświetlenie zostają na węzłach po reorderze; `getVisibleCheckboxes()` dalej działa.
- **Zakładki**: każdy panel sortowany niezależnie; przełączenie zakładki nie zmienia sortu drugiej.

### F. CSS — `offer-list.css` (light + dark)

- `.data-table th.sortable` { cursor:pointer; user-select:none; } + `:hover` (akcent).
- `.data-table th.sorted-asc::after { content:' ↑'; }`, `.sorted-desc::after { content:' ↓'; }` z akcentem `#FF8500` (light).
- `.offer-sort-mobile` (flex, widoczny tylko mobile — `display:none` na desktop, `display:flex` w breakpoincie kart), `.offer-sort-select`, `.offer-sort-dir` (≥44px).
- Warianty `[data-theme="dark"]` dla wszystkich powyższych (akcent `#f093fb`, tła/obramowania glassmorphism).

## Pliki do zmiany

| Plik | Zmiana |
|---|---|
| `templates/admin/offers/_list_items.html` | `data-sort-*` na `<tr>` i `.offer-card`; `sortable`/`data-sort-key`/`data-sort-type` na `<th>`; kontroler mobilny nad kartami |
| `static/js/pages/admin/offer-list.js` | `initializeOfferSort()`: komparator, `applySort`, listenery nagłówków i kontrolera mobilnego |
| `static/css/pages/admin/offer-list.css` | `.sortable`/`.sorted-asc`/`.sorted-desc` + style kontrolera mobilnego (light + dark) |

## Poza zakresem (YAGNI)

- Bez zmian w bazie / route / modelach.
- Bez persystencji sortu między sesjami / w localStorage.
- Bez „powrotu do domyślnego" przez klik (świadomy wybór toggle, nie 3-stanowego).
- Bez sortowania kolumn Akcje / checkbox.

## Testowanie

- Lokalnie (`http://localhost:5001`): klik w każdy sortowalny nagłówek → rosnąco, ponowny → malejąco; strzałka ↑/↓ na aktywnej kolumnie.
- Daty: poprawna chronologia; strony bez daty (`—`/„Bez limitu") na końcu w obu kierunkach.
- Status: kolejność wg priorytetu (active najpierw przy rosnąco).
- Niezależność zakładek (sort w „Bieżące" nie rusza „Zamknięte").
- Mobile: kontroler nad kartami sortuje karty; przycisk kierunku działa; touch ≥44px.
- Współpraca: po sortowaniu wyszukiwarka nadal filtruje; zaznaczenia bulk zachowane; przełączanie zakładek OK.
- Light i dark mode; desktop i mobile.
