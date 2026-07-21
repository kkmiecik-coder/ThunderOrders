# Galeria zdjęć produktu na stronie ofertowej — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Na stronie ofertowej pokazać wszystkie zdjęcia głównego produktu jako mini-galerię (pasek miniaturek + chevrony), zamiast tylko jednego głównego zdjęcia.

**Architecture:** Nowa właściwość modelu `Product.gallery_images` zwraca zdjęcia z głównym na pierwszym miejscu. Wspólny partial Jinja `_product_gallery.html` renderuje pasek + duże zdjęcie i jest dołączany (`include`) w obu szablonach oferty. Wygląd w `order-page.css`, interakcja w nowym, samodzielnym pliku `product-gallery.js` (vanilla JS, bez bibliotek), dołączonym do obu stron.

**Tech Stack:** Flask + Jinja2, SQLAlchemy (MariaDB), vanilla JS (IIFE), CSS z klasami light/dark, pytest.

## Global Constraints

- Każda gałąź to praca poza `main` (obecna gałąź: `feat/oferta-galeria-produktu`). Nie pushować na `main`.
- Testy uruchamiać: `python -m pytest`.
- CSS zawsze w wersji light **i** dark. Gradient wtapiać w `var(--card-bg)` (sama się dopasowuje do motywu).
- Elementy dotykowe min. 44px.
- Commity po polsku, konwencja: `feat(...)`, `docs(...)`, `test(...)`.
- Bez zmian w bazie / migracji. Bez zmian w panelu admina.
- Zakres: tylko główny produkt sekcji „pojedynczy produkt". Warianty i zestawy bez zmian.
- Pliki `docs/**` są w `.gitignore` — dodawać przez `git add -f`.

## File Structure

- `modules/products/models.py` — **modify**: dodać właściwość `Product.gallery_images`.
- `templates/offers/_product_gallery.html` — **create**: partial renderujący galerię (pasek + duże zdjęcie).
- `templates/offers/order_page.html` — **modify**: w `.product-image-area` użyć partiala.
- `templates/offers/order_page_preorder.html` — **modify**: w `.product-image-area` użyć partiala.
- `static/css/pages/offers/order-page.css` — **modify**: style galerii (desktop pion / mobile poziom, light+dark).
- `static/js/pages/offers/product-gallery.js` — **create**: logika galerii.
- `tests/test_product_gallery_images.py` — **create**: testy właściwości modelu.
- `tests/test_offer_gallery_render.py` — **create**: testy renderu partiala.

---

### Task 1: Właściwość modelu `Product.gallery_images`

**Files:**
- Modify: `modules/products/models.py` (klasa `Product`, po istniejącej właściwości `primary_image` ~w. 239–245)
- Test: `tests/test_product_gallery_images.py`

**Interfaces:**
- Produces: `Product.gallery_images` → `list[ProductImage]`. Zawsze zdjęcie z `is_primary=True` na pozycji 0 (o ile istnieje), reszta posortowana rosnąco po `(sort_order, id)`.

- [ ] **Step 1: Napisz test (ma się wywalić)**

Utwórz `tests/test_product_gallery_images.py`:

```python
from decimal import Decimal
from modules.products.models import ProductImage


def _img(product_id, name, sort_order, is_primary=False):
    return ProductImage(
        product_id=product_id,
        filename=name,
        path_original=f'uploads/products/{name}_orig.jpg',
        path_compressed=f'uploads/products/{name}.jpg',
        is_primary=is_primary,
        sort_order=sort_order,
    )


def test_gallery_images_puts_primary_first_then_sort_order(db, make_product):
    p = make_product(name='Album', sale_price=Decimal('150.00'))
    # celowo w złej kolejności; główne (is_primary) to slot #1 = sort_order 1
    db.session.add(_img(p.id, 'b', sort_order=2))
    db.session.add(_img(p.id, 'c', sort_order=3))
    db.session.add(_img(p.id, 'a', sort_order=1, is_primary=True))
    db.session.commit()

    imgs = p.gallery_images

    assert [i.filename for i in imgs] == ['a', 'b', 'c']
    assert imgs[0].is_primary is True


def test_gallery_images_without_primary_sorts_by_sort_order(db, make_product):
    p = make_product(name='Album2', sale_price=Decimal('99.00'))
    db.session.add(_img(p.id, 'y', sort_order=5))
    db.session.add(_img(p.id, 'x', sort_order=2))
    db.session.commit()

    assert [i.filename for i in p.gallery_images] == ['x', 'y']


def test_gallery_images_empty_when_no_images(db, make_product):
    p = make_product(name='Album3', sale_price=Decimal('10.00'))
    assert p.gallery_images == []
```

- [ ] **Step 2: Uruchom test — ma FAIL**

Run: `python -m pytest tests/test_product_gallery_images.py -v`
Expected: FAIL — `AttributeError: 'Product' object has no attribute 'gallery_images'`

- [ ] **Step 3: Dodaj właściwość w `modules/products/models.py`**

Zaraz po właściwości `primary_image` (klasa `Product`):

```python
    @property
    def gallery_images(self):
        """Wszystkie zdjęcia: główne (is_primary) zawsze pierwsze, reszta po sort_order."""
        imgs = self.images.order_by(
            ProductImage.sort_order.asc(), ProductImage.id.asc()
        ).all()
        primary = next((i for i in imgs if i.is_primary), None)
        if primary:
            imgs = [primary] + [i for i in imgs if i.id != primary.id]
        return imgs
```

- [ ] **Step 4: Uruchom test — ma PASS**

Run: `python -m pytest tests/test_product_gallery_images.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add modules/products/models.py tests/test_product_gallery_images.py
git commit -m "feat(produkty): właściwość gallery_images (główne zdjęcie zawsze pierwsze)"
```

---

### Task 2: Partial galerii + include w obu szablonach

**Files:**
- Create: `templates/offers/_product_gallery.html`
- Modify: `templates/offers/order_page.html` (blok `.product-image-area`, ~w. 193–215)
- Modify: `templates/offers/order_page_preorder.html` (blok `.product-image-area`, ~w. 143–158)
- Test: `tests/test_offer_gallery_render.py`

**Interfaces:**
- Consumes: `Product.gallery_images` (Task 1).
- Partial oczekuje zmiennej `product` (obiekt `Product`). Renderuje:
  - gdy `product.gallery_images|length > 1` → kontener `[data-gallery]` z paskiem miniaturek i dużym zdjęciem;
  - gdy dokładnie 1 zdjęcie → samo duże zdjęcie w `.zoomable-image-wrapper` (jak dziś);
  - gdy 0 zdjęć → placeholder `.no-image` (jak dziś).
- Produces (kontrakt DOM dla CSS/JS z Task 3–4): `.product-gallery[data-gallery]`, `.gallery-nav`, `.gallery-chevron-prev`, `.gallery-chevron-next`, `.gallery-strip-viewport`, `.gallery-fade-start`, `.gallery-fade-end`, `.gallery-strip`, `.gallery-thumb[data-idx][data-src][data-full-src]`, `.gallery-main-image`.

- [ ] **Step 1: Napisz test renderu (ma się wywalić)**

Utwórz `tests/test_offer_gallery_render.py`:

```python
from decimal import Decimal
from flask import render_template
from modules.products.models import ProductImage


def _img(product_id, name, sort_order, is_primary=False):
    return ProductImage(
        product_id=product_id, filename=name,
        path_original=f'uploads/products/{name}_orig.jpg',
        path_compressed=f'uploads/products/{name}.jpg',
        is_primary=is_primary, sort_order=sort_order,
    )


def test_gallery_partial_renders_strip_for_multiple_images(app, db, make_product):
    p = make_product(name='Album', sale_price=Decimal('150.00'))
    db.session.add(_img(p.id, 'a', 1, is_primary=True))
    db.session.add(_img(p.id, 'b', 2))
    db.session.add(_img(p.id, 'c', 3))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'data-gallery' in html
    assert html.count('gallery-thumb') >= 3
    assert 'gallery-chevron-prev' in html
    assert 'gallery-main-image' in html


def test_gallery_partial_single_image_has_no_strip(app, db, make_product):
    p = make_product(name='Solo', sale_price=Decimal('50.00'))
    db.session.add(_img(p.id, 'only', 1, is_primary=True))
    db.session.commit()

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'data-gallery' not in html
    assert 'zoomable-image-wrapper' in html


def test_gallery_partial_no_images_shows_placeholder(app, db, make_product):
    p = make_product(name='Pusty', sale_price=Decimal('50.00'))

    with app.test_request_context():
        html = render_template('offers/_product_gallery.html', product=p)

    assert 'no-image' in html
    assert 'data-gallery' not in html
```

- [ ] **Step 2: Uruchom test — ma FAIL**

Run: `python -m pytest tests/test_offer_gallery_render.py -v`
Expected: FAIL — `jinja2.exceptions.TemplateNotFound: offers/_product_gallery.html`

- [ ] **Step 3: Utwórz partial `templates/offers/_product_gallery.html`**

```html
{% set imgs = product.gallery_images %}
{% if imgs|length > 1 %}
<div class="product-gallery" data-gallery>
    <div class="gallery-nav">
        <button type="button" class="gallery-chevron gallery-chevron-prev" data-dir="prev" aria-label="Poprzednie zdjęcie">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="18 15 12 9 6 15"/></svg>
        </button>
        <div class="gallery-strip-viewport">
            <div class="gallery-fade gallery-fade-start"></div>
            <div class="gallery-fade gallery-fade-end"></div>
            <div class="gallery-strip">
                {% for img in imgs %}
                <button type="button" class="gallery-thumb{% if loop.first %} active{% endif %}"
                        data-idx="{{ loop.index0 }}"
                        data-src="{{ url_for('static', filename=img.path_compressed) }}"
                        data-full-src="{{ url_for('static', filename=img.path_original or img.path_compressed) }}">
                    <img src="{{ url_for('static', filename=img.path_compressed) }}"
                         alt="{{ product.name }} — {{ loop.index }}" loading="lazy">
                </button>
                {% endfor %}
            </div>
        </div>
        <button type="button" class="gallery-chevron gallery-chevron-next" data-dir="next" aria-label="Następne zdjęcie">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
    </div>
    <div class="zoomable-image-wrapper gallery-main" onclick="openLightbox(this)">
        <img src="{{ url_for('static', filename=imgs[0].path_compressed) }}"
             alt="{{ product.name }}" class="product-image-centered gallery-main-image"
             data-full-src="{{ url_for('static', filename=imgs[0].path_original or imgs[0].path_compressed) }}">
        <div class="zoom-icon">
            <svg viewBox="0 0 16 16" fill="currentColor">
                <path fill-rule="evenodd" d="M6.5 12a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM13 6.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z"/>
                <path d="M10.344 11.742c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1 6.538 6.538 0 0 1-1.398 1.4z"/>
                <path fill-rule="evenodd" d="M6.5 3a.5.5 0 0 1 .5.5V6h2.5a.5.5 0 0 1 0 1H7v2.5a.5.5 0 0 1-1 0V7H3.5a.5.5 0 0 1 0-1H6V3.5a.5.5 0 0 1 .5-.5z"/>
            </svg>
        </div>
    </div>
</div>
{% elif product.primary_image %}
<div class="zoomable-image-wrapper" onclick="openLightbox(this)">
    <img src="{{ url_for('static', filename=product.primary_image.path_compressed) }}"
         alt="{{ product.name }}" class="product-image-centered"
         data-full-src="{{ url_for('static', filename=product.primary_image.path_original or product.primary_image.path_compressed) }}">
    <div class="zoom-icon">
        <svg viewBox="0 0 16 16" fill="currentColor">
            <path fill-rule="evenodd" d="M6.5 12a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM13 6.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0z"/>
            <path d="M10.344 11.742c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1 6.538 6.538 0 0 1-1.398 1.4z"/>
            <path fill-rule="evenodd" d="M6.5 3a.5.5 0 0 1 .5.5V6h2.5a.5.5 0 0 1 0 1H7v2.5a.5.5 0 0 1-1 0V7H3.5a.5.5 0 0 1 0-1H6V3.5a.5.5 0 0 1 .5-.5z"/>
        </svg>
    </div>
</div>
{% else %}
<div class="no-image">
    <svg width="64" height="64" viewBox="0 0 16 16" fill="currentColor">
        <path d="M6.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>
        <path d="M2.002 1a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V3a2 2 0 0 0-2-2h-12zm12 1a1 1 0 0 1 1 1v6.5l-3.777-1.947a.5.5 0 0 0-.577.093l-3.71 3.71-2.66-1.772a.5.5 0 0 0-.63.062L1.002 12V3a1 1 0 0 1 1-1h12z"/>
    </svg>
</div>
{% endif %}
```

- [ ] **Step 4: Podłącz partial w `templates/offers/order_page.html`**

Zamień zawartość `<div class="product-image-area"> … </div>` (obecnie `{% if section.product.primary_image %}` … placeholder) na jedną linię include:

```html
                        <div class="product-image-area">
                            {% include 'offers/_product_gallery.html' with context %}
                        </div>
```

W tym szablonie partial dostaje `product` z kontekstu — dodaj przypisanie tuż przed include, aby `product` wskazywał na `section.product`:

```html
                        <div class="product-image-area">
                            {% with product = section.product %}
                                {% include 'offers/_product_gallery.html' %}
                            {% endwith %}
                        </div>
```

- [ ] **Step 5: Podłącz partial w `templates/offers/order_page_preorder.html`**

Analogicznie zamień zawartość `<div class="product-image-area"> … </div>` (~w. 143–158):

```html
                        <div class="product-image-area">
                            {% with product = section.product %}
                                {% include 'offers/_product_gallery.html' %}
                            {% endwith %}
                        </div>
```

- [ ] **Step 6: Uruchom testy — mają PASS**

Run: `python -m pytest tests/test_offer_gallery_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add templates/offers/_product_gallery.html templates/offers/order_page.html templates/offers/order_page_preorder.html tests/test_offer_gallery_render.py
git commit -m "feat(oferta): partial galerii produktu + include w obu szablonach"
```

---

### Task 3: Style galerii (CSS) — desktop pion, mobile poziom, light/dark

**Files:**
- Modify: `static/css/pages/offers/order-page.css` (dopisać na końcu bloku sekcji zdjęć, po regułach `.product-image-area`)

**Interfaces:**
- Consumes: klasy DOM z partiala (Task 2).
- Miniaturka desktop 64×64px, gap 10px; wysokość viewportu = 3 miniaturki + 3 gapy + 30% kolejnej ≈ `241px`. Mobile: miniaturka 56×56px, pasek poziomy.

- [ ] **Step 1: Dopisz reguły CSS**

Na końcu `static/css/pages/offers/order-page.css`:

```css
/* ===== Galeria produktu (pasek miniaturek) ===== */
.product-gallery {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 16px;
    width: 100%;
}

.gallery-nav {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
}

.gallery-chevron {
    width: 64px;
    height: 28px;
    border-radius: 8px;
    border: 1px solid var(--gray-200);
    background: var(--card-bg);
    color: var(--gray-700);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s, opacity 0.15s;
}

.gallery-chevron:hover:not(:disabled) {
    background: var(--gray-50);
}

.gallery-chevron:disabled {
    opacity: 0.35;
    cursor: not-allowed;
}

.gallery-strip-viewport {
    position: relative;
    height: 241px;
    width: 64px;
    overflow: hidden;
}

.gallery-strip {
    display: flex;
    flex-direction: column;
    gap: 10px;
    transition: transform 0.28s ease;
    will-change: transform;
}

.gallery-thumb {
    position: relative;
    width: 64px;
    height: 64px;
    flex-shrink: 0;
    border-radius: 10px;
    overflow: hidden;
    padding: 0;
    border: 2px solid transparent;
    background: var(--gray-50);
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
}

.gallery-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.gallery-thumb.active {
    border-color: #9c27b0;
    box-shadow: 0 0 0 3px rgba(156, 39, 176, 0.18);
}

.gallery-thumb:hover:not(.active) {
    border-color: var(--gray-300);
}

.gallery-fade {
    position: absolute;
    left: 0;
    right: 0;
    height: 28px;
    pointer-events: none;
    z-index: 2;
    transition: opacity 0.2s ease;
}

.gallery-fade-start {
    top: 0;
    background: linear-gradient(var(--card-bg), transparent);
}

.gallery-fade-end {
    bottom: 0;
    background: linear-gradient(transparent, var(--card-bg));
}

.gallery-main {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}

/* Mobile: pasek poziomy pod dużym zdjęciem, chevrony po bokach */
@media (max-width: 640px) {
    .product-gallery {
        flex-direction: column-reverse;
        gap: 12px;
    }

    .gallery-nav {
        flex-direction: row;
        width: 100%;
    }

    .gallery-chevron {
        width: 32px;
        height: 56px;
    }

    .gallery-strip-viewport {
        height: 56px;
        width: auto;
        flex: 1;
    }

    .gallery-strip {
        flex-direction: row;
    }

    .gallery-thumb {
        width: 56px;
        height: 56px;
    }

    .gallery-fade {
        left: auto;
        right: auto;
        top: 0;
        bottom: 0;
        height: auto;
        width: 28px;
    }

    .gallery-fade-start {
        left: 0;
        background: linear-gradient(to right, var(--card-bg), transparent);
    }

    .gallery-fade-end {
        right: 0;
        background: linear-gradient(to left, var(--card-bg), transparent);
    }
}
```

- [ ] **Step 2: Weryfikacja wizualna (light + dark, desktop)**

Uruchom aplikację i otwórz stronę ofertową z produktem mającym ≥3 zdjęcia. Sprawdź: pasek po lewej, 3 + kawałek następnej miniaturki, aktywna z obramowaniem, gradient u góry/dołu wtapia się w tło karty w obu motywach.

- [ ] **Step 3: Commit**

```bash
git add static/css/pages/offers/order-page.css
git commit -m "style(oferta): pasek miniaturek galerii (desktop pion, mobile poziom, light/dark)"
```

---

### Task 4: Interakcja galerii (JS) + include w obu szablonach

**Files:**
- Create: `static/js/pages/offers/product-gallery.js`
- Modify: `templates/offers/order_page.html` (dodać `<script>` przy istniejących skryptach, ~w. 893)
- Modify: `templates/offers/order_page_preorder.html` (dodać `<script>`, ~w. 616)

**Interfaces:**
- Consumes: DOM z Task 2, style z Task 3, globalną funkcję `openLightbox(wrapper)` (istnieje w `order-page.js` i `order-page-preorder.js`; czyta `data-full-src` z `img` w środku).
- Zachowanie: klik chevronu/miniaturki zmienia aktywne zdjęcie; duże zdjęcie (`.gallery-main-image`) dostaje nowy `src` i `data-full-src`; pasek dociąga aktywną na środek z ograniczeniem do `[0, maxScroll]`; chevron prev disabled przy `active===0`, next przy ostatnim; gradient start znika gdy przewinięcie = 0, end gdy = maxScroll. Orientacja (pion/poziom) wg `matchMedia('(max-width: 640px)')`.

- [ ] **Step 1: Utwórz `static/js/pages/offers/product-gallery.js`**

```javascript
/**
 * Galeria produktu na stronie ofertowej.
 * Pionowy (desktop) / poziomy (mobile ≤640px) pasek miniaturek z chevronami.
 * Klik chevronu/miniaturki przełącza aktywne zdjęcie, podmienia duże zdjęcie
 * i dociąga aktywną miniaturkę na środek (skrajne bez wymuszania środka).
 */
(function () {
    'use strict';

    var mobile = window.matchMedia('(max-width: 640px)');

    function initGallery(root) {
        var strip = root.querySelector('.gallery-strip');
        var viewport = root.querySelector('.gallery-strip-viewport');
        var thumbs = Array.prototype.slice.call(root.querySelectorAll('.gallery-thumb'));
        var prevBtn = root.querySelector('.gallery-chevron-prev');
        var nextBtn = root.querySelector('.gallery-chevron-next');
        var fadeStart = root.querySelector('.gallery-fade-start');
        var fadeEnd = root.querySelector('.gallery-fade-end');
        var mainImg = root.querySelector('.gallery-main-image');
        if (!strip || thumbs.length === 0) return;

        var active = 0;

        function vertical() { return !mobile.matches; }

        function render() {
            var isV = vertical();
            var t0 = thumbs[0];
            var size = isV ? t0.offsetHeight : t0.offsetWidth;
            var gap = parseFloat(getComputedStyle(strip).gap) || 0;
            var step = size + gap;
            var vpSize = isV ? viewport.clientHeight : viewport.clientWidth;
            var content = thumbs.length * size + (thumbs.length - 1) * gap;
            var maxScroll = Math.max(0, content - vpSize);

            var target = active * step + size / 2 - vpSize / 2;
            if (target < 0) target = 0;
            if (target > maxScroll) target = maxScroll;

            strip.style.transform = isV
                ? 'translateY(' + (-Math.round(target)) + 'px)'
                : 'translateX(' + (-Math.round(target)) + 'px)';

            thumbs.forEach(function (t, i) {
                t.classList.toggle('active', i === active);
            });

            if (prevBtn) prevBtn.disabled = (active === 0);
            if (nextBtn) nextBtn.disabled = (active === thumbs.length - 1);

            if (fadeStart) fadeStart.style.opacity = (target > 0.5) ? '1' : '0';
            if (fadeEnd) fadeEnd.style.opacity = (target < maxScroll - 0.5) ? '1' : '0';

            if (mainImg) {
                var src = thumbs[active].getAttribute('data-src');
                var full = thumbs[active].getAttribute('data-full-src');
                if (src) mainImg.setAttribute('src', src);
                if (full) mainImg.setAttribute('data-full-src', full);
            }
        }

        function setActive(i) {
            if (i < 0) i = 0;
            if (i > thumbs.length - 1) i = thumbs.length - 1;
            active = i;
            render();
        }

        thumbs.forEach(function (t, i) {
            t.addEventListener('click', function () { setActive(i); });
        });
        if (prevBtn) prevBtn.addEventListener('click', function () { setActive(active - 1); });
        if (nextBtn) nextBtn.addEventListener('click', function () { setActive(active + 1); });

        var resizeTimer;
        window.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(render, 120);
        });
        if (mobile.addEventListener) {
            mobile.addEventListener('change', render);
        }

        render();
    }

    function initAll() {
        document.querySelectorAll('[data-gallery]').forEach(initGallery);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
```

- [ ] **Step 2: Podłącz skrypt w `templates/offers/order_page.html`**

Tuż po istniejącym `<script src="…order-page.js">` (~w. 893) dodaj:

```html
<script src="{{ url_for('static', filename='js/pages/offers/product-gallery.js') }}"></script>
```

- [ ] **Step 3: Podłącz skrypt w `templates/offers/order_page_preorder.html`**

Tuż po istniejącym `<script src="…order-page-preorder.js">` (~w. 616) dodaj:

```html
<script src="{{ url_for('static', filename='js/pages/offers/product-gallery.js') }}"></script>
```

- [ ] **Step 4: Weryfikacja interaktywna**

Uruchom aplikację, otwórz stronę ofertową z produktem ≥6 zdjęć. Sprawdź kolejno:
- klik dolnego chevronu → następne zdjęcie aktywne, duże zdjęcie się zmienia, pasek dociąga aktywną na środek;
- na pierwszym zdjęciu górny chevron wyszarzony + górny gradient znika;
- na ostatnim zdjęciu dolny chevron wyszarzony + dolny gradient znika (całe zdjęcie widoczne);
- klik miniaturki aktywuje ją;
- klik dużego zdjęcia otwiera lightbox z **aktywnym** zdjęciem;
- to samo na wersji mobilnej (≤640px): pasek poziomy pod zdjęciem, chevrony po bokach;
- strona przedsprzedaży (preorder) zachowuje się identycznie.

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/offers/product-gallery.js templates/offers/order_page.html templates/offers/order_page_preorder.html
git commit -m "feat(oferta): interakcja galerii produktu (chevrony, centrowanie, gradient, lightbox)"
```

---

### Task 5: Weryfikacja end-to-end i pełny zestaw testów

**Files:** brak zmian kodu (jeśli wszystko działa).

- [ ] **Step 1: Cały zestaw testów**

Run: `python -m pytest tests/test_product_gallery_images.py tests/test_offer_gallery_render.py -v`
Expected: PASS (6 passed)

- [ ] **Step 2: Regresja szerzej**

Run: `python -m pytest -q`
Expected: brak nowych błędów względem stanu sprzed zmian.

- [ ] **Step 3: Weryfikacja w przeglądarce (skill `verify` / `run`)**

Na realnym produkcie z 3 zdjęciami (jak na zrzucie właścicielki): strona ofertowa pokazuje pasek 3 miniaturek zamiast jednego zdjęcia. Light + dark, desktop + mobile, obie strony (zwykła i preorder).

- [ ] **Step 4: Commit (jeśli były drobne poprawki po weryfikacji)**

```bash
git add -A
git commit -m "test(oferta): weryfikacja galerii produktu end-to-end"
```

---

## Self-Review (wykonane przy pisaniu planu)

- **Pokrycie spec:** model `gallery_images` (Task 1) ✓; render pasek/1/0 zdjęć (Task 2) ✓; desktop pion + mobile poziom + light/dark + gradient w `--card-bg` (Task 3) ✓; chevrony/centrowanie/skraje/disabled/gradient-na-skraju/podmiana dużego/lightbox/orientacja (Task 4) ✓; zakres tylko główny produkt, oba szablony ✓; bez migracji ✓.
- **Placeholders:** brak — pełny kod partiala, CSS i JS.
- **Spójność nazw:** klasy DOM z partiala (`.gallery-thumb`, `.gallery-strip`, `.gallery-fade-start/-end`, `.gallery-main-image`, `.gallery-chevron-prev/-next`, `[data-gallery]`) użyte identycznie w CSS (Task 3) i JS (Task 4). `gallery_images` spójne między modelem, partialem i testami.
