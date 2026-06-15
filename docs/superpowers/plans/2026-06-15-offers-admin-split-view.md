# Podział widoku `/admin/offers` na „Bieżące" / „Zamknięte" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Podzielić listę stron sprzedaży w panelu admina na dwie zakładki — „Bieżące" (wszystko oprócz całkowicie zamkniętych) i „Zamknięte" (`is_fully_closed`) — z sortowaniem po statusie, a wewnątrz statusu po dacie rozpoczęcia (DESC, NULL-e na końcu).

**Architecture:** Sortowanie i podział to czysta funkcja `split_and_sort_offer_pages()` w `modules/admin/offers.py` (testowalna duck-typingiem), wpięta w route `offers_list()`. Szablon `list.html` zyskuje nawigację zakładek (reuse istniejącej infrastruktury `initializeOfferTabs` z `offer-list.js` + gotowego CSS `.offer-tab-*`) i dwa panele, a powtarzalny markup wiersza tabeli i karty mobile zostaje wydzielony do makr w `templates/admin/offers/_list_items.html`. Drobna zmiana w JS rozwiązuje zduplikowany `#selectAll` (przejście na selektor po klasie).

**Tech Stack:** Flask + Jinja2 (makra, `import ... with context`), vanilla JS, CSS custom properties. **Bez zmian w bazie / migracji.**

---

## Decyzje wykonawcze (rozstrzygnięte)

- **Makra w osobnym pliku** `_list_items.html` (import `with context`), nie inline.
- **Puste stany pojedynczej zakładki = lekki tekst** (nie pełny empty-state z ikoną). Globalny empty-state z ikoną zostaje tylko gdy nie ma żadnych stron.
- **Definicje:** Zamknięte = `is_fully_closed == True`; Bieżące = reszta. Kolejność statusów: `active → paused → scheduled → draft → ended`. Data: `starts_at` DESC, `NULL` na końcu grupy.

## File Structure

| Plik | Rola | Akcja |
|---|---|---|
| `modules/admin/offers.py` | `split_and_sort_offer_pages()` + wpięcie w `offers_list()` | Modify |
| `tests/test_admin_offers_split.py` | Testy funkcji podziału/sortowania (duck typing, bez DB) | Create |
| `templates/admin/offers/_list_items.html` | Makra `offer_table(pages, tab_id)` i `offer_mobile_cards(pages)` | Create |
| `templates/admin/offers/list.html` | Nawigacja zakładek, dwa panele, puste stany per zakładka, import makr | Modify |
| `static/js/pages/admin/offer-list.js` | Obsługa wielu `.offer-select-all`; czyszczenie zaznaczenia przy zmianie zakładki | Modify |
| `static/css/pages/admin/offer-list.css` | Styl `.offer-tab-empty` (light + dark) | Modify |

## Uruchamianie testów

Z pamięci projektu: gołe `pytest` pada (`No module named 'app'`). Używaj **`python -m pytest`** z katalogu repo.

---

## Task 1: Funkcja `split_and_sort_offer_pages()`

**Files:**
- Modify: `modules/admin/offers.py` (po imporcie, przed pierwszym route — ~linia 16, za `import json`)
- Test: `tests/test_admin_offers_split.py`

- [ ] **Step 1: Napisz failing test**

Utwórz `tests/test_admin_offers_split.py`. Atrapy (duck typing — funkcja czyta tylko `.status`, `.is_fully_closed`, `.starts_at`), bez bazy:

```python
from datetime import datetime

from modules.admin.offers import split_and_sort_offer_pages


class FakePage:
    def __init__(self, name, status, is_fully_closed=False, starts_at=None):
        self.name = name
        self.status = status
        self.is_fully_closed = is_fully_closed
        self.starts_at = starts_at


def _names(pages):
    return [p.name for p in pages]


def test_closed_is_only_fully_closed():
    pages = [
        FakePage('ended_closed', 'ended', is_fully_closed=True),
        FakePage('ended_open', 'ended', is_fully_closed=False),
        FakePage('active', 'active'),
    ]
    current, closed = split_and_sort_offer_pages(pages)
    assert _names(closed) == ['ended_closed']
    # ended bez is_fully_closed zostaje w bieżących
    assert set(_names(current)) == {'ended_open', 'active'}


def test_status_order_in_current():
    pages = [
        FakePage('d', 'draft'),
        FakePage('e', 'ended'),
        FakePage('a', 'active'),
        FakePage('p', 'paused'),
        FakePage('s', 'scheduled'),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['a', 'p', 's', 'd', 'e']


def test_date_desc_within_status():
    pages = [
        FakePage('old', 'active', starts_at=datetime(2026, 1, 1, 10, 0)),
        FakePage('new', 'active', starts_at=datetime(2026, 6, 1, 10, 0)),
        FakePage('mid', 'active', starts_at=datetime(2026, 3, 1, 10, 0)),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['new', 'mid', 'old']


def test_null_starts_at_last_within_status():
    pages = [
        FakePage('nodate', 'active', starts_at=None),
        FakePage('dated', 'active', starts_at=datetime(2026, 5, 1, 10, 0)),
    ]
    current, _ = split_and_sort_offer_pages(pages)
    assert _names(current) == ['dated', 'nodate']


def test_closed_sorted_by_date_desc():
    pages = [
        FakePage('c_old', 'ended', is_fully_closed=True,
                 starts_at=datetime(2026, 1, 1, 10, 0)),
        FakePage('c_new', 'ended', is_fully_closed=True,
                 starts_at=datetime(2026, 6, 1, 10, 0)),
    ]
    _, closed = split_and_sort_offer_pages(pages)
    assert _names(closed) == ['c_new', 'c_old']
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `python -m pytest tests/test_admin_offers_split.py -v`
Expected: FAIL — `ImportError: cannot import name 'split_and_sort_offer_pages'`

- [ ] **Step 3: Zaimplementuj funkcję**

W `modules/admin/offers.py`, bezpośrednio po `import json` (linia 15) a przed komentarzem `# Lista stron Offers`, dodaj:

```python


# Kolejność statusów w zakładce „Bieżące" (od góry).
_OFFER_STATUS_ORDER = {'active': 0, 'paused': 1, 'scheduled': 2, 'draft': 3, 'ended': 4}


def split_and_sort_offer_pages(pages):
    """
    Dzieli strony ofertowe na (current_pages, closed_pages) i sortuje obie grupy.

    - closed  = strony całkowicie zamknięte (is_fully_closed == True)
    - current = cała reszta (draft/scheduled/active/paused oraz ended-niezamknięte)

    Sortowanie w obu grupach:
    1) priorytet statusu wg _OFFER_STATUS_ORDER,
    2) strony bez starts_at (NULL) na końcu grupy,
    3) starts_at malejąco (najnowsze pierwsze).
    """
    def sort_key(p):
        return (
            _OFFER_STATUS_ORDER.get(p.status, 99),
            p.starts_at is None,
            -p.starts_at.timestamp() if p.starts_at else 0.0,
        )

    closed = sorted([p for p in pages if p.is_fully_closed], key=sort_key)
    current = sorted([p for p in pages if not p.is_fully_closed], key=sort_key)
    return current, closed
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `python -m pytest tests/test_admin_offers_split.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add modules/admin/offers.py tests/test_admin_offers_split.py
git commit -m "feat(admin): split_and_sort_offer_pages dla podziału stron na bieżące/zamknięte"
```

---

## Task 2: Wpięcie funkcji w route `offers_list()`

**Files:**
- Modify: `modules/admin/offers.py` — `offers_list()` (linie 22-37)

- [ ] **Step 1: Zmodyfikuj `offers_list()`**

Zastąp całe ciało funkcji `offers_list()` (linie 25-37, od docstringa do `)`) tym:

```python
    """Lista wszystkich stron sprzedaży"""
    pages = OfferPage.query.order_by(OfferPage.created_at.desc()).all()

    # Automatyczna aktualizacja statusów (scheduled->active, active->ended)
    for page in pages:
        page.check_and_update_status()

    # Podział na zakładki + sortowanie PO aktualizacji statusów (zmienia status).
    current_pages, closed_pages = split_and_sort_offer_pages(pages)

    return render_template(
        'admin/offers/list.html',
        title='Strony sprzedaży',
        pages=pages,                  # globalne statystyki + warunek widoczności
        current_pages=current_pages,
        closed_pages=closed_pages,
    )
```

> `pages` zostaje przekazane, bo pigułki statystyk u góry (`pages|selectattr(...)`) i warunek `{% if pages %}` nadal go używają.

- [ ] **Step 2: Weryfikacja — brak błędu importu/renderu**

Run: `python -c "import modules.admin.offers"`
Expected: brak błędu (kod się parsuje, funkcja użyta poprawnie).

> Pełna weryfikacja wizualna dopiero po Tasku 4 (szablon używa nowych zmiennych). Tu sprawdzamy tylko, że route się nie wywala składniowo.

- [ ] **Step 3: Commit**

```bash
git add modules/admin/offers.py
git commit -m "feat(admin): offers_list przekazuje current_pages/closed_pages do szablonu"
```

---

## Task 3: Wydziel makra wiersza tabeli i karty mobile do `_list_items.html`

> Czysta ekstrakcja istniejącego markupu (bez zmian funkcjonalnych) do makr, żeby zakładki nie duplikowały ~350 linii. Pętle w obu blokach już używają zmiennej `page` w `{% for page in pages %}`, więc makro z argumentem `pages` jest drop-in.

**Files:**
- Create: `templates/admin/offers/_list_items.html`

- [ ] **Step 1: Utwórz `_list_items.html` ze szkieletem dwóch makr**

Utwórz plik `templates/admin/offers/_list_items.html` o strukturze:

```jinja
{# Makra listy stron sprzedaży. Importowane w list.html z `with context`,
   aby current_user / csrf_token() / url_for / filtry format_date były dostępne. #}

{% macro offer_mobile_cards(pages) %}
<div class="offer-cards-mobile">
    {% for page in pages %}
    {# ⟪WKLEJ TU zawartość pętli kart mobile⟫ #}
    {% endfor %}
</div>
{% endmacro %}

{% macro offer_table(pages, tab_id) %}
<div class="table-container">
    <div class="table-responsive">
        <table class="data-table offer-table">
            <thead>
                <tr>
                    <th class="offer-checkbox-col">
                        <input type="checkbox" id="selectAll-{{ tab_id }}" class="offer-select-all" aria-label="Zaznacz wszystkie">
                    </th>
                    <th>Nazwa</th>
                    <th>Typ</th>
                    <th>Typ wysyłki</th>
                    <th>Status</th>
                    <th>Utworzono</th>
                    <th>Rozpoczęcie</th>
                    <th>Zakończenie</th>
                    <th>Termin płatności</th>
                    <th>Akcje</th>
                </tr>
            </thead>
            <tbody>
                {% for page in pages %}
                {# ⟪WKLEJ TU zawartość pętli wierszy tabeli⟫ #}
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endmacro %}
```

- [ ] **Step 2: Wklej zawartość pętli kart mobile**

Z `templates/admin/offers/list.html` skopiuj **dokładnie** zawartość pętli kart — od `<div class="offer-card" data-search-name="{{ page.name }}">` (linia 74) do zamykającego ją `</div>` (linia 219, tuż przed `{% endfor %}`). Wklej ją w miejsce `{# ⟪WKLEJ TU zawartość pętli kart mobile⟫ #}` w makrze `offer_mobile_cards`. Nie zmieniaj niczego w środku.

- [ ] **Step 3: Wklej zawartość pętli wierszy tabeli**

Z `list.html` skopiuj **dokładnie** zawartość pętli wierszy — od `<tr data-search-name="{{ page.name }}">` (linia 247) do zamykającego `</tr>` (linia 460, tuż przed `{% endfor %}`). Wklej w miejsce `{# ⟪WKLEJ TU zawartość pętli wierszy tabeli⟫ #}` w makrze `offer_table`. Nie zmieniaj niczego w środku.

- [ ] **Step 4: Weryfikacja składni szablonu**

Run: `python -c "from app import create_app; app=create_app(); app.jinja_env.get_template('admin/offers/_list_items.html'); print('OK')"`
Expected: `OK` (szablon się kompiluje; makra parsują się poprawnie).

> Jeśli `create_app` wymaga argumentów/konfiguracji, użyj wzorca z `tests/conftest.py` do zbudowania aplikacji. Cel: potwierdzić, że plik makr kompiluje się w Jinja.

- [ ] **Step 5: Commit**

```bash
git add templates/admin/offers/_list_items.html
git commit -m "refactor(admin): wydziel makra wiersza/karty stron sprzedaży do _list_items.html"
```

---

## Task 4: Przebuduj `list.html` na dwie zakładki

**Files:**
- Modify: `templates/admin/offers/list.html` (blok `{% block content %}`, linie 10-480)

- [ ] **Step 1: Dodaj import makr na początku bloku content**

Tuż po `{% block content %}` (linia 10), jako pierwsza linia bloku, dodaj:

```jinja
{% import "admin/offers/_list_items.html" as items with context %}
```

- [ ] **Step 2: Zastąp region treści (mobile cards + tabela) zakładkami**

W `list.html` usuń cały dotychczasowy region renderujący listę — **od** `<!-- Mobile Cards -->` (linia 70) **do** zamknięcia `</div>` kontenera tabeli wraz z jego empty-state (linia 478, `{% endif %}` + `</div>` zamykające `.table-container`). Zachowaj nad nim: header ze statystykami (linie 12-47) i toolbar z wyszukiwarką (linie 49-68). Zachowaj pod nim: modale (od linii 482).

W miejsce usuniętego regionu wstaw:

```jinja
    {% if pages %}
    <!-- Nawigacja zakładek (reuse initializeOfferTabs z offer-list.js) -->
    <div class="offer-tabs-navigation">
        <button type="button" class="offer-tab-button offer-tab-active" data-tab="tab-current">
            Bieżące ({{ current_pages|length }})
        </button>
        <button type="button" class="offer-tab-button" data-tab="tab-closed">
            Zamknięte ({{ closed_pages|length }})
        </button>
    </div>

    <div class="offer-tabs-content">
        <div id="tab-current" class="offer-tab-panel offer-tab-active">
            {% if current_pages %}
                {{ items.offer_mobile_cards(current_pages) }}
                {{ items.offer_table(current_pages, 'current') }}
            {% else %}
                <div class="offer-tab-empty">Brak bieżących stron sprzedaży</div>
            {% endif %}
        </div>
        <div id="tab-closed" class="offer-tab-panel">
            {% if closed_pages %}
                {{ items.offer_mobile_cards(closed_pages) }}
                {{ items.offer_table(closed_pages, 'closed') }}
            {% else %}
                <div class="offer-tab-empty">Brak zamkniętych stron sprzedaży</div>
            {% endif %}
        </div>
    </div>
    {% else %}
    <div class="table-container">
        <div class="empty-state">
            <svg width="64" height="64" viewBox="0 0 16 16" fill="currentColor" class="empty-icon">
                <path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5L14 4.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5h-2z"/>
                <path d="M8 6.5a.5.5 0 0 1 .5.5v1.5H10a.5.5 0 0 1 0 1H8.5V11a.5.5 0 0 1-1 0V9.5H6a.5.5 0 0 1 0-1h1.5V7a.5.5 0 0 1 .5-.5z"/>
            </svg>
            <h3>Brak stron sprzedaży</h3>
            <p>Utwórz pierwszą stronę z formularzem zamówień pre-order.</p>
            <button type="button" class="btn btn-primary" onclick="openCreateModal()">
                Dodaj stronę
            </button>
        </div>
    </div>
    {% endif %}
```

> Mobile vs desktop: makra renderują oba widoki (`.offer-cards-mobile` + `.table-container`), a istniejący CSS pokazuje właściwy per breakpoint — bez zmian. Lekki komunikat `.offer-tab-empty` jest widoczny w obu trybach.

- [ ] **Step 3: Sprawdź, że stary pojedynczy `<div class="offer-search-empty">` i toolbar zostały**

Upewnij się, że linie toolbara (49-68) wraz z `<div class="offer-search-empty is-hidden" id="offerSearchEmpty"></div>` (linia 67) nie zostały przypadkiem usunięte — mają zostać nad nawigacją zakładek.

- [ ] **Step 4: Weryfikacja manualna w przeglądarce**

Uruchom serwer lokalnie (`http://localhost:5001`), zaloguj jako admin, otwórz `/admin/offers`. Expected:
- Widać dwie zakładki z licznikami; „Bieżące" aktywna domyślnie.
- W „Bieżące" strony w kolejności: active → paused → scheduled → draft → ended; wewnątrz statusu data malejąco; strony bez daty na końcu grupy.
- W „Zamknięte" tylko strony z badge „Zamknięta" (`is_fully_closed`), sortowane datą malejąco.
- Przełączanie zakładek działa (JS `initializeOfferTabs`), wybór zapamiętany po F5 (localStorage).
- Wyszukiwarka filtruje w aktywnej zakładce.
- Konsola bez błędów JS.

> Bulk select „zaznacz wszystkie" może jeszcze działać niepoprawnie z powodu zduplikowanego id — to naprawia Task 5. Pojedyncze checkboxy i pasek akcji powinny działać.

- [ ] **Step 5: Commit**

```bash
git add templates/admin/offers/list.html
git commit -m "feat(admin): podziel listę stron sprzedaży na zakładki Bieżące/Zamknięte"
```

---

## Task 5: JS — wiele `.offer-select-all` + czyszczenie zaznaczenia przy zmianie zakładki

**Files:**
- Modify: `static/js/pages/admin/offer-list.js` — `initializeBulkActions()` (linie 461-553)

- [ ] **Step 1: Zamień pojedynczy `selectAll` na kolekcję po klasie**

W `initializeBulkActions()` zamień linię 465:

```javascript
    const selectAll = document.getElementById('selectAll');
```
na:
```javascript
    // Dwie zakładki → dwa master-checkboxy (#selectAll-current / #selectAll-closed).
    // Operujemy po klasie, nie po id.
    const selectAllBoxes = Array.from(document.querySelectorAll('.offer-select-all'));
```

- [ ] **Step 2: Zaktualizuj stan master-checkboxów w `updateToolbar()`**

W `updateToolbar()` zamień blok `if (selectAll) { ... }` (linie 505-511) na:

```javascript
        if (selectAllBoxes.length) {
            const visible = getVisibleCheckboxes();
            const allChecked = visible.length > 0 && visible.every(cb => cb.checked);
            const someChecked = visible.some(cb => cb.checked);
            selectAllBoxes.forEach(box => {
                box.checked = allChecked;
                box.indeterminate = someChecked && !allChecked;
            });
        }
```

> `getVisibleCheckboxes()` zwraca tylko checkboxy aktywnej zakładki (filtr `offsetParent !== null`), więc stan master-checkboxa odzwierciedla widoczną zakładkę.

- [ ] **Step 3: Podłącz listener `change` do każdego master-checkboxa**

Zamień blok `if (selectAll) { selectAll.addEventListener('change', ...) }` (linie 538-546) na:

```javascript
    selectAllBoxes.forEach(box => {
        box.addEventListener('change', function() {
            getVisibleCheckboxes().forEach(cb => {
                cb.checked = this.checked;
                syncRowHighlight(cb);
            });
            updateToolbar();
        });
    });
```

- [ ] **Step 4: Wyczyść zaznaczenie przy zmianie zakładki**

Na końcu `initializeBulkActions()`, tuż przed zamykającą klamrą funkcji (po istniejącym kodzie obsługi szukajki, ~linia 560), dodaj:

```javascript
    // Zmiana zakładki: wyczyść zaznaczenie z poprzedniej zakładki, by pasek
    // akcji masowych nie operował na ukrytych (innej zakładki) stronach.
    document.querySelectorAll('.offer-tab-button').forEach(tabBtn => {
        tabBtn.addEventListener('click', function() {
            document.querySelectorAll('.offer-checkbox').forEach(cb => {
                cb.checked = false;
                syncRowHighlight(cb);
            });
            updateToolbar();
        });
    });
```

- [ ] **Step 5: Weryfikacja manualna**

Serwer lokalny, `/admin/offers`. Sprawdź:
- W „Bieżące": „zaznacz wszystkie" zaznacza tylko widoczne wiersze tej zakładki; pasek akcji masowych pokazuje poprawny licznik.
- Przełączenie na „Zamknięte" czyści zaznaczenie i ukrywa pasek; własny master-checkbox zakładki działa niezależnie.
- Filtrowanie szukajką + „zaznacz wszystkie" liczy tylko widoczne (niezhidowane) wiersze.
- Konsola bez błędów.

- [ ] **Step 6: Commit**

```bash
git add static/js/pages/admin/offer-list.js
git commit -m "fix(admin): obsłuż dwa master-checkboxy zakładek i czyść zaznaczenie przy zmianie"
```

---

## Task 6: CSS — styl lekkiego pustego stanu zakładki (light + dark)

**Files:**
- Modify: `static/css/pages/admin/offer-list.css` (dodać po bloku tabów, ~po linii 1668)

- [ ] **Step 1: Dodaj styl `.offer-tab-empty`**

W `static/css/pages/admin/offer-list.css`, po regule `.offer-tab-panel.offer-tab-active { ... }` (~linia 1668), dodaj:

```css
/* Lekki pusty stan pojedynczej zakładki (Bieżące/Zamknięte) */
.offer-tab-empty {
    text-align: center;
    padding: var(--space-8, 32px) var(--space-4, 16px);
    color: var(--text-secondary, #666);
    font-size: var(--text-sm, 0.875rem);
}

[data-theme="dark"] .offer-tab-empty {
    color: rgba(255, 255, 255, 0.6);
}
```

> Wartości po przecinku to fallbacki na wypadek braku zmiennej. Jeśli `offer-list.css` konsekwentnie używa konkretnych zmiennych (np. `--text-secondary`), dopasuj się do nich; fallbacki zostaw.

- [ ] **Step 2: Weryfikacja manualna — light i dark**

Przygotuj stan, w którym jedna zakładka jest pusta (np. brak zamkniętych). Otwórz `/admin/offers`:
- Light mode: komunikat wyśrodkowany, stonowany.
- Dark mode (przełącz motyw): tekst czytelny w palecie ciemnej.

- [ ] **Step 3: Commit**

```bash
git add static/css/pages/admin/offer-list.css
git commit -m "style(admin): lekki pusty stan zakładek stron sprzedaży (light + dark)"
```

---

## Task 7: Weryfikacja końcowa

- [ ] **Step 1: Testy jednostkowe nadal zielone**

Run: `python -m pytest tests/test_admin_offers_split.py -v`
Expected: PASS (5 passed).

- [ ] **Step 2: Scenariusze danych w przeglądarce**

Na lokalnym serwerze przetestuj:
1. **Mieszane** (bieżące + zamknięte): obie zakładki mają zawartość, liczniki poprawne, sortowanie zgodne z ustaleniami.
2. **Tylko bieżące**: „Zamknięte" pokazuje „Brak zamkniętych stron sprzedaży".
3. **Tylko zamknięte**: „Bieżące" (domyślna) pokazuje „Brak bieżących stron sprzedaży"; po kliknięciu „Zamknięte" — lista.
4. **Zero stron**: globalny empty-state z ikoną; brak zakładek i toolbara.

- [ ] **Step 3: Regresja istniejących funkcji**

Potwierdź: pojedyncze akcje statusów (Aktywuj/Wstrzymaj/Zakończ/Wznów), zamknij całkowicie (modal), duplikuj, usuń (modal), kopiuj link, LIVE dashboard, raporty (live/podsumowanie), pasek akcji masowych (Ustaw daty / Aktywuj / Zakończ / Zamknij / Usuń) — działają w obu zakładkach. Mobile (karty) i desktop (tabela). Konsola bez błędów.

- [ ] **Step 4: Light/dark + zapamiętywanie zakładki**

Sprawdź oba motywy; po przełączeniu na „Zamknięte" i F5 zakładka pozostaje wybrana (localStorage `offerActiveTab`).

- [ ] **Step 5: Final commit (jeśli były poprawki)**

```bash
git add -A
git commit -m "test(admin): weryfikacja podziału stron sprzedaży na zakładki"
```

---

## Self-Review (autor planu)

**Spec coverage:**
- Podział current/closed wg `is_fully_closed` → Task 1 ✓
- Sortowanie status + data DESC + NULL-e na końcu → Task 1 (testy) ✓
- Wpięcie w route po `check_and_update_status` → Task 2 ✓
- Zakładki (reuse JS+CSS) + dwa panele → Task 4 ✓
- Makra bez duplikacji markupu → Task 3 ✓
- Statystyki globalne zachowane (`pages`) → Task 2 + Task 4 (header niezmieniony) ✓
- Puste stany: globalny vs per-zakładka lekki → Task 4 + Task 6 ✓
- Zduplikowany `#selectAll` → Task 5 ✓
- Wyszukiwarka/bulk-select zachowane → Task 4/5 (weryfikacja) ✓
- Light + dark → Task 6 ✓
- Bez migracji → potwierdzone (brak zmian modeli) ✓

**Placeholder scan:** Markery `⟪WKLEJ TU⟫` w Tasku 3 są świadome — to ekstrakcja istniejącego, dużego bloku markupu (kopiowanie 1:1 wskazanych linii), nie nowy kod. Wszystkie kroki z nowym kodem mają pełny kod.

**Type/identifier consistency:** `split_and_sort_offer_pages` zwraca `(current, closed)` — spójnie używane w Task 1/2. Makra `offer_table(pages, tab_id)` / `offer_mobile_cards(pages)` spójne między Task 3 (definicja) a Task 4 (wywołania). Selektory `.offer-select-all`, `.offer-tab-button`, `.offer-tab-empty`, id `selectAll-current`/`selectAll-closed` spójne między Task 3 (HTML), Task 4 (HTML), Task 5 (JS), Task 6 (CSS). Klasy zakładek `.offer-tab-button`/`.offer-tab-panel`/`offer-tab-active` zgodne z istniejącym JS `initializeOfferTabs` i CSS.

**Ryzyko przy wykonaniu:** Task 3/4 to największy punkt regresji (przeniesienie ~350 linii markupu). Wykonać ostrożnie, zweryfikować 1:1 przed Task 5. Przy ekstrakcji uważać, by nie pominąć/zdublować zamykających tagów pętli.
