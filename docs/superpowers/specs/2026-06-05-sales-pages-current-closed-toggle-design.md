# Przełącznik „Bieżące" / „Zamknięte" w widgecie Strony sprzedaży

**Data:** 2026-06-05
**Autor:** Konrad (brainstorming z Claude)
**Status:** Zatwierdzony — gotowy do planu implementacji

---

## Cel

Dodać do headera widgetu „Strony sprzedaży" na dashboardzie klienta
(`templates/client/dashboard.html`) przełącznik dwóch zakładek: **Bieżące**
oraz **Zamknięte**. Klient może filtrować listę stron ofertowych według tego,
czy sprzedaż jeszcze trwa (lub jest zaplanowana), czy już się zakończyła.

---

## Definicje kategorii

Strony ofertowe (`OfferPage`) mają status:
`scheduled`, `active`, `paused`, `ended` (plus `ended` + `is_fully_closed`
prezentowane jako „Zamknięta"). Status `draft` nigdy nie jest widoczny dla
klienta (filtrowany już dziś).

- **Bieżące** = `status in ('scheduled', 'active', 'paused')`
  (Zaplanowana / LIVE / Wstrzymana)
- **Zamknięte** = `status == 'ended'`
  (obejmuje zarówno „Zakończona" jak i „Zamknięta" / `is_fully_closed`)

---

## Decyzje projektowe

| Zagadnienie | Decyzja |
|---|---|
| Mechanizm filtrowania | Backend filtruje przez `?filter=current\|closed`; frontend cache'uje pobrane dane i stan paginacji |
| Render stron | **JS renderuje obie zakładki od startu** przez API (`dashboard()` nie renderuje wierszy SSR — tylko flagi widoczności). Przy pierwszym pobraniu widget pokazuje stan **loading** (spinner). |
| Paginacja | **Jednolita dla obu zakładek**: pierwsze 5 stron + przycisk „Pokaż więcej" dociągający kolejne po 5 z API (`?filter=&offset=&limit=5`) |
| Cache frontend (stan) | Cache per zakładka trzyma pobrane strony ORAZ liczbę rozłożonych (`shownCount`). Przełączanie tam-z-powrotem nie powoduje ponownego fetcha i **zachowuje liczbę rozłożonych stron** (np. 2× „Pokaż więcej" = 15 stron → powrót pokazuje znów 15, nie reset do 5, nie wszystkie). Przeładowanie strony resetuje stan do domyślnej zakładki. |
| Domyślna zakładka | **Bieżące** (JS pobiera i renderuje przy starcie, z loading state) |
| Pusty stan | Komunikat w widgecie dla obu zakładek; przełącznik pozostaje widoczny |
| Widoczność widgetu | Widget widoczny gdy istnieje ≥1 strona jakiegokolwiek typu (bieżąca LUB zamknięta) — sterowane flagą `has_any` z backendu |

> **Uwaga (rewizja 2026-06-05):** Pierwotny projekt zakładał render bieżących SSR + bufor DOM, a zakładki ładowane jednorazowo `limit=100`. Zostało to zastąpione jednolitym modelem paginacji per zakładka z cache `shownCount` (powyżej), bo poprzednie podejście gubiło stan paginacji przy przełączaniu (zakładka pokazywała wszystkie strony zamiast zapamiętanej liczby) i nie miało „Pokaż więcej" dla zamkniętych.

---

## Architektura

### 1. Backend — `modules/client/routes.py`

**Wspólna funkcja pomocnicza** (jedno źródło prawdy dla podziału, używana
zarówno w `dashboard()` jak i `get_offer_pages()`):

```python
def filter_offer_pages(pages, filter_type):
    if filter_type == 'closed':
        return [p for p in pages if p.status == 'ended']
    # 'current' (domyślnie)
    return [p for p in pages if p.status in ('scheduled', 'active', 'paused')]
```

**`dashboard()`** (obecnie linie ~154-194):
- Po pobraniu (filtr `status != 'draft'`), `check_and_update_status()`,
  `sort_offer_pages()` i pre-compute `_has_sets` — podziel listę na
  `current` i `closed` przez `filter_offer_pages()`.
- Domyślnie renderuj **bieżące**: `visible = current[:5]`, `buffer = current[5:10]`.
- Rozszerz słownik `offer_pages` przekazywany do szablonu o:
  - `has_any` — bool, czy istnieje jakakolwiek strona (current LUB closed) →
    sterowanie widocznością całego widgetu
  - `has_current` — bool, czy są bieżące → pusty stan zakładki Bieżące
  - `has_closed` — bool, czy są zamknięte → pusty stan zakładki Zamknięte
  - `total` / `remaining` liczone względem **bieżących** (domyślna zakładka)
- `visible` / `buffer` jak dotychczas, ale ze zbioru `current`.

**`get_offer_pages()`** (obecnie linie ~324-408):
- Odczytaj `filter = request.args.get('filter', 'current')`.
- Po `sort_offer_pages()` przefiltruj listę przez `filter_offer_pages(pages, filter)`
  **przed** paginacją.
- `offset` / `limit` / `has_more` / `remaining` / `total` liczone względem
  przefiltrowanego zbioru.
- Reszta serializacji bez zmian.

### 2. HTML — `templates/client/dashboard.html`

**Header widgetu** (obecnie linie 77-79):

```html
<div class="widget-header widget-header-offers">
    <h2 class="widget-title">✨ Strony sprzedaży</h2>
    <div class="offer-filter-tabs" role="tablist">
        <button type="button" class="offer-filter-tab active" data-filter="current">Bieżące</button>
        <button type="button" class="offer-filter-tab" data-filter="closed">Zamknięte</button>
    </div>
</div>
```

- Warunek widoczności widgetu: zmień `{% if offer_pages.visible|length > 0 %}`
  na `{% if offer_pages.has_any %}`.
- Dodaj **wiersz pustego stanu** w `<tbody>` (desktop) — ukryty domyślnie,
  sterowany przez JS: `<tr class="offer-empty-row" style="display:none;">`
  z komórką `colspan` i komunikatem
  („Brak bieżących stron sprzedaży" / „Brak zamkniętych stron sprzedaży").
- Analogiczny pusty stan w widoku mobilnym (karty).
- Server-side renderuje domyślnie bieżące; przy starcie pokaż pusty stan,
  jeśli `has_current` jest fałszem (a `has_any` prawdą — czyli są tylko zamknięte).

### 3. JavaScript — wydzielenie do `static/js/pages/client/dashboard.js`

**Refactor (ostrożnie, dwa kroki):**
1. Wierne przeniesienie 1:1 istniejącego inline JS dashboardu
   (~860 linii z `dashboard.html`, linie ~514-1378) do nowego pliku
   `static/js/pages/client/dashboard.js`, podłączonego przez
   `<script src="{{ url_for('static', ...) }}">` na końcu body.
   - Sprawdź zależności od zmiennych Jinja2 w inline JS. Jeśli istnieją,
     przekaż je przez atrybuty `data-*` lub minimalny blok inicjalizujący.
   - Zweryfikuj, że dashboard działa identycznie po przeniesieniu (bez zmian
     funkcjonalnych).
2. Dopiero potem dołóż logikę przełącznika.

**Logika przełącznika:**
- **Stan w pamięci:** cache per zakładka, np.
  `{ current: {...}, closed: null }`. `current` wstępnie wypełniony danymi
  wyrenderowanymi server-side (offset/remaining odczytane z DOM lub `data-*`).
- **Klik zakładki:**
  1. Przełącz klasę `active` na przyciskach.
  2. Jeśli dane zakładki są w cache → renderuj z pamięci (bez fetcha).
  3. Jeśli nie → `fetch('/client/api/offer-pages?filter=<tab>&offset=0&limit=5')`,
     zapisz do cache, renderuj.
  4. Pokaż/ukryj wiersz pustego stanu zależnie od liczby wyników.
- **„Pokaż więcej":** istniejący lazy-loading dostaje aktualny `filter`
  z aktywnej zakładki i dopisuje do cache właściwej zakładki; paginacja
  liczona względem przefiltrowanego zbioru.
- Renderowanie wierszy/kart wydzielone do funkcji wielokrotnego użytku
  (wykorzystaj istniejącą logikę renderującą z lazy-loadingu).

### 4. CSS — `static/css/pages/client/dashboard.css`

Style z obsługą **light i dark mode** (CLAUDE.md):

- `.widget-header-offers` — flex, `justify-content: space-between`
  (tytuł po lewej, zakładki po prawej); na mobile dopuszczalne zawijanie/stack.
- `.offer-filter-tabs` — kontener (segment/pill toggle).
- `.offer-filter-tab` + `.offer-filter-tab.active` — stan nieaktywny/aktywny.
  - Light: akcent pomarańczowy (spójnie z hover wierszy `rgba(255,133,0,...)`).
  - Dark: akcent różowy `#f093fb` (paleta glassmorphism z CLAUDE.md).
- `.offer-empty-row` i pusty stan mobilny — wyśrodkowany, stonowany tekst.
- Touch targety na mobile min. 44px.

---

## Przepływ danych

1. **Wejście na dashboard** → `dashboard()` renderuje bieżące strony
   server-side (visible + buffer ze zbioru `current`), przekazuje flagi
   `has_any` / `has_current` / `has_closed`.
2. **Klik „Zamknięte"** → JS sprawdza cache; brak → `fetch(?filter=closed)`;
   renderuje, cache'uje. Pusto → komunikat.
3. **Klik „Bieżące"** (powrót) → renderowanie z cache, bez fetcha.
4. **„Pokaż więcej"** → fetch z aktualnym `filter` i `offset`, dopisanie
   do cache aktywnej zakładki.
5. **Przeładowanie strony** → reset do zakładki Bieżące (stan w pamięci znika).

---

## Obsługa stanów brzegowych

| Sytuacja | Zachowanie |
|---|---|
| Zero stron w ogóle | Cały widget ukryty (`has_any == False`) |
| Tylko zamknięte | Widget widoczny, domyślnie zakładka Bieżące pokazuje komunikat pustego stanu |
| Tylko bieżące | Zakładka Zamknięte pokazuje komunikat pustego stanu po kliknięciu |
| Błąd fetcha zakładki | Komunikat o błędzie / fallback; nie psuć widoku (toast jeśli dostępny) |

---

## Testowanie

- Lokalnie (`http://localhost:5001`) z danymi obejmującymi: tylko bieżące,
  tylko zamknięte, mieszane, zero stron.
- Weryfikacja: dashboard działa identycznie po wydzieleniu JS (regresja).
- Przełączanie zakładek: pierwszy fetch + brak ponownego fetcha przy powrocie.
- „Pokaż więcej" działa w obu zakładkach z poprawną paginacją.
- Light i dark mode; widok desktop i mobile (touch targety).

---

## Zakres / poza zakresem

**W zakresie:** przełącznik, filtrowanie backend, cache frontend, pusty stan,
wydzielenie inline JS dashboardu do pliku, style light/dark.

**Poza zakresem:** zmiany w modelu `OfferPage` / migracje (brak zmian w bazie),
zmiana logiki sortowania, zmiany w innych widgetach dashboardu.
