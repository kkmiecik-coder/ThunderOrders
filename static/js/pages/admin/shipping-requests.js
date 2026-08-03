// ============================================
// ADMIN SHIPPING REQUESTS MANAGEMENT
// ============================================

// ============================================
// CARD SELECTION SYSTEM
// ============================================

// Store selected shipping request IDs
let selectedRequests = new Set();
// Store client IDs for selected requests (key: requestId, value: clientId)
let selectedRequestClients = new Map();

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
    const clientId = card.dataset.clientId || '';

    if (checkbox.checked) {
        selectedRequests.add(requestId);
        selectedRequestClients.set(requestId, clientId);
        card.classList.add('selected');
    } else {
        selectedRequests.delete(requestId);
        selectedRequestClients.delete(requestId);
        card.classList.remove('selected');
    }

    updateBulkToolbar();
}

/**
 * Check if all selected requests belong to the same client
 * @returns {boolean} True if all requests are from the same client
 */
function allSelectedFromSameClient() {
    if (selectedRequestClients.size <= 1) return true;

    const clientIds = Array.from(selectedRequestClients.values());
    const firstClientId = clientIds[0];

    // All must have the same non-empty client ID
    return firstClientId !== '' && clientIds.every(id => id === firstClientId);
}

/**
 * Update the bulk toolbar visibility and count
 */
function updateBulkToolbar() {
    const bulkToolbar = document.getElementById('bulkToolbar');
    const selectedCountEl = document.getElementById('selectedCount');
    const mergeBtn = document.getElementById('btnBulkMerge');
    const mergeTooltip = document.getElementById('bulkMergeTooltip');

    if (!bulkToolbar) return;

    const count = selectedRequests.size;

    if (selectedCountEl) {
        selectedCountEl.textContent = `${count} zaznaczonych`;
    }

    // Update merge button state and tooltip
    if (mergeBtn) {
        const sameClient = allSelectedFromSameClient();
        const canMerge = count >= 2 && sameClient;
        mergeBtn.disabled = !canMerge;

        // Powód blokady widoczny w menu pod etykietą pozycji
        if (mergeTooltip) {
            if (count < 2) {
                mergeTooltip.textContent = 'Zaznacz co najmniej 2 zlecenia';
            } else if (!sameClient) {
                mergeTooltip.textContent = 'Zlecenia od różnych klientów';
            } else {
                mergeTooltip.textContent = '';
            }
        }
    }

    if (count > 0) {
        bulkToolbar.classList.remove('hidden');
    } else {
        bulkToolbar.classList.add('hidden');
        closeBulkMenu();   // pasek znika razem z rozwiniętym menu
    }
}

/**
 * Rozwijane menu akcji masowych
 */
function toggleBulkMenu() {
    const menu = document.getElementById('bulkMenu');
    const toggle = document.getElementById('bulkMenuToggle');
    const list = document.getElementById('bulkMenuList');
    if (!menu || !toggle || !list) return;

    const willOpen = list.hidden;
    list.hidden = !willOpen;
    menu.classList.toggle('open', willOpen);
    toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
}

function closeBulkMenu() {
    const menu = document.getElementById('bulkMenu');
    const toggle = document.getElementById('bulkMenuToggle');
    const list = document.getElementById('bulkMenuList');
    if (!menu || !toggle || !list || list.hidden) return;

    list.hidden = true;
    menu.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
}

/**
 * Clear all selections
 */
function clearSelection() {
    selectedRequests.clear();
    selectedRequestClients.clear();

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

/** Filtry z adresu — zaznaczenie ma objąć to, co admin faktycznie widzi. */
function currentListFilters() {
    const params = new URLSearchParams(window.location.search);
    return new URLSearchParams({
        status: params.get('status') || '',
        order_type: params.get('order_type') || '',
        search: params.get('search') || '',
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
        selectedRequestClients.clear();
        data.requests.forEach(row => {
            const id = String(row.id);
            selectedRequests.add(id);
            selectedRequestClients.set(id, row.client_id ? String(row.client_id) : '');
        });

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
            window.location.reload();
        } else {
            window.showToast(data.message || data.error || 'Nie udało się usunąć zleceń', 'error');
        }
    } catch (error) {
        console.error('Error deleting requests:', error);
        window.showToast('Nie udało się usunąć zleceń', 'error');
    }
}

/**
 * Bulk merge requests
 */
async function bulkMergeRequests() {
    const ids = getSelectedRequestIds();
    if (ids.length < 2) {
        alert('Wybierz co najmniej 2 zlecenia do scalenia');
        return;
    }

    if (!allSelectedFromSameClient()) {
        alert('Zaznaczone zlecenia pochodzą od różnych klientów. Scalanie możliwe tylko dla zleceń tego samego klienta.');
        return;
    }

    if (!confirm(`Czy na pewno scalić ${ids.length} zaznaczonych zleceń w jedno?\n\nWszystkie zamówienia z wybranych zleceń zostaną połączone w jedno zlecenie.`)) {
        return;
    }

    try {
        const response = await fetch('/admin/orders/shipping-requests/bulk-merge', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                ids: ids.map(id => parseInt(id))
            })
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json();
            alert(data.error || 'Błąd podczas scalania zleceń');
        }
    } catch (error) {
        console.error('Error merging requests:', error);
        alert('Błąd podczas scalania zleceń');
    }
}

// ============================================
// WMS ACTIONS
// ============================================

/**
 * Go to WMS for a single shipping request
 * @param {number} shippingRequestId - The shipping request ID
 */
async function handleGoToWMS(shippingRequestId) {
    await createWmsSession([shippingRequestId]);
}

/**
 * Go to WMS for all selected shipping requests (bulk action)
 */
async function bulkGoToWMS() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    await createWmsSession(ids.map(id => parseInt(id)));
}

/**
 * Create a WMS session from shipping request IDs
 * @param {number[]} shippingRequestIds - Array of shipping request IDs
 */
async function createWmsSession(shippingRequestIds) {
    try {
        const response = await fetch('/admin/orders/wms/create-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({
                shipping_request_ids: shippingRequestIds
            })
        });

        const data = await response.json();

        if (response.ok && data.redirect_url) {
            window.location.href = data.redirect_url;
        } else {
            const errorMsg = data.error || 'Nie udało się utworzyć sesji WMS';
            if (typeof window.showToast === 'function') {
                window.showToast(errorMsg, 'error');
            } else {
                alert(errorMsg);
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
 * Get CSRF token from the page
 */
function getCSRFToken() {
    return document.querySelector('input[name="csrf_token"]')?.value ||
           document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // ============================================
    // BULK TOOLBAR EVENT LISTENERS
    // ============================================

    const menuToggle = document.getElementById('bulkMenuToggle');
    if (menuToggle) {
        menuToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleBulkMenu();
        });
    }

    // Akcje siedzą w rozwijanym menu; delegacja trzyma je w jednym miejscu.
    const menuList = document.getElementById('bulkMenuList');
    if (menuList) {
        const handlers = {
            'bulk-cost': () => {
                const ids = getSelectedRequestIds();
                if (ids.length) window.openShippingRequestsModal(ids);
            },
            'merge': bulkMergeRequests,
            'wms': bulkGoToWMS,
            'export-inpost': exportSelectedToInpost,
            'delete': bulkDeleteRequests,
        };

        menuList.addEventListener('click', (e) => {
            const item = e.target.closest('.bulk-menu-item');
            if (!item || item.disabled) return;
            closeBulkMenu();
            const handler = handlers[item.dataset.action];
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

    // Zamykanie menu: klik poza paskiem i Escape
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#bulkMenu')) closeBulkMenu();
        if (!e.target.closest('#srSelectMenu')) closeSelectMenu();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeBulkMenu();
            closeSelectMenu();
        }
    });
});
