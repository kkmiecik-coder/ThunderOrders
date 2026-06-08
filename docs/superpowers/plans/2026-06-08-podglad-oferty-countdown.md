# Podgląd oferty na countdownie — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Umożliwić klientowi podejrzenie pełnej oferty (read-only, z nazwami i cenami) jeszcze przed startem sprzedaży — przez przycisk „Co jest w sprzedaży?" na countdownie otwierający modal.

**Architecture:** Nowe pole `preview_enabled` na `OfferPage` (domyślnie `True`), sterowane przełącznikiem w page builderze. Route countdown ładuje sekcje i przekazuje je do szablonu. Countdown dostaje przycisk + modal (wzorzec `modal-overlay`/`modal-content` z `modals.css`), którego treść renderuje nowy, statyczny partial read-only. `order_page.html` pozostaje nietknięty.

**Tech Stack:** Flask + Flask-Migrate (Alembic) + MariaDB, Jinja2, vanilla JS, CSS (light + dark mode).

**Spec:** `docs/superpowers/specs/2026-06-08-podglad-oferty-countdown-design.md`

---

## Mapa plików

- **Modyfikacja** `modules/offers/models.py` — pole `preview_enabled` na `OfferPage`.
- **Tworzenie** `migrations/versions/<rev>_add_preview_enabled.py` — migracja.
- **Modyfikacja** `modules/offers/routes.py` — helper `should_show_preview` + przekazanie `sections` w `countdown_page()`.
- **Tworzenie** `tests/test_offer_preview.py` — test helpera.
- **Modyfikacja** `templates/admin/offers/edit.html` — checkbox „Preview na stronie odliczania".
- **Modyfikacja** `static/js/pages/admin/offer-builder.js` — `preview_enabled` w payloadzie save.
- **Modyfikacja** `modules/admin/offers.py` — obsługa `preview_enabled` w `offers_save()`.
- **Tworzenie** `templates/offers/_preview_sections.html` — statyczny read-only render sekcji.
- **Modyfikacja** `templates/offers/countdown.html` — przycisk + modal + podpięcie CSS/JS.
- **Tworzenie** `static/css/pages/offers/countdown-preview.css` — style kart podglądu (light + dark).
- **Tworzenie** `static/js/pages/offers/countdown-preview.js` — otwieranie/zamykanie modala.
- **Modyfikacja** `static/css/components/modals.css` — ewentualny wariant `.offer-preview-*` (jeśli potrzebny), inaczej bez zmian.

---

## Task 1: Pole `preview_enabled` na modelu + migracja

**Files:**
- Modify: `modules/offers/models.py` (klasa `OfferPage`, w okolicy pól `notify_clients_on_publish` / `is_fully_closed`)
- Create: `migrations/versions/<rev>_add_preview_enabled.py`

- [ ] **Step 1: Dodaj pole do modelu**

W `modules/offers/models.py`, w klasie `OfferPage`, obok `notify_clients_on_publish` dodaj:

```python
    # Czy pokazywać podgląd oferty (read-only) na stronie countdown
    preview_enabled = db.Column(db.Boolean, default=True, nullable=False)
```

- [ ] **Step 2: Wygeneruj migrację**

Run:
```bash
flask db migrate -m "Add preview_enabled to offer_pages"
```
Expected: nowy plik w `migrations/versions/` z `op.add_column('offer_pages', ...)`.

- [ ] **Step 3: Popraw migrację — server_default dla istniejących wierszy**

Otwórz wygenerowany plik. Ponieważ kolumna jest `NOT NULL`, a tabela ma istniejące wiersze, w `upgrade()` ustaw `server_default='1'`, żeby istniejące oferty dostały `True`:

```python
def upgrade():
    op.add_column('offer_pages', sa.Column('preview_enabled', sa.Boolean(), nullable=False, server_default='1'))


def downgrade():
    op.drop_column('offer_pages', 'preview_enabled')
```

(`server_default='1'` jest wymagany dla MariaDB przy dodaniu NOT NULL do niepustej tabeli; `default=True` w modelu działa tylko po stronie aplikacji dla nowych rekordów.)

- [ ] **Step 4: Zastosuj migrację lokalnie**

Run:
```bash
flask db upgrade
```
Expected: brak błędów; `SHOW COLUMNS FROM offer_pages` pokazuje `preview_enabled tinyint(1) NOT NULL DEFAULT 1`.

- [ ] **Step 5: Commit**

```bash
git add modules/offers/models.py migrations/versions/
git commit -m "feat(offers): pole preview_enabled na OfferPage + migracja"
```

---

## Task 2: Helper decyzyjny + przekazanie sekcji w route countdown

**Files:**
- Modify: `modules/offers/routes.py` (funkcja `countdown_page`, ~linie 208-240)
- Test: `tests/test_offer_preview.py`

- [ ] **Step 1: Napisz failujący test helpera**

Utwórz `tests/test_offer_preview.py`:

```python
from modules.offers.routes import should_show_preview


class FakePage:
    def __init__(self, preview_enabled):
        self.preview_enabled = preview_enabled


def test_show_when_enabled_and_sections():
    assert should_show_preview(FakePage(True), [object(), object()]) is True


def test_hide_when_disabled():
    assert should_show_preview(FakePage(False), [object()]) is False


def test_hide_when_no_sections():
    assert should_show_preview(FakePage(True), []) is False


def test_hide_when_disabled_and_no_sections():
    assert should_show_preview(FakePage(False), []) is False
```

- [ ] **Step 2: Uruchom test — ma failować**

Run: `pytest tests/test_offer_preview.py -v`
Expected: FAIL — `ImportError: cannot import name 'should_show_preview'`.

- [ ] **Step 3: Dodaj helper w routes.py**

W `modules/offers/routes.py`, nad funkcją `countdown_page` (lub w sekcji helperów na górze pliku), dodaj:

```python
def should_show_preview(page, sections):
    """Czy pokazać przycisk podglądu oferty na countdownie.

    True tylko gdy podgląd włączony per oferta ORAZ są jakieś sekcje do pokazania.
    """
    return bool(page.preview_enabled) and len(sections) > 0
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `pytest tests/test_offer_preview.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Przekaż sekcje i flagę do szablonu countdown**

W `modules/offers/routes.py`, w `countdown_page()`, zmień ostatnią linię `return render_template('offers/countdown.html', page=page)` na:

```python
    # Podgląd oferty (read-only) — tylko gdy włączony i są sekcje
    sections = page.get_sections_ordered() if page.preview_enabled else []
    show_preview = should_show_preview(page, sections)

    return render_template(
        'offers/countdown.html',
        page=page,
        sections=sections,
        show_preview=show_preview,
    )
```

- [ ] **Step 6: Commit**

```bash
git add modules/offers/routes.py tests/test_offer_preview.py
git commit -m "feat(offers): countdown przekazuje sekcje do podglądu + helper should_show_preview"
```

---

## Task 3: Przełącznik „Preview na stronie odliczania" w page builderze

**Files:**
- Modify: `templates/admin/offers/edit.html` (sekcja ustawień, ~linie 158-167)
- Modify: `static/js/pages/admin/offer-builder.js` (funkcja `collectPageData`, ~linia 838)
- Modify: `modules/admin/offers.py` (funkcja `offers_save`, ~linia 268-269)

- [ ] **Step 1: Dodaj checkbox w edytorze**

W `templates/admin/offers/edit.html`, po bloku `notifyClientsOnPublish` (po linii 167, przed `<!-- Typ realizacji zamówień -->`), dodaj:

```html
                    <!-- Podgląd oferty na countdownie -->
                    <div class="form-group checkbox-group">
                        <label class="checkbox-label">
                            <input type="checkbox"
                                   id="previewEnabled"
                                   {% if page.preview_enabled %}checked{% endif %}>
                            <span class="checkbox-text">Preview na stronie odliczania</span>
                        </label>
                        <small class="form-hint">Klient przed startem zobaczy przycisk „Co jest w sprzedaży?" z podglądem oferty (bez możliwości zamawiania).</small>
                    </div>
```

- [ ] **Step 2: Dołącz pole do payloadu zapisu**

W `static/js/pages/admin/offer-builder.js`, w `collectPageData()` (obiekt `data`, ~linia 838), po linii `notify_clients_on_publish: ...` dodaj:

```javascript
        preview_enabled: document.getElementById('previewEnabled')?.checked ?? true,
```

- [ ] **Step 3: Obsłuż pole w zapisie backendu**

W `modules/admin/offers.py`, w `offers_save()`, po bloku `notify_clients_on_publish` (po linii 269) dodaj:

```python
        if 'preview_enabled' in data:
            page.preview_enabled = bool(data['preview_enabled'])
```

- [ ] **Step 4: Test ręczny zapisu/odczytu**

Run: uruchom aplikację (`flask run` / istniejący skrypt dev na :5001), otwórz edytor oferty, odznacz „Preview na stronie odliczania", zapisz, odśwież stronę.
Expected: checkbox pozostaje odznaczony po odświeżeniu (wartość zapisana w bazie i wczytana z `page.preview_enabled`).

- [ ] **Step 5: Commit**

```bash
git add templates/admin/offers/edit.html static/js/pages/admin/offer-builder.js modules/admin/offers.py
git commit -m "feat(offers): przełącznik 'Preview na stronie odliczania' w page builderze"
```

---

## Task 4: Statyczny partial read-only renderujący sekcje

**Files:**
- Create: `templates/offers/_preview_sections.html`

- [ ] **Step 1: Utwórz partial**

Utwórz `templates/offers/_preview_sections.html`:

```jinja2
{# Read-only podgląd oferty na countdownie. Renderuje sekcje bez kontrolek zamawiania. #}
{% for section in sections %}
    {% if section.is_heading %}
    <section class="preview-section preview-heading">
        <h2>{{ section.content }}</h2>
    </section>

    {% elif section.is_paragraph %}
    <section class="preview-section preview-paragraph">
        <p>{{ section.content }}</p>
    </section>

    {% elif section.is_product and section.product %}
    <section class="preview-section preview-product">
        <div class="preview-product-media">
            {% if section.product.primary_image %}
            <img src="{{ url_for('static', filename=section.product.primary_image.path_compressed) }}" alt="{{ section.product.name }}" loading="lazy">
            {% else %}
            <div class="preview-no-image"></div>
            {% endif %}
        </div>
        <div class="preview-product-info">
            <span class="preview-product-name">{{ section.product.name }}</span>
            <span class="preview-product-price">{{ "%.2f"|format(section.product.sale_price) }} PLN</span>
        </div>
    </section>

    {% elif section.is_set %}
    <section class="preview-section preview-set">
        <h3 class="preview-set-name">{{ section.set_name }}</h3>
        {% if section.set_image %}
        <div class="preview-set-image">
            <img src="{{ url_for('static', filename=section.set_image) }}" alt="{{ section.set_name }}" loading="lazy">
        </div>
        {% endif %}
        <div class="preview-set-items">
            {% for item in section.get_set_items_ordered() %}
                {% if item.is_product and item.product %}
                <div class="preview-set-item">
                    <span class="preview-set-item-name">{{ item.product.name }}</span>
                    <span class="preview-set-item-price">{{ "%.2f"|format(item.product.sale_price) }} PLN</span>
                </div>
                {% elif item.is_variant_group and item.variant_group %}
                    {% for product in item.get_products() %}
                    <div class="preview-set-item">
                        <span class="preview-set-item-name">{{ product.name }}</span>
                        <span class="preview-set-item-price">{{ "%.2f"|format(product.sale_price) }} PLN</span>
                    </div>
                    {% endfor %}
                {% endif %}
            {% endfor %}
        </div>
        {% if section.set_product %}
        <div class="preview-full-set">
            <span class="preview-full-set-label">Pełny set</span>
            <span class="preview-full-set-price">{{ "%.2f"|format(section.set_product.sale_price) }} PLN</span>
        </div>
        {% endif %}
    </section>

    {% elif section.is_variant_group and section.variant_group %}
    <section class="preview-section preview-variant-group">
        <h3 class="preview-set-name">{{ section.variant_group.name }}</h3>
        <div class="preview-variant-products">
            {% for product in section.get_variant_group_products() %}
            {% if product.is_active %}
            <div class="preview-variant-product">
                <div class="preview-product-media">
                    {% if product.primary_image %}
                    <img src="{{ url_for('static', filename=product.primary_image.path_compressed) }}" alt="{{ product.name }}" loading="lazy">
                    {% else %}
                    <div class="preview-no-image"></div>
                    {% endif %}
                </div>
                <div class="preview-product-info">
                    <span class="preview-product-name">{{ product.name }}</span>
                    <span class="preview-product-price">{{ "%.2f"|format(product.sale_price) }} PLN</span>
                </div>
            </div>
            {% endif %}
            {% endfor %}
        </div>
    </section>

    {% elif section.is_bonus %}
        {% set bonus = section.bonuses.first() %}
        {% if bonus and bonus.is_active and bonus.bonus_product %}
        <section class="preview-section preview-bonus">
            <div class="preview-bonus-card">
                <span class="preview-bonus-icon">&#x1F381;</span>
                <div class="preview-bonus-details">
                    <h3 class="preview-bonus-title">Bonus: {{ bonus.bonus_product.name }}</h3>
                    <p class="preview-bonus-condition">
                        {% if bonus.trigger_type == 'buy_products' %}
                            Kup wymagane produkty, a otrzymasz gratis!
                        {% elif bonus.trigger_type == 'price_threshold' %}
                            Zamów za min. {{ "%.0f"|format(bonus.threshold_value) }} PLN, a otrzymasz gratis!
                        {% elif bonus.trigger_type == 'quantity_threshold' %}
                            Zamów min. {{ bonus.threshold_value|int }} szt., a otrzymasz gratis!
                        {% endif %}
                    </p>
                </div>
            </div>
        </section>
        {% endif %}
    {% endif %}
{% endfor %}
```

> Uwaga: jeśli przy weryfikacji okaże się, że relacja bonusów lub metoda elementu setu ma inną nazwę niż w `order_page_preorder.html` (`section.bonuses.first()`, `item.get_products()`, `item.is_product`, `item.is_variant_group`), użyj nazw zgodnych z tym szablonem (to jest źródło prawdy dla read-only renderu bonusów i setów).

- [ ] **Step 2: Commit**

```bash
git add templates/offers/_preview_sections.html
git commit -m "feat(offers): partial read-only podglądu sekcji oferty"
```

---

## Task 5: Przycisk + modal na countdownie, CSS i JS

**Files:**
- Modify: `templates/offers/countdown.html` (przycisk po `countdown-cta`, modal przed `{% endblock %}` body, podpięcie CSS w `extra_css`, JS w `extra_js`)
- Create: `static/css/pages/offers/countdown-preview.css`
- Create: `static/js/pages/offers/countdown-preview.js`

- [ ] **Step 1: Dodaj przycisk pod timerem**

W `templates/offers/countdown.html`, w sekcji `<!-- CTA Hint -->` (po `<div class="countdown-cta">...</div>`, ~linia 126), dodaj:

```html
        {% if show_preview %}
        <button type="button" class="countdown-preview-btn" onclick="openOfferPreview()">
            <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
                <path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8zM1.173 8a13.133 13.133 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13.133 13.133 0 0 1 14.828 8c-.058.087-.122.183-.195.288-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5c-2.12 0-3.879-1.168-5.168-2.457A13.134 13.134 0 0 1 1.172 8z"/>
                <path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0z"/>
            </svg>
            Co jest w sprzedaży?
        </button>
        {% endif %}
```

- [ ] **Step 2: Dodaj markup modala**

W `templates/offers/countdown.html`, przed zamykającym `{% endblock %}` bloku `body_content` (po modalu logowania / po `</div>` zamykającym `.countdown-page`), dodaj:

```html
{% if show_preview %}
<!-- Offer Preview Modal -->
<div id="offerPreviewModal" class="modal-overlay">
    <div class="modal-content modal-xl offer-preview-modal">
        <div class="modal-header">
            <h2 class="modal-title">Co jest w sprzedaży?</h2>
            <button type="button" class="modal-close" onclick="closeOfferPreview()" aria-label="Zamknij">
                <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8 2.146 2.854Z"/>
                </svg>
            </button>
        </div>
        <div class="modal-body offer-preview-body">
            {% include 'offers/_preview_sections.html' %}
        </div>
    </div>
</div>
{% endif %}
```

- [ ] **Step 3: Podepnij CSS i JS**

W `templates/offers/countdown.html`, w bloku `{% block extra_css %}` (po istniejących linkach, ~linia 9) dodaj:

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/pages/offers/countdown-preview.css') }}">
```

W bloku `{% block extra_js %}` (na końcu, po istniejącym inline `<script>`) dodaj:

```html
<script src="{{ url_for('static', filename='js/pages/offers/countdown-preview.js') }}"></script>
```

- [ ] **Step 4: Utwórz JS modala**

Utwórz `static/js/pages/offers/countdown-preview.js`:

```javascript
// Podgląd oferty na countdownie — otwieranie/zamykanie modala (read-only)
(function () {
    const modal = document.getElementById('offerPreviewModal');
    if (!modal) return;

    window.openOfferPreview = function () {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    };

    window.closeOfferPreview = function () {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    };

    // Klik w tło zamyka
    modal.addEventListener('click', function (e) {
        if (e.target === modal) window.closeOfferPreview();
    });

    // ESC zamyka
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            window.closeOfferPreview();
        }
    });
})();
```

- [ ] **Step 5: Utwórz CSS (light + dark)**

Utwórz `static/css/pages/offers/countdown-preview.css`:

```css
/* Przycisk podglądu na countdownie */
.countdown-preview-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    padding: 12px 24px;
    min-height: 44px;
    border: 1px solid rgba(240, 147, 251, 0.4);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: #ffffff;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    backdrop-filter: blur(10px);
    transition: background 0.2s ease, transform 0.2s ease;
}
.countdown-preview-btn:hover {
    background: rgba(240, 147, 251, 0.2);
    transform: translateY(-2px);
}

/* Body modala podglądu */
.offer-preview-body {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.preview-section { width: 100%; }
.preview-heading h2 { margin: 8px 0; font-size: 1.25rem; color: #1a1a1a; }
.preview-paragraph p { margin: 0; color: #444; line-height: 1.6; }

/* Karta produktu */
.preview-product,
.preview-variant-product {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 12px;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    background: #ffffff;
}
.preview-product-media img,
.preview-no-image {
    width: 64px;
    height: 64px;
    object-fit: cover;
    border-radius: 8px;
    background: #f0f0f0;
    flex-shrink: 0;
}
.preview-product-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.preview-product-name { font-weight: 600; color: #1a1a1a; }
.preview-product-price { color: #f5576c; font-weight: 700; }

/* Set */
.preview-set,
.preview-variant-group {
    padding: 16px;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    background: #fafafa;
}
.preview-set-name { margin: 0 0 12px; font-size: 1.1rem; color: #1a1a1a; }
.preview-set-image img {
    width: 100%;
    max-height: 220px;
    object-fit: cover;
    border-radius: 8px;
    margin-bottom: 12px;
}
.preview-set-items {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.preview-set-item {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 8px 12px;
    background: #ffffff;
    border-radius: 8px;
}
.preview-set-item-name { color: #1a1a1a; }
.preview-set-item-price { color: #f5576c; font-weight: 600; white-space: nowrap; }
.preview-full-set {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 12px;
    padding: 12px 16px;
    border-radius: 8px;
    background: linear-gradient(135deg, rgba(240, 147, 251, 0.15), rgba(245, 87, 108, 0.15));
    font-weight: 700;
    color: #1a1a1a;
}
.preview-full-set-price { color: #f5576c; }

.preview-variant-products {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

/* Bonus */
.preview-bonus-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 16px;
    border: 1px dashed rgba(240, 147, 251, 0.5);
    border-radius: 12px;
    background: rgba(240, 147, 251, 0.06);
}
.preview-bonus-icon { font-size: 1.6rem; }
.preview-bonus-title { margin: 0 0 4px; font-size: 1rem; color: #1a1a1a; }
.preview-bonus-condition { margin: 0; font-size: 0.875rem; color: #666; }

/* ===== Dark mode ===== */
[data-theme="dark"] .countdown-preview-btn {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.3);
    color: #ffffff;
}
[data-theme="dark"] .countdown-preview-btn:hover {
    background: rgba(240, 147, 251, 0.2);
}
[data-theme="dark"] .preview-heading h2,
[data-theme="dark"] .preview-product-name,
[data-theme="dark"] .preview-set-name,
[data-theme="dark"] .preview-set-item-name,
[data-theme="dark"] .preview-full-set,
[data-theme="dark"] .preview-bonus-title { color: #ffffff; }
[data-theme="dark"] .preview-paragraph p,
[data-theme="dark"] .preview-bonus-condition { color: rgba(255, 255, 255, 0.7); }
[data-theme="dark"] .preview-product,
[data-theme="dark"] .preview-variant-product {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
}
[data-theme="dark"] .preview-set,
[data-theme="dark"] .preview-variant-group {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(240, 147, 251, 0.15);
}
[data-theme="dark"] .preview-set-item {
    background: rgba(255, 255, 255, 0.05);
}
[data-theme="dark"] .preview-no-image {
    background: rgba(255, 255, 255, 0.08);
}
[data-theme="dark"] .preview-bonus-card {
    background: rgba(240, 147, 251, 0.08);
    border-color: rgba(240, 147, 251, 0.3);
}
```

- [ ] **Step 6: Test ręczny (light + dark)**

Run: uruchom aplikację na :5001, utwórz/znajdź ofertę w statusie `scheduled` z datą startu w przyszłości, kilkoma sekcjami (produkt, set, variant_group, bonus, heading, paragraph) i `preview_enabled=True`. Wejdź na `/countdown?page=<token>`.
Expected:
- Przycisk „Co jest w sprzedaży?" widoczny pod timerem.
- Klik otwiera modal z wszystkimi typami sekcji (nazwy + ceny, składy setów, warianty, bonusy, nagłówki/opisy), bez przycisków zamawiania.
- ESC, klik w tło i przycisk „×" zamykają modal.
- Przełącz motyw na dark — modal i karty czytelne, paleta różowa zgodna z projektem.
- Wyłącz `preview_enabled` w edytorze, zapisz, odśwież countdown → przycisk znika.

- [ ] **Step 7: Commit**

```bash
git add templates/offers/countdown.html static/css/pages/offers/countdown-preview.css static/js/pages/offers/countdown-preview.js
git commit -m "feat(offers): przycisk i modal podglądu oferty na countdownie"
```

---

## Self-review (do wykonania przed deployem)

- **Pokrycie spec:** model+migracja (Task 1), page builder toggle (Task 3), route (Task 2), przycisk+modal (Task 5), partial read-only ze wszystkimi typami sekcji wraz z heading/paragraph (Task 4), CSS light+dark (Task 5), wykluczenia YAGNI zachowane (`order_page.html` nietknięty). ✓
- **Spójność nazw:** `preview_enabled` (model/migracja/save/JS/template), `should_show_preview` + `show_preview` (route/template), `openOfferPreview`/`closeOfferPreview` (JS/template), `#offerPreviewModal` (JS/template). ✓
- **Weryfikacja przy implementacji:** potwierdzić nazwy relacji bonusów i metod elementu setu względem `templates/offers/order_page_preorder.html` (źródło prawdy) — patrz uwaga w Task 4 Step 1.

## Deploy

Po merge do `main`: auto-deploy webhook (łącznie z migracją `flask db upgrade`). Restart usług na serwerze zgodnie z `docs/DEPLOYMENT.md`: `sudo systemctl restart thunderorders-http thunderorders-ws`.
