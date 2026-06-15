# Podział widoku stron sprzedaży na „Bieżące" / „Zamknięte"

**Data:** 2026-06-15
**Strona:** `/admin/offers` (lista stron sprzedaży)
**Typ zmiany:** UI + drobna logika sortowania w route. **Bez migracji bazy** (zmiana czysto prezentacyjna, korzysta z istniejących pól).

## Uwaga: to NIE jest widget klienta

Istnieje osobna, podobnie nazwana funkcja na **dashboardzie klienta** (`/client`, widget „Strony sprzedaży", plan `docs/superpowers/plans/2026-06-05-sales-pages-current-closed-toggle.md`). Tam „Zamknięte" = `status == 'ended'` (łącznie z `is_fully_closed`), z lazy-loadingiem przez API. **Ten spec dotyczy panelu admina (`/admin/offers`)** — inna powierzchnia, węższa definicja „Zamknięte" (tylko `is_fully_closed`), pełny SSR bez API/paginacji.

## Cel

Podzielić listę stron sprzedaży na dwie zakładki:
- **Bieżące** — wszystkie strony oprócz całkowicie zamkniętych.
- **Zamknięte** — wyłącznie strony z `is_fully_closed = True`.

Dodatkowo: sortowanie po statusie, a wewnątrz statusu po dacie rozpoczęcia sprzedaży.

## Decyzje (ustalone z użytkownikiem)

1. **Definicja „Zamknięte"** = tylko `OfferPage.is_fully_closed == True`. Strony o statusie `ended`, które **nie** są całkowicie zamknięte, zostają w „Bieżące" (są jeszcze wznawialne / do dokończenia).
2. **Kolejność statusów** w „Bieżące" (grupy od góry): `active → paused → scheduled → draft → ended`.
3. **Kierunek daty** wewnątrz statusu: `starts_at` malejąco (najnowsze pierwsze); strony bez daty (`NULL`) na końcu grupy.
4. **Mechanizm UI:** zakładki — reuse istniejącej infrastruktury (JS + CSS już w repo).

## Stan istniejący (co już jest gotowe)

- **JS:** `static/js/pages/admin/offer-list.js` → `initializeOfferTabs()` obsługuje klasy `.offer-tab-button` / `.offer-tab-panel`, przełączanie (`offer-tab-active`), zapamiętywanie aktywnej zakładki w `localStorage` (`offerActiveTab`). Funkcja jest wywoływana, ale na tej stronie nie ma jeszcze zakładek (`if (tabButtons.length === 0) return;`). **Nie wymaga zmian** — wystarczy dodać markup.
- **CSS:** `static/css/pages/admin/offer-list.css` → bloki `.offer-tabs-navigation`, `.offer-tab-button`, `.offer-tab-panel` + warianty `[data-theme="dark"]` (od ~linii 1607). **Light i dark mode już pokryte.**
- **Route:** `modules/admin/offers.py` → `offers_list()` (linia ~25) pobiera `OfferPage.query.order_by(OfferPage.created_at.desc()).all()`, wywołuje `check_and_update_status()` na każdej stronie, renderuje `admin/offers/list.html` z `pages`.
- **Szablon:** `templates/admin/offers/list.html` ma dwa równoległe renderingi tej samej listy: `.offer-cards-mobile` (karty mobile) i `.table-container` (tabela desktop), oba iterują `{% for page in pages %}`.

## Zakres prac

### A. Route — `modules/admin/offers.py`, `offers_list()`

Po pętli `check_and_update_status()` (musi być po niej — pętla zmienia statusy) podzielić i posortować w Pythonie, przekazać do szablonu dwie gotowe listy.

```python
STATUS_ORDER = {'active': 0, 'paused': 1, 'scheduled': 2, 'draft': 3, 'ended': 4}

def _sort_key(p):
    return (
        STATUS_ORDER.get(p.status, 99),       # priorytet statusu
        p.starts_at is None,                  # NULL-e na końcu grupy
        -(p.starts_at.timestamp()) if p.starts_at else 0,  # data malejąco
    )

closed_pages = sorted([p for p in pages if p.is_fully_closed], key=_sort_key)
current_pages = sorted([p for p in pages if not p.is_fully_closed], key=_sort_key)
```

Render: przekazać `current_pages` i `closed_pages` (zamiast/oprócz `pages`). `pages` pozostaje przekazane wyłącznie jeśli jest potrzebne do globalnych statystyk i empty-state (patrz niżej) — albo przekazać `total_count = len(pages)`.

Cała logika sortowania/podziału po stronie serwera (SSR). Jinja tylko renderuje.

### B. Szablon — `templates/admin/offers/list.html`

1. **Wydzielić powtarzalny markup do makr**, aby nie duplikować ~200 linii wiersza/karty dla dwóch zakładek:
   - `{% macro offer_table_rows(pages) %}` → zawartość `<tbody>` (pętla wierszy tabeli).
   - `{% macro offer_mobile_cards(pages) %}` → pętla kart mobilnych.

   Makra definiować w tym samym pliku (`{% macro %}` na górze) lub w osobnym pliku importowanym przez `{% import %}`. Preferencja: osobny plik `templates/admin/offers/_list_items.html` importowany — czystsze, ale jeśli makra używają `csrf_token()` / `current_user` / `url_for`, trzeba `{% import ... with context %}`. **Decyzja implementacyjna:** użyć `with context`, żeby globalne helpery i `current_user` były dostępne wewnątrz makr.

2. **Dodać nawigację zakładek** (przed kontentem):

```html
<div class="offer-tabs-navigation">
    <button type="button" class="offer-tab-button offer-tab-active" data-tab="tab-current">
        Bieżące ({{ current_pages|length }})
    </button>
    <button type="button" class="offer-tab-button" data-tab="tab-closed">
        Zamknięte ({{ closed_pages|length }})
    </button>
</div>
```

3. **Opakować kontent w dwa panele:**

```html
<div class="offer-tabs-content">
    <div id="tab-current" class="offer-tab-panel offer-tab-active">
        {# mobile cards + tabela, zasilane current_pages #}
    </div>
    <div id="tab-closed" class="offer-tab-panel">
        {# mobile cards + tabela, zasilane closed_pages #}
    </div>
</div>
```

   Wewnątrz każdego panelu wywołać oba makra (mobile + desktop) z odpowiednią listą.

4. **Toolbar (wyszukiwarka + „Dodaj stronę")** zostaje nad zakładkami — wspólny dla obu (wyszukiwarka filtruje przez `.is-hidden` ortogonalnie do zakładek).

5. **Pigułki statystyk** (góra) — bez zmian, pozostają globalne (podsumowują wszystkie strony). Wymaga dostępu do globalnych liczników; obecny markup używa `pages|...` — zostaje, więc route musi nadal dostarczać dane do tych liczb (np. przekazać `pages` lub policzyć liczniki w route).

### C. Stany puste

- **Brak jakichkolwiek stron** (`current_pages` i `closed_pages` puste) → globalny `empty-state` jak obecnie (i ukryć nawigację zakładek + toolbar, jak teraz przy `{% if pages %}`).
- **Pusta pojedyncza zakładka** (np. brak zamkniętych) → lekki komunikat w panelu, np. „Brak zamkniętych stron sprzedaży" / „Brak bieżących stron sprzedaży" (zamiast globalnego empty-state). Spójny wizualnie z lekkim stylem (nie pełny duży empty-state).

### D. Wyszukiwarka i bulk-select — weryfikacja (bez zmian logiki)

- **Wyszukiwarka:** filtruje `[data-search-name]` przez `.is-hidden`. Działa niezależnie od zakładek. Zweryfikować, że komunikat „brak wyników" (`#offerSearchEmpty`) zachowuje sens przy aktywnej zakładce; jeśli trzeba — drobna korekta, ale celem jest brak zmian.
- **Bulk-select:** `getVisibleCheckboxes()` filtruje `cb.offsetParent !== null`, więc checkboxy w nieaktywnym (ukrytym) panelu są automatycznie pomijane. Zweryfikować, że „zaznacz wszystkie" działa per widoczna zakładka. **Uwaga:** w tabeli jest jeden `#selectAll` (`id`) — przy dwóch panelach desktop pojawią się dwa elementy o tym samym `id`. Trzeba to rozwiązać: albo unikalne `id` per zakładka (`selectAllCurrent` / `selectAllClosed`) z dopasowaniem JS, albo zachować jeden master-checkbox. **Decyzja:** nadać unikalne `id` i zaktualizować selektor w JS (`getElementById('selectAll')` → obsługa obu). To jedyna realna zmiana w JS.

### E. CSS

- Zakładki: reuse istniejących klas — **bez nowego CSS dla samej nawigacji**.
- Komunikat pustej zakładki: jeśli brak pasującej klasy, dodać lekki styl w `offer-list.css` z wariantem `[data-theme="dark"]` (paleta glassmorphism z CLAUDE.md).

## Pliki do zmiany

| Plik | Zmiana |
|------|--------|
| `modules/admin/offers.py` | `offers_list()`: podział + sortowanie, przekazanie `current_pages` / `closed_pages` (+ dane do globalnych statystyk) |
| `templates/admin/offers/list.html` | makra dla wierszy/kart, nawigacja zakładek, dwa panele, puste stany per zakładka |
| `templates/admin/offers/_list_items.html` *(opcjonalnie)* | wydzielone makra (jeśli nie inline) |
| `static/js/pages/admin/offer-list.js` | tylko obsługa zduplikowanego `#selectAll` (unikalne id per zakładka) |
| `static/css/pages/admin/offer-list.css` | tylko styl komunikatu pustej zakładki (light + dark), jeśli brak gotowej klasy |

## Poza zakresem (YAGNI)

- Brak zmian w bazie / migracji.
- Brak zmian w logice statusów (`check_and_update_status`, close-complete itd.).
- Brak zmian w pigułkach statystyk (pozostają globalne).
- Brak filtrów/sortowania konfigurowalnego przez użytkownika — kolejność jest stała wg ustaleń.

## Testowanie

- Lokalnie (`http://localhost:5001`, XAMPP): strony w różnych statusach trafiają do właściwej zakładki; kolejność statusów i dat zgodna z ustaleniami; NULL-owe `starts_at` na końcu grupy.
- Przełączanie zakładek + zapamiętywanie w `localStorage`.
- Wyszukiwarka działa w obu zakładkach; bulk-select „zaznacz wszystkie" działa per zakładka i nie łapie ukrytego panelu.
- Light i dark mode.
- Widok mobile (karty) i desktop (tabela).
- Puste stany: brak stron w ogóle vs pusta pojedyncza zakładka.
