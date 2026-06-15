# Sortowanie listy `/admin/offers` przez klik w nagłówki kolumn

**Data:** 2026-06-15
**Strona:** `/admin/offers` (lista stron sprzedaży, po podziale na zakładki Bieżące/Zamknięte)
**Typ zmiany:** Czysto front-end (HTML/Jinja makra + JS + CSS). **Bez zmian w bazie / route / Pythonie.**

## Cel

Sortowanie listy stron sprzedaży po kliknięciu w nagłówek kolumny (rosnąco/malejąco), **dopasowane 1:1 do istniejącego mechanizmu sortowania ze strony zamówień produktów** (`/admin/products/stock-orders`).

## Wzorzec referencyjny: `stock-orders`

Użytkownik wskazał działający mechanizm na `stock-orders` — odwzorowujemy go. Jego cechy (z `static/js/pages/admin/stock-orders.js`, `templates/admin/warehouse/stock_orders.html`, `static/css/pages/admin/stock-orders.css`):

- Nagłówek: `<th class="sortable" data-column="X" onclick="sortTable('X')">Etykieta</th>` (inline `onclick` — świadomie zgodnie z istniejącym wzorcem; spójność z `stock-orders` ma priorytet nad ogólną zasadą separacji JS/HTML).
- Dane na `<tr>`: atrybuty `data-*` (np. `data-status="{{ order.status }}"`, `data-date="{{ order.created_at.timestamp() }}"`). **Daty jako `.timestamp()` (liczba); brak daty → `0`.**
- JS `sortTable(column)`: `COLUMN_TO_DATASET` (mapa kolumna→klucz dataset), `NUMERIC_COLUMNS` (zbiór kolumn liczbowych, w tym daty), toggle `asc`⇄`desc`, aktualizacja wskaźników tylko w obrębie danej tabeli, reorder przez `appendChild`.
- CSS wskaźnika: bazowo `⇅` (opacity 0.3) na każdym `.sortable th`, po sortowaniu `↑`/`↓` (`#FF8500` light, `#f093fb` dark).

## Decyzje (ustalone z użytkownikiem)

1. **Mechanizm: client-side (JS)** w stylu `stock-orders`.
2. **Sortowalne kolumny:** Nazwa, Typ, Typ wysyłki, Status, Utworzono, Rozpoczęcie, Zakończenie, Termin płatności. **Bez** kolumny Akcje i checkboxa.
3. **Cykl klików:** toggle — 1. klik rosnąco, kolejny odwraca kierunek.
4. **Tylko tabela (desktop).** `stock-orders` nie ma sortowania na mobile; karty mobilne na ofertach zachowują domyślny porządek (status + data). (Można dodać kontroler mobilny w przyszłości — poza zakresem tej zmiany.)
5. **Sortowanie po statusie** używa priorytetu (active → paused → scheduled → draft → ended), nie alfabetu — to jedyne świadome odstępstwo od generycznego sortowania `stock-orders` (gdzie status idzie alfabetycznie); priorytet jest bardziej użyteczny i był wcześniej zatwierdzony.
6. **Stan sortowania:** per tabela/zakładka, efemeryczny — reset po przeładowaniu (F5) do domyślnego porządku status+data.

## Adaptacja vs `stock-orders` (różnica strukturalna)

`stock-orders` ma zakładki **server-side** (`?tab=`) → w DOM jest tylko jedna tabela, więc ich `sortTable` może szukać `th` globalnie i trzymać stan w zmiennych modułowych. Strona ofert ma **obie** zakładki w DOM jednocześnie (client-side), więc:

- `onclick` przekazuje element: `onclick="sortTable('starts', this)"`, a funkcja zawęża się do `this.closest('table')`.
- Stan sortowania trzymany **per tabela** w atrybutach na elemencie `<table>` (`data-sort-column`, `data-sort-dir`), nie w zmiennych globalnych — żeby sort w „Bieżące" nie mieszał „Zamknięte".

Reuse rozstrzygnięty technicznie: sorter implementowany **lokalnie w `offer-list.js`** (ta sama konwencja klas/atrybutów/CSS), bez refaktoryzacji działającej produkcyjnie `stock-orders.js` do wspólnego modułu (zbyt ryzykowne dla parytetu).

## Architektura

### A. Atrybuty `data-*` na wierszu — makro `offer_table` (`_list_items.html`)

Na korzeniu każdego `<tr>` (obok istniejącego `data-search-name`) dodać:

| Atrybut | Wartość (Jinja) | Sortowanie |
|---|---|---|
| `data-name` | `{{ page.name }}` | text |
| `data-ptype` | `{{ page.page_type }}` | text |
| `data-shipping` | `{{ 'proxy' if page.payment_stages == 4 else 'polska' }}` | text |
| `data-status` | `{{ page.status }}` | status (priorytet) |
| `data-created` | `{{ page.created_at.timestamp() if page.created_at else 0 }}` | num |
| `data-starts` | `{{ page.starts_at.timestamp() if page.starts_at else 0 }}` | num |
| `data-ends` | `{{ page.ends_at.timestamp() if page.ends_at else 0 }}` | num |
| `data-deadline` | `{{ page.payment_deadline.timestamp() if page.payment_deadline else 0 }}` | num |

> Brak daty → `0` (jak w `stock-orders`): przy rosnąco trafia na początek, przy malejąco na koniec. Świadoma parytetowa decyzja (nie „zawsze na końcu").

Atrybuty tylko na `<tr>` (desktop). Karty mobilne **nie** dostają atrybutów (sort desktop-only).

### B. Nagłówki tabeli — makro `offer_table`

Sortowalne `<th>` otrzymują klasę `sortable`, `data-column` i inline `onclick`:

| Kolumna | `data-column` | onclick |
|---|---|---|
| Nazwa | `name` | `sortTable('name', this)` |
| Typ | `ptype` | `sortTable('ptype', this)` |
| Typ wysyłki | `shipping` | `sortTable('shipping', this)` |
| Status | `status` | `sortTable('status', this)` |
| Utworzono | `created` | `sortTable('created', this)` |
| Rozpoczęcie | `starts` | `sortTable('starts', this)` |
| Zakończenie | `ends` | `sortTable('ends', this)` |
| Termin płatności | `deadline` | `sortTable('deadline', this)` |

Kolumny checkbox i Akcje bez zmian. (Uwaga: ten sam thead jest renderowany dla obu zakładek — `data-column` powtarza się w dwóch tabelach, dlatego zawężamy po `this.closest('table')`.)

### C. Silnik sortujący — `offer-list.js`

Dodać (wzorowane na `stock-orders.js`, zaadaptowane do wielu tabel):

```javascript
const OFFER_COLUMN_TO_DATASET = {
    name: 'name', ptype: 'ptype', shipping: 'shipping', status: 'status',
    created: 'created', starts: 'starts', ends: 'ends', deadline: 'deadline',
};
const OFFER_NUMERIC_COLUMNS = new Set(['created', 'starts', 'ends', 'deadline']);
const OFFER_STATUS_PRIORITY = { active: 0, paused: 1, scheduled: 2, draft: 3, ended: 4 };

function sortTable(column, thEl) {
    const table = thEl.closest('table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Stan per tabela (atrybuty na <table>)
    let dir = 'asc';
    if (table.dataset.sortColumn === column) {
        dir = table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
    }
    table.dataset.sortColumn = column;
    table.dataset.sortDir = dir;

    // Wskaźniki tylko w tej tabeli
    table.querySelectorAll('th.sortable').forEach(h => {
        h.classList.remove('sorted-asc', 'sorted-desc');
        if (h.dataset.column === column) {
            h.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
        }
    });

    const key = OFFER_COLUMN_TO_DATASET[column] || column;
    const isNumeric = OFFER_NUMERIC_COLUMNS.has(column);
    const isStatus = column === 'status';

    rows.sort((a, b) => {
        let av = a.dataset[key] || '';
        let bv = b.dataset[key] || '';
        if (isStatus) {
            av = OFFER_STATUS_PRIORITY[av] ?? 99;
            bv = OFFER_STATUS_PRIORITY[bv] ?? 99;
        } else if (isNumeric) {
            av = parseFloat(av) || 0;
            bv = parseFloat(bv) || 0;
        } else {
            av = av.toLowerCase();
            bv = bv.toLowerCase();
        }
        if (av < bv) return dir === 'asc' ? -1 : 1;
        if (av > bv) return dir === 'asc' ? 1 : -1;
        return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
}
```

`sortTable` musi być w zasięgu globalnym (wołane z inline `onclick`) — zdefiniować na poziomie modułu `offer-list.js` (nie wewnątrz `DOMContentLoaded`), tak jak `stock-orders.js` ma `sortTable` na górze pliku. Inne funkcje wołane z inline `onclick` w `list.html` (np. `changePageStatus`, `openCreateModal`) są w `<script>` w szablonie — `sortTable` umieszczamy w `offer-list.js` na poziomie modułu, co wystarcza dla `onclick`.

### D. Współpraca z istniejącymi mechanizmami (bez zmian w nich)

- **Wyszukiwarka:** reorder dotyczy też wierszy ukrytych `.is-hidden`; klasa zostaje na węźle → filtr działa po sortowaniu.
- **Bulk-select:** stan `checked`/podświetlenie zostają na węzłach po `appendChild`; `getVisibleCheckboxes()` działa dalej.
- **Zakładki:** stan per tabela → sort w jednej zakładce nie rusza drugiej.

### E. CSS — `offer-list.css` (light + dark)

Dodać (zakres `.offer-table` żeby nie ruszać innych tabel), wartości z `stock-orders.css`:

```css
.offer-table th.sortable {
    cursor: pointer;
    user-select: none;
    position: relative;
    padding-right: 24px;
}
.offer-table th.sortable::after {
    content: '⇅';
    position: absolute;
    right: 8px;
    opacity: 0.3;
    font-size: 14px;
}
.offer-table th.sorted-asc::after { content: '↑'; opacity: 1; color: #FF8500; }
.offer-table th.sorted-desc::after { content: '↓'; opacity: 1; color: #FF8500; }

[data-theme="dark"] .offer-table th.sorted-asc::after,
[data-theme="dark"] .offer-table th.sorted-desc::after { color: #f093fb; }
```

(Jeśli `.offer-table th` ma już hover/padding z reguł współdzielonych, nie nadpisywać — dodać tylko brakujące właściwości sortowania. Zweryfikować w implementacji.)

## Pliki do zmiany

| Plik | Zmiana |
|---|---|
| `templates/admin/offers/_list_items.html` | `data-*` na `<tr>`; `sortable`/`data-column`/`onclick` na sortowalnych `<th>` |
| `static/js/pages/admin/offer-list.js` | `sortTable(column, thEl)` + stałe map/priorytetu (poziom modułu) |
| `static/css/pages/admin/offer-list.css` | `.offer-table th.sortable` + wskaźniki `⇅`/`↑`/`↓` (light + dark) |

## Poza zakresem (YAGNI)

- Bez zmian w bazie / route / modelach.
- Bez sortowania na mobile (kartach) — `stock-orders` go nie ma; ewentualnie osobna zmiana w przyszłości.
- Bez persystencji sortu między sesjami.
- Bez „powrotu do domyślnego" przez klik (toggle, nie 3-stanowy).
- Bez refaktoryzacji `stock-orders.js` do wspólnego modułu.

## Testowanie

- Lokalnie (`http://localhost:5001`): klik w każdy sortowalny nagłówek → rosnąco, ponowny → malejąco; wskaźnik `⇅`→`↑`/`↓`.
- Daty (Utworzono/Rozpoczęcie/Zakończenie/Termin): poprawna chronologia po timestamp; brak daty (`0`) na początku przy rosnąco.
- Status: kolejność wg priorytetu (active najpierw rosnąco).
- Tekst (Nazwa/Typ/Typ wysyłki): alfabetycznie, case-insensitive.
- Niezależność zakładek: sort w „Bieżące" nie zmienia „Zamknięte"; każda tabela trzyma własny stan.
- Współpraca: po sortowaniu wyszukiwarka filtruje; zaznaczenia bulk zachowane; przełączanie zakładek OK.
- Light i dark mode (strzałki czytelne, akcent `#FF8500`/`#f093fb`).
