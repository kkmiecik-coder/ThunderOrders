# Scalony modal zlecenia wysyłki — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zastąpić trzy rozjeżdżające się warianty modala zlecenia wysyłki jednym modalem w układzie lista + szczegóły, obsługującym od 1 do N zleceń, z wymaganym gabarytem i terminem płatności.

**Architecture:** Jeden partial Jinja (`_shipping_request_modal.html`) dołączany na obu stronach, jeden nowy plik JS (`shipping-request-modal.js`) trzymający stan edycji w pamięci i zapisujący `N × PUT` dopiero na „Zapisz wszystkie", jedno miejsce ze stylami (`modals.css`). Backend bez zmian — wszystkie potrzebne pola przyjmuje istniejący endpoint.

**Tech Stack:** Flask + Jinja2, waniliowy JavaScript (bez frameworka, IIFE + delegacja zdarzeń), CSS z wariantami `[data-theme="dark"]`, testy `pytest` przez `python -m pytest`.

**Spec:** [docs/superpowers/specs/2026-08-03-gabaryt-w-modalu-masowym-design.md](../specs/2026-08-03-gabaryt-w-modalu-masowym-design.md)

## Global Constraints

- Wszystkie style modala wyłącznie w `static/css/components/modals.css`, każdy z wariantem `[data-theme="dark"]` (paleta: tła `rgba(255,255,255,0.05)`, obramowania `rgba(240,147,251,0.15)`, akcent `#f093fb`, tekst `#ffffff`).
- Komunikaty użytkownika przez `window.showToast(msg, type)`. `window.Toast` w tym projekcie nie istnieje — nie używać. Żadnych nowych `alert()`.
- Testy uruchamiane jako `python -m pytest` (gołe `pytest` pada na `No module named 'app'`).
- Brak zmian w backendzie i w bazie — żadnych migracji.
- Elementy dotykowe min. 44 px wysokości na mobile.
- Kod JS bez inline `onclick` w nowym markupie — delegacja zdarzeń i `data-*`. Wyjątek: istniejące `onclick="openShippingRequestModal(id)"` w `wms_dashboard.html` i `detail.html` zostają, obsłuży je globalny alias.
- Gabaryt: wartości `mini`, `A`, `B`, `C` z etykietami `Mini`, `A - Mały`, `B - Średni`, `C - Duży`.
- Zlecenie jest gotowe, gdy ma gabaryt, sumę kosztów > 0 i termin płatności; termin nie jest wymagany przy statusie `oplacone`.

---

## File Structure

| Plik | Odpowiedzialność |
|---|---|
| `templates/admin/orders/_shipping_request_modal.html` | jedyny markup modala: nagłówek, pasek zbiorczy, kontener listy, kontener szczegółów, stopka |
| `static/js/pages/admin/shipping-request-modal.js` | **nowy** — stan modala, pobieranie danych, render, walidacja, zapis, anulowanie |
| `static/js/pages/admin/shipping-requests.js` | zaznaczanie kart i akcje masowe (scal, WMS, usuń); traci cały kod modala |
| `static/css/components/modals.css` | style modala (siatka, lista, znaczniki, pasek zbiorczy, żetony mobilne) |
| `static/css/pages/admin/shipping-requests-list.css` | style kart listy zleceń; traci reguły modala |
| `templates/admin/orders/wms_dashboard.html` | usuwa `#bulkCostModal`, zmienia etykietę przycisku |
| `templates/admin/orders/detail.html` | usuwa kopię modala, dołącza partial |
| `tests/test_shipping_request_modal_merge.py` | **nowy** — testy renderowania scalonego modala |

---

### Task 1: Jeden modal na obu stronach (markup + testy renderowania)

Zadanie kończy się tym, że obie strony renderują ten sam, nowy markup modala, a `#bulkCostModal` znika z kodu. Modal jest jeszcze pusty w środku — wypełnia go Task 2.

**Files:**
- Test: `tests/test_shipping_request_modal_merge.py` (create)
- Modify: `templates/admin/orders/_shipping_request_modal.html` (całość)
- Modify: `templates/admin/orders/wms_dashboard.html:706-745` (etykieta przycisku), `:751-771` (usunięcie `#bulkCostModal`)
- Modify: `templates/admin/orders/detail.html:3071-3180` (usunięcie kopii, include)

**Interfaces:**
- Produces: `#editShippingRequestModal` z gniazdami `#srModalList`, `#srModalDetail`, `#srBulkBar`, `#srModalProgress`, `#srModalSaveBtn`, `#srCancelRequestBtn`, `#srModalTitle` — Task 2 renderuje do nich treść.

- [ ] **Step 1: Napisz testy renderowania**

Utwórz `tests/test_shipping_request_modal_merge.py`:

```python
"""Scalony modal zlecenia wysyłki: jeden markup na obu stronach."""


def _admin(make_user):
    return make_user(role='admin', email='admin@example.com', profile_completed=True)


def _sr_with_order(db, make_user, make_order):
    from modules.orders.models import ShippingRequest, ShippingRequestOrder
    u = make_user()
    o = make_order(u, status='dostarczone_gom')
    sr = ShippingRequest(request_number=ShippingRequest.generate_request_number(),
                         user_id=u.id, status='czeka_na_wycene')
    db.session.add(sr)
    db.session.commit()
    db.session.add(ShippingRequestOrder(shipping_request_id=sr.id, order_id=o.id))
    db.session.commit()
    return sr, o


def test_wms_renders_merged_modal_without_bulk_modal(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert resp.status_code == 200
    assert b'id="editShippingRequestModal"' in resp.data
    assert b'id="srModalList"' in resp.data
    assert b'id="srBulkBar"' in resp.data
    assert b'id="bulkCostModal"' not in resp.data


def test_wms_bulk_button_relabeled(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert 'Koszty i gabaryt'.encode() in resp.data


def test_order_detail_uses_same_modal_partial(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr, order = _sr_with_order(db, make_user, make_order)
    resp = client.get(f'/admin/orders/{order.id}')
    assert resp.status_code == 200
    assert b'id="editShippingRequestModal"' in resp.data
    assert b'id="srModalDetail"' in resp.data
    # gniazda, których stara kopia w detail.html nie miała:
    assert b'id="srBulkParcelSize"' in resp.data
    assert b'id="srModalList"' in resp.data


def test_modal_partial_included_once_per_page(client, db, make_user, make_order, login):
    login(_admin(make_user))
    _sr_with_order(db, make_user, make_order)
    resp = client.get('/admin/orders/wms?tab=shipping')
    assert resp.data.count(b'id="editShippingRequestModal"') == 1
```

- [ ] **Step 2: Uruchom testy — mają paść**

```bash
python -m pytest tests/test_shipping_request_modal_merge.py -v
```

Oczekiwane: FAIL — `id="srModalList"` nie istnieje, `id="bulkCostModal"` wciąż jest w WMS, `detail.html` nie renderuje `srModalDetail`.

- [ ] **Step 3: Przepisz partial modala**

Zastąp całą zawartość `templates/admin/orders/_shipping_request_modal.html`:

```html
<!-- Scalony modal zlecenia wysyłki: obsługuje 1..N zleceń (lista + szczegóły) -->
<div id="editShippingRequestModal" class="modal-overlay">
    <div class="modal-content modal-xl sr-modal">
        <div class="modal-header">
            <h2 id="srModalTitle">Zlecenie <span id="srModalNumber"></span></h2>
            <button type="button" class="modal-close" id="srModalCloseX" aria-label="Zamknij">&times;</button>
        </div>

        <div class="sr-bulk-bar" id="srBulkBar" hidden>
            <span class="sr-bulk-bar-title">Ustaw we wszystkich</span>
            <div class="sr-bulk-bar-fields">
                <div class="form-group">
                    <label class="form-label" for="srBulkDeadlineDate">Termin płatności</label>
                    <div class="sr-inline-fields">
                        <input type="date" id="srBulkDeadlineDate" class="form-control">
                        <input type="time" id="srBulkDeadlineTime" class="form-control" value="23:59">
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label" for="srBulkMaterial">Materiał</label>
                    <select id="srBulkMaterial" class="form-control">
                        <option value="">-- Bez zmian --</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label" for="srBulkParcelSize">Gabaryt</label>
                    <select id="srBulkParcelSize" class="form-control">
                        <option value="">-- Bez zmian --</option>
                        <option value="mini">Mini</option>
                        <option value="A">A - Mały</option>
                        <option value="B">B - Średni</option>
                        <option value="C">C - Duży</option>
                    </select>
                </div>
            </div>
            <button type="button" class="btn btn-secondary" id="srBulkApply">Zastosuj</button>
        </div>

        <div class="modal-body sr-modal-body">
            <nav class="sr-modal-list" id="srModalList" hidden aria-label="Zaznaczone zlecenia"></nav>
            <div class="sr-modal-detail" id="srModalDetail"></div>
        </div>

        <div class="modal-footer sr-modal-footer">
            <span class="sr-modal-progress" id="srModalProgress"></span>
            <div class="sr-modal-footer-actions">
                <button type="button" class="btn btn-danger" id="srCancelRequestBtn" hidden>Anuluj zlecenie</button>
                <button type="button" class="btn btn-secondary" id="srModalCloseBtn">Zamknij</button>
                <button type="button" class="btn btn-primary" id="srModalSaveBtn">Zapisz wszystkie</button>
            </div>
        </div>
    </div>
</div>
```

- [ ] **Step 4: Usuń `#bulkCostModal` i zmień etykietę przycisku w WMS**

W `templates/admin/orders/wms_dashboard.html` zmień etykietę przycisku (linie 710–715):

```html
            <button class="btn-bulk" data-action="bulk-cost" title="Koszty i gabaryt">
                <svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M4 10.781c.148 1.667 1.513 2.85 3.591 3.003V15h1.043v-1.216c2.27-.179 3.678-1.438 3.678-3.3 0-1.59-.947-2.51-2.956-3.028l-.722-.187V3.467c1.122.11 1.879.714 2.07 1.616h1.47c-.166-1.6-1.54-2.748-3.54-2.875V1H7.591v1.233c-1.939.23-3.27 1.472-3.27 3.156 0 1.454.966 2.483 2.661 2.917l.61.162v4.031c-1.149-.17-1.94-.8-2.131-1.718H4zm3.391-3.836c-1.043-.263-1.6-.825-1.6-1.616 0-.944.704-1.641 1.8-1.828v3.495l-.2-.05zm1.591 1.872c1.287.323 1.852.859 1.852 1.769 0 1.097-.826 1.828-2.2 1.939V8.73l.348.086z"/>
                </svg>
                Koszty i gabaryt
            </button>
```

Następnie usuń cały blok `<!-- Bulk Cost Modal -->` wraz z `<div id="bulkCostModal">…</div>` (linie 751–770), zostawiając `{% endif %}` zamykający blok `active_tab == 'shipping'`.

- [ ] **Step 5: Podmień kopię modala w detail.html na include**

W `templates/admin/orders/detail.html` usuń cały blok `<div id="editShippingRequestModal" class="modal-overlay">…</div>` (linie ~3071–3180) i wstaw w jego miejsce:

```html
{% include 'admin/orders/_shipping_request_modal.html' %}
```

- [ ] **Step 6: Uruchom testy — mają przejść**

```bash
python -m pytest tests/test_shipping_request_modal_merge.py -v
```

Oczekiwane: 4 passed.

- [ ] **Step 7: Sprawdź, że nic innego się nie wywróciło**

```bash
python -m pytest tests/ -q
```

Oczekiwane: brak nowych błędów względem stanu sprzed zmiany.

- [ ] **Step 8: Commit**

```bash
git add tests/test_shipping_request_modal_merge.py templates/admin/orders/_shipping_request_modal.html templates/admin/orders/wms_dashboard.html templates/admin/orders/detail.html
git commit -m "refactor(wms): jeden markup modala zlecenia wysylki na obu stronach"
```

---

### Task 2: Otwarcie modala, lista zleceń i panel szczegółów

Po tym zadaniu modal otwiera się z każdego z trzech wejść, pobiera dane i renderuje komplet sekcji. Zapis jeszcze nie działa.

**Files:**
- Create: `static/js/pages/admin/shipping-request-modal.js`
- Modify: `templates/admin/orders/wms_dashboard.html` (blok `extra_js`), `templates/admin/orders/detail.html` (sekcja skryptów)

**Interfaces:**
- Consumes: gniazda DOM z Task 1.
- Produces: `window.openShippingRequestsModal(ids)`, `window.openShippingRequestModal(id)` (alias), `window.closeShippingRequestModal()`; wewnętrzny obiekt `state` z polami `ids`, `data` (Map), `edits` (Map), `materials` (Array), `activeId`.

- [ ] **Step 1: Utwórz plik modala ze stanem i pobieraniem danych**

Utwórz `static/js/pages/admin/shipping-request-modal.js`:

```js
/**
 * Scalony modal zlecenia wysyłki (1..N zleceń).
 * Stan edycji trzymany w pamięci; zapis dopiero na "Zapisz wszystkie".
 */
(function () {
    'use strict';

    const PARCEL_LABELS = { mini: 'Mini', A: 'A - Mały', B: 'B - Średni', C: 'C - Duży' };
    const COURIER_LABELS = {
        inpost: 'InPost', dpd: 'DPD', dhl: 'DHL', ups: 'UPS', fedex: 'FedEx',
        gls: 'GLS', pocztex: 'Pocztex', orlen: 'Orlen Paczka', other: 'Inny'
    };

    const state = {
        ids: [],
        data: new Map(),      // id -> odpowiedź GET
        edits: new Map(),     // id -> zmiany użytkownika
        materials: [],
        activeId: null,
    };

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        const cookie = document.cookie.split(';').map(c => c.trim())
            .find(c => c.startsWith('csrf_token='));
        return cookie ? cookie.substring('csrf_token='.length) : '';
    }

    function notify(message, type) {
        if (typeof window.showToast === 'function') window.showToast(message, type);
        else console.warn(message);
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function money(value) {
        return (parseFloat(value) || 0).toFixed(2);
    }

    /** Skrót adresu do listy i nagłówka. */
    function addressSummary(sr) {
        if (sr.address_type === 'pickup_point') {
            const courier = sr.pickup_courier || 'Punkt odbioru';
            return sr.pickup_point_id ? `${courier}: ${sr.pickup_point_id}` : courier;
        }
        return sr.shipping_city ? `Kurier · ${sr.shipping_city}` : 'Kurier';
    }

    /** Stan edycji zlecenia — inicjowany z danych z serwera. */
    function initEdits(sr) {
        const deadline = sr.payment_deadline ? sr.payment_deadline.split('T') : null;
        return {
            orderCosts: new Map(sr.orders.map(o => [o.id, o.shipping_cost || 0])),
            deadlineDate: deadline ? deadline[0] : '',
            deadlineTime: deadline ? deadline[1].substring(0, 5) : '23:59',
            parcelSize: sr.parcel_size || '',
            packagingMaterialId: sr.packaging_material_id || '',
            courier: sr.courier || '',
            trackingNumber: sr.tracking_number || '',
        };
    }

    function totalCost(id) {
        const edits = state.edits.get(id);
        if (!edits) return 0;
        let sum = 0;
        edits.orderCosts.forEach(v => { sum += parseFloat(v) || 0; });
        return Math.round(sum * 100) / 100;
    }

    window.openShippingRequestsModal = openShippingRequestsModal;
    window.openShippingRequestModal = (id) => openShippingRequestsModal([id]);
    window.closeShippingRequestModal = closeModal;
})();
```

- [ ] **Step 2: Dopisz pobieranie danych i otwarcie modala**

W tym samym pliku, przed blokiem `window.*`, dodaj:

```js
    async function fetchMaterials() {
        try {
            const resp = await fetch('/api/orders/packaging-materials');
            const data = await resp.json();
            return data.materials || [];
        } catch (error) {
            console.error('Nie udało się pobrać materiałów:', error);
            return [];   // modal działa dalej, select materiału zostaje pusty
        }
    }

    async function openShippingRequestsModal(ids) {
        const modal = document.getElementById('editShippingRequestModal');
        if (!modal || !ids || !ids.length) return;

        state.ids = ids.map(String);
        state.data.clear();
        state.edits.clear();
        state.activeId = null;

        const detail = document.getElementById('srModalDetail');
        detail.innerHTML = '<div class="sr-modal-loading">Ładowanie danych…</div>';
        modal.classList.add('active');

        const [materials, responses] = await Promise.all([
            fetchMaterials(),
            Promise.all(state.ids.map(id =>
                fetch(`/admin/orders/shipping-requests/${id}`).then(r => r.json())
            )),
        ]);

        state.materials = materials;
        responses.forEach(sr => {
            state.data.set(String(sr.id), sr);
            state.edits.set(String(sr.id), initEdits(sr));
        });

        state.activeId = state.ids[0];
        renderHeader();
        renderList();
        renderDetail();
    }

    function closeModal() {
        const modal = document.getElementById('editShippingRequestModal');
        if (!modal || !modal.classList.contains('active')) return;
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active', 'closing');
            state.ids = [];
            state.data.clear();
            state.edits.clear();
            state.activeId = null;
        }, 350);
    }
```

- [ ] **Step 3: Dopisz render nagłówka, listy i paska zbiorczego**

```js
    function renderHeader() {
        const many = state.ids.length > 1;
        const title = document.getElementById('srModalTitle');
        const bulkBar = document.getElementById('srBulkBar');
        const list = document.getElementById('srModalList');
        const cancelBtn = document.getElementById('srCancelRequestBtn');
        const saveBtn = document.getElementById('srModalSaveBtn');

        if (many) {
            title.textContent = `Zlecenia wysyłki · ${state.ids.length}`;
            saveBtn.textContent = 'Zapisz wszystkie';
        } else {
            const sr = state.data.get(state.activeId);
            title.textContent = `Zlecenie ${sr ? sr.request_number : ''}`;
            saveBtn.textContent = 'Zapisz';
        }

        bulkBar.hidden = !many;
        list.hidden = !many;
        cancelBtn.hidden = many;

        if (many) renderBulkMaterials();
    }

    function renderBulkMaterials() {
        const select = document.getElementById('srBulkMaterial');
        select.innerHTML = '<option value="">-- Bez zmian --</option>';
        state.materials.forEach(m => select.appendChild(materialOption(m)));
    }

    function materialOption(m) {
        const price = m.sale_price != null ? ` — ${money(m.sale_price)} zł` : '';
        const size = m.size_display ? ` (${m.size_display})` : '';
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.type_display} ${m.name}${size}${price}`;
        opt.dataset.salePrice = m.sale_price != null ? m.sale_price : '';
        opt.dataset.sizeCategory = m.size_category || '';
        return opt;
    }

    function renderList() {
        const list = document.getElementById('srModalList');
        if (list.hidden) return;

        list.innerHTML = state.ids.map(id => {
            const sr = state.data.get(id);
            if (!sr) return '';
            const edits = state.edits.get(id);
            const ready = isReady(id);
            // GET zwraca tylko dane adresowe — nie ma obiektu użytkownika.
            const client = sr.shipping_name || sr.pickup_city || '';
            const parcel = edits.parcelSize ? PARCEL_LABELS[edits.parcelSize] : 'brak gabarytu';
            const cost = totalCost(id);
            return `
                <button type="button" class="sr-list-item${id === state.activeId ? ' active' : ''}${ready ? ' ready' : ' incomplete'}"
                        data-sr-id="${id}">
                    <span class="sr-list-mark" aria-hidden="true">${ready ? '✓' : '!'}</span>
                    <span class="sr-list-body">
                        <span class="sr-list-number">${escapeHtml(sr.request_number)}</span>
                        <span class="sr-list-meta">${escapeHtml(client)} · ${escapeHtml(addressSummary(sr))}</span>
                        <span class="sr-list-meta">${cost > 0 ? money(cost) + ' PLN' : 'brak kosztu'} · ${escapeHtml(parcel)}</span>
                    </span>
                </button>
            `;
        }).join('');

        renderProgress();
    }

    function renderProgress() {
        const progress = document.getElementById('srModalProgress');
        const ready = state.ids.filter(isReady).length;
        progress.textContent = state.ids.length > 1
            ? `Gotowe ${ready} z ${state.ids.length}`
            : '';
    }
```

- [ ] **Step 4: Dopisz warunek gotowości i render panelu szczegółów**

```js
    /** Zlecenie gotowe = gabaryt + koszt > 0 + termin (poza już opłaconymi). */
    function isReady(id) {
        const sr = state.data.get(id);
        const edits = state.edits.get(id);
        if (!sr || !edits) return false;
        if (!edits.parcelSize) return false;
        if (totalCost(id) <= 0) return false;
        if (sr.status !== 'oplacone' && !(edits.deadlineDate && edits.deadlineTime)) return false;
        return true;
    }

    function renderDetail() {
        const container = document.getElementById('srModalDetail');
        const id = state.activeId;
        const sr = state.data.get(id);
        const edits = state.edits.get(id);
        if (!sr || !edits) return;

        const ordersRows = sr.orders.map(o => `
            <tr>
                <td><a href="/admin/orders/${o.id}" target="_blank" class="sr-order-link">${escapeHtml(o.order_number)}</a></td>
                <td class="text-right">${money(o.total_amount)} PLN</td>
                <td>
                    <div class="sr-cost-input">
                        <input type="number" class="form-control sr-order-cost" data-order-id="${o.id}"
                               step="0.01" min="0" placeholder="0.00"
                               value="${edits.orderCosts.get(o.id) > 0 ? money(edits.orderCosts.get(o.id)) : ''}">
                        <span class="currency">PLN</span>
                    </div>
                </td>
            </tr>
        `).join('');

        const prefLabels = { karton: 'Karton', koperta: 'Koperta' };
        const courierOptions = Object.entries(COURIER_LABELS).map(([value, label]) =>
            `<option value="${value}"${edits.courier === value ? ' selected' : ''}>${label}</option>`
        ).join('');
        const parcelOptions = Object.entries(PARCEL_LABELS).map(([value, label]) =>
            `<option value="${value}"${edits.parcelSize === value ? ' selected' : ''}>${label}</option>`
        ).join('');

        container.innerHTML = `
            <div class="sr-detail-head">
                <span class="sr-detail-number">${escapeHtml(sr.request_number)}</span>
                <span class="sr-detail-status badge">${escapeHtml(sr.status_display_name || sr.status)}</span>
            </div>

            <section class="sr-detail-section">
                <h3>Wycena</h3>
                <div class="sr-detail-grid">
                    <div class="form-group">
                        <label class="form-label" for="srTotalCost">Koszt całkowity</label>
                        <div class="sr-cost-input">
                            <input type="number" id="srTotalCost" class="form-control" step="0.01" min="0"
                                   placeholder="0.00" value="${totalCost(id) > 0 ? money(totalCost(id)) : ''}">
                            <span class="currency">PLN</span>
                            <button type="button" class="btn btn-sm btn-secondary" id="srDistribute">Rozłóż</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srDeadlineDate">Termin płatności</label>
                        <div class="sr-inline-fields">
                            <input type="date" id="srDeadlineDate" class="form-control" value="${edits.deadlineDate}">
                            <input type="time" id="srDeadlineTime" class="form-control" value="${edits.deadlineTime}">
                        </div>
                    </div>
                </div>
            </section>

            <section class="sr-detail-section">
                <h3>Zamówienia (${sr.orders.length})</h3>
                <table class="sr-orders-table">
                    <thead><tr><th>Zamówienie</th><th class="text-right">Wartość</th><th>Koszt wysyłki</th></tr></thead>
                    <tbody>${ordersRows}</tbody>
                </table>
            </section>

            <section class="sr-detail-section">
                <h3>Opakowanie</h3>
                <div class="sr-detail-grid">
                    <div class="form-group">
                        <label class="form-label" for="srPackagingMaterial">Materiał / cennik</label>
                        <select id="srPackagingMaterial" class="form-control"></select>
                        <small class="input-hint">Wybór podstawia cenę i gabaryt — można nadpisać ręcznie.</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srParcelSize">Gabaryt</label>
                        <select id="srParcelSize" class="form-control">
                            <option value="">-- Wybierz --</option>
                            ${parcelOptions}
                        </select>
                    </div>
                </div>
                <div class="sr-client-panel">
                    <span class="sr-client-panel-title">Od klienta</span>
                    <span class="sr-client-hint">Opakowanie: ${escapeHtml(prefLabels[sr.client_package_preference] || '—')}</span>
                    <span class="sr-client-hint">Uwagi: ${escapeHtml(sr.client_notes || '—')}</span>
                </div>
            </section>

            <section class="sr-detail-section">
                <h3>Adres dostawy</h3>
                <div class="sr-address-preview">${addressHtml(sr)}</div>
            </section>

            <section class="sr-detail-section">
                <h3>Dane wysyłki</h3>
                <div class="sr-detail-grid">
                    <div class="form-group">
                        <label class="form-label" for="srCourier">Kurier</label>
                        <select id="srCourier" class="form-control">
                            <option value="">-- Wybierz kuriera --</option>
                            ${courierOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srTracking">Numer tracking</label>
                        <input type="text" id="srTracking" class="form-control" placeholder="Numer przesyłki"
                               value="${escapeHtml(edits.trackingNumber)}">
                    </div>
                </div>
            </section>
        `;

        renderDetailMaterials(sr, edits);
    }

    function renderDetailMaterials(sr, edits) {
        const select = document.getElementById('srPackagingMaterial');
        if (!select) return;
        select.innerHTML = '<option value="">-- Wybierz materiał --</option>';
        state.materials.forEach(m => select.appendChild(materialOption(m)));

        // Materiał zdezaktywowany, ale przypisany — dołóż, żeby nie zgubić przypisania.
        const pm = sr.packaging_material;
        if (pm && !state.materials.some(m => m.id === pm.id)) {
            const opt = materialOption(pm);
            opt.textContent += ' (nieaktywny)';
            select.appendChild(opt);
        }
        select.value = edits.packagingMaterialId || '';
    }

    function addressHtml(sr) {
        if (sr.address_type === 'pickup_point') {
            return [
                `<div class="address-type-badge pickup">Paczkomat / Punkt odbioru</div>`,
                sr.pickup_courier ? `<div><strong>${escapeHtml(sr.pickup_courier)}</strong></div>` : '',
                sr.pickup_point_id ? `<div class="pickup-id">${escapeHtml(sr.pickup_point_id)}</div>` : '',
                sr.pickup_address ? `<div>${escapeHtml(sr.pickup_address)}</div>` : '',
                `<div>${escapeHtml(sr.pickup_postal_code || '')} ${escapeHtml(sr.pickup_city || '')}</div>`,
            ].join('');
        }
        return [
            sr.shipping_name ? `<div><strong>${escapeHtml(sr.shipping_name)}</strong></div>` : '',
            sr.shipping_address ? `<div>${escapeHtml(sr.shipping_address)}</div>` : '',
            `<div>${escapeHtml(sr.shipping_postal_code || '')} ${escapeHtml(sr.shipping_city || '')}</div>`,
            sr.shipping_voivodeship ? `<div class="text-muted">woj. ${escapeHtml(sr.shipping_voivodeship)}</div>` : '',
        ].join('') || '<span class="text-muted">Brak adresu</span>';
    }
```

- [ ] **Step 5: Podepnij skrypt na obu stronach**

W `templates/admin/orders/wms_dashboard.html`, w bloku `extra_js`, po `shipping-requests.js`:

```html
<script src="{{ url_for('static', filename='js/pages/admin/shipping-request-modal.js') }}"></script>
```

To samo w `templates/admin/orders/detail.html`, po istniejącym `<script src="…/shipping-requests.js">`.

- [ ] **Step 6: Sprawdź w przeglądarce**

Uruchom serwer (preview_start), wejdź na `/admin/orders/wms?tab=shipping`, kliknij zlecenie.
Oczekiwane: modal otwiera się z jedną pozycją, bez lewej listy, z sekcjami Wycena / Zamówienia /
Opakowanie / Adres dostawy / Dane wysyłki. W konsoli brak błędów.

- [ ] **Step 7: Commit**

```bash
git add static/js/pages/admin/shipping-request-modal.js templates/admin/orders/wms_dashboard.html templates/admin/orders/detail.html
git commit -m "feat(wms): scalony modal zlecenia - render listy i szczegolow"
```

---

### Task 3: Stan edycji, przełączanie zleceń i wskaźnik kompletności

Po tym zadaniu zmiany w polach przeżywają przełączenie na inne zlecenie, a lista pokazuje aktualny stan gotowości.

**Files:**
- Modify: `static/js/pages/admin/shipping-request-modal.js`

**Interfaces:**
- Consumes: `state`, `renderList()`, `renderDetail()`, `isReady(id)`, `totalCost(id)` z Task 2.
- Produces: `bindEvents()` wywoływane raz przy starcie; delegacja zdarzeń na `#srModalDetail` i `#srModalList`.

- [ ] **Step 1: Dodaj delegację zdarzeń dla panelu szczegółów**

```js
    function bindDetailEvents() {
        const detail = document.getElementById('srModalDetail');

        detail.addEventListener('input', (e) => {
            const edits = state.edits.get(state.activeId);
            if (!edits) return;

            if (e.target.classList.contains('sr-order-cost')) {
                const orderId = parseInt(e.target.dataset.orderId, 10);
                edits.orderCosts.set(orderId, parseFloat(e.target.value) || 0);
                const total = document.getElementById('srTotalCost');
                if (total) total.value = totalCost(state.activeId) > 0 ? money(totalCost(state.activeId)) : '';
                refreshStatus();
                return;
            }

            if (e.target.id === 'srTracking') { edits.trackingNumber = e.target.value; return; }
            if (e.target.id === 'srDeadlineDate') { edits.deadlineDate = e.target.value; refreshStatus(); return; }
            if (e.target.id === 'srDeadlineTime') { edits.deadlineTime = e.target.value; refreshStatus(); return; }
        });

        detail.addEventListener('change', (e) => {
            const edits = state.edits.get(state.activeId);
            if (!edits) return;

            if (e.target.id === 'srParcelSize') { edits.parcelSize = e.target.value; refreshStatus(); return; }
            if (e.target.id === 'srCourier') { edits.courier = e.target.value; return; }
            if (e.target.id === 'srPackagingMaterial') {
                applyMaterial(state.activeId, e.target.options[e.target.selectedIndex]);
                renderDetail();
                refreshStatus();
            }
        });

        detail.addEventListener('click', (e) => {
            if (e.target.closest('#srDistribute')) distributeCost(state.activeId);
        });
    }

    /** Materiał podstawia cenę (z rozłożeniem) i gabaryt — obie wartości można potem nadpisać. */
    function applyMaterial(id, option) {
        const edits = state.edits.get(id);
        if (!edits || !option) return;

        edits.packagingMaterialId = option.value || '';
        const size = option.dataset.sizeCategory;
        if (size) edits.parcelSize = size;

        const price = parseFloat(option.dataset.salePrice);
        if (!isNaN(price) && price > 0) spreadCost(id, price);
    }

    /** Rozkłada kwotę równo na zamówienia; resztę z zaokrąglenia dostaje pierwsze. */
    function spreadCost(id, total) {
        const edits = state.edits.get(id);
        const orderIds = Array.from(edits.orderCosts.keys());
        if (!orderIds.length) return;

        const base = Math.floor((total / orderIds.length) * 100) / 100;
        const remainder = Math.round((total - base * orderIds.length) * 100) / 100;
        orderIds.forEach((orderId, index) => {
            edits.orderCosts.set(orderId, index === 0 ? base + remainder : base);
        });
    }

    function distributeCost(id) {
        const input = document.getElementById('srTotalCost');
        const total = parseFloat(input.value) || 0;
        if (total <= 0) {
            notify('Wpisz koszt całkowity, zanim go rozłożysz', 'error');
            return;
        }
        spreadCost(id, total);
        renderDetail();
        refreshStatus();
    }

    function refreshStatus() {
        renderList();
        renderProgress();
    }
```

- [ ] **Step 2: Dodaj przełączanie zleceń w liście**

```js
    function bindListEvents() {
        document.getElementById('srModalList').addEventListener('click', (e) => {
            const item = e.target.closest('.sr-list-item');
            if (!item) return;
            state.activeId = item.dataset.srId;
            renderList();
            renderDetail();
        });
    }
```

- [ ] **Step 3: Podepnij oba bindery raz przy starcie**

Na końcu IIFE, przed eksportem `window.*`:

```js
    document.addEventListener('DOMContentLoaded', () => {
        if (!document.getElementById('editShippingRequestModal')) return;
        bindDetailEvents();
        bindListEvents();
        document.getElementById('srModalCloseX').addEventListener('click', closeModal);
        document.getElementById('srModalCloseBtn').addEventListener('click', closeModal);
        document.getElementById('editShippingRequestModal').addEventListener('click', (e) => {
            if (e.target.id === 'editShippingRequestModal') closeModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
    });
```

- [ ] **Step 4: Sprawdź w przeglądarce**

Zaznacz 3 zlecenia, otwórz „Koszty i gabaryt". Wpisz koszt w pierwszym, przełącz na drugie, wróć.
Oczekiwane: wpisana wartość jest na miejscu, znacznik pierwszego zlecenia zmienia się na `✓` dopiero
po uzupełnieniu gabarytu i terminu, licznik w stopce pokazuje „Gotowe N z 3".

- [ ] **Step 5: Commit**

```bash
git add static/js/pages/admin/shipping-request-modal.js
git commit -m "feat(wms): stan edycji i wskaznik kompletnosci w modalu zlecenia"
```

---

### Task 4: Pasek „Ustaw we wszystkich"

**Files:**
- Modify: `static/js/pages/admin/shipping-request-modal.js`

**Interfaces:**
- Consumes: `applyMaterial(id, option)`, `refreshStatus()`, `renderDetail()` z Task 3.
- Produces: `bindBulkBarEvents()`.

- [ ] **Step 1: Dodaj obsługę przycisku „Zastosuj"**

```js
    function bindBulkBarEvents() {
        document.getElementById('srBulkApply').addEventListener('click', () => {
            const date = document.getElementById('srBulkDeadlineDate').value;
            const time = document.getElementById('srBulkDeadlineTime').value;
            const materialSelect = document.getElementById('srBulkMaterial');
            const parcelSize = document.getElementById('srBulkParcelSize').value;

            const materialOption = materialSelect.value
                ? materialSelect.options[materialSelect.selectedIndex]
                : null;

            if (!date && !materialOption && !parcelSize) {
                notify('Wypełnij choć jedno pole, żeby ustawić je we wszystkich zleceniach', 'error');
                return;
            }

            state.ids.forEach(id => {
                const edits = state.edits.get(id);
                if (!edits) return;
                if (date) { edits.deadlineDate = date; edits.deadlineTime = time || '23:59'; }
                if (materialOption) applyMaterial(id, materialOption);
                if (parcelSize) edits.parcelSize = parcelSize;   // jawny gabaryt wygrywa z materiałem
            });

            renderDetail();
            refreshStatus();
            notify(`Ustawiono w ${state.ids.length} zleceniach`, 'success');
        });
    }
```

- [ ] **Step 2: Podepnij binder**

W handlerze `DOMContentLoaded` z Task 3, po `bindListEvents();`:

```js
        bindBulkBarEvents();
```

- [ ] **Step 3: Sprawdź w przeglądarce**

Zaznacz 3 zlecenia, w pasku ustaw termin, materiał i gabaryt `B`, kliknij „Zastosuj".
Oczekiwane: toast „Ustawiono w 3 zleceniach", każde zlecenie ma termin, gabaryt `B` (mimo gabarytu
z materiału) i rozłożoną cenę materiału; licznik pokazuje „Gotowe 3 z 3".

- [ ] **Step 4: Commit**

```bash
git add static/js/pages/admin/shipping-request-modal.js
git commit -m "feat(wms): pasek ustaw we wszystkich w modalu zlecenia"
```

---

### Task 5: Walidacja i zapis

**Files:**
- Modify: `static/js/pages/admin/shipping-request-modal.js`

**Interfaces:**
- Consumes: `state`, `isReady(id)`, `totalCost(id)`, `renderDetail()`, `refreshStatus()`.
- Produces: `validate()` → `{ok: boolean, blocking: string[]}`, `saveAll()`.

- [ ] **Step 1: Dodaj walidację**

```js
    /** Zwraca listę numerów zleceń, które blokują zapis. */
    function validate() {
        const blocking = [];
        state.ids.forEach(id => {
            const sr = state.data.get(id);
            const edits = state.edits.get(id);
            if (!sr || !edits) return;

            const needsDeadline = sr.status !== 'oplacone';
            const hasDeadline = edits.deadlineDate && edits.deadlineTime;
            let invalid = !edits.parcelSize || totalCost(id) <= 0 || (needsDeadline && !hasDeadline);

            if (!invalid && needsDeadline && new Date(`${edits.deadlineDate}T${edits.deadlineTime}`) <= new Date()) {
                invalid = true;
            }
            if (invalid) blocking.push(id);
        });
        return { ok: blocking.length === 0, blocking };
    }
```

- [ ] **Step 2: Dodaj zapis**

```js
    function payloadFor(id) {
        const edits = state.edits.get(id);
        const payload = {
            order_costs: Array.from(edits.orderCosts.entries())
                .map(([orderId, cost]) => ({ order_id: orderId, shipping_cost: parseFloat(cost) || 0 })),
            parcel_size: edits.parcelSize,
            courier: edits.courier,
            tracking_number: edits.trackingNumber,
        };
        if (edits.deadlineDate && edits.deadlineTime) {
            payload.payment_deadline = `${edits.deadlineDate}T${edits.deadlineTime}`;
        }
        // Klucz obecny = "ustaw albo wyczyść", więc pusty wybór nie może zerować przypisania.
        if (edits.packagingMaterialId) {
            payload.packaging_material_id = parseInt(edits.packagingMaterialId, 10);
        }
        return payload;
    }

    async function saveAll() {
        const { ok, blocking } = validate();
        if (!ok) {
            state.activeId = blocking[0];
            renderList();
            renderDetail();
            const numbers = blocking.map(id => state.data.get(id).request_number).join(', ');
            notify(`Uzupełnij gabaryt i termin płatności: ${numbers}`, 'error');
            return;
        }

        const saveBtn = document.getElementById('srModalSaveBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Zapisywanie…';

        const failed = [];
        for (const id of state.ids) {
            try {
                const resp = await fetch(`/admin/orders/shipping-requests/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify(payloadFor(id)),
                });
                if (!resp.ok) failed.push(id);
            } catch (error) {
                console.error('Błąd zapisu zlecenia', id, error);
                failed.push(id);
            }
        }

        saveBtn.disabled = false;
        saveBtn.textContent = state.ids.length > 1 ? 'Zapisz wszystkie' : 'Zapisz';

        if (!failed.length) {
            closeModal();
            window.location.reload();
            return;
        }
        const numbers = failed.map(id => state.data.get(id).request_number).join(', ');
        notify(`Nie zapisano: ${numbers}`, 'error');
    }
```

- [ ] **Step 3: Podepnij przycisk zapisu**

W handlerze `DOMContentLoaded`:

```js
        document.getElementById('srModalSaveBtn').addEventListener('click', saveAll);
```

- [ ] **Step 4: Sprawdź w przeglądarce**

Zaznacz 2 zlecenia, zostaw jedno bez gabarytu, kliknij „Zapisz wszystkie".
Oczekiwane: brak zapisu, modal przeskakuje na wadliwe zlecenie, toast z jego numerem.
Następnie uzupełnij gabaryt i zapisz — strona przeładowuje się, wartości widoczne na kartach.

- [ ] **Step 5: Potwierdź kontrakt backendu**

```bash
python -m pytest tests/test_admin_shipping_request_material.py -v
```

Oczekiwane: 3 passed — jawny `parcel_size` nadal wygrywa z gabarytem z materiału.

- [ ] **Step 6: Commit**

```bash
git add static/js/pages/admin/shipping-request-modal.js
git commit -m "feat(wms): walidacja i zapis scalonego modala zlecenia"
```

---

### Task 6: Anulowanie zlecenia w trybie pojedynczym

**Files:**
- Modify: `static/js/pages/admin/shipping-request-modal.js`

**Interfaces:**
- Consumes: `state.activeId`, `csrfToken()`, `closeModal()`.
- Produces: `cancelRequest()` podpięte pod `#srCancelRequestBtn`.

- [ ] **Step 1: Dodaj anulowanie**

```js
    async function cancelRequest() {
        const sr = state.data.get(state.activeId);
        if (!sr) return;

        const confirmed = confirm(
            `Czy na pewno anulować zlecenie ${sr.request_number}?\n\n` +
            'Wszystkie zamówienia zostaną odłączone od tego zlecenia i wrócą do puli dostępnych zamówień klienta.'
        );
        if (!confirmed) return;

        try {
            const resp = await fetch(`/admin/orders/shipping-requests/${sr.id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            });
            const data = await resp.json();
            if (data.success) {
                closeModal();
                window.location.reload();
            } else {
                notify(data.message || data.error || 'Nie udało się anulować zlecenia', 'error');
            }
        } catch (error) {
            console.error('Błąd anulowania zlecenia:', error);
            notify('Nie udało się anulować zlecenia', 'error');
        }
    }
```

- [ ] **Step 2: Podepnij przycisk**

W handlerze `DOMContentLoaded`:

```js
        document.getElementById('srCancelRequestBtn').addEventListener('click', cancelRequest);
```

- [ ] **Step 3: Sprawdź w przeglądarce**

Otwórz pojedyncze zlecenie → przycisk „Anuluj zlecenie" widoczny w stopce.
Otwórz dwa zlecenia przez akcję masową → przycisku nie ma.

- [ ] **Step 4: Commit**

```bash
git add static/js/pages/admin/shipping-request-modal.js
git commit -m "feat(wms): anulowanie zlecenia w scalonym modalu"
```

---

### Task 7: Style — jedno źródło w modals.css

**Files:**
- Modify: `static/css/components/modals.css` (dopisanie sekcji na końcu)
- Modify: `static/css/pages/admin/shipping-requests-list.css` (usunięcie reguł modala)

**Interfaces:**
- Consumes: klasy z markupu Task 1 i renderów Task 2.
- Produces: komplet stylów `.sr-modal*`, `.sr-list-*`, `.sr-detail-*`, `.sr-bulk-bar*` w `modals.css`.

- [ ] **Step 1: Dopisz style w modals.css**

Na końcu `static/css/components/modals.css`:

```css
/* ==========================================
   SCALONY MODAL ZLECENIA WYSYŁKI
   ========================================== */

.sr-modal-body {
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: 20px;
    align-items: start;
}

.sr-modal-body:has(.sr-modal-list[hidden]) {
    grid-template-columns: 1fr;
}

.sr-modal-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 60vh;
    overflow-y: auto;
}

.sr-list-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    width: 100%;
    min-height: 44px;
    padding: 10px 12px;
    text-align: left;
    background: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    cursor: pointer;
    transition: border-color 0.2s, background 0.2s;
}

.sr-list-item:hover { border-color: #c8c8c8; }
.sr-list-item.active { border-color: #f093fb; background: rgba(240, 147, 251, 0.08); }

.sr-list-mark {
    flex: 0 0 auto;
    width: 20px;
    height: 20px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    font-size: 12px;
    font-weight: 700;
    color: #ffffff;
}

.sr-list-item.ready .sr-list-mark { background: #22c55e; }
.sr-list-item.incomplete .sr-list-mark { background: #f59e0b; }

.sr-list-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.sr-list-number { font-weight: 600; font-size: 14px; color: #333333; }
.sr-list-meta { font-size: 12px; color: #666666; overflow: hidden; text-overflow: ellipsis; }

.sr-bulk-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 16px;
    padding: 14px 24px;
    background: #f7f7f9;
    border-bottom: 1px solid #e0e0e0;
}

.sr-bulk-bar[hidden] { display: none; }
.sr-bulk-bar-title { font-size: 13px; font-weight: 600; color: #333333; }
.sr-bulk-bar-fields { display: flex; flex-wrap: wrap; gap: 12px; flex: 1; }
.sr-inline-fields { display: flex; gap: 8px; }

.sr-detail-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.sr-detail-number { font-size: 16px; font-weight: 600; color: #333333; }
.sr-detail-status { font-size: 11px; padding: 3px 8px; border-radius: 4px; background: #eeeef2; color: #444444; }

.sr-detail-section { margin-bottom: 20px; }
.sr-detail-section h3 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em; color: #666666; margin-bottom: 10px; }
.sr-detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }

.sr-cost-input { display: flex; align-items: center; gap: 8px; }
.sr-cost-input .form-control { max-width: 140px; }
.sr-cost-input .currency { font-size: 13px; color: #666666; }

.sr-client-panel {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 12px;
    padding: 10px 12px;
    background: #f7f7f9;
    border-radius: 8px;
    font-size: 13px;
    color: #333333;
}

.sr-client-panel-title { font-weight: 600; color: #666666; }
.sr-modal-loading { padding: 40px 20px; text-align: center; color: #666666; }
.sr-modal-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.sr-modal-footer-actions { display: flex; gap: 8px; margin-left: auto; }
.sr-modal-progress { font-size: 13px; color: #666666; }

.sr-modal .input-error { border-color: #ef4444 !important; }

/* Dark mode */
[data-theme="dark"] .sr-list-item {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .sr-list-item:hover { border-color: rgba(240, 147, 251, 0.3); }
[data-theme="dark"] .sr-list-item.active { border-color: #f093fb; background: rgba(240, 147, 251, 0.12); }
[data-theme="dark"] .sr-list-number { color: #ffffff; }
[data-theme="dark"] .sr-list-meta { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .sr-bulk-bar {
    background: rgba(255, 255, 255, 0.05);
    border-bottom-color: rgba(240, 147, 251, 0.15);
}

[data-theme="dark"] .sr-bulk-bar-title,
[data-theme="dark"] .sr-detail-number { color: #ffffff; }

[data-theme="dark"] .sr-detail-status {
    background: rgba(255, 255, 255, 0.1);
    color: rgba(255, 255, 255, 0.8);
}

[data-theme="dark"] .sr-detail-section h3,
[data-theme="dark"] .sr-modal-progress,
[data-theme="dark"] .sr-modal-loading,
[data-theme="dark"] .sr-cost-input .currency,
[data-theme="dark"] .sr-client-panel-title { color: rgba(255, 255, 255, 0.6); }

[data-theme="dark"] .sr-client-panel {
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.8);
}

/* Mobile: lista jako przewijalny pasek żetonów nad szczegółami */
@media (max-width: 768px) {
    .sr-modal-body { grid-template-columns: 1fr; }

    .sr-modal-list {
        flex-direction: row;
        max-height: none;
        overflow-x: auto;
        padding-bottom: 4px;
    }

    .sr-list-item { flex: 0 0 auto; min-width: 160px; }
    .sr-bulk-bar { padding: 12px 16px; }
    .sr-bulk-bar-fields { flex-direction: column; }
    .sr-inline-fields .form-control,
    .sr-detail-grid .form-control { min-height: 44px; }
    .sr-modal-footer { flex-direction: column; align-items: stretch; }
    .sr-modal-footer-actions { margin-left: 0; flex-wrap: wrap; }
    .sr-modal-footer-actions .btn { flex: 1; min-height: 44px; }
}
```

- [ ] **Step 2: Usuń reguły modala z pliku strony**

W `static/css/pages/admin/shipping-requests-list.css` usuń bloki:
- `.bulk-cost-loading`, `.bulk-cost-entry`, `.bulk-cost-entry-saved`, `.bulk-cost-entry-error`,
  `.bulk-cost-entry-header`, `.bulk-cost-sr-number`, `.bulk-cost-sr-status`, `.bulk-cost-total-group`
  (+ zagnieżdżone), `.bulk-cost-orders-table` (~965–1050),
- odpowiadające im warianty `[data-theme="dark"]` (~1365–1400),
- reguły wnętrza starego modala: `.sr-boxes-row`, `.sr-box`, `.sr-section`, `.sr-client-panel`
  (jeśli występuje), `.sr-shipping-section`, `.sr-shipping-info`, `.sr-shipping-info-row`,
  `.sr-shipping-label`, `.sr-shipping-value`, `.sr-shipping-edit-btn`, `.sr-section-header`.

Zostaw reguły kart listy: `.sr-card`, `.sr-checkbox*`, `.sr-notes-*`, `.sr-actions`.

- [ ] **Step 3: Sprawdź oba motywy i mobile**

W przeglądarce: modal w light i dark, następnie `resize_window` na `mobile`.
Oczekiwane: lista jako poziomy pasek żetonów, pola w jednej kolumnie, przyciski stopki pełnej
szerokości, brak poziomego scrolla strony.

- [ ] **Step 4: Commit**

```bash
git add static/css/components/modals.css static/css/pages/admin/shipping-requests-list.css
git commit -m "style(wms): style scalonego modala w modals.css (light + dark + mobile)"
```

---

### Task 8: Usunięcie martwego kodu i weryfikacja całości

**Files:**
- Modify: `static/js/pages/admin/shipping-requests.js`

**Interfaces:**
- Consumes: `window.openShippingRequestsModal` z Task 2.
- Produces: `shipping-requests.js` zawężony do zaznaczania kart i akcji masowych.

- [ ] **Step 1: Usuń kod modala z shipping-requests.js**

Usuń funkcje: `openShippingRequestModal`, `closeShippingRequestModal`, `toggleShippingEdit`,
`renderOrdersTable`, `updateTotalShippingCost`, `renderAddressPreview`, `distributeShippingCost`,
`cancelShippingRequest`, `openBulkCostModal`, `distributeBulkCost`, `closeBulkCostModal`,
`submitBulkCosts` oraz zmienną `currentShippingRequest`.

Usuń też podpięcia w `DOMContentLoaded`: handler `matSelectEl`, submit `editShippingRequestForm`,
submit `bulkCostForm`, listener zamykania `bulkCostModal`, handler `Escape` zamykający oba modale
(przeszedł do nowego pliku).

- [ ] **Step 2: Przepnij przycisk akcji masowej na nowy modal**

W `shipping-requests.js`, w bloku listenerów paska masowego:

```js
    const bulkCostBtn = document.querySelector('.btn-bulk[data-action="bulk-cost"]');
    if (bulkCostBtn) {
        bulkCostBtn.addEventListener('click', () => {
            const ids = getSelectedRequestIds();
            if (!ids.length) return;
            window.openShippingRequestsModal(ids);
        });
    }
```

- [ ] **Step 3: Sprawdź, że nie został żaden martwy odnośnik**

```bash
grep -rn "bulkCostModal\|submitBulkCosts\|toggleShippingEdit\|openBulkCostModal" templates/ static/js/ | grep -v vendor
```

Oczekiwane: brak wyników.

- [ ] **Step 4: Uruchom pełny zestaw testów**

```bash
python -m pytest tests/ -q
```

Oczekiwane: brak nowych błędów; `tests/test_shipping_request_modal_merge.py` i
`tests/test_admin_shipping_request_material.py` zielone.

- [ ] **Step 5: Przejdź ręcznie scenariusze ze specyfikacji**

Na `http://localhost:5001`, punkty 1–10 z sekcji „Testy ręczne" specyfikacji: oba wejścia do modala,
tryb wielu zleceń, pasek zbiorczy, walidacja gabarytu, termin w przeszłości, poprawny zapis i przejście
statusu, zlecenie kurierskie, anulowanie, light/dark, mobile.

- [ ] **Step 6: Commit**

```bash
git add static/js/pages/admin/shipping-requests.js
git commit -m "refactor(wms): usuniecie kodu starych modali z shipping-requests.js"
```

---

## Uwagi wykonawcze

- **Nie pushuj bez zgody Konrada** — push do `main` uruchamia auto-deploy na produkcję.
- Po zakończeniu zadania 8 zaktualizuj ClickUp [869eczm7p](https://app.clickup.com/t/869eczm7p) na `complete`
  i wróć do [869e674py](https://app.clickup.com/t/869e674py) (eksport InPost), który czeka na komplet gabarytów.
- `spreadCost` daje resztę z zaokrąglenia **pierwszemu** zamówieniu (tak działał modal masowy);
  stary modal pojedynczy dawał ją ostatniemu. Ujednolicenie jest zamierzone.
