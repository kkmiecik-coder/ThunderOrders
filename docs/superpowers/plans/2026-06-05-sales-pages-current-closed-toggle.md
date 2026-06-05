# Przełącznik „Bieżące" / „Zamknięte" w widgecie Strony sprzedaży — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać przełącznik dwóch zakładek (Bieżące / Zamknięte) w headerze widgetu „Strony sprzedaży" na dashboardzie klienta, filtrujący strony ofertowe po backendzie z cache po stronie frontu.

**Architecture:** Backend (`modules/client/routes.py`) zyskuje wspólną funkcję `filter_offer_pages()` używaną przez `dashboard()` (renderuje domyślnie bieżące) i `get_offer_pages()` (API przyjmuje `?filter=current|closed` i filtruje przed paginacją). Frontend: cały inline JS dashboardu wydzielany do `static/js/pages/client/dashboard.js` (z przekazaniem zależności Jinja2 przez `data-*`/inline init), a logika przełącznika cache'uje pobrane zakładki w pamięci. Style zakładek w `static/css/pages/client/dashboard.css` (light + dark).

**Tech Stack:** Flask + Jinja2, vanilla JS (fetch), CSS custom properties. Brak zmian w bazie danych / migracji.

---

## Definicje kategorii (referencja dla całego planu)

- **Bieżące (`current`)** = `status in ('scheduled', 'active', 'paused')`
- **Zamknięte (`closed`)** = `status == 'ended'` (obejmuje „Zakończona" i „Zamknięta"/`is_fully_closed`)
- `draft` nigdy nie jest widoczny dla klienta (filtrowany już dziś przez `status != 'draft'`).

---

## File Structure

| Plik | Rola | Akcja |
|---|---|---|
| `modules/client/routes.py` | `filter_offer_pages()`, zmiany w `dashboard()` i `get_offer_pages()` | Modify |
| `tests/test_client_offer_filter.py` | Testy filtra i API | Create |
| `templates/client/dashboard.html` | Header z zakładkami, puste stany, wydzielenie JS, init zależności Jinja2 | Modify |
| `static/js/pages/client/dashboard.js` | Cały dotychczasowy inline JS + logika przełącznika | Create |
| `static/css/pages/client/dashboard.css` | Style zakładek i pustego stanu (light + dark) | Modify |

---

## Uwaga o środowisku testowym

Sprawdź na początku, czy w repo istnieje katalog `tests/` i jak uruchamiane są testy:

Run: `ls tests/ 2>/dev/null && cat pytest.ini setup.cfg pyproject.toml conftest.py 2>/dev/null | head -40`

Jeśli **nie ma** infrastruktury pytest ani fixture aplikacji, NIE buduj jej od zera w tym planie. Zamiast testów automatycznych w Tasku 1 i 2, zweryfikuj `filter_offer_pages()` przez `flask shell` (komendy podane w krokach jako alternatywa) i przejdź do zadań frontendowych. Zadania 3-6 są weryfikowane manualnie w przeglądarce (`http://localhost:5001`) niezależnie od pytest.

---

## Task 1: Funkcja `filter_offer_pages()` w backendzie

**Files:**
- Modify: `modules/client/routes.py` (po `sort_offer_pages`, ~linia 55)
- Test: `tests/test_client_offer_filter.py`

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_client_offer_filter.py`. Test używa lekkich obiektów-atrap (duck typing — funkcja czyta tylko `.status`), więc nie wymaga bazy danych:

```python
from modules.client.routes import filter_offer_pages


class FakePage:
    def __init__(self, status):
        self.status = status


def _statuses(pages):
    return [p.status for p in pages]


def test_filter_current_returns_scheduled_active_paused():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'current')
    assert _statuses(result) == ['scheduled', 'active', 'paused']


def test_filter_closed_returns_only_ended():
    pages = [FakePage('scheduled'), FakePage('active'), FakePage('paused'),
             FakePage('ended')]
    result = filter_offer_pages(pages, 'closed')
    assert _statuses(result) == ['ended']


def test_filter_defaults_to_current_for_unknown():
    pages = [FakePage('active'), FakePage('ended')]
    result = filter_offer_pages(pages, 'garbage')
    assert _statuses(result) == ['active']


def test_filter_preserves_order():
    pages = [FakePage('active'), FakePage('scheduled'), FakePage('paused')]
    result = filter_offer_pages(pages, 'current')
    assert _statuses(result) == ['active', 'scheduled', 'paused']
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python -m pytest tests/test_client_offer_filter.py -v`
Expected: FAIL — `ImportError: cannot import name 'filter_offer_pages'`

(Alternatywa bez pytest: pomiń ten krok, weryfikacja w Step 4.)

- [ ] **Step 3: Zaimplementuj `filter_offer_pages()`**

W `modules/client/routes.py`, bezpośrednio po funkcji `sort_offer_pages` (po linii 54), dodaj:

```python
def filter_offer_pages(pages, filter_type):
    """
    Dzieli strony ofertowe na "bieżące" i "zamknięte" dla przełącznika
    na dashboardzie klienta. Jedno źródło prawdy dla dashboard() i API.

    - 'closed': strony zakończone (status == 'ended', obejmuje też
      is_fully_closed, bo to nadal status 'ended').
    - 'current' (domyślnie): zaplanowane / aktywne (LIVE) / wstrzymane.

    Zachowuje kolejność wejściową (zakładamy, że lista jest już posortowana
    przez sort_offer_pages).
    """
    if filter_type == 'closed':
        return [p for p in pages if p.status == 'ended']
    return [p for p in pages if p.status in ('scheduled', 'active', 'paused')]
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_client_offer_filter.py -v`
Expected: PASS (4 passed)

Alternatywa bez pytest (`flask shell`):
```python
from modules.client.routes import filter_offer_pages
class F:
    def __init__(s, st): s.status = st
ps = [F('scheduled'), F('active'), F('paused'), F('ended')]
print([p.status for p in filter_offer_pages(ps, 'current')])  # ['scheduled','active','paused']
print([p.status for p in filter_offer_pages(ps, 'closed')])   # ['ended']
```

- [ ] **Step 5: Commit**

```bash
git add modules/client/routes.py tests/test_client_offer_filter.py
git commit -m "feat(client): funkcja filter_offer_pages dla przełącznika stron sprzedaży"
```

---

## Task 2: `dashboard()` renderuje bieżące + flagi, API przyjmuje `?filter`

**Files:**
- Modify: `modules/client/routes.py` — `dashboard()` (~linie 154-194), `get_offer_pages()` (~linie 324-356)
- Test: `tests/test_client_offer_filter.py` (dopisanie, jeśli istnieje fixture aplikacji)

- [ ] **Step 1: Zmodyfikuj `dashboard()` — podział na current/closed**

W `modules/client/routes.py`, w funkcji `dashboard()`, zastąp blok budujący słownik `offer_pages` (obecnie linie ~166-175, od komentarza `# Pre-compute has_sets` do zamknięcia słownika `offer_pages`) tym:

```python
    # Pre-compute has_sets for each page
    for page in offer_pages_all:
        page._has_sets = len(page.get_set_sections()) > 0

    # Podział na bieżące/zamknięte dla przełącznika (Task: sales-pages-toggle).
    # Domyślnie dashboard renderuje bieżące; zamknięte dociąga JS przez API.
    current_pages = filter_offer_pages(offer_pages_all, 'current')
    closed_pages = filter_offer_pages(offer_pages_all, 'closed')

    offer_pages = {
        'visible': current_pages[:5],          # First 5 visible (bieżące)
        'buffer': current_pages[5:10],         # Next 5 in buffer (hidden)
        'total': len(current_pages),           # total dla zakładki bieżące
        'remaining': max(0, len(current_pages) - 5),
        'has_any': len(offer_pages_all) > 0,   # czy pokazać widget w ogóle
        'has_current': len(current_pages) > 0, # pusty stan zakładki bieżące
        'has_closed': len(closed_pages) > 0,   # pusty stan zakładki zamknięte
    }
```

- [ ] **Step 2: Zmodyfikuj `get_offer_pages()` — odczyt i zastosowanie `filter`**

W funkcji `get_offer_pages()` (~linia 338), tuż po odczycie `offset` i `limit`, dodaj odczyt filtra:

```python
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 5, type=int)
    filter_type = request.args.get('filter', 'current')
```

Następnie w tej samej funkcji, **po** `sort_offer_pages(offer_pages_all)` a **przed** linią `pages_slice = offer_pages_all[offset:offset + limit]` (~linia 354), wstaw filtrowanie i przepnij paginację na przefiltrowaną listę:

```python
    # Sort: ta sama logika co na dashboardzie (kolejność musi być identyczna)
    sort_offer_pages(offer_pages_all)

    # Filtruj wg zakładki PRZED paginacją, żeby offset/remaining liczyły się
    # względem przefiltrowanego zbioru.
    filtered_pages = filter_offer_pages(offer_pages_all, filter_type)

    # Paginacja
    pages_slice = filtered_pages[offset:offset + limit]
    has_more = len(filtered_pages) > offset + limit
    remaining = max(0, len(filtered_pages) - offset - limit)
```

Oraz w bloku `return jsonify({...})` (~linia 402) zmień `'total': len(offer_pages_all)` na `'total': len(filtered_pages)`.

> **Uwaga:** Funkcja `refreshOfferStatuses()` w JS woła `/client/api/offer-pages?offset=0&limit=100` **bez** parametru `filter`. Dzięki domyślnemu `'current'` zwróci to bieżące strony — i tak ma to sens, bo countdown/odświeżanie dotyczy aktywnych/zaplanowanych. Nie zmieniamy tego wywołania w tym tasku.

- [ ] **Step 3: Weryfikacja manualna (uruchom serwer)**

Uruchom lokalnie aplikację (`http://localhost:5001`), zaloguj się jako klient i sprawdź endpointy w przeglądarce / curl:

Run: `curl -s 'http://localhost:5001/client/api/offer-pages?filter=closed&offset=0&limit=5' -H 'Cookie: <session>' | python -m json.tool | head -30`

Expected: JSON z `"success": true`, w `pages` wyłącznie strony o statusie `ended`, `total` = liczba zamkniętych.

Run to samo z `filter=current` — Expected: tylko `scheduled`/`active`/`paused`.

(Jeśli sesja przez curl jest niewygodna, zweryfikuj w DevTools → Network po implementacji frontu w Tasku 5.)

- [ ] **Step 4: Commit**

```bash
git add modules/client/routes.py
git commit -m "feat(client): dashboard renderuje bieżące strony, API filtruje przez ?filter"
```

---

## Task 3: Wydzielenie inline JS dashboardu do osobnego pliku (1:1, bez zmian funkcjonalnych)

> Ten task NIE dodaje logiki przełącznika. To wierne przeniesienie istniejącego kodu, żeby kolejny task budował już na czystym pliku. Zależności Jinja2 (`chart_data`, `url_for('achievements.gallery')`) przekazujemy przez `data-*` / inline init.

**Files:**
- Create: `static/js/pages/client/dashboard.js`
- Modify: `templates/client/dashboard.html` (blok `{% block extra_js %}`, linie ~514-1381; oraz dodanie kontenera danych init)

- [ ] **Step 1: Utwórz `static/js/pages/client/dashboard.js`**

Skopiuj CAŁĄ zawartość obecnego bloku `<script>` z `dashboard.html` (od `document.addEventListener('DOMContentLoaded', function() {` w linii 517 do zamykającego `});` w linii 1377) do nowego pliku `static/js/pages/client/dashboard.js`. Zachowaj kod 1:1, z dwoma wyjątkami opisanymi w Step 2 i Step 3 (zależności Jinja2).

Struktura pliku po przeniesieniu:
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // ... cały dotychczasowy kod ...
});
```

- [ ] **Step 2: Zastąp zależności Jinja2 w pliku JS — chart_data**

W przeniesionym kodzie Chart.js (dawne linie 530, 533) były:
```javascript
labels: {{ chart_data['labels'] | tojson }},
...
data: {{ chart_data['values'] | tojson }},
```

Zastąp je odczytem z elementu DOM. Znajdź w pliku JS sekcję tworzącą `ordersChart` i zmień początek bloku `if (ordersCtx) {` tak, by czytał dane z `data-*` atrybutów canvasa:

```javascript
    const ordersCtx = document.getElementById('ordersChart');
    if (ordersCtx) {
        const isMobile = window.innerWidth <= 768;
        const chartLabels = JSON.parse(ordersCtx.dataset.labels || '[]');
        const chartValues = JSON.parse(ordersCtx.dataset.values || '[]');
```

oraz w obiekcie `data`:
```javascript
                labels: chartLabels,
                datasets: [{
                    label: 'Liczba zamówień',
                    data: chartValues,
```

- [ ] **Step 3: Zastąp zależność Jinja2 w pliku JS — achievements gallery URL**

W sekcji ACHIEVEMENTS WIDGET (dawna linia 1366) było:
```javascript
badgesHtml += '<a href="' + "{{ url_for('achievements.gallery') }}" + '" class="widget-badge widget-badge-more">'
```

Zastąp odczytem z `data-*` na kontenerze `#widget-badges`:
```javascript
            var badgesEl = document.getElementById('widget-badges');
            var galleryUrl = badgesEl ? (badgesEl.dataset.galleryUrl || '#') : '#';
```
(umieść tę linię przy istniejącym `var badgesEl = document.getElementById('widget-badges');` — uważaj, że `badgesEl` jest już deklarowane niżej w bloku `if (recent.length === 0)`; przenieś deklarację `badgesEl` na górę bloku `.then`, a niżej usuń ponowne `var`). Następnie użyj `galleryUrl`:
```javascript
                    badgesHtml += '<a href="' + galleryUrl + '" class="widget-badge widget-badge-more">'
```

- [ ] **Step 4: Zaktualizuj `dashboard.html` — przekaż dane przez data-* i podłącz plik**

W `dashboard.html`:

(a) Canvas wykresu (linia 358) — dodaj `data-labels` i `data-values`:
```html
<canvas id="ordersChart"
        data-labels="{{ chart_data['labels'] | tojson | forceescape }}"
        data-values="{{ chart_data['values'] | tojson | forceescape }}"></canvas>
```

(b) Kontener odznak (linia 489) — dodaj `data-gallery-url`:
```html
<div class="widget-badges" id="widget-badges" data-gallery-url="{{ url_for('achievements.gallery') }}">
```

(c) Zastąp cały blok `{% block extra_js %}` (linie 514-1381). Usuń duży inline `<script>...</script>` (linie 516-1378), zostaw zewnętrzne skrypty i dodaj nasz plik:
```html
{% block extra_js %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="{{ url_for('static', filename='js/pages/client/dashboard.js') }}"></script>
<script src="{{ url_for('static', filename='js/vendor/shepherd.min.js') }}"></script>
<script src="{{ url_for('static', filename='js/components/onboarding-tour.js') }}"></script>
{% endblock %}
```

> **Kolejność skryptów ma znaczenie:** Chart.js musi być przed `dashboard.js` (bo `new Chart` używa globalnego `Chart`). Shepherd/onboarding po — bez zmian względem oryginału.

- [ ] **Step 5: Weryfikacja manualna — dashboard działa identycznie**

Uruchom serwer, otwórz dashboard klienta. Sprawdź w przeglądarce (i konsoli — brak błędów JS):
- Wykres „Moje zamówienia" renderuje się z danymi i reaguje na zmianę okresu.
- Widget odznak ładuje się; link „więcej" działa (jeśli >5 odznak).
- Strony sprzedaży: countdown/timing widoczny, „Pokaż więcej" działa, modal macierzy otwiera się.

Expected: zachowanie identyczne jak przed wydzieleniem. Konsola bez błędów.

- [ ] **Step 6: Commit**

```bash
git add templates/client/dashboard.html static/js/pages/client/dashboard.js
git commit -m "refactor(client): wydziel inline JS dashboardu do osobnego pliku"
```

---

## Task 4: HTML — header z zakładkami, puste stany, warunek widoczności widgetu

**Files:**
- Modify: `templates/client/dashboard.html` (header widgetu ~linie 74-79; tbody desktop; kontener kart mobile; warunek widoczności)

- [ ] **Step 1: Zmień warunek widoczności widgetu**

Linia 74: zamień
```html
{% if offer_pages.visible|length > 0 %}
```
na
```html
{% if offer_pages.has_any %}
```

- [ ] **Step 2: Dodaj zakładki do headera widgetu**

Zastąp blok headera (linie 77-79):
```html
            <div class="widget-header">
                <h2 class="widget-title">✨ Strony sprzedaży</h2>
            </div>
```
tym:
```html
            <div class="widget-header widget-header-offers">
                <h2 class="widget-title">✨ Strony sprzedaży</h2>
                <div class="offer-filter-tabs" role="tablist" aria-label="Filtr stron sprzedaży">
                    <button type="button" class="offer-filter-tab active" data-filter="current" role="tab" aria-selected="true">Bieżące</button>
                    <button type="button" class="offer-filter-tab" data-filter="closed" role="tab" aria-selected="false">Zamknięte</button>
                </div>
            </div>
```

- [ ] **Step 3: Dodaj wiersz pustego stanu (desktop) do `<tbody>`**

W `<tbody id="offersTableBody">`, na końcu (po pętli `{% for page in offer_pages.buffer %}...{% endfor %}`, przed `</tbody>` w linii 207), dodaj wiersz pustego stanu. Domyślnie ukryty, jeśli są bieżące; widoczny jeśli ich nie ma:
```html
                        {# Pusty stan zakładki — sterowany przez JS #}
                        <tr class="offer-empty-row"{% if offer_pages.has_current %} style="display: none;"{% endif %}>
                            <td colspan="5" class="offer-empty-cell">
                                <span class="offer-empty-text">Brak bieżących stron sprzedaży</span>
                            </td>
                        </tr>
```

- [ ] **Step 4: Dodaj pusty stan (mobile) do kontenera kart**

W `<div class="offer-cards offer-mobile" id="offersCardsBody">`, na końcu (po pętli buffer, przed `</div>` w linii 322), dodaj:
```html
                    {# Pusty stan mobile — sterowany przez JS #}
                    <div class="offer-card-empty"{% if offer_pages.has_current %} style="display: none;"{% endif %}>
                        <span class="offer-empty-text">Brak bieżących stron sprzedaży</span>
                    </div>
```

- [ ] **Step 5: Ukryj „Pokaż więcej" gdy zakładka bieżące pusta**

Warunek `{% if offer_pages.remaining > 0 %}` (linia 324) już sam z siebie nie pokaże przycisku gdy nie ma bieżących (`remaining` liczone z `current_pages`). Pozostaw bez zmian — działa poprawnie.

- [ ] **Step 6: Weryfikacja manualna**

Otwórz dashboard. Expected:
- Header widgetu pokazuje tytuł + dwie zakładki (Bieżące aktywna).
- Jeśli są bieżące strony — widać je, pusty stan ukryty.
- Jeśli istnieją tylko zamknięte (przygotuj taki stan danych) — widget widoczny, zakładka Bieżące pokazuje „Brak bieżących stron sprzedaży".
- Zakładki jeszcze nie przełączają (JS w Tasku 5) — to oczekiwane.

- [ ] **Step 7: Commit**

```bash
git add templates/client/dashboard.html
git commit -m "feat(client): zakładki Bieżące/Zamknięte i puste stany w widgecie stron sprzedaży"
```

---

## Task 5: JS — logika przełącznika z cache + integracja z „Pokaż więcej"

**Files:**
- Modify: `static/js/pages/client/dashboard.js` (sekcja LAZY LOADING ofert; nowa sekcja TABS)

**Kontekst istniejącego kodu (z którego korzystamy):**
- IIFE „EXCLUSIVE PAGES - LAZY LOADING" zawiera: `createTableRowHTML(page)`, `createCardHTML(page)`, `getStatusHTML(page)`, `fetchMorePages(offset, limit)`, oraz handler `loadMoreBtn`. Te funkcje renderujące wykorzystamy do przełącznika.
- Elementy: `#offersTableBody`, `#offersCardsBody`, `#offersLoadMoreBtn`, `#offersShowMore`, wiersz `.offer-empty-row`, karta `.offer-card-empty`.

- [ ] **Step 1: Wydziel renderowanie i stan do współdzielonego scope**

W `dashboard.js`, w IIFE lazy-loadingu ofert, podnieś stan zakładek. Na początku IIFE (po pobraniu elementów `loadMoreBtn`, `tableBody`, `cardsBody`, `showMoreContainer`) — UWAGA: ta IIFE robi `if (!loadMoreBtn) return;`. Zmień to, bo przełącznik musi działać też gdy bieżące są puste (brak `loadMoreBtn`). Zastąp:

```javascript
        if (!loadMoreBtn) return;

        let currentOffset = parseInt(loadMoreBtn.dataset.visible) + parseInt(loadMoreBtn.dataset.buffer);
        let isLoading = false;
```
na:
```javascript
        // tableBody jest wymagane do działania przełącznika; loadMoreBtn może
        // nie istnieć (gdy zakładka bieżące jest pusta).
        if (!tableBody) return;

        let currentOffset = loadMoreBtn
            ? parseInt(loadMoreBtn.dataset.visible) + parseInt(loadMoreBtn.dataset.buffer)
            : 0;
        let isLoading = false;

        // Stan zakładek: 'current' wyrenderowane server-side; 'closed' dociągane
        // leniwie. Cache trzyma surowe dane stron i offset paginacji per zakładka.
        let activeFilter = 'current';
        const tabCache = {
            current: { loaded: true, pages: null, offset: currentOffset, fetchedAll: false },
            closed: { loaded: false, pages: [], offset: 0, fetchedAll: false }
        };
```

- [ ] **Step 2: Dodaj funkcję renderującą listę z danych (reużywa istniejących helperów)**

W tej samej IIFE, po definicji `getStatusHTML(page)` (czyli po linii z `}` zamykającą `getStatusHTML`), dodaj funkcję czyszczącą i renderującą zbiór stron do tabeli i kart:

```javascript
        // Czyści dynamiczne wiersze/karty (zostawia pusty stan) i renderuje
        // podany zbiór stron. Używane przy przełączaniu zakładek.
        function renderPages(pages) {
            const emptyRow = tableBody.querySelector('.offer-empty-row');
            const emptyCard = cardsBody ? cardsBody.querySelector('.offer-card-empty') : null;

            // Usuń wszystkie wiersze oprócz pustego stanu
            tableBody.querySelectorAll('tr').forEach(tr => {
                if (!tr.classList.contains('offer-empty-row')) tr.remove();
            });
            if (cardsBody) {
                cardsBody.querySelectorAll('.offer-card').forEach(c => c.remove());
            }

            if (!pages || pages.length === 0) {
                if (emptyRow) emptyRow.style.display = '';
                if (emptyCard) emptyCard.style.display = '';
                return;
            }
            if (emptyRow) emptyRow.style.display = 'none';
            if (emptyCard) emptyCard.style.display = 'none';

            pages.forEach(page => {
                const tpl = document.createElement('template');
                tpl.innerHTML = createTableRowHTML(page).trim();
                const newRow = tpl.content.firstElementChild;
                if (emptyRow) tableBody.insertBefore(newRow, emptyRow);
                else tableBody.appendChild(newRow);

                if (cardsBody) {
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = createCardHTML(page);
                    const newCard = tempDiv.firstElementChild;
                    if (emptyCard) cardsBody.insertBefore(newCard, emptyCard);
                    else cardsBody.appendChild(newCard);
                }
            });

            updateOfferTimings();
        }
```

> `updateOfferTimings` jest zdefiniowane w zewnętrznym scope DOMContentLoaded (poza IIFE) i jest dostępne tutaj przez domknięcie — bez zmian.

- [ ] **Step 3: Dodaj sterowanie przyciskiem „Pokaż więcej" per zakładka**

Po `renderPages`, dodaj funkcję ustawiającą widoczność/tekst przycisku „Pokaż więcej" na podstawie stanu zakładki (z danych API: `total`, `offset`):

```javascript
        // Pokazuje/ukrywa i ustawia tekst "Pokaż więcej" wg stanu zakładki.
        function syncShowMore(total, shownCount) {
            if (!showMoreContainer || !loadMoreBtn) return;
            const remaining = Math.max(0, total - shownCount);
            if (remaining <= 0) {
                showMoreContainer.style.display = 'none';
            } else {
                showMoreContainer.style.display = '';
                loadMoreBtn.textContent = `Pokaż ${Math.min(remaining, 5)} więcej →`;
                loadMoreBtn.dataset.remaining = remaining;
                loadMoreBtn.dataset.total = total;
            }
        }
```

- [ ] **Step 4: Dodaj funkcję przełączania zakładki**

Dalej w IIFE dodaj główną funkcję obsługującą przełącznik:

```javascript
        async function switchTab(filter) {
            if (filter === activeFilter) return;
            activeFilter = filter;

            // Aktualizuj wygląd przycisków
            document.querySelectorAll('.offer-filter-tab').forEach(btn => {
                const isActive = btn.dataset.filter === filter;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });

            const cache = tabCache[filter];

            // Zakładka bieżące: pierwszy raz odbuduj z DOM (już wyrenderowana
            // server-side). Cache.pages == null oznacza "użyj tego co jest".
            if (filter === 'current' && cache.pages === null) {
                // Re-render nie jest potrzebny — ale przy powrocie z 'closed'
                // tabela została wyczyszczona, więc musimy mieć dane. Pobierz raz.
                if (!cache.fetchedAll) {
                    const data = await fetchTabData('current', 0, 100);
                    cache.pages = data ? data.pages : [];
                    cache.total = data ? data.total : cache.pages.length;
                    cache.fetchedAll = true;
                }
            }

            if (!cache.loaded || cache.pages === null || cache.pages.length === 0 && !cache.fetchedAll) {
                const data = await fetchTabData(filter, 0, 100);
                cache.pages = data ? data.pages : [];
                cache.total = data ? data.total : cache.pages.length;
                cache.loaded = true;
                cache.fetchedAll = true;
            }

            renderPages(cache.pages);
            syncShowMore(cache.total || cache.pages.length, cache.pages.length);
        }

        // Pobiera dane zakładki z API (z parametrem filter).
        async function fetchTabData(filter, offset, limit) {
            try {
                const response = await fetch(
                    `/client/api/offer-pages?filter=${filter}&offset=${offset}&limit=${limit}`
                );
                const data = await response.json();
                return data && data.success ? data : null;
            } catch (err) {
                console.error('Błąd pobierania stron zakładki:', err);
                if (window.Toast) window.Toast.show('Nie udało się załadować stron', 'error');
                return null;
            }
        }
```

> **Decyzja upraszczająca:** zamiast paginować zamknięte po 5 z buforem, pobieramy całą zakładką (`limit=100`) przy pierwszym przełączeniu i cache'ujemy. To zgodne ze spec (cache w pamięci, brak ponownego fetcha przy powrocie) i znacznie prostsze niż dublowanie logiki bufora. Dla zakładki bieżące „Pokaż więcej" działa po staremu (Step 6). Dla zamkniętych — `syncShowMore` ukryje przycisk, bo `total == shownCount` po pełnym pobraniu.

- [ ] **Step 5: Podłącz listenery klików zakładek**

Na końcu IIFE (przed jej zamknięciem `})();`), dodaj:

```javascript
        document.querySelectorAll('.offer-filter-tab').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.filter));
        });
```

- [ ] **Step 6: Zabezpiecz handler „Pokaż więcej" — działa tylko dla bieżących**

Istniejący handler `loadMoreBtn.addEventListener('click', ...)` operuje na buforze server-side, który istnieje tylko dla zakładki bieżące. Owiń jego ciało wczesnym wyjściem, gdy aktywna zakładka to nie 'current'. Na początku callbacku (po `e.preventDefault();`) dodaj:

```javascript
            e.preventDefault();
            if (activeFilter !== 'current') return;  // zamknięte ładowane w całości
            if (isLoading) return;
```

(reszta handlera bez zmian — bufor/fetch dotyczą tylko bieżących).

- [ ] **Step 7: Weryfikacja manualna — pełny przepływ**

Uruchom serwer, dashboard klienta. Sprawdź:
1. Domyślnie zakładka **Bieżące** aktywna, lista bieżących, „Pokaż więcej" działa jak wcześniej.
2. Klik **Zamknięte** → pobiera (Network: `?filter=closed`), pokazuje zamknięte; jeśli brak — „Brak bieżących stron sprzedaży"? → **NIE**, mobile/desktop empty text dla zamkniętych powinien brzmieć inaczej. **PRZEJDŹ do Step 8** (dynamiczny tekst pustego stanu).
3. Powrót na **Bieżące** → brak nowego requestu (Network), render z cache.
4. Ponowny klik **Zamknięte** → brak nowego requestu, render z cache.
5. Light i dark mode, desktop i mobile.

- [ ] **Step 8: Dynamiczny komunikat pustego stanu wg zakładki**

Statyczny tekst „Brak bieżących stron sprzedaży" jest błędny dla zakładki zamknięte. W `renderPages`, gdy ustawiasz pusty stan, ustaw też tekst wg `activeFilter`. Zmień blok pustego stanu w `renderPages` (z Step 2):

```javascript
            if (!pages || pages.length === 0) {
                const emptyText = activeFilter === 'closed'
                    ? 'Brak zamkniętych stron sprzedaży'
                    : 'Brak bieżących stron sprzedaży';
                if (emptyRow) {
                    emptyRow.style.display = '';
                    const cell = emptyRow.querySelector('.offer-empty-text');
                    if (cell) cell.textContent = emptyText;
                }
                if (emptyCard) {
                    emptyCard.style.display = '';
                    const span = emptyCard.querySelector('.offer-empty-text');
                    if (span) span.textContent = emptyText;
                }
                return;
            }
```

> Server-side pusty stan (Task 4) startuje na zakładce bieżące, więc statyczny tekst „Brak bieżących..." jest tam poprawny. JS nadpisuje go dopiero przy przełączeniu.

- [ ] **Step 9: Ponowna weryfikacja manualna**

Powtórz Step 7. Teraz pusta zakładka zamknięte pokazuje „Brak zamkniętych stron sprzedaży", a pusta bieżące „Brak bieżących stron sprzedaży".

- [ ] **Step 10: Commit**

```bash
git add static/js/pages/client/dashboard.js
git commit -m "feat(client): logika przełącznika Bieżące/Zamknięte z cache w pamięci"
```

---

## Task 6: CSS — style zakładek i pustego stanu (light + dark)

**Files:**
- Modify: `static/css/pages/client/dashboard.css` (sekcja „Exclusive Pages Widget", ~od linii 870)

- [ ] **Step 1: Dodaj style zakładek i pustego stanu**

W `static/css/pages/client/dashboard.css`, w sekcji „Exclusive Pages Widget" (po regule `[data-theme="dark"] .widget-offers { ... }`, ~linia 890), dodaj:

```css
/* --- Przełącznik Bieżące/Zamknięte --- */
.widget-header-offers {
    flex-wrap: wrap;
    gap: var(--space-3);
}

.offer-filter-tabs {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    background: var(--gray-100);
    border-radius: 8px;
}

.offer-filter-tab {
    appearance: none;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: var(--text-sm);
    font-weight: var(--font-medium);
    padding: 8px 16px;
    min-height: 44px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
}

.offer-filter-tab:hover {
    color: var(--text-primary);
}

.offer-filter-tab.active {
    background: var(--card-bg);
    color: #FF8500;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
}

/* Pusty stan zakładki */
.offer-empty-cell {
    text-align: center;
    padding: var(--space-8) var(--space-4);
}

.offer-card-empty {
    text-align: center;
    padding: var(--space-8) var(--space-4);
}

.offer-empty-text {
    color: var(--text-secondary);
    font-size: var(--text-sm);
}

/* Dark mode */
[data-theme="dark"] .offer-filter-tabs {
    background: rgba(255, 255, 255, 0.05);
}

[data-theme="dark"] .offer-filter-tab {
    color: rgba(255, 255, 255, 0.6);
}

[data-theme="dark"] .offer-filter-tab:hover {
    color: rgba(255, 255, 255, 0.9);
}

[data-theme="dark"] .offer-filter-tab.active {
    background: rgba(240, 147, 251, 0.15);
    color: #f093fb;
    box-shadow: none;
}

[data-theme="dark"] .offer-empty-text {
    color: rgba(255, 255, 255, 0.6);
}
```

> **Touch target:** `min-height: 44px` na `.offer-filter-tab` spełnia wytyczną mobilną (min 44px). Na desktopie pill pozostaje kompaktowy wizualnie dzięki wewnętrznemu paddingowi.

- [ ] **Step 2: Weryfikacja manualna — light i dark**

Otwórz dashboard. Sprawdź:
- Light mode: zakładki jako pill, aktywna pomarańczowa na jasnym tle, nieaktywna szara.
- Dark mode (przełącz motyw): aktywna różowa `#f093fb` na półprzezroczystym tle, czytelna.
- Mobile (DevTools responsive ≤768px): zakładki czytelne, dotykalne (44px), zawijają się pod tytuł jeśli ciasno.
- Pusty stan: wyśrodkowany, stonowany tekst w obu trybach.

- [ ] **Step 3: Commit**

```bash
git add static/css/pages/client/dashboard.css
git commit -m "style(client): zakładki Bieżące/Zamknięte i pusty stan (light + dark)"
```

---

## Task 7: Weryfikacja końcowa całości

- [ ] **Step 1: Scenariusze danych**

Przetestuj na lokalnym serwerze (`http://localhost:5001`) cztery stany danych (przygotuj przez panel admina / DB):
1. **Mieszane** (bieżące + zamknięte): obie zakładki mają zawartość, „Pokaż więcej" na bieżących.
2. **Tylko bieżące**: zakładka Zamknięte pokazuje pusty komunikat.
3. **Tylko zamknięte**: widget widoczny, domyślna zakładka Bieżące pokazuje pusty komunikat; po kliknięciu Zamknięte — lista.
4. **Zero stron**: cały widget ukryty.

- [ ] **Step 2: Cache i brak zbędnych requestów**

DevTools → Network. Przełącz Bieżące→Zamknięte→Bieżące→Zamknięte. Expected: tylko PIERWSZE wejście na każdą zakładkę generuje request `?filter=...`; powroty renderują z cache (brak nowych requestów). Przeładowanie strony (F5) resetuje do zakładki Bieżące.

- [ ] **Step 3: Regresja istniejących funkcji**

Potwierdź, że nadal działają: wykres zamówień + zmiana okresu, lazy-loading ostatnich zamówień, widget odznak, modal macierzy setów, countdown/timing stron. Konsola bez błędów.

- [ ] **Step 4: Light/dark + mobile**

Sprawdź cały widget w obu motywach i w widoku mobilnym (karty zamiast tabeli, touch targety).

- [ ] **Step 5: Final commit (jeśli były poprawki)**

```bash
git add -A
git commit -m "test(client): weryfikacja przełącznika stron sprzedaży"
```

---

## Self-Review (wykonane przez autora planu)

**Spec coverage:**
- Definicje current/closed → Task 1 ✓
- Backend filtruje przez `?filter` → Task 2 ✓
- Domyślnie bieżące server-side → Task 2 (dashboard) + Task 4 (warunek) ✓
- Cache frontend bez ponownego fetcha → Task 5 (tabCache) + Task 7 Step 2 ✓
- Pusty stan obu zakładek, przełącznik widoczny → Task 4 + Task 5 Step 8 ✓
- Widget widoczny gdy ≥1 strona → Task 2 (`has_any`) + Task 4 Step 1 ✓
- Wydzielenie inline JS do pliku → Task 3 ✓
- Style light + dark, touch 44px → Task 6 ✓

**Placeholder scan:** Brak TBD/TODO/„handle edge cases". Każdy krok z kodem ma pełny kod.

**Type/identifier consistency:** `filter_offer_pages(pages, filter_type)` spójne w Task 1/2. Klucze słownika `offer_pages` (`has_any`/`has_current`/`has_closed`) spójne między Task 2 (routes) a Task 4 (template). Funkcje JS `renderPages`/`syncShowMore`/`switchTab`/`fetchTabData` spójne w Task 5. Selektory `.offer-empty-row`/`.offer-card-empty`/`.offer-empty-text`/`.offer-filter-tab` spójne między Task 4 (HTML), Task 5 (JS), Task 6 (CSS).

**Ryzyko do pilnowania przy wykonaniu:** Task 3 (wydzielenie JS) to największy punkt regresji — wykonać ostrożnie, zweryfikować dashboard 1:1 przed Task 5. Deklaracja `badgesEl` w achievements (Task 3 Step 3) wymaga uwagi, by nie zdublować `var`.
