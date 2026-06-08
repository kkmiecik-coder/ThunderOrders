# Podgląd oferty na countdownie — projekt

**Data:** 2026-06-08
**Status:** zatwierdzony projekt, przed implementacją

## Problem

Klienci w fazie `scheduled` (przed startem sprzedaży) widzą wyłącznie stronę
countdown (`templates/offers/countdown.html`) — timer, muzykę, animowane tło i datę
startu. Nie wiedzą, co dokładnie będzie w sprzedaży, więc nie mogą się przygotować.

## Cel

Umożliwić klientowi podejrzenie **pełnej zawartości oferty** (z nazwami i cenami) jeszcze
przed startem, w sposób **minimalnie inwazyjny** dla istniejącej struktury — przez przycisk
na countdownie otwierający modal z ofertą w trybie read-only.

## Decyzje (z brainstormingu)

- **Zakres:** pełna oferta read-only — wszystkie typy sekcji, ale bez przycisków zamawiania.
- **Nazwy i ceny:** widoczne.
- **Forma:** modal otwierany przyciskiem na countdownie (nie osobna podstrona, nie inline pod timerem).
- **Sterowanie:** przełącznik `preview_enabled` per oferta, **domyślnie włączony**, ustawiany w page builderze.
- **Render:** nowy, statyczny partial read-only — `order_page.html` pozostaje nietknięty.
- **Przycisk:** pod timerem, tekst **„Co jest w sprzedaży?"**.

## Architektura

### 1. Model + migracja

`OfferPage` (`modules/offers/models.py`) — nowe pole:

```python
preview_enabled = db.Column(db.Boolean, default=True, nullable=False)
```

Migracja Flask-Migrate: `flask db migrate -m "Add preview_enabled to offer_pages"` →
weryfikacja wygenerowanego pliku → `flask db upgrade` lokalnie. Wartość domyślna `True`
sprawia, że istniejące oferty od razu mają podgląd włączony.

### 2. Page builder (edytor oferty)

- `templates/admin/offers/edit.html` — w sekcji „Ustawienia strony" (obecnie linie ~124-188)
  dodać przełącznik **„Preview na stronie odliczania"** (checkbox, domyślnie zaznaczony),
  wzorowany na istniejącym `notifyClientsOnPublish`.
- `modules/admin/offers.py` — `offers_save()` (POST `/admin/offers/<id>/save`): odczyt
  `data['preview_enabled']` → `page.preview_enabled = bool(data['preview_enabled'])`.
- Front edytora (JS budujący payload save) — dołączyć stan checkboxa do wysyłanego JSON-a.
- `offers_edit()` / kontekst szablonu — upewnić się, że aktualna wartość pola jest
  odzwierciedlona w stanie checkboxa przy wczytaniu edytora.

### 3. Backend — route countdown

`modules/offers/routes.py` — `countdown_page()` (obecnie kończy się na ~linii 240):

- Jeśli `page.preview_enabled`: `sections = page.get_sections_ordered()` i przekazać do
  szablonu (`render_template('offers/countdown.html', page=page, sections=sections)`).
- Jeśli wyłączony: `sections = []` (albo nie przekazywać) — przycisk się nie pokaże.
- Bez zmian w logice statusów ani przekierowań.

### 4. Frontend — countdown

`templates/offers/countdown.html`:

- Pod sekcją `countdown-info` dodać przycisk **„Co jest w sprzedaży?"**, renderowany tylko gdy
  `page.preview_enabled and sections`.
- Modal wg wzorca projektu: `modal-overlay` + `modal-content`, otwierany
  `classList.add('active')`, zamykany `remove('active')`. Markup renderowany serwerowo
  (ukryty), zawartość z partiala.
- Nowy partial `templates/offers/_preview_sections.html` — statyczny read-only render
  każdego typu sekcji:
  - `heading` / `paragraph` → tekst,
  - `product` → karta: zdjęcie, nazwa, **cena**,
  - `set` → nazwa setu, skład (produkty + ceny), opcjonalnie „Pełny set" z ceną,
  - `variant_group` → nazwa grupy + lista produktów (zdjęcie, nazwa, cena),
  - `bonus` → statyczna karta „Bonus: …" z warunkiem (wzór z `order_page_preorder.html`),
  - **bez** kontrolek ilości, selektorów rozmiaru, info o dostępności, lightboxa.

### 5. CSS / JS (osobne pliki, light + dark mode)

- **Shell modala** → `static/css/components/modals.css` (light + dark, glassmorphism — zgodnie
  z paletą projektu).
- **Style kart podglądu** → nowy `static/css/pages/offers/countdown-preview.css` (lekkie,
  czytelne karty read-only; `order-page.css` nietknięty). Light + dark.
- **JS** → nowy `static/js/pages/offers/countdown-preview.js` (otwórz/zamknij modal, ESC,
  klik w tło). `countdown.js` i `order-page.js` nietknięte.
- Pliki podpięte w `countdown.html` (CSS w `extra_css`, JS na końcu body).

## Zakres wykluczony (YAGNI)

- Brak zmian w `order_page.html` i jego JS.
- Brak wishlisty / interakcji (to była osobna propozycja).
- Brak podglądu na dashboardzie w zakładce „Wkrótce" — tylko na stronie countdown
  (możliwe rozszerzenie w przyszłości).

## Testowanie

- Oferta `scheduled` z `preview_enabled=True` i sekcjami → przycisk widoczny, modal pokazuje
  wszystkie typy sekcji read-only z nazwami i cenami.
- Oferta `scheduled` z `preview_enabled=False` → brak przycisku.
- Oferta `scheduled` bez sekcji → brak przycisku.
- Light i dark mode → poprawny wygląd modala i kart.
- Przełącznik w page builderze zapisuje i wczytuje wartość poprawnie.
- Brak regresji na stronie sprzedaży (`order_page.html`) — niezmieniona.
