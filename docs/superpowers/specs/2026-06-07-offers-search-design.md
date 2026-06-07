# Szukajka na liście stron sprzedaży (`/admin/offers`)

**Data:** 2026-06-07
**Branch:** `feature/offers-search`
**Status:** zatwierdzony projekt, gotowy do planu implementacji

## Cel

Dodać pole wyszukiwania na stronie `/admin/offers`, które **filtruje już
wyrenderowane** strony sprzedaży po nazwie, na żywo, bez przeładowania i bez
zapytań do serwera. Filtr działa na wszystkich rodzajach stron (`exclusive`,
`preorder`) — lista jest wspólna i płaska, więc dzieje się to automatycznie.

To NIE jest dropdown z listą wyników. To filtr ukrywający/pokazujący elementy,
które już są na stronie.

## Kontekst

- Route: `offers_list` w `modules/admin/offers.py` — renderuje
  `admin/offers/list.html` z płaską listą wszystkich `OfferPage`.
- Template renderuje listę w **dwóch równoległych reprezentacjach**:
  - mobile cards: `.offer-card` z nazwą w `.offer-card-title`,
  - desktop table: `<tr>` z nazwą w `.page-name-link`.
  - O tym, która reprezentacja jest widoczna, decyduje CSS (breakpoint).
- Nazwa to zwykły `{{ page.name }}`.
- Komponent `searchable-select.js` z pagebuildera to dropdown filtrujący opcje
  `<select>` — celowo NIE używamy go tutaj.
- Brak zmian w bazie i routcie → **żadnej migracji**.

## Podejście

Czysto klienckie filtrowanie (wariant A z brainstormu). Świadomie ograniczone do
tej jednej strony — bez wydzielania reużywalnego komponentu.

## Zmiany

### 1. HTML — `templates/admin/offers/list.html`

- Nowy blok `.offer-search-bar` (pełnej szerokości) wstawiony **między
  `.stats-row` (kończy się ~linia 53) a `{% if pages %}` (~linia 56)**,
  renderowany tylko gdy `pages` istnieją. Zawiera ikonę lupy (inline SVG, jak
  pozostałe ikony na stronie) oraz:
  ```html
  <input type="text" id="offerSearchInput"
         placeholder="Szukaj strony po nazwie...">
  ```
- Do każdej karty mobile (`.offer-card`) i każdego wiersza tabeli (`<tr>`)
  dodajemy `data-search-name="{{ page.name|lower }}"` — wspólny hak filtrowania
  obu reprezentacji naraz.
- Element komunikatu braku wyników `.offer-search-empty` (domyślnie ukryty),
  wstawiony raz po obu reprezentacjach listy. Treść: `Brak stron pasujących do
  „<fraza>"`. Fraza wstrzykiwana przez JS (`textContent`, nie `innerHTML` —
  bezpieczeństwo).

### 2. JS — `static/js/pages/admin/offer-list.js`

- Nowa funkcja `initializeOfferSearch()` dopięta do istniejącego
  `DOMContentLoaded`.
- Guard: jeśli brak `#offerSearchInput`, funkcja wychodzi (plik może być
  współdzielony — nie psuje innych stron).
- Normalizacja frazy: `trim()` + `toLowerCase()` + usunięcie ogonków
  (`normalize('NFD').replace(/\p{Diacritic}/gu, '')`), żeby „lacie" znajdowało
  „Łacie". Ta sama normalizacja stosowana do `data-search-name` przy
  porównaniu.
- Na zdarzenie `input`: przelot po wszystkich `[data-search-name]`, porównanie
  `includes`, toggle widoczności przez klasę `.is-hidden` (która ustawia
  `display: none`).
- Po przefiltrowaniu liczone są widoczne elementy. Jeśli 0 — pokazujemy
  `.offer-search-empty` z wpisaną frazą i chowamy kontenery listy
  (`.offer-cards-mobile`, kontener tabeli); w przeciwnym razie chowamy
  komunikat i pokazujemy kontenery.
- Pusta fraza = reset: wszystko widoczne, komunikat ukryty.

### 3. CSS — `static/css/pages/admin/offer-list.css`

- Style `.offer-search-bar` (kontener), pola input, ikony lupy oraz
  `.offer-search-empty`.
- **Light mode + dark mode** (`[data-theme="dark"]`) zgodnie z paletą
  glassmorphism z CLAUDE.md (tła `rgba(255,255,255,0.05)`, obramowania
  `rgba(240,147,251,0.15)`, akcent `#f093fb`, blur).
- Style specyficzne dla strony → `offer-list.css` (to nie modal, więc NIE
  `modals.css`).
- Klasa `.is-hidden { display: none; }` (jeśli jeszcze nie istnieje na stronie).

## Świadomie pominięte (YAGNI)

- Liczniki w `.stats-row` zostają niezmienione (pokazują sumy globalne, nie
  przefiltrowane).
- Brak debounce — lista jest mała, `input` w zupełności wystarcza.
- Brak zapamiętywania frazy w localStorage.
- Brak zmian w bazie, modelu i routcie → brak migracji.
- Brak wydzielania reużywalnego komponentu filtra (wariant C odrzucony).

## Kryteria sukcesu

- Wpisanie fragmentu nazwy ukrywa wszystkie strony, które go nie zawierają,
  pokazuje pasujące — na żywo, na desktopie i mobile.
- Wyszukiwanie ignoruje wielkość liter i polskie ogonki.
- Brak trafień → czytelny komunikat z wpisaną frazą.
- Wyczyszczenie pola przywraca pełną listę.
- Poprawny wygląd w light i dark mode.
- Brak przeładowania strony, brak zapytań do serwera, brak migracji.
