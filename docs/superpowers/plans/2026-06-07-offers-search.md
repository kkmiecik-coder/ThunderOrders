# Szukajka na liście stron sprzedaży — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać na `/admin/offers` pole, które na żywo filtruje już wyrenderowane strony sprzedaży po nazwie (klient-side, bez przeładowania i bez API).

**Architecture:** Każda karta mobile i wiersz tabeli dostaje `data-search-name`. Nowa funkcja JS na `input` chowa/pokazuje elementy klasą `.is-hidden`, a przy zerowych trafieniach pokazuje komunikat i chowa oba kontenery list. Zero zmian w bazie, modelu i routcie → brak migracji.

**Tech Stack:** Jinja2 (template), vanilla JS (`offer-list.js`), CSS z light+dark mode (`offer-list.css`).

**Uwaga o testach:** Projekt nie ma frameworka testów JS (tylko testy Pythona, a ta zmiana ich nie dotyka). Zgodnie z YAGNI nie wprowadzamy frameworka pod jeden filtr — weryfikacja odbywa się w przeglądarce (Task 4, skill `webapp-testing` / Playwright na `http://localhost:5001`).

---

## File Structure

- **Modify:** `templates/admin/offers/list.html` — pasek szukajki + komunikat braku wyników + `data-search-name` na kartach i wierszach.
- **Modify:** `static/css/pages/admin/offer-list.css` — style paska, komunikatu, `.is-hidden` (light + dark).
- **Modify:** `static/js/pages/admin/offer-list.js` — funkcja `initializeOfferSearch()` + wpięcie do `DOMContentLoaded`.

Struktura DOM strony (dla orientacji): wewnątrz `.offer-page` są kolejno `.page-header`, `.stats-row` (kończy się ~linia 53), potem blok `{% if pages %}` z `.offer-cards-mobile` (~57–196), a potem `.table-container` (~199–439) z tabelą lub pustym stanem. Pasek szukajki wstawiamy między `.stats-row` a `.offer-cards-mobile`.

---

## Task 1: HTML — pasek szukajki, komunikat, atrybuty filtrowania

**Files:**
- Modify: `templates/admin/offers/list.html`

- [ ] **Step 1: Wstaw pasek szukajki i kontener komunikatu**

W `templates/admin/offers/list.html` znajdź koniec bloku `.stats-row` (linia 53 `</div>`) i następujący po nim komentarz `<!-- Mobile Cards -->` (linia 55). Wstaw między nie nowy blok:

```html
    </div>

    <!-- Search -->
    {% if pages %}
    <div class="offer-search-bar">
        <svg class="offer-search-icon" width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/>
        </svg>
        <input type="text" id="offerSearchInput" class="offer-search-input"
               placeholder="Szukaj strony po nazwie..." autocomplete="off">
    </div>
    <div class="offer-search-empty is-hidden" id="offerSearchEmpty"></div>
    {% endif %}

    <!-- Mobile Cards -->
```

(Pierwsza linia `</div>` powyżej to zamknięcie istniejącego `.stats-row` — nie dubluj go; ma jedynie pokazać kontekst wstawienia.)

- [ ] **Step 2: Dodaj `data-search-name` na karcie mobile**

Znajdź `<div class="offer-card">` (linia ~59) i zamień na:

```html
        <div class="offer-card" data-search-name="{{ page.name }}">
```

- [ ] **Step 3: Dodaj `data-search-name` na wierszu tabeli**

W `<tbody>` tabeli znajdź `{% for page in pages %}` (linia ~217) i następujący po nim `<tr>` (linia ~218). Zamień ten `<tr>` na:

```html
                    <tr data-search-name="{{ page.name }}">
```

(Jinja autoescapuje wartość atrybutu, więc cudzysłowy/znaki w nazwie są bezpieczne. Normalizację — lowercase, usuwanie ogonków — robi JS po obu stronach porównania, więc tu zostawiamy surowe `{{ page.name }}`.)

- [ ] **Step 4: Sprawdź spójność szablonu**

Run: `python -c "import jinja2; jinja2.Environment().parse(open('templates/admin/offers/list.html').read())"`
Expected: brak wyjątku (szablon parsuje się poprawnie).

- [ ] **Step 5: Commit**

```bash
git add templates/admin/offers/list.html
git commit -m "feat(offers): pasek szukajki i data-search-name na liście stron"
```

---

## Task 2: CSS — style paska, komunikatu, `.is-hidden` (light + dark)

**Files:**
- Modify: `static/css/pages/admin/offer-list.css`

- [ ] **Step 1: Dopisz style na końcu pliku**

Dopisz na końcu `static/css/pages/admin/offer-list.css` (po ostatniej regule):

```css

/* ===== Szukajka stron sprzedaży ===== */
.offer-search-bar {
    position: relative;
    margin-bottom: var(--space-4);
}

.offer-search-icon {
    position: absolute;
    left: var(--space-3);
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-secondary);
    pointer-events: none;
}

.offer-search-input {
    width: 100%;
    padding: var(--space-3) var(--space-3) var(--space-3) calc(var(--space-3) + 26px);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    font-size: var(--text-base);
    background: var(--bg-primary);
    color: var(--text-primary);
    transition: border-color 0.2s, box-shadow 0.2s;
}

.offer-search-input:focus {
    outline: none;
    border-color: var(--primary-color);
    box-shadow: 0 0 0 3px rgba(255, 133, 0, 0.1);
}

.offer-search-empty {
    padding: var(--space-6);
    text-align: center;
    color: var(--text-secondary);
    font-size: var(--text-base);
}

/* Współdzielona klasa ukrywania (filtr) */
.is-hidden {
    display: none !important;
}

/* Dark mode */
[data-theme="dark"] .offer-search-input {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(240, 147, 251, 0.2);
    color: #ffffff;
}

[data-theme="dark"] .offer-search-input::placeholder {
    color: rgba(255, 255, 255, 0.4);
}

[data-theme="dark"] .offer-search-input:focus {
    border-color: #f093fb;
    box-shadow: 0 0 0 3px rgba(240, 147, 251, 0.15);
    background: rgba(255, 255, 255, 0.08);
}

[data-theme="dark"] .offer-search-icon {
    color: rgba(255, 255, 255, 0.5);
}

[data-theme="dark"] .offer-search-empty {
    color: rgba(255, 255, 255, 0.6);
}
```

(`display: none !important` jest celowe — `.offer-cards-mobile` i `.table-container` mają reguły `display` w media queries; bez `!important` `.is-hidden` mogłoby nie nadpisać widoczności na niektórych breakpointach.)

- [ ] **Step 2: Sprawdź brak literówek w nazwach klas**

Run: `grep -c "offer-search-input\|offer-search-empty\|offer-search-icon\|is-hidden" static/css/pages/admin/offer-list.css`
Expected: liczba >= 8 (każda klasa pojawia się w light i/lub dark mode).

- [ ] **Step 3: Commit**

```bash
git add static/css/pages/admin/offer-list.css
git commit -m "style(offers): style szukajki i komunikatu braku wyników (light+dark)"
```

---

## Task 3: JS — funkcja filtrująca

**Files:**
- Modify: `static/js/pages/admin/offer-list.js`

- [ ] **Step 1: Wepnij inicjalizację do `DOMContentLoaded`**

W `static/js/pages/admin/offer-list.js` znajdź blok (linie ~6–11):

```javascript
document.addEventListener('DOMContentLoaded', function() {
    initializeOfferTabs();
    initializeSettingsTabs(); // Left sidebar tabs in settings panel
    initializeCustomSelects();
    initializeAutoIncreaseForm();
    initializeDeleteForm();
    initializePaymentReminders();
});
```

Dodaj wywołanie `initializeOfferSearch();` na końcu listy:

```javascript
document.addEventListener('DOMContentLoaded', function() {
    initializeOfferTabs();
    initializeSettingsTabs(); // Left sidebar tabs in settings panel
    initializeCustomSelects();
    initializeAutoIncreaseForm();
    initializeDeleteForm();
    initializePaymentReminders();
    initializeOfferSearch();
});
```

- [ ] **Step 2: Dopisz funkcję na końcu pliku**

Dopisz na końcu `static/js/pages/admin/offer-list.js`:

```javascript

/**
 * Live-filtr listy stron sprzedaży po nazwie.
 * Chowa/pokazuje już wyrenderowane karty mobile i wiersze tabeli.
 * Guard: jeśli na stronie nie ma pola szukajki, nic nie robi.
 */
function initializeOfferSearch() {
    const input = document.getElementById('offerSearchInput');
    if (!input) return;

    const emptyMessage = document.getElementById('offerSearchEmpty');
    const containers = document.querySelectorAll('.offer-cards-mobile, .table-container');
    const items = document.querySelectorAll('[data-search-name]');

    // lowercase + usunięcie polskich ogonków, żeby "lacie" znajdowało "Łacie"
    const normalize = (str) => (str || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/\p{Diacritic}/gu, '')
        .trim();

    input.addEventListener('input', function() {
        const query = normalize(input.value);
        let visibleCount = 0;

        items.forEach(item => {
            const name = normalize(item.getAttribute('data-search-name'));
            const matches = query === '' || name.includes(query);
            item.classList.toggle('is-hidden', !matches);
            if (matches) visibleCount++;
        });

        const noResults = query !== '' && visibleCount === 0;
        containers.forEach(c => c.classList.toggle('is-hidden', noResults));

        if (emptyMessage) {
            emptyMessage.classList.toggle('is-hidden', !noResults);
            if (noResults) {
                emptyMessage.textContent = `Brak stron pasujących do „${input.value.trim()}"`;
            }
        }
    });
}
```

- [ ] **Step 3: Sprawdź poprawność składni JS**

Run: `node --check static/js/pages/admin/offer-list.js`
Expected: brak outputu, exit 0 (składnia OK).

- [ ] **Step 4: Commit**

```bash
git add static/js/pages/admin/offer-list.js
git commit -m "feat(offers): live-filtr listy stron sprzedaży po nazwie"
```

---

## Task 4: Weryfikacja w przeglądarce

**Files:** brak (weryfikacja manualna/Playwright).

**Sub-skill:** użyj `webapp-testing` (Playwright). Aplikacja musi działać na `http://localhost:5001` (uruchom lokalny serwer Flask, jeśli nie działa). Zaloguj się do panelu admina i wejdź na `/admin/offers`. Na liście musi być co najmniej kilka stron o różnych nazwach (najlepiej jedna z polskim znakiem, np. zawierająca „ł").

- [ ] **Step 1: Filtrowanie pozytywne**

Wpisz w pole `#offerSearchInput` fragment nazwy jednej ze stron.
Expected: widoczne tylko strony zawierające ten fragment; reszta zniknęła (zarówno w widoku desktop, jak i po zwężeniu okna do mobile).

- [ ] **Step 2: Ignorowanie wielkości liter i ogonków**

Wpisz ten sam fragment wielkimi literami oraz wersję bez ogonka (np. `lacie` dla nazwy z „Łacie").
Expected: te same wyniki co w kroku 1 — wielkość liter i ogonki nie mają znaczenia.

- [ ] **Step 3: Brak wyników**

Wpisz frazę, która nie pasuje do żadnej strony (np. `zzzzz`).
Expected: lista znika, pojawia się komunikat `Brak stron pasujących do „zzzzz"` z wpisaną frazą.

- [ ] **Step 4: Reset**

Wyczyść pole.
Expected: wszystkie strony wracają, komunikat braku wyników znika.

- [ ] **Step 5: Dark mode**

Przełącz motyw na dark (`[data-theme="dark"]`).
Expected: pole szukajki i komunikat mają poprawne tła/obramowania/akcenty (różowy `#f093fb` na focusie, czytelny tekst); brak białego pola na ciemnym tle.

- [ ] **Step 6: Brak regresji konsoli**

Sprawdź konsolę przeglądarki na `/admin/offers`.
Expected: brak nowych błędów JS związanych z `initializeOfferSearch`.

---

## Self-review (autor planu)

- **Pokrycie spec:** pasek pod statystykami (Task 1 Step 1) ✓; `data-search-name` na obu reprezentacjach (Task 1 Step 2–3) ✓; normalizacja ogonków/wielkości liter (Task 3) ✓; komunikat braku wyników z frazą (Task 3 + Task 1) ✓; light+dark (Task 2) ✓; brak migracji/route/API ✓; pominięcia YAGNI (liczniki, debounce, localStorage) — nieuwzględnione celowo, zgodnie ze spec ✓.
- **Placeholdery:** brak — każdy krok ma konkretny kod/komendę.
- **Spójność nazw:** `offerSearchInput`, `offerSearchEmpty`, `offer-search-bar/input/icon/empty`, `is-hidden`, `data-search-name`, `initializeOfferSearch` — użyte identycznie w HTML, CSS i JS.
