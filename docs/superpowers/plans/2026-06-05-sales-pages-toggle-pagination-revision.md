# Rewizja: jednolita paginacja per zakładka z cache stanu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Zastąpić hybrydowy mechanizm (SSR bufor dla bieżących + `limit=100` dla zakładek) jednolitym modelem paginacji per zakładka: pierwsze 5 + „Pokaż więcej" po 5, z cache zapamiętującym liczbę rozłożonych stron (`shownCount`). JS renderuje obie zakładki od startu (loading state); backend dostarcza tylko flagi widoczności.

**Dlaczego:** Poprzednie podejście gubiło stan paginacji — przełączenie zakładki pokazywało wszystkie strony (`limit=100`) zamiast zapamiętanej liczby, a zamknięte nie miały „Pokaż więcej". Zgłoszone przez użytkownika.

**Tech Stack:** Flask/Jinja2, vanilla JS (fetch), CSS. Brak zmian w bazie.

---

## Docelowy model stanu (JS, w IIFE "EXCLUSIVE PAGES - LAZY LOADING")

```javascript
let activeFilter = 'current';
const PAGE_SIZE = 5;
const tabCache = {
    current: { pages: [], shownCount: 0, total: null, initialized: false },
    closed:  { pages: [], shownCount: 0, total: null, initialized: false }
};
```
- `pages` — wszystkie dotąd pobrane strony zakładki (rosnie przy „Pokaż więcej").
- `shownCount` — ile stron jest aktualnie rozłożonych (renderowanych).
- `total` — ile jest wszystkich stron zakładki (z API `data.total`).
- `initialized` — czy zakładka była już raz pobrana.

Reguły:
- **ensureTab(filter)**: jeśli `!initialized` → loading + fetch `offset=0, limit=5`, zapisz `pages`, `total`, `shownCount=pages.length`, `initialized=true`.
- **renderActive()**: `renderPages(cache.pages.slice(0, cache.shownCount))`; `syncShowMore(cache.total, cache.shownCount)`.
- **switchTab(filter)**: ustaw aktywny + aria; `await ensureTab(filter)` (z guardem stale-response); `renderActive()`.
- **loadMore()** (obie zakładki): jeśli `pages.length > shownCount` (mamy zapas) → `shownCount = min(shownCount+5, pages.length)`; w przeciwnym razie fetch `offset=pages.length, limit=5`, dopisz do `pages`, zwiększ `shownCount` o pobraną liczbę; potem `renderActive()`. (Tu zapas zawsze 0 — pobieramy dokładnie tyle ile pokazujemy — więc praktycznie zawsze fetch; logika „zapasu" zostaje na wypadek przyszłego prefetchu, ale można pominąć i zawsze fetchować po 5.)
- **Start (DOMContentLoaded)**: jeśli widget istnieje (`tableBody`), `switchTab` nie odpala (to ten sam filtr) — zamiast tego wywołaj `ensureTab('current').then(renderActive)` jawnie przy inicjalizacji.

---

## Task R1: Backend — `dashboard()` tylko flagi widoczności

**Files:** Modify `modules/client/routes.py` — `dashboard()`.

- [ ] **Step 1:** W `dashboard()` uprość słownik `offer_pages`. Po `sort_offer_pages(offer_pages_all)` (zostaw sortowanie i `check_and_update_status`), zastąp blok `_has_sets` + `current_pages`/`offer_pages` tym:

```python
    # JS renderuje obie zakładki przez API; tutaj liczymy tylko flagi widoczności.
    has_current = any(p.status in ('scheduled', 'active', 'paused') for p in offer_pages_all)
    has_closed = any(p.status == 'ended' for p in offer_pages_all)

    offer_pages = {
        'has_any': len(offer_pages_all) > 0,
        'has_current': has_current,
        'has_closed': has_closed,
    }
```
Usuń pre-compute `_has_sets` w `dashboard()` (API liczy `has_sets` samodzielnie w serializacji). NIE zmieniaj `get_offer_pages()` — ono już paginuje poprawnie z `?filter`.

- [ ] **Step 2:** `python -m py_compile modules/client/routes.py && echo OK`
- [ ] **Step 3:** Commit: `refactor(client): dashboard liczy tylko flagi widoczności widgetu stron`

---

## Task R2: Szablon — usuń SSR wiersze/bufor, dodaj loading state

**Files:** Modify `templates/client/dashboard.html` (offer widget).

- [ ] **Step 1:** W `<tbody id="offersTableBody">` usuń obie pętle `{% for page in offer_pages.visible %}...{% endfor %}` i `{% for page in offer_pages.buffer %}...{% endfor %}`. Zostaw pusty wiersz stanu `.offer-empty-row` (ukryty domyślnie) ORAZ dodaj wiersz loading:
```html
                    <tbody id="offersTableBody">
                        {# Loading — widoczny do pierwszego renderu JS #}
                        <tr class="offer-loading-row">
                            <td colspan="5" class="offer-loading-cell">
                                <span class="offer-spinner"></span>
                                <span class="offer-loading-text">Ładowanie stron…</span>
                            </td>
                        </tr>
                        {# Pusty stan zakładki — sterowany przez JS #}
                        <tr class="offer-empty-row" style="display: none;">
                            <td colspan="5" class="offer-empty-cell">
                                <span class="offer-empty-text">Brak bieżących stron sprzedaży</span>
                            </td>
                        </tr>
                    </tbody>
```

- [ ] **Step 2:** W `<div class="offer-cards offer-mobile" id="offersCardsBody">` usuń obie pętle for. Dodaj loading + zostaw empty:
```html
                <div class="offer-cards offer-mobile" id="offersCardsBody">
                    {# Loading mobile #}
                    <div class="offer-card-loading">
                        <span class="offer-spinner"></span>
                        <span class="offer-loading-text">Ładowanie stron…</span>
                    </div>
                    {# Pusty stan mobile — sterowany przez JS #}
                    <div class="offer-card-empty" style="display: none;">
                        <span class="offer-empty-text">Brak bieżących stron sprzedaży</span>
                    </div>
                </div>
```

- [ ] **Step 3:** Zastąp warunkowy blok „Pokaż więcej" — usuń `{% if offer_pages.remaining > 0 %}` warunek i `data-*` zależne od SSR. Renderuj kontener zawsze (ukryty domyślnie, JS steruje):
```html
                <div class="offer-show-more" id="offersShowMore" style="display: none;">
                    <button type="button" class="show-more-btn" id="offersLoadMoreBtn">Pokaż więcej →</button>
                </div>
```

- [ ] **Step 4:** Warunek widoczności widgetu pozostaje `{% if offer_pages.has_any %}` (bez zmian).

- [ ] **Step 5:** Sanity-check tagów (zbalansowane). Commit: `feat(client): pusty tbody + loading state w widgecie stron (render po stronie JS)`

---

## Task R3: JS — jednolita paginacja per zakładka z cache shownCount

**Files:** Modify `static/js/pages/client/dashboard.js` (IIFE "EXCLUSIVE PAGES - LAZY LOADING").

Zastąp CAŁĄ logikę stanu/paginacji w tej IIFE (od deklaracji `currentOffset`/`isLoading`/`tabCache` przez `switchTab`, `fetchMorePages`, `updateButtonText`, handler `loadMoreBtn`) nowym, jednolitym modelem. Zachowaj BEZ ZMIAN: `createTableRowHTML`, `createCardHTML`, `getStatusHTML`, `renderPages` (z drobną korektą: ukrywanie loading), `fetchTabData`, listenery zakładek, `updateOfferTimings` (zewnętrzny scope).

- [ ] **Step 1:** Stan + stałe (zastąp dotychczasowy blok `currentOffset`/`isLoading`/`tabCache`):
```javascript
        if (!tableBody) return;

        const PAGE_SIZE = 5;
        let isLoading = false;
        let activeFilter = 'current';
        const tabCache = {
            current: { pages: [], shownCount: 0, total: null, initialized: false },
            closed:  { pages: [], shownCount: 0, total: null, initialized: false }
        };
```

- [ ] **Step 2:** `renderPages` — ukryj loading na czas renderu. Na początku funkcji (po pobraniu emptyRow/emptyCard) dodaj usunięcie/ukrycie loading:
```javascript
            const loadingRow = tableBody.querySelector('.offer-loading-row');
            const loadingCard = cardsBody ? cardsBody.querySelector('.offer-card-loading') : null;
            if (loadingRow) loadingRow.style.display = 'none';
            if (loadingCard) loadingCard.style.display = 'none';
```
Reszta `renderPages` bez zmian (czyści `tr` poza empty/loading — UWAGA: pętla czyszcząca usuwa wszystkie `tr` poza `.offer-empty-row`; dodaj wyjątek dla `.offer-loading-row` żeby go nie usuwać, tylko ukrywać):
```javascript
            tableBody.querySelectorAll('tr').forEach(tr => {
                if (!tr.classList.contains('offer-empty-row') &&
                    !tr.classList.contains('offer-loading-row')) tr.remove();
            });
```
Analogicznie dla kart: usuwając `.offer-card` nie ruszamy `.offer-card-loading`/`.offer-card-empty` (różne klasy — już OK).

- [ ] **Step 3:** Funkcja pokazująca loading (przed ensureTab):
```javascript
        function showLoading() {
            const loadingRow = tableBody.querySelector('.offer-loading-row');
            const loadingCard = cardsBody ? cardsBody.querySelector('.offer-card-loading') : null;
            const emptyRow = tableBody.querySelector('.offer-empty-row');
            const emptyCard = cardsBody ? cardsBody.querySelector('.offer-card-empty') : null;
            tableBody.querySelectorAll('tr').forEach(tr => {
                if (!tr.classList.contains('offer-empty-row') &&
                    !tr.classList.contains('offer-loading-row')) tr.remove();
            });
            if (cardsBody) cardsBody.querySelectorAll('.offer-card').forEach(c => c.remove());
            if (emptyRow) emptyRow.style.display = 'none';
            if (emptyCard) emptyCard.style.display = 'none';
            if (loadingRow) loadingRow.style.display = '';
            if (loadingCard) loadingCard.style.display = '';
        }
```

- [ ] **Step 4:** `syncShowMore` — zostaw, ale upewnij się że działa z nowym kontenerem (zawsze w DOM). Wersja:
```javascript
        function syncShowMore(total, shownCount) {
            if (!showMoreContainer || !loadMoreBtn) return;
            const remaining = Math.max(0, (total || 0) - shownCount);
            if (remaining <= 0) {
                showMoreContainer.style.display = 'none';
            } else {
                showMoreContainer.style.display = '';
                loadMoreBtn.textContent = `Pokaż ${Math.min(remaining, PAGE_SIZE)} więcej →`;
                loadMoreBtn.disabled = false;
            }
        }
```

- [ ] **Step 5:** `ensureTab`, `renderActive`, `switchTab`, `loadMore` (zastąp stare `switchTab`/`fetchMorePages`/`updateButtonText`):
```javascript
        // Pobiera pierwsze PAGE_SIZE stron zakładki przy pierwszym wejściu.
        async function ensureTab(filter) {
            const cache = tabCache[filter];
            if (cache.initialized) return;
            showLoading();
            const data = await fetchTabData(filter, 0, PAGE_SIZE);
            if (activeFilter !== filter) return;       // stale guard
            cache.pages = data ? data.pages.slice() : [];
            cache.total = data ? data.total : cache.pages.length;
            cache.shownCount = cache.pages.length;
            cache.initialized = true;
        }

        function renderActive() {
            const cache = tabCache[activeFilter];
            renderPages(cache.pages.slice(0, cache.shownCount));
            syncShowMore(cache.total, cache.shownCount);
        }

        async function switchTab(filter) {
            if (filter === activeFilter) return;
            activeFilter = filter;
            document.querySelectorAll('.offer-filter-tab').forEach(btn => {
                const isActive = btn.dataset.filter === filter;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            await ensureTab(filter);
            if (activeFilter !== filter) return;        // stale guard
            renderActive();
        }

        async function loadMore() {
            if (isLoading) return;
            const cache = tabCache[activeFilter];
            const filterAtStart = activeFilter;
            // Mamy zapas w cache? pokaż bez fetcha.
            if (cache.pages.length > cache.shownCount) {
                cache.shownCount = Math.min(cache.shownCount + PAGE_SIZE, cache.pages.length);
                renderActive();
                return;
            }
            // Brak zapasu — dociągnij kolejne PAGE_SIZE.
            isLoading = true;
            if (loadMoreBtn) { loadMoreBtn.disabled = true; loadMoreBtn.textContent = 'Ładowanie…'; }
            const data = await fetchTabData(activeFilter, cache.pages.length, PAGE_SIZE);
            isLoading = false;
            if (activeFilter !== filterAtStart) return; // stale guard
            if (data && data.pages.length) {
                cache.pages.push(...data.pages);
                cache.total = data.total;
                cache.shownCount = cache.pages.length;
            }
            renderActive();
        }
```

- [ ] **Step 6:** Listenery + inicjalizacja przy starcie (zastąp stary handler `loadMoreBtn` i wiązanie zakładek):
```javascript
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', (e) => { e.preventDefault(); loadMore(); });
        }
        document.querySelectorAll('.offer-filter-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.filter));
        });

        // Start: renderuj domyślną zakładkę (bieżące) z loading state.
        ensureTab('current').then(() => { if (activeFilter === 'current') renderActive(); });
```

- [ ] **Step 7:** Usuń martwy kod, który został zastąpiony: stara `fetchMorePages`, `updateButtonText`, stary handler `loadMoreBtn`, odwołania do `currentOffset`/`.offer-buffered`. Sprawdź: `grep -n "offer-buffered\|fetchMorePages\|updateButtonText\|currentOffset\|limit=100" static/js/pages/client/dashboard.js` → oczekiwane brak trafień w tej IIFE.

- [ ] **Step 8:** `node --check static/js/pages/client/dashboard.js && echo OK`. Commit: `feat(client): jednolita paginacja per zakładka z cache shownCount i loading`

---

## Task R4: CSS — spinner / loading state (light + dark)

**Files:** Modify `static/css/pages/client/dashboard.css` (sekcja Exclusive Pages Widget).

- [ ] **Step 1:** Dodaj style loading (po stylach pustego stanu). Light + dark:
```css
/* Loading state widgetu stron */
.offer-loading-cell,
.offer-card-loading {
    text-align: center;
    padding: var(--space-8) var(--space-4);
}

.offer-loading-text {
    color: var(--text-secondary);
    font-size: var(--text-sm);
    margin-left: var(--space-2);
    vertical-align: middle;
}

.offer-spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid var(--gray-200);
    border-top-color: #FF8500;
    border-radius: 50%;
    vertical-align: middle;
    animation: offer-spin 0.7s linear infinite;
}

@keyframes offer-spin {
    to { transform: rotate(360deg); }
}

[data-theme="dark"] .offer-spinner {
    border: 2px solid rgba(255, 255, 255, 0.15);
    border-top-color: #f093fb;
}

[data-theme="dark"] .offer-loading-text {
    color: rgba(255, 255, 255, 0.6);
}
```
(Jeśli `--gray-200`/`--space-2` nie istnieją, podstaw najbliższe istniejące — zweryfikuj grepem.)

- [ ] **Step 2:** Grep markerów. Commit: `style(client): spinner i loading state widgetu stron (light + dark)`

---

## Self-Review (autor planu)

- Stan paginacji per zakładka (`shownCount`) zapamiętany — switch tam-z-powrotem zachowuje liczbę rozłożonych ✓
- Obie zakładki: 5 + „Pokaż więcej" po 5 ✓
- JS renderuje od startu, loading state ✓
- Backend tylko flagi ✓
- `dashboard()` nie renderuje SSR wierszy; szablon pusty tbody + loading ✓
- Stale-guardy w ensureTab/switchTab/loadMore ✓
- Brak `limit=100`, brak bufora DOM ✓
- Identifiers spójne: PAGE_SIZE, tabCache shape, ensureTab/renderActive/switchTab/loadMore ✓
