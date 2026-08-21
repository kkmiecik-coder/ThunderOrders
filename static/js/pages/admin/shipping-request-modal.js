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
        mode: 'costs',        // 'costs' = wycena i ustawienia, 'ship' = oznaczanie wysyłki
    };

    // Pola podświetlane klasą input-error dla poszczególnych braków.
    const ISSUE_FIELDS = {
        parcelSize: ['srParcelSize'],
        cost: ['srTotalCost'],
        deadline: ['srDeadline'],
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
        return {
            orderCosts: new Map(sr.orders.map(o => [o.id, o.shipping_cost || 0])),
            // "YYYY-MM-DDTHH:MM" — format pola datetime-local i payloadu PUT
            deadline: sr.payment_deadline ? sr.payment_deadline.substring(0, 16) : '',
            parcelSize: sr.parcel_size || '',
            packagingMaterialId: sr.packaging_material_id || '',
            courier: sr.courier || '',
            trackingNumber: sr.tracking_number || '',
            // Status bieżący + wartość początkowa: payload leci tylko przy realnej
            // zmianie (patrz payloadFor).
            status: sr.status || '',
            statusPoczatkowy: sr.status || '',
            // Ręcznie wpisana kwota całkowita; null = pole pochodne (suma kosztów zamówień).
            totalDraft: null,
        };
    }

    /** Numer zlecenia do komunikatów — dane mogą już nie być w pamięci. */
    function requestNumber(id) {
        const sr = state.data.get(id);
        return (sr && sr.request_number) || `#${id}`;
    }

    /** Czy to paczka zbiorcza (wiele klientów w jednym kartonie). */
    function isConsolidation(id) {
        const sr = state.data.get(id);
        return !!(sr && sr.is_consolidation);
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

    async function openShippingRequestsModal(ids, options) {
        const modal = document.getElementById('editShippingRequestModal');
        if (!modal || !ids || !ids.length) return;

        state.mode = (options && options.mode === 'ship') ? 'ship' : 'costs';

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

        // Powody nieudanego pobrania — bez nich admin widział „Nie udało się pobrać
        // danych zlecenia" i nie wiedział, czy to brak uprawnień, 404 czy padnięty serwer.
        const loadErrors = [];
        const [materials, responses] = await Promise.all([
            fetchMaterials(),
            Promise.all(requested.map(id =>
                fetch(`/admin/orders/shipping-requests/${id}`)
                    .then(r => (r.ok
                        ? r.json()
                        : Promise.reject(new Error(`serwer odpowiedział HTTP ${r.status}`))))
                    .catch(error => {
                        console.error('Nie udało się pobrać zlecenia', id, error);
                        loadErrors.push(`zlecenie #${id}: ${error.message || 'brak połączenia z serwerem'}`);
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
            notify(escapeHtml(`Nie udało się pobrać danych zlecenia — ${loadErrors.join('; ')}`), 'error');
            closeModal();
            return;
        }
        if (loaded.length < requested.length) {
            notify(escapeHtml(
                `Nie udało się pobrać ${requested.length - loaded.length} z ${requested.length} `
                + `zleceń — ${loadErrors.join('; ')}`), 'error');
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

        const ship = state.mode === 'ship';

        if (many) {
            title.textContent = ship
                ? `Wysyłka · ${state.ids.length} zleceń`
                : `Zlecenia wysyłki · ${state.ids.length}`;
            saveBtn.textContent = ship ? 'Oznacz jako wysłane' : 'Zapisz wszystkie';
        } else {
            const sr = state.data.get(state.activeId);
            const number = sr ? sr.request_number : '';
            title.textContent = ship ? `Wysyłka — ${number}` : `Zlecenie ${number}`;
            saveBtn.textContent = ship ? 'Oznacz jako wysłane' : 'Zapisz';
        }

        bulkBar.hidden = !many;
        list.hidden = !many;
        cancelBtn.hidden = many;

        // Nazwa przycisku ma opisywać to, co on faktycznie robi. DELETE na paczce
        // zbiorczej NIE anuluje niczego — rozwiązuje konsolidację i oddaje zamówienia
        // właścicielom; na zwykłym zleceniu kasuje zlecenie.
        cancelBtn.textContent = isConsolidation(state.activeId)
            ? 'Rozwiąż paczkę'
            : 'Usuń zlecenie';

        // W trybie wysyłki termin płatności nigdzie nie jest wysyłany — samo pole
        // tylko myli, więc znika z paska "Ustaw we wszystkich" (nie sam input,
        // cała grupa .form-group, inaczej zostaje osierocony <label>).
        const bulkDeadlineField = document.getElementById('srBulkDeadline');
        const bulkDeadlineGroup = bulkDeadlineField && bulkDeadlineField.closest('.form-group');
        if (bulkDeadlineGroup) bulkDeadlineGroup.hidden = ship;

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
            // addressee_name domyka to, czego GET nie ma: obiektu użytkownika nie
            // zwraca, a `shipping_name` jest puste przy paczkomacie — lista pokazywała
            // wtedy miasto punktu odbioru w miejscu, gdzie admin szuka nazwiska.
            const client = sr.addressee_name || sr.pickup_city || '';
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

        // Wysyłka nie wymaga żadnego pola — numer przesyłki i kurier są nieobowiązkowe,
        // a gabaryt i termin płatności nie mają na nią wpływu.
        if (state.mode === 'ship') return [];

        const issues = [];
        if (!edits.parcelSize) issues.push('parcelSize');
        if (totalCost(id) <= 0) issues.push('cost');

        if (sr.status !== 'oplacone') {   // opłacone zlecenie nie potrzebuje już terminu
            const past = edits.deadline && new Date(edits.deadline) <= new Date();
            if (!edits.deadline || past) issues.push('deadline');
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

        const manyOrders = sr.orders.length > 1;

        // Fakty: zamowienia to lista do przeczytania, nie formularz.
        const ordersFact = sr.orders.map(o => `
            <li class="sr-fact-order">
                <a href="/admin/orders/${o.id}" target="_blank" class="sr-order-link">${escapeHtml(o.order_number)}</a>
                <span class="sr-fact-order-value">${money(o.total_amount)} PLN</span>
            </li>
        `).join('');

        // Podzial kosztu ma sens dopiero od dwoch zamowien — przy jednym
        // koszt calkowity JEST kosztem tego zamowienia.
        const splitRows = manyOrders ? sr.orders.map(o => `
            <div class="sr-split-row">
                <span class="sr-split-order">${escapeHtml(o.order_number)}</span>
                <div class="sr-cost-input">
                    <input type="number" class="form-control sr-order-cost" data-order-id="${o.id}"
                           step="0.01" min="0" placeholder="0.00"
                           value="${edits.orderCosts.get(o.id) > 0 ? money(edits.orderCosts.get(o.id)) : ''}">
                    <span class="currency">PLN</span>
                </div>
            </div>
        `).join('') : '';

        // To samo zdanie, które karta WMS pokazuje pod grupami uczestników — serwer
        // liczy je raz (ShippingRequest.consolidation_block_note). Wiersze podziału
        // kosztu są tu płaską listą numerów zamówień, bez podziału na ludzi, więc bez
        // tego admin nie widzi, CZYJE pole zostawia puste. Pusty string, gdy paczka
        // jest rozliczona albo to zwykłe zlecenie — wtedy nie ma o czym informować.
        // Własna klasa (nie .sr-block-note z karty): modal wisi też w detail.html,
        // które nie ładuje shipping-requests-list.css, a style modali żyją w modals.css.
        // <div>, nie <p>: `[data-theme="dark"] .modal-body p` ma wyższą specyficzność
        // niż `[data-theme="dark"] .sr-split-note` i zjadało kolor ostrzeżenia.
        const blockNote = sr.consolidation_block_note
            ? `<div class="sr-split-note">${escapeHtml(sr.consolidation_block_note)}</div>`
            : '';

        const prefLabels = { karton: 'Karton', koperta: 'Koperta' };
        const courierOptions = Object.entries(COURIER_LABELS).map(([value, label]) =>
            `<option value="${value}"${edits.courier === value ? ' selected' : ''}>${label}</option>`
        ).join('');
        const parcelOptions = Object.entries(PARCEL_LABELS).map(([value, label]) =>
            `<option value="${value}"${edits.parcelSize === value ? ' selected' : ''}>${label}</option>`
        ).join('');

        container.innerHTML = `
            <header class="sr-detail-head">
                <span class="sr-detail-number">${escapeHtml(sr.request_number)}</span>
                ${(sr.available_statuses && sr.available_statuses.length > 1) ? `
                <select class="sr-detail-status-select" data-sr-id="${sr.id}"
                        title="Zmiana statusu wykonuje komplet skutków: znaczniki czasu, kaskadę na zamówienia i powiadomienie do klienta">
                    ${sr.available_statuses.map(st => `
                        <option value="${escapeHtml(st.slug)}"${st.slug === sr.status ? ' selected' : ''}>${escapeHtml(st.name)}</option>
                    `).join('')}
                </select>` : `
                <span class="sr-detail-status badge">${escapeHtml(sr.status_display_name || sr.status)}</span>`}
                ${sr.addressee_name ? `<span class="sr-detail-client">${escapeHtml(sr.addressee_name)}</span>` : ''}
            </header>

            <section class="sr-facts">
                <div class="sr-fact">
                    <span class="sr-fact-label">${sr.address_type === 'pickup_point' ? 'Punkt odbioru' : 'Adres dostawy'}</span>
                    <p class="sr-fact-value">${addressLine(sr)}</p>
                </div>
                <div class="sr-fact">
                    <span class="sr-fact-label">Od klienta</span>
                    <p class="sr-fact-value">
                        <span class="sr-fact-pref">${escapeHtml(prefLabels[sr.client_package_preference] || '—')}</span>
                        ${sr.client_notes ? escapeHtml(sr.client_notes) : '<span class="sr-fact-muted">bez uwag</span>'}
                    </p>
                </div>
                <div class="sr-fact sr-fact--orders">
                    <span class="sr-fact-label">Zamówienia (${sr.orders.length})</span>
                    <ul class="sr-fact-orders">${ordersFact}</ul>
                </div>
            </section>

            <section class="sr-settings">
                <h3 class="sr-settings-title">Ustawienia wysyłki</h3>
                <div class="sr-settings-grid">
                    <div class="form-group">
                        <label class="form-label" for="srTotalCost">Koszt całkowity</label>
                        <div class="sr-cost-input">
                            <input type="number" id="srTotalCost" class="form-control" step="0.01" min="0"
                                   placeholder="0.00" value="">
                            <span class="currency">PLN</span>
                            ${manyOrders ? '<button type="button" class="btn btn-sm btn-secondary" id="srDistribute">Rozłóż</button>' : ''}
                        </div>
                    </div>
                    ${state.mode === 'ship' ? '' : `
                    <div class="form-group">
                        <label class="form-label" for="srDeadline">Termin płatności</label>
                        <input type="datetime-local" id="srDeadline" class="form-control" value="${edits.deadline}">
                    </div>`}
                    <div class="form-group">
                        <label class="form-label" for="srPackagingMaterial">Materiał / cennik</label>
                        <select id="srPackagingMaterial" class="form-control"></select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srParcelSize">Gabaryt</label>
                        <select id="srParcelSize" class="form-control">
                            <option value="">-- Wybierz --</option>
                            ${parcelOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srCourier">Kurier</label>
                        <select id="srCourier" class="form-control">
                            <option value="">-- Wybierz kuriera --</option>
                            ${courierOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" for="srTracking">Numer przesyłki</label>
                        <input type="text" id="srTracking" class="form-control" placeholder="Numer przesyłki" value="">
                        ${state.mode === 'ship' ? '' : `
                        <p class="sr-tracking-note">
                            Numer zapiszemy od razu, ale klient dostanie powiadomienie
                            o nadaniu dopiero po oznaczeniu zlecenia jako wysłane.
                        </p>`}
                    </div>
                </div>
                ${blockNote}
                ${manyOrders ? `
                <div class="sr-split">
                    <span class="sr-split-title">Podział kosztu na zamówienia</span>
                    <div class="sr-split-rows">${splitRows}</div>
                </div>` : ''}
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

    /** Adres w jednym wierszu — w panelu liczy sie pion, nie ozdobny blok. */
    function addressLine(sr) {
        if (sr.address_type === 'pickup_point') {
            const point = [sr.pickup_courier, sr.pickup_point_id].filter(Boolean).join(' ');
            const rest = [sr.pickup_address, [sr.pickup_postal_code, sr.pickup_city].filter(Boolean).join(' ')]
                .filter(Boolean).join(', ');
            const parts = [
                point ? `<span class="sr-fact-strong">${escapeHtml(point)}</span>` : '',
                rest ? escapeHtml(rest) : '',
            ].filter(Boolean);
            return parts.length ? parts.join(' · ') : '<span class="sr-fact-muted">Brak adresu</span>';
        }

        const line = [
            sr.shipping_address,
            [sr.shipping_postal_code, sr.shipping_city].filter(Boolean).join(' '),
            sr.shipping_voivodeship ? `woj. ${sr.shipping_voivodeship}` : '',
        ].filter(Boolean).join(', ');
        return line
            ? `<span class="sr-fact-strong">Kurier</span> · ${escapeHtml(line)}`
            : '<span class="sr-fact-muted">Brak adresu</span>';
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
            if (e.target.id === 'srDeadline') {
                edits.deadline = e.target.value;
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
            // Zatwierdzona kwota calkowita od razu rozklada sie na zamowienia —
            // inaczej do bazy szla suma pozycji, a nie to, co widac w polu.
            if (e.target.id === 'srTotalCost') {
                const total = parseFloat(e.target.value) || 0;
                if (total > 0) {
                    spreadCost(state.activeId, total);
                    renderDetail();
                    refreshStatus();
                    clearFixedFieldErrors(state.activeId);
                }
                return;
            }
            if (e.target.classList.contains('sr-detail-status-select')) {
                edits.status = e.target.value;
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
        // Na waskich ekranach pasek startuje zwiniety (CSS chowa pola);
        // na desktopie klasa nic nie zmienia, bo pola sa widoczne zawsze.
        const toggle = document.getElementById('srBulkBarToggle');
        toggle.addEventListener('click', () => {
            const bar = document.getElementById('srBulkBar');
            const expanded = bar.classList.toggle('expanded');
            toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        });

        document.getElementById('srBulkApply').addEventListener('click', () => {
            // W trybie wysyłki termin jest ukryty i nie ma go gdzie wysłać —
            // nie liczy się ani do walidacji "choć jedno pole", ani do zastosowania.
            const deadline = state.mode === 'ship' ? '' : document.getElementById('srBulkDeadline').value;
            const materialSelect = document.getElementById('srBulkMaterial');
            const parcelSize = document.getElementById('srBulkParcelSize').value;

            // Nazwa lokalna nie może przysłaniać modułowej funkcji materialOption().
            const selectedMaterial = materialSelect.value
                ? materialSelect.options[materialSelect.selectedIndex]
                : null;

            if (!deadline && !selectedMaterial && !parcelSize) {
                notify('Wypełnij choć jedno pole, żeby ustawić je we wszystkich zleceniach', 'error');
                return;
            }

            state.ids.forEach(id => {
                const edits = state.edits.get(id);
                if (!edits) return;
                if (deadline) edits.deadline = deadline;
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
        if (edits.deadline) {
            payload.payment_deadline = edits.deadline;
        }
        // Tylko gdy admin FAKTYCZNIE zmienil status. Modal wysyla caly payload,
        // wiec niezmieniony status w zadaniu nie moze uruchamiac przejscia
        // (a dla zlecenia zrodlowego paczki — konczyc sie odmowa zapisu kosztow).
        if (edits.status && edits.status !== edits.statusPoczatkowy) {
            payload.status = edits.status;
        }
        // Klucz obecny = "ustaw albo wyczyść", więc pusty wybór nie może zerować przypisania.
        if (edits.packagingMaterialId) {
            payload.packaging_material_id = parseInt(edits.packagingMaterialId, 10);
        }
        return payload;
    }

    /** Payload dla adresu wysyłki — bez terminu i materiału, które wysyłki nie dotyczą. */
    function shipPayloadFor(id) {
        const edits = state.edits.get(id);
        if (!edits) return null;
        return {
            courier: edits.courier,
            tracking_number: edits.trackingNumber,
            parcel_size: edits.parcelSize,
            shipping_cost: totalCost(id),
            order_costs: Array.from(edits.orderCosts.entries())
                .map(([orderId, cost]) => ({ order_id: orderId, shipping_cost: parseFloat(cost) || 0 })),
        };
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
        // Konkretne powody odmowy prosto z serwera — w OBU trybach. Wcześniej tryb
        // wyceny gubił treść odpowiedzi i pokazywał samo „Nie zapisano: WYS/000050",
        // więc admin nie wiedział, co jest nie tak (przy 500 nie wiedział nawet, że
        // to błąd serwera, a nie jego pomyłka).
        const failMessages = [];
        state.saveResults.clear();
        for (const id of state.ids) {
            const ship = state.mode === 'ship';
            const payload = ship ? shipPayloadFor(id) : payloadFor(id);
            if (!payload) {
                failed.push(id);
                state.saveResults.set(id, 'save-failed');
                continue;
            }
            try {
                const url = ship
                    ? `/admin/orders/shipping-requests/${id}/ship`
                    : `/admin/orders/shipping-requests/${id}`;
                const resp = await fetch(url, {
                    method: ship ? 'POST' : 'PUT',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify(payload),
                });
                if (!resp.ok) {
                    failed.push(id);
                    // Odpowiedź błędu może nie być JSON-em (np. 502 z proxy) — stąd try/catch
                    // i fallback. Klucz zależy od endpointu: PUT zlecenia oddaje `error`,
                    // /ship oddaje `message`.
                    let reason = '';
                    try {
                        const data = await resp.json();
                        reason = data && (data.error || data.message);
                    } catch (parseError) {
                        reason = '';
                    }
                    // Komunikaty backendu zawierają już numer zlecenia, więc nie doklejamy
                    // go drugi raz — prefiks jest tylko w zastępczym komunikacie.
                    failMessages.push(reason
                        || `${requestNumber(id)}: nie zapisano, serwer odpowiedział HTTP ${resp.status}`);
                }
                state.saveResults.set(id, resp.ok ? 'saved' : 'save-failed');
            } catch (error) {
                console.error('Błąd zapisu zlecenia', id, error);
                failed.push(id);
                failMessages.push(`${requestNumber(id)}: brak połączenia z serwerem — zapis nie doszedł`);
                state.saveResults.set(id, 'save-failed');
            }
        }

        saveBtn.disabled = false;
        saveBtn.textContent = state.mode === 'ship'
            ? 'Oznacz jako wysłane'
            : (state.ids.length > 1 ? 'Zapisz wszystkie' : 'Zapisz');

        if (!failed.length) {
            closeModal();
            sessionStorage.removeItem('wmsShippingSelection');
            window.location.reload();
            return;
        }
        renderList();   // pozycje dostają klasy saved / save-failed
        if (failMessages.length) {
            // Kilka nieudanych zleceń pokazujemy jako czytelną listę, nie sklejone w jedną kaszę.
            notify(failMessages.map(escapeHtml).join('<br>'), 'error');
        } else {
            const numbers = failed.map(requestNumber).join(', ');
            notify(`Nie zapisano: ${numbers}`, 'error');
        }
    }

    async function cancelRequest() {
        const sr = state.data.get(state.activeId);
        if (!sr) return;

        // Pytanie musi opisywać skutek, a nie „anulowanie", którego tu nie ma:
        // paczka zbiorcza zostaje rozwiązana (zlecenia klientów żyją dalej),
        // zwykłe zlecenie znika, a jego zamówienia wracają do puli.
        const paczka = !!sr.is_consolidation;
        const pytanie = paczka
            ? `Rozwiązać paczkę zbiorczą ${sr.request_number}?\n\n`
              + 'Zamówienia wrócą do zleceń swoich właścicieli, a sama paczka zniknie. '
              + 'Zleceń klientów to nie anuluje.'
            : `Usunąć zlecenie ${sr.request_number}?\n\n`
              + 'Wszystkie zamówienia zostaną odłączone od tego zlecenia i wrócą do puli '
              + 'dostępnych zamówień klienta.';
        if (!confirm(pytanie)) return;

        const czynnosc = paczka
            ? `Nie rozwiązano paczki ${sr.request_number}`
            : `Nie usunięto zlecenia ${sr.request_number}`;
        try {
            const resp = await fetch(`/admin/orders/shipping-requests/${sr.id}`, {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            });
            // Odpowiedź błędu nie musi być JSON-em (np. 502 z proxy) — stąd fallback
            // na status HTTP zamiast wysypania się na parsowaniu.
            let data = null;
            try {
                data = await resp.json();
            } catch (parseError) {
                data = null;
            }
            if (resp.ok && data && data.success) {
                closeModal();
                sessionStorage.removeItem('wmsShippingSelection');
                window.location.reload();
            } else {
                const powod = (data && (data.message || data.error))
                    || `${czynnosc} — serwer odpowiedział HTTP ${resp.status}`;
                notify(escapeHtml(powod), 'error');
            }
        } catch (error) {
            console.error('Błąd usuwania zlecenia:', error);
            notify(`${czynnosc} — brak połączenia z serwerem`, 'error');
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
    window.openShipModal = (ids) => openShippingRequestsModal(ids, { mode: 'ship' });
    window.closeShippingRequestModal = closeModal;
})();
