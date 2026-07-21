# Galeria zdjęć produktu na stronie ofertowej — projekt

Data: 2026-07-21
Gałąź: `feat/oferta-galeria-produktu`

## Problem

Na stronie sprzedażowej (ofertowej) przy głównym produkcie wyświetla się tylko
jedno zdjęcie — główne (`primary_image`) — mimo że do produktu można dodać do 10
zdjęć. Pozostałe zdjęcia są dodane w bazie, ale nigdy nie trafiają na stronę.

Cel: pokazać wszystkie dodane zdjęcia produktu w formie pionowej mini-galerii
(pasek miniaturek) obok dużego zdjęcia, z nawigacją chevronami.

## Zakres

- **Dotyczy tylko głównego produktu** sekcji „pojedynczy produkt" na stronie
  ofertowej — duże zdjęcie w `.product-image-area`.
- **Nie dotyczy** małych kafelków wariantów i zestawów (zostają bez zmian:
  jedno zdjęcie + powiększenie po kliknięciu / lightbox).
- Dotyczy **obu** szablonów oferty:
  - `templates/offers/order_page.html` (sekcja ~193–215)
  - `templates/offers/order_page_preorder.html` (sekcja ~143–158)

## Zachowanie (uzgodnione z właścicielką)

### Desktop — pasek pionowy po lewej stronie dużego zdjęcia
1. Pasek miniaturek pionowo, po lewej od dużego zdjęcia.
2. Chevron (strzałka) u góry i u dołu paska.
3. Widoczne **3 miniaturki + 30% czwartej** (podpowiedź, że jest więcej).
4. **Zdjęcie główne zawsze pierwsze** w pasku.
5. Kliknięcie chevronu **przełącza aktywne zdjęcie** (nie tylko przewija pasek):
   - duży podgląd od razu zmienia się na aktywne zdjęcie,
   - pasek sam **dociąga aktywną miniaturkę na środek**,
   - wyjątek: **ostatnie** zdjęcie nie jest wpychane na środek — pasek zatrzymuje
     się na końcu, ostatnia miniaturka jest przy dolnej krawędzi.
6. Aktywna miniaturka ma **obramowanie** (akcent) + delikatną poświatę.
7. **Górny chevron wyszarzony (disabled)**, gdy aktywne jest pierwsze (główne)
   zdjęcie. **Dolny chevron wyszarzony**, gdy aktywne jest ostatnie zdjęcie.
8. Na pasek nałożony **gradient zanikający do przezroczystości** u góry i u dołu
   (efekt łagodnego wtapiania miniaturek).
   - Górny gradient **znika, gdy aktywne jest pierwsze (główne) zdjęcie** — całe
     główne zdjęcie widoczne.
   - Dolny gradient **znika, gdy aktywne jest ostatnie zdjęcie** — całe ostatnie
     zdjęcie widoczne.
9. Kliknięcie miniaturki również ją aktywuje (to samo co nawigacja chevronem).
10. Kliknięcie **dużego** zdjęcia nadal otwiera lightbox (powiększenie) — pokazuje
    aktualnie aktywne zdjęcie w pełnej rozdzielczości.

### Mobile (≤640px) — pasek poziomy pod dużym zdjęciem
- Duże zdjęcie na górze, pod nim **poziomy** pasek miniaturek.
- Chevrony **po lewej i prawej** stronie paska.
- Ta sama logika: 3 + 30% widoczne, aktywna wyśrodkowana (poza skrajnymi),
  gradient wtapiający po bokach, wyszarzone chevrony na skraju.

### Przypadki brzegowe
- **0 zdjęć**: bez zmian — placeholder „brak zdjęcia" jak dziś.
- **1 zdjęcie**: bez paska i chevronów — samo duże zdjęcie (jak dziś) + lightbox.
- **2–3 zdjęcia**: pasek pokazuje wszystkie (mieszczą się), brak przewijania;
  chevrony nadal przełączają aktywne, wyszarzone na skrajach.

## Dane

Model `Product` (`modules/products/models.py`):
- Zdjęcia: relacja `images` (dynamic), każde ma `is_primary`, `sort_order`
  (= numer slotu #1..#10), `path_compressed`, `path_original`.
- Dodajemy właściwość `gallery_images`: wszystkie zdjęcia posortowane po
  `sort_order`, z **głównym (is_primary) wymuszonym na pierwszej pozycji**.
  Dzięki temu „główne zawsze pierwsze" jest gwarantowane niezależnie od danych.

```python
@property
def gallery_images(self):
    imgs = self.images.order_by(ProductImage.sort_order.asc(),
                                ProductImage.id.asc()).all()
    primary = next((i for i in imgs if i.is_primary), None)
    if primary:
        imgs = [primary] + [i for i in imgs if i.id != primary.id]
    return imgs
```

## Architektura zmian

### 1. Model — `modules/products/models.py`
Dodać właściwość `gallery_images` (wyżej). Bez zmian w bazie / migracji.

### 2. Szablony — `order_page.html` i `order_page_preorder.html`
Zastąpić dotychczasowy blok `.product-image-area` (single `primary_image`)
strukturą galerii. Gdy `gallery_images|length > 1` — render paska; w przeciwnym
razie dotychczasowe pojedyncze zdjęcie. Zarys HTML:

```html
<div class="product-image-area">
  {% set imgs = section.product.gallery_images %}
  {% if imgs|length > 1 %}
  <div class="product-gallery" data-gallery>
    <button type="button" class="gallery-chevron gallery-chevron-prev" data-dir="prev" aria-label="Poprzednie zdjęcie">…chevron…</button>
    <div class="gallery-strip-viewport">
      <div class="gallery-fade gallery-fade-start"></div>
      <div class="gallery-fade gallery-fade-end"></div>
      <div class="gallery-strip">
        {% for img in imgs %}
        <button type="button" class="gallery-thumb{% if loop.first %} active{% endif %}"
                data-idx="{{ loop.index0 }}"
                data-src="{{ url_for('static', filename=img.path_compressed) }}"
                data-full-src="{{ url_for('static', filename=img.path_original or img.path_compressed) }}">
          <img src="{{ url_for('static', filename=img.path_compressed) }}" alt="{{ section.product.name }} — {{ loop.index }}" loading="lazy">
        </button>
        {% endfor %}
      </div>
    </div>
    <button type="button" class="gallery-chevron gallery-chevron-next" data-dir="next" aria-label="Następne zdjęcie">…chevron…</button>
  </div>
  <div class="zoomable-image-wrapper" onclick="openLightbox(this)">
    <img src="…imgs[0].compressed…" data-full-src="…imgs[0].original…" class="product-image-centered gallery-main-image" alt="…">
    <div class="zoom-icon">…</div>
  </div>
  {% elif section.product.primary_image %}
    …dotychczasowe pojedyncze zdjęcie bez zmian…
  {% else %}
    …placeholder „no-image" bez zmian…
  {% endif %}
</div>
```

Uwaga: `.product-gallery` owija pasek + duże zdjęcie; na desktopie układ w rzędzie
(pasek po lewej), na mobile w kolumnie (pasek pod spodem) — sterowane CSS-em.

### 3. CSS — `static/css/pages/offers/order-page.css`
Nowe reguły dla `.product-gallery`, `.gallery-strip*`, `.gallery-thumb`,
`.gallery-chevron`, `.gallery-fade`. Wersje light + dark (zgodnie z konwencją
projektu). Breakpoint mobilny (≤640px): zmiana orientacji na poziomą (chevrony
po bokach, pasek pod zdjęciem). Miniaturki min. 44px (touch). Gradient realizowany
nakładkami `.gallery-fade` (linear-gradient od koloru tła karty do przezroczystości).

### 4. JS — nowy plik `static/js/pages/offers/product-gallery.js`
Wspólna, samowystarczalna logika galerii, podpięta w OBU szablonach
(`order_page.html` i `order_page_preorder.html`) obok istniejących skryptów.
- Inicjalizuje **każdy** `[data-gallery]` na stronie osobno (może być wiele produktów).
- Stan: `active` (indeks aktywnej miniaturki).
- Nawigacja: chevron prev/next zmienia `active` o ±1 (w granicach); klik miniaturki
  ustawia `active` bezpośrednio.
- Render:
  - podmiana `src` i `data-full-src` dużego zdjęcia na wartości aktywnej miniaturki
    (dzięki temu lightbox pokaże aktywne zdjęcie),
  - klasa `active` na aktywnej miniaturce,
  - przesunięcie paska (`translateY`/`translateX`) tak, by aktywna była na środku,
    **z ograniczeniem do zakresu [0, maxScroll]** (skrajne nie są wpychane na środek),
  - `disabled` górnego/lewego chevronu gdy `active === 0`, dolnego/prawego gdy
    `active === ostatni`,
  - widoczność gradientów zależna od pozycji przewinięcia: początkowy gradient
    znika przy `active === 0`, końcowy przy `active === ostatni`.
- Orientacja (pion/poziom) wykrywana przez `matchMedia('(max-width: 640px)')`;
  przy zmianie rozmiaru okna przelicza przesunięcie na właściwej osi.
- Brak zależności od bibliotek zewnętrznych; zgodne ze stylem istniejących
  skryptów (vanilla JS, IIFE).

## Testy / weryfikacja
- Produkt z 6 zdjęciami: nawigacja chevronami, centrowanie, skraje bez centrowania,
  wyszarzone chevrony, znikające gradienty na skrajach, klik miniaturki, lightbox
  pokazuje aktywne zdjęcie.
- Produkt z 1 zdjęciem: brak paska, zachowanie jak dziś.
- Produkt bez zdjęć: placeholder.
- Desktop i mobile (≤640px) — obie orientacje.
- Light i dark mode.
- Obie strony: `order_page` i `order_page_preorder`.

## Poza zakresem (YAGNI)
- Przesuwanie palcem (swipe) na mobile — na razie tylko chevrony i klik.
- Autoodtwarzanie / karuzela.
- Galeria w małych kafelkach wariantów i zestawów.
- Zmiany w panelu admina (dodawanie zdjęć działa i zostaje bez zmian).
