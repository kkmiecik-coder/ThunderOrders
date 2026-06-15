# Sortowanie listy `/admin/offers` przez klik w nagłówki — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać sortowanie listy stron sprzedaży przez klik w nagłówki kolumn (toggle rosnąco/malejąco), 1:1 z mechanizmem ze strony `stock-orders`, zawężone do tabeli klikniętego nagłówka (bo obie zakładki są w DOM).

**Architecture:** Czysto front-end. Makro `offer_table` dostaje na `<tr>` atrybuty `data-*` (daty jako `.timestamp()`), a sortowalne `<th>` klasę `sortable` + `data-column` + inline `onclick="sortTable('X', this)"`. Globalna funkcja `sortTable(column, thEl)` w `offer-list.js` (poziom modułu, jak `stock-orders.js`) sortuje wiersze `this.closest('table')`, trzymając stan per `<table>`. CSS wskaźnika `⇅`/`↑`/`↓` skopiowany ze `stock-orders.css` (light + dark).

**Tech Stack:** Jinja2 makra, vanilla JS (klasyczny skrypt, nie module/IIFE — top-level funkcje są globalne), CSS custom properties. Bez zmian w bazie / route / Pythonie / testach pytest.

---

## Kontekst dla wykonawcy

- Wzorzec do odwzorowania żyje w: `static/js/pages/admin/stock-orders.js` (funkcja `sortTable`, linie 1-78), `templates/admin/warehouse/stock_orders.html` (nagłówki `<th class="sortable" data-column=... onclick=...>` i `<tr data-...>`), `static/css/pages/admin/stock-orders.css` (linie ~305-340, 1140-1141).
- Plik makr ofert: `templates/admin/offers/_list_items.html` — makro `offer_table(pages, tab_id)` zawiera `<thead>` (10 kolumn) i pętlę `{% for page in pages %}<tr data-search-name="{{ page.name }}">...</tr>{% endfor %}`.
- `offer-list.js` NIE jest owinięty w IIFE — ma blok `DOMContentLoaded` na górze, a niżej top-level deklaracje funkcji. Dodanie `function sortTable(...)` na poziomie modułu czyni ją globalną (dostępną dla inline `onclick`), dokładnie jak w `stock-orders.js`.
- `offer-list.css` jest ładowany na stronie listy ofert; `stock-orders.css` NIE — dlatego CSS wskaźnika trzeba dodać do `offer-list.css`.
- Sortowalna tabela ma klasę `data-table offer-table`. Reguły CSS zawęzić do `.offer-table`.
- Strona ma dwie tabele w DOM (panele `#tab-current`, `#tab-closed`), oba z tym samym `<thead>` z makra → `data-column` powtarza się; zawężenie po `this.closest('table')` jest konieczne.

Brak testów pytest dla tej zmiany (czysty DOM/JS; w repo nie ma runnera JS). Weryfikacja: składnia JS (`node --check`), kompilacja szablonu, oraz manualnie w przeglądarce.

---

## Task 1: Atrybuty `data-*` na wierszu + sortowalne nagłówki (makro `offer_table`)

**Files:**
- Modify: `templates/admin/offers/_list_items.html` — makro `offer_table` (`<thead>` i otwarcie `<tr>` w pętli)

- [ ] **Step 1: Dodaj atrybuty `data-*` do `<tr>`**

W makrze `offer_table`, znajdź otwarcie wiersza w pętli:
```jinja
                {% for page in pages %}
                <tr data-search-name="{{ page.name }}">
```
Zamień otwarcie `<tr ...>` na (zachowaj `data-search-name`, dodaj pozostałe):
```jinja
                {% for page in pages %}
                <tr data-search-name="{{ page.name }}"
                    data-name="{{ page.name }}"
                    data-ptype="{{ page.page_type }}"
                    data-shipping="{{ 'proxy' if page.payment_stages == 4 else 'polska' }}"
                    data-status="{{ page.status }}"
                    data-created="{{ page.created_at.timestamp() if page.created_at else 0 }}"
                    data-starts="{{ page.starts_at.timestamp() if page.starts_at else 0 }}"
                    data-ends="{{ page.ends_at.timestamp() if page.ends_at else 0 }}"
                    data-deadline="{{ page.payment_deadline.timestamp() if page.payment_deadline else 0 }}">
```

- [ ] **Step 2: Oznacz sortowalne nagłówki w `<thead>`**

W tym samym makrze, w `<thead>`, zamień obecne `<th>` na wersje sortowalne (kolumny checkbox i Akcje BEZ zmian):
```jinja
                    <th class="offer-checkbox-col">
                        <input type="checkbox" id="selectAll-{{ tab_id }}" class="offer-select-all" aria-label="Zaznacz wszystkie">
                    </th>
                    <th class="sortable" data-column="name" onclick="sortTable('name', this)">Nazwa</th>
                    <th class="sortable" data-column="ptype" onclick="sortTable('ptype', this)">Typ</th>
                    <th class="sortable" data-column="shipping" onclick="sortTable('shipping', this)">Typ wysyłki</th>
                    <th class="sortable" data-column="status" onclick="sortTable('status', this)">Status</th>
                    <th class="sortable" data-column="created" onclick="sortTable('created', this)">Utworzono</th>
                    <th class="sortable" data-column="starts" onclick="sortTable('starts', this)">Rozpoczęcie</th>
                    <th class="sortable" data-column="ends" onclick="sortTable('ends', this)">Zakończenie</th>
                    <th class="sortable" data-column="deadline" onclick="sortTable('deadline', this)">Termin płatności</th>
                    <th>Akcje</th>
```

- [ ] **Step 3: Weryfikacja kompilacji szablonu**

Run: `venv/bin/python -c "from app import create_app; app=create_app(); app.jinja_env.get_template('admin/offers/_list_items.html'); print('OK')"`
Expected: `OK` (ostrzeżenie Sentry/eventlet niezwiązane).

- [ ] **Step 4: Commit**

```bash
git add templates/admin/offers/_list_items.html
git commit -m "feat(admin): atrybuty data-* i sortowalne nagłówki w tabeli stron sprzedaży

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Funkcja `sortTable` w `offer-list.js`

**Files:**
- Modify: `static/js/pages/admin/offer-list.js` (dodać na poziomie modułu, np. zaraz po nagłówkowym komentarzu/przed blokiem `DOMContentLoaded`)

- [ ] **Step 1: Dodaj stałe i funkcję `sortTable` na początku pliku**

Na górze `static/js/pages/admin/offer-list.js`, PO bloku komentarza nagłówkowego (`/** ... */`) a PRZED `document.addEventListener('DOMContentLoaded', ...)`, wstaw:

```javascript
/**
 * Sortowanie tabeli stron sprzedaży — odwzorowanie mechanizmu ze stock-orders.
 * Zawężone do tabeli klikniętego nagłówka (obie zakładki są w DOM jednocześnie).
 * Stan sortowania trzymany per <table> w data-sort-column / data-sort-dir.
 */
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

    // Toggle kierunku; stan per tabela
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

> `sortTable` musi być na poziomie modułu (globalna), bo woła ją inline `onclick` z makra. NIE umieszczać jej wewnątrz `DOMContentLoaded` ani żadnej innej funkcji.

- [ ] **Step 2: Weryfikacja składni**

Run: `node --check static/js/pages/admin/offer-list.js`
Expected: exit 0 (brak wyjścia / brak błędu składni).

- [ ] **Step 3: Commit**

```bash
git add static/js/pages/admin/offer-list.js
git commit -m "feat(admin): sortTable dla listy stron sprzedaży (per-tabela, toggle asc/desc)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: CSS wskaźnika sortowania (light + dark)

**Files:**
- Modify: `static/css/pages/admin/offer-list.css` (dodać przy stylach tabeli ofert; np. po regułach `.offer-table` lub na końcu sekcji tabeli)

- [ ] **Step 1: Dodaj reguły wskaźnika**

W `static/css/pages/admin/offer-list.css` dodaj (wartości skopiowane ze `stock-orders.css`, zakres `.offer-table` by nie ruszać innych tabel):

```css
/* Sortowanie kolumn — wskaźnik jak na stock-orders */
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

.offer-table th.sorted-asc::after {
    content: '↑';
    opacity: 1;
    color: #FF8500;
}

.offer-table th.sorted-desc::after {
    content: '↓';
    opacity: 1;
    color: #FF8500;
}

/* Dark mode */
[data-theme="dark"] .offer-table th.sorted-asc::after,
[data-theme="dark"] .offer-table th.sorted-desc::after {
    color: #f093fb;
}
```

- [ ] **Step 2: Weryfikacja**

Run: `grep -n "offer-table th.sortable\|sorted-asc\|sorted-desc" static/css/pages/admin/offer-list.css`
Expected: pokazuje regułę bazową, oba warianty `sorted-asc`/`sorted-desc` (light) oraz blok `[data-theme="dark"]`.

- [ ] **Step 3: Commit**

```bash
git add static/css/pages/admin/offer-list.css
git commit -m "style(admin): wskaźnik sortowania kolumn stron sprzedaży (light + dark)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Weryfikacja końcowa (manualna w przeglądarce)

- [ ] **Step 1: Sanity automatyczny**

Run: `node --check static/js/pages/admin/offer-list.js && venv/bin/python -c "from app import create_app; app=create_app(); app.jinja_env.get_template('admin/offers/list.html'); print('OK')"`
Expected: `OK`.

- [ ] **Step 2: Scenariusze w przeglądarce (`http://localhost:5001/admin/offers`)**

- Klik w „Nazwa" → alfabetycznie rosnąco (`↑`); ponowny klik → malejąco (`↓`). Bazowo każdy sortowalny nagłówek pokazuje `⇅`.
- „Utworzono"/„Rozpoczęcie"/„Zakończenie"/„Termin płatności" → poprawna chronologia; wiersze bez daty (`0`) na początku przy rosnąco, na końcu przy malejąco.
- „Status" → kolejność wg priorytetu (active, paused, scheduled, draft, ended) przy rosnąco.
- „Typ"/„Typ wysyłki" → alfabetycznie.
- Tylko jedna kolumna naraz ma wskaźnik `↑`/`↓` (po kliku w inną — poprzednia wraca do `⇅`).

- [ ] **Step 3: Niezależność zakładek i współpraca**

- Posortuj w „Bieżące", przełącz na „Zamknięte" → „Zamknięte" zachowuje własny (domyślny) porządek; sort w jednej nie zmienia drugiej. Posortuj „Zamknięte" niezależnie.
- Po sortowaniu wpisz frazę w wyszukiwarkę → filtr nadal działa.
- Zaznacz kilka wierszy, posortuj → zaznaczenia i pasek akcji masowych zachowane.

- [ ] **Step 4: Light/dark + brak błędów**

- Sprawdź light i dark mode (strzałki czytelne; akcent `#FF8500` light / `#f093fb` dark).
- Konsola bez błędów JS (szczególnie: `sortTable is not defined` oznaczałoby, że funkcja nie jest globalna — wróć do Task 2 Step 1).

- [ ] **Step 5: Final commit (jeśli były poprawki)**

```bash
git add -A
git commit -m "test(admin): weryfikacja sortowania kolumn stron sprzedaży"
```

---

## Self-Review (autor planu)

**Spec coverage:**
- `data-*` na `<tr>` (daty jako timestamp, null→0) → Task 1 Step 1 ✓
- Sortowalne `<th>` z `data-column` + inline `onclick` → Task 1 Step 2 ✓
- `sortTable` per-tabela, toggle, status=priorytet, numeric daty, text reszta → Task 2 ✓
- CSS `⇅`/`↑`/`↓` light + dark, zakres `.offer-table` → Task 3 ✓
- Niezależność zakładek, współpraca z search/bulk → Task 4 Step 3 ✓
- Desktop only (brak mobile) → brak zadań mobile (zgodnie ze spec) ✓
- Bez zmian bazy/route/Pythonu → potwierdzone ✓

**Placeholder scan:** Brak TBD/TODO. Każdy krok z kodem ma pełny kod.

**Type/identifier consistency:** `data-column` (`name/ptype/shipping/status/created/starts/ends/deadline`) == klucze `OFFER_COLUMN_TO_DATASET` == sufiksy atrybutów `data-*` na `<tr>` == argumenty `onclick`. `OFFER_NUMERIC_COLUMNS` = cztery kolumny dat. `sortTable(column, thEl)` — sygnatura spójna między Task 1 (onclick) a Task 2 (definicja). Klasy `.sortable`/`.sorted-asc`/`.sorted-desc` spójne między Task 1 (HTML), Task 2 (JS toggluje) i Task 3 (CSS).

**Ryzyko przy wykonaniu:** Najczęstszy błąd — umieszczenie `sortTable` wewnątrz `DOMContentLoaded` (przestaje być globalna → `onclick` rzuca `sortTable is not defined`). Task 2 Step 1 wyraźnie wymaga poziomu modułu.
