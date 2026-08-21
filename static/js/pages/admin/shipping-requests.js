// ============================================
// ADMIN SHIPPING REQUESTS MANAGEMENT
// ============================================

// ============================================
// CARD SELECTION SYSTEM
// ============================================

// Store selected shipping request IDs
let selectedRequests = new Set();
// Status zleceń zaznaczonych przez "zaznacz na wszystkich stronach" — te zlecenia
// nie mają karty w DOM (są poza bieżącą stroną), więc akcje zbiorcze czytające
// status z karty potrzebują tego zapasowego źródła (patrz bulkMarkShipped).
let selectedRequestStatuses = new Map();

// Paginacja to zwykłe przeładowanie strony (<a href>), więc zaznaczenie trzymane
// tylko w zmiennych JS ginie przy zmianie strony. sessionStorage (jak przy
// srDeleteNotice) przenosi je przez przeładowanie; czyszczone jawnie tam, gdzie
// zaznaczenie zostaje skonsumowane przez akcję zbiorczą (patrz wywołania niżej).
const SR_SELECTION_STORAGE_KEY = 'wmsShippingSelection';

function persistSelection() {
    sessionStorage.setItem(SR_SELECTION_STORAGE_KEY, JSON.stringify({
        ids: Array.from(selectedRequests),
        statuses: Array.from(selectedRequestStatuses.entries()),
    }));
}

function restoreSelection() {
    const raw = sessionStorage.getItem(SR_SELECTION_STORAGE_KEY);
    if (!raw) return;

    try {
        const data = JSON.parse(raw);
        selectedRequests = new Set(data.ids || []);
        selectedRequestStatuses = new Map(data.statuses || []);
    } catch (error) {
        sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);
    }
}

/**
 * Toggle card selection when clicking on the card
 * @param {HTMLElement} card - The card element
 * @param {Event} event - The click event
 */
function toggleCardSelection(card, event) {
    // Don't toggle if clicking on interactive elements
    if (event.target.closest('a, button, input, select, textarea')) {
        return;
    }

    const checkbox = card.querySelector('.sr-checkbox');
    if (checkbox) {
        checkbox.checked = !checkbox.checked;
        handleCheckboxChange(checkbox);
    }
}

/**
 * Handle checkbox change
 * @param {HTMLInputElement} checkbox - The checkbox element
 */
function handleCheckboxChange(checkbox) {
    const card = checkbox.closest('.sr-card');
    const requestId = checkbox.dataset.id;

    if (checkbox.checked) {
        selectedRequests.add(requestId);
        selectedRequestStatuses.set(requestId, card.dataset.status || '');
        card.classList.add('selected');
    } else {
        selectedRequests.delete(requestId);
        selectedRequestStatuses.delete(requestId);
        card.classList.remove('selected');
    }

    persistSelection();
    updateBulkToolbar();
}

// Wspólny komponent paska akcji masowych (static/js/components/bulk-toolbar.js).
// Tworzony leniwie, bo pasek renderuje się tylko na zakładce "shipping".
let bulkPasek = null;

function getBulkPasek() {
    if (!bulkPasek && window.BulkToolbar) {
        bulkPasek = window.BulkToolbar.init('bulkToolbar');
    }
    return bulkPasek;
}

/**
 * Update the bulk toolbar visibility and count
 */
function updateBulkToolbar() {
    const pasek = getBulkPasek();
    const consolidateBtn = document.getElementById('btnBulkConsolidate');
    const consolidateTooltip = document.getElementById('bulkConsolidateTooltip');
    const markShippedBtn = document.getElementById('btnBulkMarkShipped');

    if (!pasek) return;

    const count = selectedRequests.size;

    // Pasek i tak chowa się przy zerze zaznaczonych, ale pozycja menu ma być
    // wyłączona tak samo jak "Konsoliduj wysyłki" — spójnie, na wypadek gdyby menu
    // zostało otwarte w trakcie zmiany zaznaczenia.
    if (markShippedBtn) {
        markShippedBtn.disabled = count === 0;
    }

    // Konsolidacja z definicji łączy zlecenia różnych klientów, więc jedynym
    // warunkiem blokady jest liczba zaznaczonych (min. 2) — bez sprawdzania klienta.
    if (consolidateBtn) {
        consolidateBtn.disabled = count < 2;
        if (consolidateTooltip) {
            consolidateTooltip.textContent = count < 2 ? 'Zaznacz co najmniej 2 zlecenia' : '';
        }
    }

    // Komponent sam ustawia tekst licznika (z odmianą) i chowa pasek razem
    // z rozwiniętym menu, gdy nic nie jest zaznaczone.
    pasek.update(count);
}

/**
 * Clear all selections
 */
function clearSelection() {
    selectedRequests.clear();
    selectedRequestStatuses.clear();
    sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);

    // Uncheck all checkboxes
    document.querySelectorAll('.sr-checkbox').forEach(checkbox => {
        checkbox.checked = false;
    });

    // Remove selected class from all cards
    document.querySelectorAll('.sr-card').forEach(card => {
        card.classList.remove('selected');
    });

    updateBulkToolbar();
}

/**
 * Get array of selected request IDs
 * @returns {string[]} Array of selected IDs
 */
function getSelectedRequestIds() {
    return Array.from(selectedRequests);
}

// ============================================
// MENU ZAZNACZANIA
// ============================================

/** Odświeża checkboxy widocznych kart według stanu zaznaczenia. */
function syncCheckboxesWithSelection() {
    document.querySelectorAll('.sr-checkbox').forEach(checkbox => {
        const isSelected = selectedRequests.has(checkbox.dataset.id);
        checkbox.checked = isSelected;
        const card = checkbox.closest('.sr-card');
        if (card) card.classList.toggle('selected', isSelected);
    });
}

function selectAllOnPage(shouldSelect) {
    document.querySelectorAll('.sr-checkbox').forEach(checkbox => {
        if (checkbox.checked !== shouldSelect) {
            checkbox.checked = shouldSelect;
            handleCheckboxChange(checkbox);
        }
    });
}

/** Filtry z adresu — zaznaczenie ma objąć to, co admin faktycznie widzi.
 * Bez consolidation „zaznacz na wszystkich stronach” w widoku „scalone”
 * cichnie zapytałoby o domyślny widok (bez źródeł) — inny zestaw niż na ekranie. */
function currentListFilters() {
    const params = new URLSearchParams(window.location.search);
    return new URLSearchParams({
        status: params.get('status') || '',
        order_type: params.get('order_type') || '',
        search: params.get('search') || '',
        consolidation: params.get('consolidation') || '',
    });
}

async function selectAllPages() {
    try {
        const response = await fetch(
            `/api/orders/shipping-requests/filtered-ids?${currentListFilters()}`
        );
        const data = await response.json();

        if (!response.ok || !data.success) {
            window.showToast('Nie udało się pobrać listy zleceń', 'error');
            return;
        }

        selectedRequests.clear();
        selectedRequestStatuses.clear();
        data.requests.forEach(row => {
            const id = String(row.id);
            selectedRequests.add(id);
            selectedRequestStatuses.set(id, row.status || '');
        });

        persistSelection();
        syncCheckboxesWithSelection();
        updateBulkToolbar();
        window.showToast(
            `Zaznaczono ${data.requests.length} ${pluralizeRequests(data.requests.length)}`,
            'success'
        );
    } catch (error) {
        console.error('Error selecting all pages:', error);
        window.showToast('Nie udało się pobrać listy zleceń', 'error');
    }
}

function pluralizeRequests(count) {
    if (count === 1) return 'zlecenie';
    const rest = count % 10;
    const teens = count % 100;
    if (rest >= 2 && rest <= 4 && (teens < 12 || teens > 14)) return 'zlecenia';
    return 'zleceń';
}

function toggleSelectMenu() {
    const menu = document.getElementById('srSelectMenu');
    const toggle = document.getElementById('srSelectToggle');
    const list = document.getElementById('srSelectMenuList');
    if (!menu || !toggle || !list) return;

    const willOpen = list.hidden;
    list.hidden = !willOpen;
    menu.classList.toggle('open', willOpen);
    toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}

function closeSelectMenu() {
    const menu = document.getElementById('srSelectMenu');
    const toggle = document.getElementById('srSelectToggle');
    const list = document.getElementById('srSelectMenuList');
    if (!menu || !toggle || !list || list.hidden) return;

    list.hidden = true;
    menu.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
}

// ============================================
// BULK ACTIONS
// ============================================

/**
 * Treść potwierdzenia usuwania.
 *
 * Odkąd można zaznaczyć zlecenia na wszystkich stronach, część usuwanych
 * pozycji bywa poza ekranem — wtedy mówimy o tym wprost i wypisujemy numery,
 * żeby skala operacji nie była zaskoczeniem.
 */
function buildDeleteConfirmation(ids) {
    const visibleIds = new Set(
        Array.from(document.querySelectorAll('.sr-checkbox')).map(cb => cb.dataset.id)
    );
    const offScreen = ids.filter(id => !visibleIds.has(id));

    const lines = [
        `Czy na pewno usunąć ${ids.length} ${pluralizeRequests(ids.length)}?`,
    ];

    if (offScreen.length) {
        lines.push('', `Uwaga: ${offScreen.length} ${pluralizeRequests(offScreen.length)} ` +
                       'spoza tej strony — zaznaczenie obejmuje inne strony listy.');
    }

    const numbers = ids
        .map(id => document.querySelector(`.sr-card[data-request-id="${id}"] .sr-card-number`))
        .filter(Boolean)
        .map(el => el.textContent.trim());

    // Numery wypisujemy tylko wtedy, gdy znamy je dla wszystkich usuwanych
    // zleceń — niepełna lista przy większej liczbie wprowadzałaby w błąd.
    if (numbers.length === ids.length && numbers.length <= 10) {
        lines.push('', numbers.join(', '));
    }

    lines.push('', 'Wszystkie zamówienia zostaną odłączone od tych zleceń i wrócą do puli dostępnych zamówień klienta.');

    return lines.join('\n');
}

/**
 * Bulk delete requests
 */
async function bulkDeleteRequests() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    if (!confirm(buildDeleteConfirmation(ids))) {
        return;
    }

    try {
        const response = await fetch('/admin/orders/shipping-requests/bulk-cancel', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                ids: ids.map(id => parseInt(id))
            })
        });

        const data = await response.json();
        if (response.ok) {
            // Część zleceń może zostać pominięta (np. już wysłane) — komunikat
            // z serwera musi dotrwać do widoku mimo przeładowania strony.
            if (data.skipped_count && data.skipped_count > 0) {
                sessionStorage.setItem('srDeleteNotice', data.message);
            }
            sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);
            window.location.reload();
        } else {
            window.showToast(data.message || data.error || 'Nie udało się usunąć zleceń', 'error');
        }
    } catch (error) {
        console.error('Error deleting requests:', error);
        window.showToast('Nie udało się usunąć zleceń', 'error');
    }
}

// ============================================
// WMS ACTIONS
// ============================================

// Referencja do "finish" oczekującego (jeszcze nierozwiązanego) wywołania askReopenMode.
// Pozwala domknąć poprzednie wywołanie, gdy otwierane jest kolejne, żeby w danym
// momencie żyło najwyżej jedno wywołanie i jego komplet nasłuchów.
let pendingReopenFinish = null;

/**
 * Pyta o tryb powrotu spakowanego zlecenia (lub zaznaczenia) do WMS.
 * @param {string} [requestNumber] - numer zlecenia do wyświetlenia (przy count === 1)
 * @param {number} [count] - liczba zaznaczonych zleceń; > 1 pokazuje treść zbiorczą
 * @returns {Promise<'full'|'repack'|null>} wybrany tryb albo null przy anulowaniu
 */
function askReopenMode(requestNumber, count = 1) {
    return new Promise(resolve => {
        const modal = document.getElementById('wmsReopenModal');
        if (!modal) { resolve(null); return; }

        // Jeśli poprzednie wywołanie wciąż czeka na wybór, domknij je z wynikiem null
        // (odepnie jego nasłuchy i rozwiąże jego obietnicę), zanim otworzymy okno ponownie.
        if (pendingReopenFinish) {
            pendingReopenFinish(null);
        }

        const isMulti = count > 1;
        const title = document.getElementById('wmsReopenTitle');
        const leadSingle = document.getElementById('wmsReopenLeadSingle');
        const leadMulti = document.getElementById('wmsReopenLeadMulti');

        if (title) title.textContent = isMulti ? 'Zlecenia są już spakowane' : 'Zlecenie jest już spakowane';
        if (leadSingle) leadSingle.hidden = isMulti;
        if (leadMulti) leadMulti.hidden = !isMulti;

        if (isMulti) {
            document.getElementById('wmsReopenCount').textContent = String(count);
            document.getElementById('wmsReopenCountWord').textContent = pluralizeRequests(count);
        } else {
            document.getElementById('wmsReopenNumber').textContent = requestNumber || '';
        }

        modal.classList.add('active');

        function finish(mode) {
            modal.classList.remove('active');
            modal.querySelectorAll('.wms-reopen-option').forEach(btn => {
                btn.removeEventListener('click', onOption);
            });
            document.getElementById('wmsReopenCancel').removeEventListener('click', onCancel);
            document.getElementById('wmsReopenClose').removeEventListener('click', onCancel);
            modal.removeEventListener('click', onOverlayClick);
            document.removeEventListener('keydown', onKeydown);
            if (pendingReopenFinish === finish) {
                pendingReopenFinish = null;
            }
            resolve(mode);
        }
        function onOption(e) { finish(e.currentTarget.dataset.mode); }
        function onCancel() { finish(null); }
        function onOverlayClick(e) {
            if (e.target === modal) finish(null);
        }
        function onKeydown(e) {
            if (e.key === 'Escape') finish(null);
        }

        pendingReopenFinish = finish;

        modal.querySelectorAll('.wms-reopen-option').forEach(btn => {
            btn.addEventListener('click', onOption);
        });
        document.getElementById('wmsReopenCancel').addEventListener('click', onCancel);
        document.getElementById('wmsReopenClose').addEventListener('click', onCancel);
        modal.addEventListener('click', onOverlayClick);
        document.addEventListener('keydown', onKeydown);
    });
}

/**
 * Go to WMS for a single shipping request
 * @param {number} shippingRequestId - The shipping request ID
 * @param {string} [status] - status zlecenia; 'spakowane' uruchamia pytanie o tryb
 * @param {string} [requestNumber] - numer zlecenia do okna wyboru
 */
async function handleGoToWMS(shippingRequestId, status, requestNumber) {
    if (status === 'spakowane') {
        const mode = await askReopenMode(requestNumber);
        if (!mode) return;
        await createWmsSession([shippingRequestId], mode);
        return;
    }
    await createWmsSession([shippingRequestId]);
}

/**
 * Go to WMS for all selected shipping requests (bulk action)
 *
 * Jeśli wśród zaznaczonych jest choć jedno spakowane zlecenie, pytamy raz
 * o tryb powrotu (jak przy przycisku na karcie) i stosujemy wybór do całego
 * zaznaczenia — inaczej zaznaczenie spakowanych zleceń kończyłoby się błędem
 * z serwera (sesji WMS nie da się założyć wprost dla spakowanego zlecenia).
 */
async function bulkGoToWMS() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    const hasPacked = ids.some(id => {
        const card = document.querySelector(`.sr-card[data-request-id="${id}"]`);
        const status = card ? card.dataset.status : selectedRequestStatuses.get(id);
        return status === 'spakowane';
    });

    let mode;
    if (hasPacked) {
        let requestNumber;
        if (ids.length === 1) {
            const numberEl = document.querySelector(`.sr-card[data-request-id="${ids[0]}"] .sr-card-number`);
            requestNumber = numberEl ? numberEl.textContent.trim() : '';
        }
        mode = await askReopenMode(requestNumber, ids.length);
        if (!mode) return;
    }

    await createWmsSession(ids.map(id => parseInt(id)), mode);
}

/**
 * Oznacza zaznaczone zlecenia jako wysłane — otwiera scalony modal w trybie wysyłki.
 * Zlecenia inne niż spakowane odpadają przed otwarciem, żeby modal nie obiecywał
 * czegoś, co i tak odbije się błędem po stronie serwera.
 */
function bulkMarkShipped() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    const packed = [];
    const skipped = [];
    ids.forEach(id => {
        const card = document.querySelector(`.sr-card[data-request-id="${id}"]`);
        // Zaznaczenie "na wszystkich stronach" dociąga zlecenia spoza bieżącej
        // strony — te nie mają karty w DOM, więc status bierzemy z mapy zebranej
        // przy zaznaczaniu (selectAllPages). Nieznany status = pomijamy.
        const status = card ? card.dataset.status : selectedRequestStatuses.get(id);
        if (status === 'spakowane') packed.push(id);
        else skipped.push(id);
    });

    if (skipped.length) {
        const msg = `Pominięto ${skipped.length} ${pluralizeRequests(skipped.length)} — oznaczyć jako wysłane można tylko spakowane`;
        if (typeof window.showToast === 'function') window.showToast(msg, 'warning');
        else alert(msg);
    }
    if (!packed.length) return;

    window.openShipModal(packed);
}

/**
 * Create a WMS session from shipping request IDs
 * @param {number[]} shippingRequestIds - Array of shipping request IDs
 * @param {'full'|'repack'} [reopenMode] - tryb powrotu spakowanego zlecenia
 */
async function createWmsSession(shippingRequestIds, reopenMode) {
    try {
        const body = { shipping_request_ids: shippingRequestIds };
        if (reopenMode) body.reopen_mode = reopenMode;

        const response = await fetch('/admin/orders/wms/create-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (response.ok && data.redirect_url) {
            sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);
            window.location.href = data.redirect_url;
        } else {
            // Backend (wms_create_session) zwraca 'message' (i ewentualnie listę
            // powodów w 'errors'), nigdy 'error' — bez tego komunikaty typu
            // "Nieznany tryb powrotu do WMS" albo "zablokowane 14:32" nie docierały.
            const errorMsg = data.message || data.error || 'Nie udało się utworzyć sesji WMS';
            if (typeof window.showToast === 'function') {
                window.showToast(errorMsg, 'error');
            } else {
                alert(errorMsg);
            }
            if (data.errors && data.errors.length) {
                if (typeof window.showToast === 'function') {
                    window.showToast(formatExportWarnings(data.errors), 'warning', 12000);
                } else {
                    alert(data.errors.join('\n'));
                }
            }
        }
    } catch (error) {
        console.error('Error creating WMS session:', error);
        const errorMsg = 'Błąd podczas tworzenia sesji WMS';
        if (typeof window.showToast === 'function') {
            window.showToast(errorMsg, 'error');
        } else {
            alert(errorMsg);
        }
    }
}

// ============================================
// EKSPORT INPOST
// ============================================

/**
 * Buduje plik CSV do masowego nadania w panelu InPost i pobiera go.
 * Ostrzeżenia (pominięte zlecenia, braki telefonu) pokazujemy osobnym toastem,
 * bo plik i tak powstaje — admin musi wiedzieć, czego w nim nie ma.
 */
async function exportSelectedToInpost() {
    const ids = getSelectedRequestIds();
    if (!ids.length) return;

    try {
        const response = await fetch('/admin/orders/shipping-requests/export-inpost', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ ids })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            window.showToast(data.error || 'Nie udało się przygotować pliku', 'error');
            return;
        }

        if (data.exported > 0) {
            downloadCsv(data.csv, data.filename);
            window.showToast(
                `Plik gotowy: ${data.exported} ${pluralizeShipments(data.exported)}`,
                'success'
            );
        } else {
            window.showToast('Żadne z zaznaczonych zleceń nie nadaje się do eksportu', 'error');
        }

        if (data.warnings && data.warnings.length) {
            window.showToast(formatExportWarnings(data.warnings), 'warning', 12000);
        }
    } catch (error) {
        console.error('Error exporting to InPost:', error);
        window.showToast('Błąd podczas przygotowania pliku', 'error');
    }
}

/** BOM pozwala Excelowi poprawnie odczytać polskie znaki. */
function downloadCsv(csvText, filename) {
    const blob = new Blob(['﻿' + csvText], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function pluralizeShipments(count) {
    if (count === 1) return 'przesyłka';
    const rest = count % 10;
    const teens = count % 100;
    if (rest >= 2 && rest <= 4 && (teens < 12 || teens > 14)) return 'przesyłki';
    return 'przesyłek';
}

/** Przy dużym zaznaczeniu lista ostrzeżeń bywa długa — skracamy do 5 pozycji. */
function formatExportWarnings(warnings) {
    const escape = (text) => {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    const shown = warnings.slice(0, 5).map(escape);
    if (warnings.length > shown.length) {
        shown.push(`…i ${warnings.length - shown.length} więcej`);
    }
    return shown.join('<br>');
}

// ============================================
// PRODUCTS TOGGLE
// ============================================

/**
 * Toggle visibility of hidden order products
 * @param {HTMLElement} button - The toggle button
 */
function toggleOrderProducts(button) {
    const productsContainer = button.parentElement;
    const hiddenProducts = productsContainer.querySelector('.order-products-hidden');

    if (!hiddenProducts) return;

    const isHidden = hiddenProducts.style.display === 'none';

    if (isHidden) {
        hiddenProducts.style.display = 'flex';
        button.textContent = 'Ukryj';
        button.classList.add('expanded');
    } else {
        hiddenProducts.style.display = 'none';
        button.textContent = 'Pokaż';
        button.classList.remove('expanded');
    }
}

/**
 * Toggle visibility of the shipping request's orders beyond the first 3
 * @param {HTMLElement} button - The "Pokaż więcej" button rendered after the orders list
 */
function toggleExtraOrders(button) {
    // Przycisk jest dzieckiem .sr-orders-compact, obok wierszy zamówień
    // (nie jego sąsiadem) — ukryte wiersze szukamy więc wśród rodzeństwa.
    const container = button.parentElement;
    if (!container) return;

    const hiddenOrders = container.querySelectorAll('.sr-order-extra');
    if (!hiddenOrders.length) return;

    const isExpanded = button.dataset.expanded === 'true';

    hiddenOrders.forEach((order) => {
        order.style.display = isExpanded ? 'none' : '';
    });

    // Liczba w tekście przycisku to liczba ukrytych ZAMÓWIEŃ, nie liczba elementów
    // .sr-order-extra: w karcie paczki zbiorczej w pełni ukryta grupa uczestnika to
    // jeden wrapper obejmujący kilka zamówień naraz, więc hiddenOrders.length by ją
    // zaniżał po zwinięciu. Serwer policzył prawdziwą liczbę raz, w data-hidden-count.
    const hiddenCount = parseInt(button.dataset.hiddenCount, 10) || hiddenOrders.length;

    if (isExpanded) {
        button.textContent = `Pokaż więcej (${hiddenCount})`;
        button.dataset.expanded = 'false';
    } else {
        button.textContent = 'Pokaż mniej';
        button.dataset.expanded = 'true';
    }
}

/**
 * Dla każdego pola "Uwagi", które nie mieści się w 2 linijkach, przycina
 * widoczny tekst (wyszukiwaniem binarnym po słowach) tak, żeby razem z "…"
 * kończył się dokładnie tam, gdzie ma stanąć przycisk "Pokaż więcej" —
 * czysty CSS (line-clamp/float) nie daje przycisku dokleić się do ostatniego
 * widocznego słowa, gdy pełny tekst jest dłuższy niż klamrowany obszar.
 */
function initNotesClamp() {
    document.querySelectorAll('.sr-notes-clamp').forEach((clamp) => {
        const textEl = clamp.querySelector('.sr-notes-text');
        const btn = clamp.querySelector('.sr-notes-toggle');
        if (!textEl || !btn) return;

        // scrollHeight/clientHeight na samym <span> tekstu to zawsze 0 (element
        // inline bez własnego "boxa"). Mierzymy więc na .sr-notes-clamp, które
        // ma max-height + overflow: hidden z CSS — clientHeight to zawsze
        // wysokość 2 linijek, scrollHeight to rzeczywista wysokość treści.
        const fullText = textEl.textContent.trim();
        const maxHeight = clamp.clientHeight;

        // Przycisk musi być widoczny już na czas pomiaru — inaczej po jego
        // pokazaniu jego własna szerokość dokłada się na końcu ostatniej
        // linijki i zawija tekst na (przyciętą) trzecią linijkę.
        clamp.classList.add('sr-has-more');

        if (clamp.scrollHeight <= maxHeight + 1) {
            clamp.classList.remove('sr-has-more');
            return;
        }

        const words = fullText.split(' ');
        let lo = 0;
        let hi = words.length;

        while (lo < hi) {
            const mid = lo + Math.ceil((hi - lo) / 2);
            textEl.textContent = words.slice(0, mid).join(' ') + '…';
            if (clamp.scrollHeight <= maxHeight + 1) {
                lo = mid;
            } else {
                hi = mid - 1;
            }
        }

        const truncatedText = words.slice(0, lo).join(' ') + '…';
        textEl.textContent = truncatedText;
        clamp.dataset.fullText = fullText;
        clamp.dataset.truncatedText = truncatedText;
    });
}

/**
 * Toggle "Uwagi" text between truncated (2 lines) and full content
 * @param {HTMLElement} button - The inline "Pokaż więcej/mniej" toggle
 */
function toggleNotesClamp(button) {
    const clamp = button.closest('.sr-notes-clamp');
    const textEl = clamp?.querySelector('.sr-notes-text');
    if (!clamp || !textEl) return;

    const isExpanded = clamp.classList.toggle('sr-notes-expanded');
    textEl.textContent = isExpanded ? clamp.dataset.fullText : clamp.dataset.truncatedText;
    button.textContent = isExpanded ? 'Pokaż mniej' : 'Pokaż więcej';
}

/**
 * Get CSRF token from the page
 */
function getCSRFToken() {
    return document.querySelector('input[name="csrf_token"]')?.value ||
           document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

/**
 * Escape HTML to prevent XSS (wstawianie tekstu do innerHTML)
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// KONSOLIDACJA WYSYŁEK
// ============================================

// `mode` rozróżnia trzy warianty modalu, bo mają różną semantykę zapisu:
// 'create' — nowa paczka z zaznaczonych samodzielnych zleceń (POST /consolidate z lead_request_id),
// 'attach' — zaznaczenie zawierało istniejącą paczkę: dopięcie nowych zleceń do niej
//            (POST /consolidate z target_id),
// 'manage' — modal otwarty z gotowej paczki: zmiana wiodącego idzie osobnym, dedykowanym
//            endpointem /consolidation/lead — NIE generycznym /consolidate, bo ten drugi
//            próbowałby dopiąć uczestników, którzy już należą do tej paczki, a backend
//            (waliduj_do_konsolidacji) odrzuca dopinanie już dopiętych jako błąd.
let consolidationState = {
    requests: [], leadId: null, targetId: null, mode: 'create',
    targetHasTracking: false, originalLeadId: null,
};

const CONSOLIDATION_HINT_LEAD =
    'Wybierz zlecenie wiodące — jego adres, adresat i kontakt trafią na paczkę.';

/** Pobiera dane zaznaczonych zleceń i otwiera modal w trybie tworzenia. */
async function openConsolidationModal(ids) {
    const dane = await fetchConsolidationPreview(ids);
    if (!dane) return;
    // Bez tego `dane.requests[0].id` rzuca TypeError, gdy zaznaczenie wskazuje na
    // rekordy skasowane w międzyczasie (sessionStorage przeżywa reload) — modal po
    // prostu się nie otwierał, bez żadnego komunikatu.
    if (!dane.requests || !dane.requests.length) {
        window.showToast('Nie znaleziono zaznaczonych zleceń — odśwież listę.', 'error');
        return;
    }

    // Zaznaczona paczka zbiorcza oznacza dopięcie do niej, nie tworzenie nowej.
    const zbiorcze = dane.requests.find(r => r.is_consolidation);
    consolidationState = {
        requests: dane.requests,
        // W trybie dopięcia adresat NIE podlega wyborowi: dopinamy do gotowej paczki,
        // która ma już swojego wiodącego, a POST /consolidate z target_id żadnego
        // lead_request_id nie przyjmuje. Wskazujemy więc na samą paczkę, żeby
        // podsumowanie pokazało jej FAKTYCZNEGO adresata zamiast „—", a wiersze nie
        // udawały wybieralnych (wcześniej klik podświetlał wiersz i przeliczał
        // podsumowanie, po czym backend po cichu ignorował wybór). Adresata zmienia
        // się w trybie „Zarządzaj paczką", dedykowanym endpointem /consolidation/lead.
        leadId: zbiorcze ? zbiorcze.id : dane.requests[0].id,
        targetId: zbiorcze ? zbiorcze.id : null,
        mode: zbiorcze ? 'attach' : 'create',
        targetHasTracking: zbiorcze ? !!zbiorcze.has_tracking : false,
        originalLeadId: zbiorcze ? zbiorcze.id : null,
    };

    document.getElementById('consolidationModalTitle').textContent =
        zbiorcze ? `Dopnij do paczki ${zbiorcze.request_number}` : 'Konsolidacja wysyłek';
    document.getElementById('consolidationSubmitBtn').textContent =
        zbiorcze ? 'Dopnij do paczki' : 'Scal w paczkę zbiorczą';
    document.getElementById('consolidationDissolveBtn').style.display = 'none';
    document.getElementById('consolidationHint').textContent = zbiorcze
        ? `Zlecenia zostaną dopięte do paczki ${zbiorcze.request_number}. Adresat paczki ` +
          'nie zmienia się — zmienisz go przyciskiem „Zarządzaj paczką".'
        : CONSOLIDATION_HINT_LEAD;

    renderConsolidation(dane.blocked);
    document.getElementById('consolidationModal').classList.add('active');
}

async function fetchConsolidationPreview(ids) {
    try {
        const r = await fetch(
            `/admin/orders/shipping-requests/consolidation-preview?ids=${ids.join(',')}`);
        if (!r.ok) {
            const e = await r.json();
            window.showToast(e.error || 'Nie udało się pobrać danych zleceń', 'error');
            return null;
        }
        return await r.json();
    } catch (error) {
        console.error('Consolidation preview error:', error);
        window.showToast('Nie udało się pobrać danych zleceń', 'error');
        return null;
    }
}

/**
 * Miękkie ostrzeżenia modalu — informują, NIE blokują przycisku (twarde blokady
 * idą osobno, listą `blocked` z preview). Oba wymienione wprost w specyfikacji.
 */
function consolidationNotices() {
    const uwagi = [];
    const wiersze = consolidationState.requests;
    const scalanie = consolidationState.mode !== 'manage';

    if (scalanie && wiersze.length > 1) {
        // Paczka dostaje status najmniej zaawansowany ze scalanych — admin ma
        // wiedzieć, że opłacone zlecenie „cofnie się" w widoku paczki.
        const statusy = new Set(wiersze.map(r => r.status));
        if (statusy.size > 1) {
            const naj = wiersze.reduce((a, r) =>
                (r.status_sort_order || 0) < (a.status_sort_order || 0) ? r : a, wiersze[0]);
            uwagi.push(`Scalane zlecenia mają różne statusy — paczka dostanie status ` +
                       `„${naj.status_name}", najmniej zaawansowany ze scalanych.`);
        }
        // Numer przesyłki bywa wpisywany przed spakowaniem; etykieta u kuriera
        // zostaje z adresem sprzed scalenia.
        const zTrackingiem = wiersze.filter(r => r.has_tracking).map(r => r.request_number);
        if (zTrackingiem.length) {
            uwagi.push(`Zlecenia ${zTrackingiem.join(', ')} mają już numer przesyłki — ` +
                       `etykieta u kuriera zostanie z poprzednim adresem.`);
        }
    }

    if (consolidationState.mode === 'manage' && consolidationState.targetHasTracking &&
        consolidationState.leadId !== consolidationState.originalLeadId) {
        uwagi.push('Paczka ma już numer przesyłki — zmiana adresata przepisze adres ' +
                   'w systemie, ale etykieta u kuriera zostanie stara.');
    }

    return uwagi;
}

function renderConsolidation(blokady) {
    const lista = document.getElementById('consolidationList');
    lista.innerHTML = '';
    // W trybie dopięcia wiersze są tylko listą dopinanych zleceń, nie wyborem
    // adresata — klasa wyłącza podpowiedzi interaktywności (kursor, hover).
    lista.classList.toggle('consolidation-list--readonly',
                           consolidationState.mode === 'attach');

    consolidationState.requests
        .filter(r => !r.is_consolidation)
        .forEach(r => {
            const row = document.createElement('div');
            const wybrany = consolidationState.mode !== 'attach' &&
                            r.id === consolidationState.leadId;
            row.className = 'consolidation-row' + (wybrany ? ' is-lead' : '');
            row.dataset.id = r.id;
            row.innerHTML = `
                <div class="consolidation-row-main">
                    <strong>${escapeHtml(r.request_number)}</strong>
                    · ${escapeHtml(r.client_name)}
                    <div class="consolidation-row-meta">
                        ${escapeHtml(r.full_address)} · ${r.orders_count} zam. · ${escapeHtml(r.status_name)}
                    </div>
                </div>`;
            // "Wypnij" ma sens tylko dla uczestników JUŻ przypiętych do paczki (tryb
            // zarządzania) — w trybie dopięcia wiersze to dopiero kandydaci do dopięcia,
            // detach na nich zawsze skończyłby się błędem 404 z backendu.
            if (consolidationState.mode === 'manage') {
                // Zaksięgowanie wpłaty offline ma sens tylko dla uczestnika, który
                // jeszcze nie jest opłacony — po opłaceniu przycisk znika sam.
                if (r.status === 'czeka_na_oplacenie' || r.status === 'czeka_na_wycene') {
                    const wplata = document.createElement('button');
                    wplata.type = 'button';
                    wplata.className = 'consolidation-register-pay';
                    wplata.textContent = 'Zaksięguj wpłatę';
                    wplata.title = 'Wpłata przyjęta poza systemem (gotówka, przelew)';
                    wplata.dataset.registerPay = r.id;
                    wplata.dataset.requestNumber = r.request_number;
                    row.appendChild(wplata);
                }
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'consolidation-detach';
                btn.textContent = 'Wypnij';
                btn.dataset.detach = r.id;
                row.appendChild(btn);
            }
            lista.appendChild(row);
        });

    // Event delegation — escapeHtml nie escapuje apostrofów, więc żadnych inline onclick
    // z danymi klienta. Klik w wiersz ustawia wiodące, klik w „Wypnij" wypina.
    lista.onclick = (e) => {
        const wplata = e.target.closest('[data-register-pay]');
        if (wplata) {
            zaksiegujWplateZlecenia(parseInt(wplata.dataset.registerPay, 10),
                                    wplata.dataset.requestNumber);
            return;
        }
        const detach = e.target.closest('[data-detach]');
        if (detach) {
            detachFromConsolidation(parseInt(detach.dataset.detach, 10));
            return;
        }
        // W trybie dopięcia wiersz nie ustawia adresata (backend go nie przyjmuje),
        // więc klik nie może udawać wyboru — patrz komentarz przy consolidationState.
        if (consolidationState.mode === 'attach') return;
        const row = e.target.closest('.consolidation-row');
        if (!row) return;
        consolidationState.leadId = parseInt(row.dataset.id, 10);
        renderConsolidation(blokady);
    };

    renderConsolidationSummary();

    const uwagi = consolidationNotices();
    const notices = document.getElementById('consolidationNotices');
    notices.innerHTML = uwagi.map(t => `<p>${escapeHtml(t)}</p>`).join('');
    notices.style.display = uwagi.length ? '' : 'none';

    const box = document.getElementById('consolidationWarnings');
    const submit = document.getElementById('consolidationSubmitBtn');
    if (blokady && blokady.length) {
        box.textContent = blokady.join(' ');
        box.style.display = '';
        submit.disabled = true;
    } else {
        box.style.display = 'none';
        submit.disabled = false;
    }
}

function renderConsolidationSummary() {
    const lead = consolidationState.requests.find(r => r.id === consolidationState.leadId);
    // Bez filtra is_consolidation: w trybie dopięcia requests zawiera też samą paczkę
    // docelową (wyłączoną tylko z listy wierszy do wyboru) — jej zamówienia muszą wejść
    // do sumy, inaczej podsumowanie liczyłoby tylko nowo dopinanych, nie całej paczki.
    const suma = consolidationState.requests
        .reduce((acc, r) => acc + r.orders_count, 0);
    const dl = document.getElementById('consolidationSummary');
    dl.innerHTML = `
        <dt>Adresat</dt><dd>${lead ? escapeHtml(lead.client_name) : '—'}</dd>
        <dt>Adres</dt><dd>${lead ? escapeHtml(lead.full_address) : '—'}</dd>
        <dt>Kontakt</dt><dd>${lead && lead.client_email ? escapeHtml(lead.client_email) : '—'}</dd>
        <dt>Zawartość</dt><dd>${suma} zamówień</dd>`;
}

function closeConsolidationModal() {
    document.getElementById('consolidationModal').classList.remove('active');
}

async function submitConsolidation() {
    try {
        if (consolidationState.mode === 'manage') {
            // Tryb zarządzania zmienia tylko zlecenie wiodące — dedykowany endpoint,
            // patrz komentarz przy definicji consolidationState.mode.
            const r = await fetch(
                `/admin/orders/shipping-requests/${consolidationState.targetId}/consolidation/lead`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                    body: JSON.stringify({ lead_request_id: consolidationState.leadId }),
                });
            const dane = await r.json();
            if (!r.ok) {
                window.showToast(dane.error || 'Nie udało się zapisać adresata', 'error');
                return;
            }
            window.location.reload();
            return;
        }

        const ids = consolidationState.requests.map(r => r.id);
        const body = consolidationState.targetId
            ? { ids, target_id: consolidationState.targetId }
            : { ids, lead_request_id: consolidationState.leadId };

        const r = await fetch('/admin/orders/shipping-requests/consolidate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify(body),
        });
        const dane = await r.json();
        if (!r.ok) {
            window.showToast(dane.error || 'Nie udało się scalić zleceń', 'error');
            return;
        }
        sessionStorage.removeItem(SR_SELECTION_STORAGE_KEY);
        window.location.reload();
    } catch (error) {
        console.error('Consolidation submit error:', error);
        window.showToast('Nie udało się zapisać zmian', 'error');
    }
}

/** Modal w trybie zarządzania gotową paczką — z karty zbiorczej. */
async function openConsolidationManageModal(consolidationId) {
    const dane = await fetchConsolidationPreview([consolidationId]);
    if (!dane) return;
    // Ten sam guard co w openConsolidationModal: paczka mogła zniknąć (rozwiązana
    // w innej karcie), a `dane.requests[0]` rzuciłby wtedy TypeError.
    if (!dane.requests || !dane.requests.length) {
        window.showToast('Nie znaleziono tej paczki — odśwież listę.', 'error');
        return;
    }
    const zbiorcze = dane.requests[0];

    const sources = await fetchConsolidationPreview(zbiorcze.source_ids);
    if (!sources) return;

    consolidationState = {
        requests: sources.requests,
        leadId: zbiorcze.lead_source_request_id,
        targetId: consolidationId,
        mode: 'manage',
        // Do ostrzeżenia o nieaktualnej etykiecie u kuriera przy zmianie adresata.
        targetHasTracking: !!zbiorcze.has_tracking,
        originalLeadId: zbiorcze.lead_source_request_id,
    };
    document.getElementById('consolidationModalTitle').textContent =
        `Paczka ${zbiorcze.request_number}`;
    document.getElementById('consolidationSubmitBtn').textContent = 'Zapisz adresata';
    document.getElementById('consolidationHint').textContent = CONSOLIDATION_HINT_LEAD;
    document.getElementById('consolidationDissolveBtn').style.display = '';
    // `sources.blocked` tu zawsze zgłasza "już należy do paczki" dla każdego uczestnika —
    // preview nie odróżnia „już w TEJ paczce" od „w innej" (patrz routes.py). Walidację
    // faktycznej zmiany i tak robi docelowy endpoint /consolidation/lead przy zapisie.
    renderConsolidation([]);
    document.getElementById('consolidationModal').classList.add('active');
}

async function zaksiegujWplateZlecenia(sourceId, requestNumber) {
    // Wpłata przyjęta poza systemem (gotówka, przelew bez potwierdzenia od
    // klienta). Backend księguje E4 wszystkich zamówień tego zlecenia, pomijając
    // pozycje bez należności i te, które klient już opłacił.
    const nazwa = requestNumber || 'to zlecenie';
    if (!confirm(
        `Zaksięgować wpłatę za wysyłkę zlecenia ${nazwa}?\n\n` +
        'Użyj, gdy klient zapłacił poza systemem — gotówką albo przelewem, ' +
        'do którego nie wgrywa potwierdzenia.')) return;
    try {
        const r = await fetch(`/admin/payment-confirmations/register-request/${sourceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
            body: JSON.stringify({ note: 'Zaksięgowano z modala paczki zbiorczej' }),
        });
        const dane = await r.json();
        if (!r.ok || !dane.success) {
            window.showToast(dane.message || 'Nie udało się zaksięgować wpłaty', 'error');
            return;
        }
        window.showToast(dane.message, 'success');
        window.location.reload();
    } catch (error) {
        console.error('Register payment error:', error);
        window.showToast('Nie udało się zaksięgować wpłaty', 'error');
    }
}

async function detachFromConsolidation(sourceId) {
    if (!confirm('Wypiąć to zlecenie z paczki zbiorczej?')) return;
    try {
        const r = await fetch(
            `/admin/orders/shipping-requests/${consolidationState.targetId}/consolidation/detach`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                body: JSON.stringify({ source_id: sourceId }),
            });
        const dane = await r.json();
        if (!r.ok) {
            window.showToast(dane.error || 'Nie udało się wypiąć zlecenia', 'error');
            return;
        }
        window.location.reload();
    } catch (error) {
        console.error('Consolidation detach error:', error);
        window.showToast('Nie udało się wypiąć zlecenia', 'error');
    }
}

async function dissolveConsolidation() {
    if (!confirm('Rozwiązać paczkę zbiorczą? Zlecenia wrócą do samodzielnej wysyłki.')) return;
    try {
        const r = await fetch(
            `/admin/orders/shipping-requests/${consolidationState.targetId}/consolidation/dissolve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
                body: JSON.stringify({}),
            });
        const dane = await r.json();
        if (!r.ok) {
            window.showToast(dane.error || 'Nie udało się rozwiązać paczki', 'error');
            return;
        }
        window.location.reload();
    } catch (error) {
        console.error('Consolidation dissolve error:', error);
        window.showToast('Nie udało się rozwiązać paczki', 'error');
    }
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // ============================================
    // BULK TOOLBAR EVENT LISTENERS
    // ============================================

    // Komponent obsługuje rozwijanie menu, zamykanie kliknięciem poza i Escape.
    const pasek = getBulkPasek();
    if (pasek) {
        pasek.initMenu('bulkMenu', 'bulkMenuToggle', 'bulkMenuList');

        // Akcje siedzą w rozwijanym menu; delegacja trzyma je w jednym miejscu.
        const handlers = {
            'bulk-cost': () => {
                const ids = getSelectedRequestIds();
                if (ids.length) window.openShippingRequestsModal(ids);
            },
            'consolidate': () => openConsolidationModal(getSelectedRequestIds().map(Number)),
            'mark-shipped': bulkMarkShipped,
            'wms': bulkGoToWMS,
            'export-inpost': exportSelectedToInpost,
            'delete': bulkDeleteRequests,
        };

        pasek.onAction((action) => {
            pasek.closeMenu();
            const handler = handlers[action];
            if (handler) handler();
        });
    }

    // ============================================
    // MENU ZAZNACZANIA
    // ============================================

    // Komunikat o pominiętych zleceniach przetrwał przeładowanie po usuwaniu
    const deleteNotice = sessionStorage.getItem('srDeleteNotice');
    if (deleteNotice) {
        sessionStorage.removeItem('srDeleteNotice');
        window.showToast(deleteNotice, 'warning', 10000);
    }

    // Odtwarza zaznaczenie zapisane przed przejściem na inną stronę listy —
    // dotyczy tylko kart obecnych w DOM tej strony, reszta zostaje w pamięci
    // (patrz selectAllPages / SR_SELECTION_STORAGE_KEY).
    restoreSelection();
    syncCheckboxesWithSelection();
    updateBulkToolbar();

    const selectToggle = document.getElementById('srSelectToggle');
    if (selectToggle) {
        selectToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleSelectMenu();
        });
    }

    const selectList = document.getElementById('srSelectMenuList');
    if (selectList) {
        const selectHandlers = {
            'page-all': () => selectAllOnPage(true),
            'page-none': () => selectAllOnPage(false),
            'all-all': selectAllPages,
            'all-none': clearSelection,
        };

        selectList.addEventListener('click', (e) => {
            const item = e.target.closest('.sr-select-item');
            if (!item) return;
            closeSelectMenu();
            const handler = selectHandlers[item.dataset.selectAction];
            if (handler) handler();
        });
    }

    // Zamykanie menu zaznaczania: klik poza nim i Escape.
    // Menu akcji masowych zamyka już komponent (initMenu).
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#srSelectMenu')) closeSelectMenu();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSelectMenu();
        }
    });

    initNotesClamp();
});

// Cofnięcie pomyłkowego oznaczenia jako wysłane. Kasowanie zlecenia po wysyłce
// jest zablokowane (zabierało tracking, daty i opinię o dostawie), więc pomyłka
// musi mieć własne, odwracalne wyjście. Event delegation po data-* — bez inline
// onclick z danymi (escapeHtml nie escapuje apostrofów).
document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.js-unship');
    if (!btn) return;
    e.stopPropagation();

    const numer = btn.dataset.srNumber || 'to zlecenie';
    if (!confirm(
        `Cofnąć wysyłkę zlecenia ${numer}?\n\n` +
        'Zlecenie wróci do stanu „Spakowane", a numer przesyłki i wpisy nadania ' +
        'zostaną usunięte. Klient nie dostanie o tym powiadomienia.')) return;

    try {
        const r = await fetch(`/admin/orders/shipping-requests/${btn.dataset.srId}/unship`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCSRFToken() },
        });
        const dane = await r.json();
        if (!r.ok || !dane.success) {
            window.showToast(dane.message || 'Nie udało się cofnąć wysyłki', 'error');
            return;
        }
        window.showToast(dane.message, 'success');
        window.location.reload();
    } catch (error) {
        console.error('Unship error:', error);
        window.showToast('Nie udało się cofnąć wysyłki', 'error');
    }
});
