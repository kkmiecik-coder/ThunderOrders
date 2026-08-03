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
        saveResults: new Map(), // id -> 'saved' | 'save-failed' (po próbie zapisu)
        materials: [],
        activeId: null,
    };

    // Pola podświetlane klasą input-error dla poszczególnych braków.
    const ISSUE_FIELDS = {
        parcelSize: ['srParcelSize'],
        cost: ['srTotalCost'],
        deadline: ['srDeadlineDate', 'srDeadlineTime'],
    };

    let closeTimer = null;   // timeout sprzątający po animacji zamknięcia
    let loadToken = 0;       // rozpoznaje, czy trwające pobieranie dotyczy jeszcze otwartego modala

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
            // Ręcznie wpisana kwota całkowita; null = pole pochodne (suma kosztów zamówień).
            totalDraft: null,
        };
    }

    /** Numer zlecenia do komunikatów — dane mogą już nie być w pamięci. */
    function requestNumber(id) {
        const sr = state.data.get(id);
        return (sr && sr.request_number) || `#${id}`;
    }

    function totalCost(id) {
        const edits = state.edits.get(id);
        if (!edits) return 0;
        let sum = 0;
        edits.orderCosts.forEach(v => { sum += parseFloat(v) || 0; });
        return Math.round(sum * 100) / 100;
    }

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

        // Zaległe sprzątanie po zamknięciu nie może zamknąć świeżo otwartego modala.
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        modal.classList.remove('closing');

        const token = ++loadToken;
        const requested = ids.map(String);
        state.ids = requested;
        state.data.clear();
        state.edits.clear();
        state.saveResults.clear();
        state.activeId = null;

        const detail = document.getElementById('srModalDetail');
        detail.innerHTML = '<div class="sr-modal-loading">Ładowanie danych…</div>';
        modal.classList.add('active');

        const [materials, responses] = await Promise.all([
            fetchMaterials(),
            Promise.all(requested.map(id =>
                fetch(`/admin/orders/shipping-requests/${id}`)
                    .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
                    .catch(error => {
                        console.error('Nie udało się pobrać zlecenia', id, error);
                        return null;   // zlecenie odpada, reszta modala działa dalej
                    })
            )),
        ]);

        // Modal zamknięty albo otwarty ponownie z innym zestawem — porzuć wynik.
        if (token !== loadToken) return;

        state.materials = materials;
        const loaded = [];
        responses.forEach(sr => {
            if (!sr || sr.id == null) return;
            const id = String(sr.id);
            state.data.set(id, sr);
            state.edits.set(id, initEdits(sr));
            loaded.push(id);
        });

        if (!loaded.length) {
            notify('Nie udało się pobrać danych zlecenia', 'error');
            closeModal();
            return;
        }
        if (loaded.length < requested.length) {
            notify(`Nie udało się pobrać ${requested.length - loaded.length} z ${requested.length} zleceń`, 'error');
        }

        state.ids = loaded;
        state.activeId = state.ids[0];
        renderHeader();
        renderList();
        renderDetail();
    }

    function closeModal() {
        const modal = document.getElementById('editShippingRequestModal');
        if (!modal || !modal.classList.contains('active') || closeTimer) return;
        loadToken++;   // trwające pobieranie nie wypełni już zamykanego modala
        modal.classList.add('closing');
        closeTimer = setTimeout(() => {
            closeTimer = null;
            modal.classList.remove('active', 'closing');
            state.ids = [];
            state.data.clear();
            state.edits.clear();
            state.saveResults.clear();
            state.activeId = null;
        }, 350);
    }

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
        if (!list) return;
        // Licznik żyje w stopce, więc musi być odświeżony także w trybie jednego zlecenia.
        renderProgress();
        if (list.hidden) {
            list.innerHTML = '';
            return;
        }

        list.innerHTML = state.ids.map(id => {
            const sr = state.data.get(id);
            if (!sr) return '';
            const edits = state.edits.get(id);
            const ready = isReady(id);
            // GET zwraca tylko dane adresowe — nie ma obiektu użytkownika.
            const client = sr.shipping_name || sr.pickup_city || '';
            const parcel = edits.parcelSize ? PARCEL_LABELS[edits.parcelSize] : 'brak gabarytu';
            const cost = totalCost(id);
            const saveResult = state.saveResults.get(id);
            return `
                <button type="button" class="sr-list-item${id === state.activeId ? ' active' : ''}${ready ? ' ready' : ' incomplete'}${saveResult ? ' ' + saveResult : ''}"
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
    }

    function renderProgress() {
        const progress = document.getElementById('srModalProgress');
        if (!progress) return;
        const ready = state.ids.filter(isReady).length;
        progress.textContent = state.ids.length > 1
            ? `Gotowe ${ready} z ${state.ids.length}`
            : '';
    }

    /**
     * Braki blokujące zapis jednego zlecenia — jedno źródło prawdy dla znacznika
     * na liście i dla walidacji zapisu. Zwraca null, gdy zlecenia nie ma w pamięci.
     */
    function requestIssues(id) {
        const sr = state.data.get(id);
        const edits = state.edits.get(id);
        if (!sr || !edits) return null;

        const issues = [];
        if (!edits.parcelSize) issues.push('parcelSize');
        if (totalCost(id) <= 0) issues.push('cost');

        if (sr.status !== 'oplacone') {   // opłacone zlecenie nie potrzebuje już terminu
            const hasDeadline = edits.deadlineDate && edits.deadlineTime;
            const past = hasDeadline
                && new Date(`${edits.deadlineDate}T${edits.deadlineTime}`) <= new Date();
            if (!hasDeadline || past) issues.push('deadline');
        }
        return issues;
    }

    /** Zlecenie gotowe = gabaryt + koszt > 0 + termin w przyszłości (poza już opłaconymi). */
    function isReady(id) {
        const issues = requestIssues(id);
        return !!issues && issues.length === 0;
    }

    /** Podświetla pola z brakami w panelu szczegółów aktywnego zlecenia. */
    function markInvalidFields(id) {
        const issues = requestIssues(id) || [];
        issues.forEach(issue => {
            (ISSUE_FIELDS[issue] || []).forEach(fieldId => {
                const el = document.getElementById(fieldId);
                if (el) el.classList.add('input-error');
            });
        });
    }

    /** Zdejmuje podświetlenie z pól, których brak użytkownik już usunął (nigdy go nie dodaje). */
    function clearFixedFieldErrors(id) {
        const issues = requestIssues(id) || [];
        Object.keys(ISSUE_FIELDS).forEach(issue => {
            if (issues.indexOf(issue) !== -1) return;
            ISSUE_FIELDS[issue].forEach(fieldId => {
                const el = document.getElementById(fieldId);
                if (el) el.classList.remove('input-error');
            });
        });
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
                                   placeholder="0.00" value="">
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
                               value="">
                    </div>
                </div>
            </section>
        `;

        // Wartości ustawiamy właściwością, nie w atrybucie — escapeHtml nie
        // escapuje cudzysłowu, więc numer z " rozbiłby atrybut value.
        const trackingEl = document.getElementById('srTracking');
        if (trackingEl) trackingEl.value = edits.trackingNumber || '';

        // Ręcznie wpisana kwota przeżywa przerysowanie; bez niej pole jest pochodne.
        const totalEl = document.getElementById('srTotalCost');
        if (totalEl) {
            totalEl.value = edits.totalDraft != null
                ? edits.totalDraft
                : (totalCost(id) > 0 ? money(totalCost(id)) : '');
        }

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

    function bindDetailEvents() {
        const detail = document.getElementById('srModalDetail');

        detail.addEventListener('input', (e) => {
            const edits = state.edits.get(state.activeId);
            if (!edits) return;

            if (e.target.classList.contains('sr-order-cost')) {
                const orderId = parseInt(e.target.dataset.orderId, 10);
                edits.orderCosts.set(orderId, parseFloat(e.target.value) || 0);
                edits.totalDraft = null;   // ręczny koszt zamówienia wraca pole całkowite do roli pochodnej
                const total = document.getElementById('srTotalCost');
                if (total) total.value = totalCost(state.activeId) > 0 ? money(totalCost(state.activeId)) : '';
                refreshStatus();
                clearFixedFieldErrors(state.activeId);
                return;
            }

            if (e.target.id === 'srTotalCost') { edits.totalDraft = e.target.value; return; }
            if (e.target.id === 'srTracking') { edits.trackingNumber = e.target.value; return; }
            if (e.target.id === 'srDeadlineDate' || e.target.id === 'srDeadlineTime') {
                if (e.target.id === 'srDeadlineDate') edits.deadlineDate = e.target.value;
                else edits.deadlineTime = e.target.value;
                refreshStatus();
                clearFixedFieldErrors(state.activeId);
                return;
            }
        });

        detail.addEventListener('change', (e) => {
            const edits = state.edits.get(state.activeId);
            if (!edits) return;

            if (e.target.id === 'srParcelSize') {
                edits.parcelSize = e.target.value;
                refreshStatus();
                clearFixedFieldErrors(state.activeId);
                return;
            }
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
        // Po rozłożeniu (Rozłóż, materiał, pasek zbiorczy) kwota całkowita znów jest pochodna.
        edits.totalDraft = null;
    }

    function distributeCost(id) {
        const input = document.getElementById('srTotalCost');
        const total = parseFloat(input ? input.value : '') || 0;
        if (total <= 0) {
            notify('Wpisz koszt całkowity, zanim go rozłożysz', 'error');
            return;
        }
        spreadCost(id, total);
        renderDetail();
        refreshStatus();
    }

    function refreshStatus() {
        renderList();   // renderList odświeża też licznik w stopce
    }

    function bindListEvents() {
        document.getElementById('srModalList').addEventListener('click', (e) => {
            const item = e.target.closest('.sr-list-item');
            if (!item) return;
            state.activeId = item.dataset.srId;
            renderList();
            renderDetail();
        });
    }

    function bindBulkBarEvents() {
        document.getElementById('srBulkApply').addEventListener('click', () => {
            const date = document.getElementById('srBulkDeadlineDate').value;
            const time = document.getElementById('srBulkDeadlineTime').value;
            const materialSelect = document.getElementById('srBulkMaterial');
            const parcelSize = document.getElementById('srBulkParcelSize').value;

            // Nazwa lokalna nie może przysłaniać modułowej funkcji materialOption().
            const selectedMaterial = materialSelect.value
                ? materialSelect.options[materialSelect.selectedIndex]
                : null;

            if (!date && !selectedMaterial && !parcelSize) {
                notify('Wypełnij choć jedno pole, żeby ustawić je we wszystkich zleceniach', 'error');
                return;
            }

            state.ids.forEach(id => {
                const edits = state.edits.get(id);
                if (!edits) return;
                if (date) { edits.deadlineDate = date; edits.deadlineTime = time || '23:59'; }
                if (selectedMaterial) applyMaterial(id, selectedMaterial);
                if (parcelSize) edits.parcelSize = parcelSize;   // jawny gabaryt wygrywa z materiałem
            });

            renderDetail();
            refreshStatus();
            notify(`Ustawiono w ${state.ids.length} zleceniach`, 'success');
        });
    }

    /** Zwraca listę id zleceń, które blokują zapis (ten sam warunek co znacznik na liście). */
    function validate() {
        const blocking = [];
        state.ids.forEach(id => {
            const issues = requestIssues(id);
            if (!issues) return;   // brak danych = nie ma czego zapisywać
            if (issues.length) blocking.push(id);
        });
        return { ok: blocking.length === 0, blocking };
    }

    function payloadFor(id) {
        const edits = state.edits.get(id);
        if (!edits) return null;   // modal zamknięty w trakcie zapisu
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
            markInvalidFields(state.activeId);
            const numbers = blocking.map(requestNumber).join(', ');
            notify(`Uzupełnij gabaryt i termin płatności: ${numbers}`, 'error');
            return;
        }

        const saveBtn = document.getElementById('srModalSaveBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Zapisywanie…';

        const failed = [];
        state.saveResults.clear();
        for (const id of state.ids) {
            const payload = payloadFor(id);
            if (!payload) {
                failed.push(id);
                state.saveResults.set(id, 'save-failed');
                continue;
            }
            try {
                const resp = await fetch(`/admin/orders/shipping-requests/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify(payload),
                });
                if (!resp.ok) failed.push(id);
                state.saveResults.set(id, resp.ok ? 'saved' : 'save-failed');
            } catch (error) {
                console.error('Błąd zapisu zlecenia', id, error);
                failed.push(id);
                state.saveResults.set(id, 'save-failed');
            }
        }

        saveBtn.disabled = false;
        saveBtn.textContent = state.ids.length > 1 ? 'Zapisz wszystkie' : 'Zapisz';

        if (!failed.length) {
            closeModal();
            window.location.reload();
            return;
        }
        renderList();   // pozycje dostają klasy saved / save-failed
        const numbers = failed.map(requestNumber).join(', ');
        notify(`Nie zapisano: ${numbers}`, 'error');
    }

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

    document.addEventListener('DOMContentLoaded', () => {
        if (!document.getElementById('editShippingRequestModal')) return;
        bindDetailEvents();
        bindListEvents();
        bindBulkBarEvents();
        document.getElementById('srModalSaveBtn').addEventListener('click', saveAll);
        document.getElementById('srCancelRequestBtn').addEventListener('click', cancelRequest);
        document.getElementById('srModalCloseX').addEventListener('click', closeModal);
        document.getElementById('srModalCloseBtn').addEventListener('click', closeModal);
        document.getElementById('editShippingRequestModal').addEventListener('click', (e) => {
            if (e.target.id === 'editShippingRequestModal') closeModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
    });

    window.openShippingRequestsModal = openShippingRequestsModal;
    window.openShippingRequestModal = (id) => openShippingRequestsModal([id]);
    window.closeShippingRequestModal = closeModal;
})();
