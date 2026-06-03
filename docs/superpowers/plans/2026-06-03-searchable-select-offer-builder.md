# Searchable Select w Offer Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać wyszukiwarkę na górze custom-dropdownu w 3 miejscach offer-buildera (grupa wariantowa w secie, „Produkt – komplet setu", samodzielna sekcja „Grupa wariantowa").

**Architecture:** Samodzielny komponent vanilla-JS (`searchable-select`) jako progressive enhancement nad natywnym `<select class="searchable-select">`. Natywny select zostaje źródłem prawdy (`pointer-events: none`); klik na `.custom-select-display` otwiera panel z inputem wyszukiwarki i listą opcji budowaną na żywo z selecta. Wybór ustawia `select.value` i dispatchuje natywny `change`, więc istniejące handlery i `collectPageData()` działają bez zmian. Cała logika oparta na delegacji zdarzeń na `document` → bezpieczna dla dynamicznie dodawanych sekcji.

**Tech Stack:** Vanilla JS (IIFE, brak zależności), CSS (light + dark mode / glassmorphism), Flask/Jinja2 templates.

**Uwaga o testach:** Projekt nie ma runnera testów JS (brak `package.json`/node_modules). Wprowadzanie toolchaina testowego byłoby scope creepem niezgodnym z konwencją repo. Weryfikacja każdego zadania jest **manualna w przeglądarce** (`http://localhost:5001`, aplikacja uruchamiana przez venv python z `DB_HOST=127.0.0.1`).

**Kluczowe odkrycie:** Każdy z 3 selectów istnieje w DWÓCH miejscach — w szablonach JS (`offer-builder.js`, nowo dodawane sekcje) ORAZ w Jinja (`edit.html`, sekcje wczytywane z zapisanej strony). Oba muszą zostać zaktualizowane.

---

## File Structure

- **Create:** `static/css/components/searchable-select.css` — style panelu, inputu, opcji + reguła `pointer-events`/flex; light + dark mode.
- **Create:** `static/js/components/searchable-select.js` — komponent (delegacja zdarzeń, open/close, filtrowanie, klawiatura, sync display).
- **Modify:** `templates/admin/offers/edit.html` — dołączenie nowego CSS (`extra_css`) i JS (`extra_js`) + dodanie wrapperów/klas w 3 server-renderowanych selectach.
- **Modify:** `static/js/pages/admin/offer-builder.js` — dodanie wrapperów/klas w 3 szablonach HTML (stringi).

Kolejność zadań gwarantuje, że każdy commit jest bezpieczny: CSS i JS dodane przed markupem nie mają na co działać (brak klasy `searchable-select` w DOM), więc nic nie psują; ostatnie zadania aktywują funkcję.

---

## Task 1: Komponent CSS

**Files:**
- Create: `static/css/components/searchable-select.css`
- Modify: `templates/admin/offers/edit.html` (blok `extra_css`, linie 5-7)

- [ ] **Step 1: Utwórz plik CSS**

Utwórz `static/css/components/searchable-select.css` z pełną treścią:

```css
/* Searchable Select component
   Panel + input wyszukiwarki nad natywnym <select class="searchable-select">.
   Bazowe style .custom-select-wrapper / .custom-select-display są w offer-builder.css */

/* Natywny select = ukryty magazyn danych; kliknięcia idą do .custom-select-display */
.custom-select-wrapper select.searchable-select {
    pointer-events: none;
}

/* Wrapper jako element flex w nagłówku karty grupy wariantowej w secie */
.variant-group-header .custom-select-wrapper {
    flex: 1;
    min-width: 0;
}

/* Stan otwarty: obrót chevronu */
.custom-select-wrapper.is-open .custom-select-display svg {
    transform: rotate(180deg);
}

/* Panel */
.searchable-select-panel {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 50;
    display: flex;
    flex-direction: column;
    max-height: 280px;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    overflow: hidden;
}

.searchable-select-search {
    padding: 8px;
    border-bottom: 1px solid #eee;
}

.searchable-select-input {
    width: 100%;
    box-sizing: border-box;
    padding: 8px 10px;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    font-size: 13px;
    color: #374151;
    outline: none;
}

.searchable-select-input:focus {
    border-color: #f093fb;
}

.searchable-select-options {
    list-style: none;
    margin: 0;
    padding: 4px;
    overflow-y: auto;
}

.searchable-select-option {
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
    color: #374151;
    cursor: pointer;
}

.searchable-select-option:hover,
.searchable-select-option.is-highlighted {
    background: #faf5ff;
}

.searchable-select-option.is-selected {
    font-weight: 600;
    color: #f5576c;
}

.searchable-select-empty {
    list-style: none;
    padding: 12px 10px;
    text-align: center;
    font-size: 12px;
    color: #9ca3af;
}

/* Dark mode */
[data-theme="dark"] .searchable-select-panel {
    background: rgba(30, 20, 40, 0.98);
    backdrop-filter: blur(12px);
    border-color: rgba(240, 147, 251, 0.25);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}

[data-theme="dark"] .searchable-select-search {
    border-bottom-color: rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .searchable-select-input {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.2);
    color: #ffffff;
}

[data-theme="dark"] .searchable-select-input:focus {
    border-color: rgba(240, 147, 251, 0.5);
}

[data-theme="dark"] .searchable-select-option {
    color: rgba(255, 255, 255, 0.9);
}

[data-theme="dark"] .searchable-select-option:hover,
[data-theme="dark"] .searchable-select-option.is-highlighted {
    background: rgba(255, 255, 255, 0.08);
}

[data-theme="dark"] .searchable-select-option.is-selected {
    color: #f093fb;
}

[data-theme="dark"] .searchable-select-empty {
    color: rgba(255, 255, 255, 0.5);
}
```

- [ ] **Step 2: Dołącz CSS w edit.html**

W `templates/admin/offers/edit.html` zamień blok (linie 5-7):

```html
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/offer-builder.css') }}">
{% endblock %}
```

na:

```html
{% block extra_css %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/admin/offer-builder.css') }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/components/searchable-select.css') }}">
{% endblock %}
```

- [ ] **Step 3: Weryfikacja manualna**

Uruchom aplikację (`http://localhost:5001`), otwórz edycję dowolnej oferty z sekcją Set. W DevTools → Network potwierdź, że `searchable-select.css` ładuje się ze statusem 200. Strona wygląda jak wcześniej (brak klasy `searchable-select` w DOM, więc żadnych zmian wizualnych).
Expected: plik CSS 200, brak regresji wizualnych.

- [ ] **Step 4: Commit**

```bash
git add static/css/components/searchable-select.css templates/admin/offers/edit.html
git commit -m "feat(offer-builder): add searchable-select component styles"
```

---

## Task 2: Komponent JS

**Files:**
- Create: `static/js/components/searchable-select.js`
- Modify: `templates/admin/offers/edit.html` (blok `extra_js`, po linii 955)

- [ ] **Step 1: Utwórz plik JS**

Utwórz `static/js/components/searchable-select.js` z pełną treścią:

```javascript
/**
 * Searchable Select - progressive enhancement dla natywnych <select class="searchable-select">.
 * Natywny <select> pozostaje źródłem prawdy; po kliknięciu .custom-select-display
 * pokazuje się panel z inputem wyszukiwarki i listą opcji budowaną na żywo z selecta.
 * Wybór ustawia select.value, dispatchuje natywny 'change' i aktualizuje tekst triggera.
 * Cała logika na delegacji zdarzeń -> działa dla dynamicznie dodawanych sekcji.
 */
(function () {
    'use strict';

    let openWrapper = null;

    function getSelect(wrapper) {
        return wrapper.querySelector('select.searchable-select');
    }

    function syncDisplay(select) {
        const wrapper = select.closest('.custom-select-wrapper');
        if (!wrapper) return;
        const text = wrapper.querySelector('.custom-select-display .selected-text');
        if (!text) return;
        const opt = select.options[select.selectedIndex];
        if (opt && opt.value) {
            text.textContent = opt.text;
        } else if (select.options[0]) {
            text.textContent = select.options[0].text;
        }
    }

    function closePanel() {
        if (!openWrapper) return;
        const panel = openWrapper.querySelector('.searchable-select-panel');
        if (panel) panel.remove();
        openWrapper.classList.remove('is-open');
        openWrapper = null;
    }

    function openPanel(wrapper) {
        closePanel();
        const select = getSelect(wrapper);
        if (!select) return;

        const panel = document.createElement('div');
        panel.className = 'searchable-select-panel';

        const searchWrap = document.createElement('div');
        searchWrap.className = 'searchable-select-search';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'searchable-select-input';
        input.placeholder = 'Szukaj...';
        searchWrap.appendChild(input);

        const list = document.createElement('ul');
        list.className = 'searchable-select-options';

        // Buduj opcje na zywo z natywnego selecta (pomijaj placeholder z pustym value)
        Array.from(select.options).forEach(function (opt) {
            if (!opt.value) return;
            const li = document.createElement('li');
            li.className = 'searchable-select-option';
            li.dataset.value = opt.value;
            li.textContent = opt.text;
            if (opt.value === select.value) li.classList.add('is-selected');
            list.appendChild(li);
        });

        const empty = document.createElement('li');
        empty.className = 'searchable-select-empty';
        empty.textContent = 'Brak wynikow';
        empty.style.display = 'none';
        list.appendChild(empty);

        panel.appendChild(searchWrap);
        panel.appendChild(list);
        wrapper.appendChild(panel);
        wrapper.classList.add('is-open');
        openWrapper = wrapper;
        input.focus();

        let highlighted = -1;

        function visibleOptions() {
            return Array.from(list.querySelectorAll('.searchable-select-option'))
                .filter(function (li) { return li.style.display !== 'none'; });
        }

        function filter() {
            const q = input.value.trim().toLowerCase();
            let any = false;
            list.querySelectorAll('.searchable-select-option').forEach(function (li) {
                const match = li.textContent.toLowerCase().indexOf(q) !== -1;
                li.style.display = match ? '' : 'none';
                li.classList.remove('is-highlighted');
                if (match) any = true;
            });
            highlighted = -1;
            empty.style.display = any ? 'none' : '';
        }

        function choose(li) {
            select.value = li.dataset.value;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            syncDisplay(select);
            closePanel();
        }

        function setHighlight(idx) {
            const opts = visibleOptions();
            opts.forEach(function (o) { o.classList.remove('is-highlighted'); });
            if (idx < 0 || idx >= opts.length) { highlighted = -1; return; }
            opts[idx].classList.add('is-highlighted');
            opts[idx].scrollIntoView({ block: 'nearest' });
            highlighted = idx;
        }

        input.addEventListener('input', filter);
        input.addEventListener('keydown', function (e) {
            const opts = visibleOptions();
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setHighlight(Math.min(highlighted + 1, opts.length - 1));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setHighlight(Math.max(highlighted - 1, 0));
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (highlighted >= 0 && opts[highlighted]) choose(opts[highlighted]);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                closePanel();
            }
        });
        list.addEventListener('click', function (e) {
            const li = e.target.closest('.searchable-select-option');
            if (li) choose(li);
        });
    }

    // Delegacja: klik na .custom-select-display, ktorego wrapper ma searchable-select
    document.addEventListener('click', function (e) {
        const display = e.target.closest('.custom-select-display');
        if (display) {
            const wrapper = display.closest('.custom-select-wrapper');
            if (wrapper && getSelect(wrapper)) {
                e.preventDefault();
                if (openWrapper === wrapper) {
                    closePanel();
                } else {
                    openPanel(wrapper);
                }
                return;
            }
        }
        // Klik poza panelem i poza triggerem -> zamknij
        if (openWrapper &&
            !e.target.closest('.searchable-select-panel') &&
            !e.target.closest('.custom-select-display')) {
            closePanel();
        }
    });

    // Sync tekstu triggera gdy value zmieni sie (nasz dispatch lub programowo)
    document.addEventListener('change', function (e) {
        if (e.target.matches && e.target.matches('select.searchable-select')) {
            syncDisplay(e.target);
        }
    });

    // Poczatkowy sync dla server-renderowanych selectow
    function initialSync() {
        document.querySelectorAll('select.searchable-select').forEach(syncDisplay);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialSync);
    } else {
        initialSync();
    }
})();
```

- [ ] **Step 2: Dołącz JS w edit.html**

W `templates/admin/offers/edit.html` w bloku `extra_js` (linia 955) dodaj nowy `<script>` PO linii z `offer-builder.js`:

```html
{% block extra_js %}
<script src="{{ url_for('static', filename='js/pages/admin/offer-builder.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/searchable-select.js') }}"></script>
```

(reszta bloku — istniejący `<script>` z inicjalizacją — bez zmian)

- [ ] **Step 3: Weryfikacja manualna**

Odśwież edycję oferty. W DevTools → Console brak błędów; Network: `searchable-select.js` 200. Ponieważ żaden select nie ma jeszcze klasy `searchable-select`, dropdowny działają po staremu (natywnie).
Expected: brak błędów w konsoli, brak regresji.

- [ ] **Step 4: Commit**

```bash
git add static/js/components/searchable-select.js templates/admin/offers/edit.html
git commit -m "feat(offer-builder): add searchable-select component logic"
```

---

## Task 3: Aktywacja dropdownu „Produkt – komplet setu" (`.set-product-select`)

Ten select już ma `.custom-select-wrapper` + `.custom-select-display` w obu miejscach — wystarczy dodać klasę `searchable-select`.

**Files:**
- Modify: `static/js/pages/admin/offer-builder.js:485`
- Modify: `templates/admin/offers/edit.html:519`

- [ ] **Step 1: JS template — dodaj klasę**

W `static/js/pages/admin/offer-builder.js` (linia 485) zamień:

```html
                                    <select class="form-select set-product-select" onchange="markDirty(); updateSetProductPreview(this)">
```

na:

```html
                                    <select class="form-select set-product-select searchable-select" onchange="markDirty(); updateSetProductPreview(this)">
```

- [ ] **Step 2: Jinja template — dodaj klasę**

W `templates/admin/offers/edit.html` (linia 519) zamień:

```html
                                        <select class="form-select set-product-select" onchange="markDirty(); updateSetProductPreview(this)">
```

na:

```html
                                        <select class="form-select set-product-select searchable-select" onchange="markDirty(); updateSetProductPreview(this)">
```

- [ ] **Step 3: Weryfikacja manualna**

1. Edycja oferty z sekcją Set zawierającą grupę wariantową (pole „Produkt – komplet setu" widoczne).
2. Kliknij dropdown „Produkt – komplet setu" → otwiera się panel z inputem wyszukiwarki na górze.
3. Wpisz fragment nazwy → lista filtruje się. ↑/↓ podświetla, Enter wybiera, Esc zamyka, klik poza zamyka.
4. Po wyborze: tekst triggera się aktualizuje ORAZ karta podglądu produktu (`set-product-preview-card`) pokazuje nazwę/cenę/zdjęcie (potwierdza dispatch `change` → `updateSetProductPreview`).
5. Zapisz stronę, odśwież → wybrany produkt nadal widoczny w triggerze i podglądzie.

Expected: wyszukiwarka działa, podgląd i zapis/wczytanie OK.

- [ ] **Step 4: Commit**

```bash
git add static/js/pages/admin/offer-builder.js templates/admin/offers/edit.html
git commit -m "feat(offer-builder): searchable dropdown for set product select"
```

---

## Task 4: Aktywacja dropdownu grupy wariantowej w secie (`.set-item-variant-group`)

Goły select → owinięcie w `.custom-select-wrapper` + `.custom-select-display` + klasa.

**Files:**
- Modify: `static/js/pages/admin/offer-builder.js:1315-1318`
- Modify: `templates/admin/offers/edit.html:428-436`

- [ ] **Step 1: JS template — owiń select**

W `static/js/pages/admin/offer-builder.js` (linie 1315-1318) zamień:

```html
                <select class="form-select variant-group-select set-item-variant-group" onchange="updateSetVariantGroupProducts(this)">
                    <option value="">Wybierz grupę...</option>
                    ${variantGroupOptions}
                </select>
```

na:

```html
                <div class="custom-select-wrapper">
                    <select class="form-select variant-group-select set-item-variant-group searchable-select" onchange="updateSetVariantGroupProducts(this)">
                        <option value="">Wybierz grupę...</option>
                        ${variantGroupOptions}
                    </select>
                    <div class="custom-select-display">
                        <span class="selected-text">Wybierz grupę...</span>
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                        </svg>
                    </div>
                </div>
```

- [ ] **Step 2: Jinja template — owiń select**

W `templates/admin/offers/edit.html` (linie 428-436) zamień:

```html
                                            <select class="form-select variant-group-select set-item-variant-group" onchange="updateSetVariantGroupProducts(this)">
                                                <option value="">Wybierz grupę...</option>
                                                {% for vg in variant_groups %}
                                                <option value="{{ vg.id }}" data-products="{{ vg.products|length }}"
                                                        {% if item.variant_group_id == vg.id %}selected{% endif %}>
                                                    {{ vg.name }} ({{ vg.products|length }} produktów)
                                                </option>
                                                {% endfor %}
                                            </select>
```

na:

```html
                                            <div class="custom-select-wrapper">
                                                <select class="form-select variant-group-select set-item-variant-group searchable-select" onchange="updateSetVariantGroupProducts(this)">
                                                    <option value="">Wybierz grupę...</option>
                                                    {% for vg in variant_groups %}
                                                    <option value="{{ vg.id }}" data-products="{{ vg.products|length }}"
                                                            {% if item.variant_group_id == vg.id %}selected{% endif %}>
                                                        {{ vg.name }} ({{ vg.products|length }} produktów)
                                                    </option>
                                                    {% endfor %}
                                                </select>
                                                <div class="custom-select-display">
                                                    <span class="selected-text">{% set sel_vg = (variant_groups|selectattr('id','equalto',item.variant_group_id)|first) %}{% if sel_vg %}{{ sel_vg.name }} ({{ sel_vg.products|length }} produktów){% else %}Wybierz grupę...{% endif %}</span>
                                                    <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                                                        <path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                                                    </svg>
                                                </div>
                                            </div>
```

- [ ] **Step 3: Weryfikacja manualna — nowa karta**

1. Edycja oferty → w sekcji Set kliknij „+ Dodaj grupę wariantową".
2. Nowa karta: kliknij dropdown grupy → panel z wyszukiwarką na górze, wpisanie filtruje grupy.
3. Wybierz grupę → tekst triggera się aktualizuje ORAZ poniżej ładują się produkty grupy (`variant-group-products`, potwierdza `change` → `updateSetVariantGroupProducts`).
4. Sprawdź layout: dropdown wypełnia szerokość między ikoną a badge „Grupa" (reguła `.variant-group-header .custom-select-wrapper { flex: 1 }`).

Expected: wyszukiwarka działa, produkty grupy się ładują, layout poprawny.

- [ ] **Step 4: Weryfikacja manualna — zapisana karta**

1. Zapisz stronę z wybraną grupą w secie, odśwież.
2. Trigger pokazuje nazwę wcześniej wybranej grupy (np. „Nazwa (12 produktów)"), a produkty grupy są załadowane.
3. Kliknij dropdown → opcja bieżącej grupy ma wyróżnienie `is-selected`, wyszukiwarka działa.

Expected: wartość i wygląd zachowane po wczytaniu.

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/admin/offer-builder.js templates/admin/offers/edit.html
git commit -m "feat(offer-builder): searchable dropdown for set variant group"
```

---

## Task 5: Aktywacja dropdownu samodzielnej sekcji „Grupa wariantowa" (`.variant-group-select`)

Goły select → owinięcie w `.custom-select-wrapper` + `.custom-select-display` + klasa.

**Files:**
- Modify: `static/js/pages/admin/offer-builder.js:646-649`
- Modify: `templates/admin/offers/edit.html:699-708`

- [ ] **Step 1: JS template — owiń select**

W `static/js/pages/admin/offer-builder.js` (linie 646-649) zamień:

```html
                                <select class="form-select variant-group-select" data-variant-group-id="" onchange="updateVariantGroupPreview(this)">
                                    <option value="">Wybierz grupę wariantową...</option>
                                    ${document.getElementById('variantGroupOptionTemplate')?.innerHTML || ''}
                                </select>
```

na:

```html
                                <div class="custom-select-wrapper">
                                    <select class="form-select variant-group-select searchable-select" data-variant-group-id="" onchange="updateVariantGroupPreview(this)">
                                        <option value="">Wybierz grupę wariantową...</option>
                                        ${document.getElementById('variantGroupOptionTemplate')?.innerHTML || ''}
                                    </select>
                                    <div class="custom-select-display">
                                        <span class="selected-text">Wybierz grupę wariantową...</span>
                                        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                                            <path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                                        </svg>
                                    </div>
                                </div>
```

- [ ] **Step 2: Jinja template — owiń select**

W `templates/admin/offers/edit.html` (linie 699-708) zamień:

```html
                                    <select class="form-select variant-group-select" data-variant-group-id="{{ section.variant_group_id or '' }}" onchange="updateVariantGroupPreview(this)">
                                        <option value="">Wybierz grupę wariantową...</option>
                                        {% for vg in variant_groups %}
                                        <option value="{{ vg.id }}"
                                                data-products="{{ vg.products|length }}"
                                                {% if section.variant_group_id == vg.id %}selected{% endif %}>
                                            {{ vg.name }} ({{ vg.products|length }} produktów)
                                        </option>
                                        {% endfor %}
                                    </select>
```

na:

```html
                                    <div class="custom-select-wrapper">
                                        <select class="form-select variant-group-select searchable-select" data-variant-group-id="{{ section.variant_group_id or '' }}" onchange="updateVariantGroupPreview(this)">
                                            <option value="">Wybierz grupę wariantową...</option>
                                            {% for vg in variant_groups %}
                                            <option value="{{ vg.id }}"
                                                    data-products="{{ vg.products|length }}"
                                                    {% if section.variant_group_id == vg.id %}selected{% endif %}>
                                                {{ vg.name }} ({{ vg.products|length }} produktów)
                                            </option>
                                            {% endfor %}
                                        </select>
                                        <div class="custom-select-display">
                                            <span class="selected-text">{% set sel_vg = (variant_groups|selectattr('id','equalto',section.variant_group_id)|first) %}{% if sel_vg %}{{ sel_vg.name }} ({{ sel_vg.products|length }} produktów){% else %}Wybierz grupę wariantową...{% endif %}</span>
                                            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                                                <path d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
                                            </svg>
                                        </div>
                                    </div>
```

- [ ] **Step 3: Weryfikacja manualna — nowa sekcja**

1. Edycja oferty → dodaj sekcję „Grupa wariantowa".
2. Kliknij dropdown grupy → panel z wyszukiwarką, filtrowanie działa.
3. Wybierz grupę → trigger aktualizuje tekst, a podgląd produktów grupy się ładuje (`updateVariantGroupPreview`).

Expected: wyszukiwarka działa, podgląd grupy OK.

- [ ] **Step 4: Weryfikacja manualna — zapisana sekcja + dark mode**

1. Zapisz, odśwież → trigger pokazuje wybraną grupę, podgląd załadowany.
2. Przełącz na **dark mode** → panel, input, opcje i podświetlenie czytelne i spójne z resztą buildera.

Expected: wartość zachowana; wygląd w dark mode poprawny.

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/admin/offer-builder.js templates/admin/offers/edit.html
git commit -m "feat(offer-builder): searchable dropdown for standalone variant group section"
```

---

## Task 6: Weryfikacja końcowa (wszystkie scenariusze)

**Files:** brak zmian — tylko weryfikacja.

- [ ] **Step 1: Pełny przebieg w light mode**

Na jednej ofercie sprawdź wszystkie 3 wyszukiwarki w jednym przebiegu:
- Set: „Produkt – komplet setu" (Task 3).
- Set: grupa wariantowa po „+ Dodaj grupę wariantową" (Task 4).
- Samodzielna sekcja „Grupa wariantowa" (Task 5).
Dla każdej: otwarcie, filtrowanie, klawiatura (↑/↓/Enter/Esc), klik poza zamyka, „Brak wyników" przy braku dopasowań.

- [ ] **Step 2: Tylko jeden panel naraz**

Otwórz jeden dropdown, potem kliknij inny → pierwszy się zamyka, drugi otwiera.

- [ ] **Step 3: Zapis i wczytanie**

Wybierz wartości we wszystkich 3, zapisz, odśwież → wszystkie triggery pokazują wybrane wartości; `collectPageData` zapisał poprawnie (sprawdź, że po ponownym zapisie nic się nie gubi).

- [ ] **Step 4: Dark mode end-to-end**

Powtórz Step 1 w dark mode — czytelność i spójność wszystkich 3 paneli.

- [ ] **Step 5: Brak regresji konsoli**

Przez cały przebieg DevTools → Console bez błędów JS.

Expected: wszystkie scenariusze przechodzą; brak błędów.

---

## Self-Review (wypełnione przy pisaniu planu)

**Pokrycie specu:**
- Komponent searchable-select (architektura, mechanika, event delegation) → Task 1-2. ✅
- Dropdown #1 set-item-variant-group → Task 4. ✅
- Dropdown #2 set-product-select → Task 3. ✅
- Dropdown #3 standalone variant_group → Task 5. ✅
- Pliki (nowy JS, nowy CSS, edycja offer-builder.js, edycja edit.html) → wszystkie objęte. ✅
- Light + dark mode → Task 1 (CSS) + weryfikacja Task 5/6. ✅
- Bez zmian w bazie/backendzie → potwierdzone (tylko frontend). ✅
- Dynamiczne sekcje działają od razu → delegacja zdarzeń (Task 2) + weryfikacja Task 4/5 Step 3. ✅
- Kryteria akceptacji 1-6 ze specu → pokryte weryfikacjami Task 3-6. ✅

**Skan placeholderów:** brak TBD/TODO; cały kod podany dosłownie. ✅

**Spójność nazw:** klasa-marker `searchable-select`, klasy `custom-select-wrapper`/`custom-select-display`/`selected-text` (istniejące), klasy panelu `searchable-select-panel`/`-search`/`-input`/`-options`/`-option`/`-empty`, stany `is-open`/`is-selected`/`is-highlighted` — użyte spójnie w CSS (Task 1) i JS (Task 2). Funkcje `syncDisplay`/`openPanel`/`closePanel`/`getSelect` spójne. ✅
