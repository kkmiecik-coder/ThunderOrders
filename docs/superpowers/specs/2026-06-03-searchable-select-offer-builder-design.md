# Searchable Select w Offer Builder — Design

**Data:** 2026-06-03
**Autor:** Konrad + Claude
**Status:** Zatwierdzony — gotowy do planu implementacji

---

## Cel

W pagebuilderze ofert (`offer-builder`) dropdowny grup wariantowych i produktów listują wszystkie pozycje, co przy dużej liczbie utrudnia wybór. Należy dodać **wyszukiwarkę na górze custom-dropdownu** w wybranych miejscach.

## Zakres (3 dropdowny)

| # | Dropdown (klasa) | Lokalizacja | Stan obecny |
|---|------------------|-------------|-------------|
| 1 | `.set-item-variant-group` | karta grupy wariantowej w sekcji „Set produktów" (przycisk „+ Dodaj grupę wariantową") | goły `<select>` |
| 2 | `.set-product-select` | pole „Produkt – komplet setu" | już owinięty w `.custom-select-wrapper` + `.custom-select-display` |
| 3 | `.variant-group-select` | samodzielna sekcja „Grupa wariantowa" (sekcja typu `variant_group`) | goły `<select>` |

**Poza zakresem:** pozostałe dropdowny (np. `.product-select`, `.set-item-product`, produkty w bonusach) — bez zmian.

---

## Architektura — komponent „searchable-select"

Samodzielny komponent vanilla JS + CSS działający jako **progressive enhancement** nad natywnym `<select>`:

- Natywny `<select>` pozostaje w DOM jako **źródło prawdy** (`value`, opcje, atrybuty `data-*`). Otrzymuje `pointer-events: none` — staje się ukrytym magazynem danych.
- Widoczny trigger to istniejący `.custom-select-display` (tekst zaznaczonej opcji + chevron).
- Po kliknięciu triggera otwiera się **panel** z **inputem wyszukiwarki na samej górze** + przewijalną listą opcji budowaną **na żywo** z natywnego selecta przy każdym otwarciu.
- Wybór opcji → ustawia `select.value`, wywołuje natywny event `change` i aktualizuje tekst triggera.

**Decyzje projektowe:**

- **Czytanie opcji na żywo** przy każdym otwarciu panelu — opcje są generowane dynamicznie (`updateProductDropdowns`, szablony `productOptionTemplate` / `variantGroupOptionTemplate`), więc nic nie trzeba ręcznie odświeżać.
- **Dispatch natywnego `change`** — istniejące handlery (`updateSetVariantGroupProducts`, `updateSetProductPreview`, `updateCustomSelect`) oraz `collectPageData()` działają bez zmian; komponent jest dla nich przezroczysty.
- **Event delegation na `document`** — brak per-element init; karty i sekcje dodawane dynamicznie działają automatycznie.

## Mechanika

Cała logika oparta na delegacji zdarzeń na `document`:

- Klik na `.custom-select-display` (w wrapperze zawierającym `select.searchable-select`) → otwórz / przełącz panel. Tylko **jeden panel otwarty naraz** (otwarcie nowego zamyka poprzedni).
- Wpisywanie w input wyszukiwarki → filtrowanie opcji po tekście (case-insensitive, `includes`). Opcja-placeholder z pustym `value` nie jest pokazywana na liście.
- Klik na opcję → ustawienie `select.value`, dispatch `change`, aktualizacja tekstu triggera, zamknięcie panelu.
- Klik poza panelem / `Esc` → zamknięcie.
- Strzałki ↑/↓ → przesuwanie podświetlenia po widocznych opcjach; `Enter` → wybór podświetlonej.
- Autofocus na inpucie wyszukiwarki po otwarciu panelu.
- Po otwarciu panel pokazuje pełną (niefiltrowaną) listę; input jest pusty.

## Struktura DOM (docelowa, dla każdego z 3 selectów)

```html
<div class="custom-select-wrapper">
    <select class="form-select ... searchable-select" ...>
        <option value="">Wybierz...</option>
        ...opcje...
    </select>
    <div class="custom-select-display">
        <span class="selected-text">Wybierz...</span>
        <svg>...chevron...</svg>
    </div>
    <!-- panel budowany dynamicznie przez komponent przy otwarciu -->
</div>
```

- **#2 (`.set-product-select`)** już ma tę strukturę — wystarczy dodać klasę `searchable-select` do `<select>`.
- **#1 i #3** to gołe selecty — w szablonach HTML (stringi w `offer-builder.js`) trzeba owinąć je w `.custom-select-wrapper` + `.custom-select-display` i dodać klasę `searchable-select`.

Panel (wstrzykiwany przez komponent):

```html
<div class="searchable-select-panel">
    <div class="searchable-select-search">
        <input type="text" class="searchable-select-input" placeholder="Szukaj...">
    </div>
    <ul class="searchable-select-options">
        <li class="searchable-select-option" data-value="...">Tekst opcji</li>
        ...
        <li class="searchable-select-empty">Brak wyników</li>
    </ul>
</div>
```

## Pliki

- **Nowy:** `static/js/components/searchable-select.js` — komponent (delegacja zdarzeń, otwieranie/zamykanie, filtrowanie, klawiatura).
- **Nowy:** `static/css/components/searchable-select.css` — style panelu + wyszukiwarki, **light + dark mode** (glassmorphism: tła `rgba(255,255,255,0.05)`, obramowania `rgba(240,147,251,0.15)`–`0.3`, akcent `#f093fb`, `backdrop-filter: blur(...)`). Reguła `select.searchable-select { pointer-events: none; }`. Bazowe style `.custom-select-display` pozostają w `offer-builder.css`.
- **Edycja:** `static/js/pages/admin/offer-builder.js` — dodanie wrapperów + klasy `searchable-select` w 3 szablonach HTML (set variant group card, set-product-select — już ma wrapper, standalone variant_group section).
- **Edycja:** `templates/admin/offers/edit.html` — dołączenie nowego pliku JS i CSS.

**Bez zmian w bazie danych.** **Bez zmian w backendzie** — format zapisu (`collectPageData`) identyczny.

## Zgodność z zasadami projektu

- Separacja JS/CSS od HTML — cały kod w dedykowanych plikach `.js` / `.css`.
- Light + dark mode dla wszystkich nowych stylów.
- To nie modal — style w `components/searchable-select.css` (nie w `modals.css`).
- Brak migracji (czysto frontend).

## Kryteria akceptacji

1. W secie po „+ Dodaj grupę wariantową" dropdown grupy ma input wyszukiwarki na górze; wpisywanie filtruje listę grup.
2. Pole „Produkt – komplet setu" ma wyszukiwarkę; podgląd produktu (`set-product-preview-card`) nadal działa po wyborze.
3. Samodzielna sekcja „Grupa wariantowa" ma wyszukiwarkę; podgląd produktów grupy nadal się ładuje.
4. Zapis i wczytanie strony (edit) zachowują wybrane wartości; `collectPageData` bez zmian.
5. Działa w light i dark mode; spójny wygląd z resztą buildera.
6. Dynamicznie dodane karty/sekcje od razu mają działającą wyszukiwarkę (bez przeładowania).
