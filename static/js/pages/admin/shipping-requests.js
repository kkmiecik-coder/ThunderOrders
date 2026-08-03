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
// BULK ACTIONS
// ============================================

/**
 * Bulk delete requests
 */
async function bulkDeleteRequests() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    if (!confirm(`Czy na pewno usunąć ${ids.length} zaznaczonych zleceń?\n\nWszystkie zamówienia zostaną odłączone od tych zleceń i wrócą do puli dostępnych zamówień klienta.`)) {
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
            if (data.skipped_count && data.skipped_count > 0) {
                alert(data.message);
            }
            window.location.reload();
        } else {
            alert(data.message || data.error || 'Błąd podczas usuwania zleceń');
        }
    } catch (error) {
        console.error('Error deleting requests:', error);
        alert('Błąd podczas usuwania zleceń');
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

    // Zamykanie menu: klik poza paskiem i Escape
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#bulkMenu')) closeBulkMenu();
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeBulkMenu();
    });
});
