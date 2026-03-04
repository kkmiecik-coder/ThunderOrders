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

        // Update tooltip message based on reason for disabled state
        if (mergeTooltip) {
            if (count < 2) {
                mergeTooltip.textContent = 'Zaznacz co najmniej 2 zlecenia do scalenia';
            } else if (!sameClient) {
                mergeTooltip.textContent = 'Zaznaczone zlecenia pochodzą od różnych klientów';
            }
        }
    }

    if (count > 0) {
        bulkToolbar.classList.remove('hidden');
    } else {
        bulkToolbar.classList.add('hidden');
    }
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
 * Open bulk cost modal for selected shipping requests
 */
async function openBulkCostModal() {
    const ids = getSelectedRequestIds();
    if (ids.length === 0) return;

    const container = document.getElementById('bulkCostEntries');
    if (!container) return;

    container.innerHTML = '<div class="bulk-cost-loading">Ładowanie danych...</div>';

    const modal = document.getElementById('bulkCostModal');
    if (modal) modal.classList.add('active');

    try {
        // Fetch all selected SRs in parallel
        const responses = await Promise.all(
            ids.map(id => fetch(`/admin/orders/shipping-requests/${id}`).then(r => r.json()))
        );

        container.innerHTML = '';

        responses.forEach(sr => {
            const totalCost = sr.calculated_shipping_cost || 0;
            const ordersHtml = sr.orders.map(o => `
                <tr>
                    <td><a href="/admin/orders/${o.id}" target="_blank" class="sr-order-link">${o.order_number}</a></td>
                    <td class="text-right">${parseFloat(o.total_amount).toFixed(2)} PLN</td>
                    <td>
                        <div class="sr-cost-input">
                            <input type="number" class="form-input bulk-order-cost"
                                data-sr-id="${sr.id}" data-order-id="${o.id}"
                                value="${o.shipping_cost > 0 ? parseFloat(o.shipping_cost).toFixed(2) : ''}"
                                step="0.01" min="0" placeholder="0.00">
                            <span class="currency">PLN</span>
                        </div>
                    </td>
                </tr>
            `).join('');

            const entry = document.createElement('div');
            entry.className = 'bulk-cost-entry';
            entry.dataset.srId = sr.id;
            entry.innerHTML = `
                <div class="bulk-cost-entry-header">
                    <span class="bulk-cost-sr-number">${sr.request_number}</span>
                    <span class="bulk-cost-sr-status badge">${sr.status_display_name || sr.status}</span>
                    <div class="bulk-cost-total-group">
                        <input type="number" class="form-input bulk-total-cost" data-sr-id="${sr.id}"
                            value="${totalCost > 0 ? totalCost.toFixed(2) : ''}"
                            step="0.01" min="0" placeholder="0.00">
                        <span class="currency">PLN</span>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="distributeBulkCost(${sr.id})" title="Rozłóż równo">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M16 3h5v5M8 3H3v5M3 16v5h5M21 16v5h-5M12 8v8M8 12h8"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <table class="sr-orders-table bulk-cost-orders-table">
                    <thead>
                        <tr>
                            <th>Zamówienie</th>
                            <th class="text-right">Wartość</th>
                            <th>Koszt wysyłki</th>
                        </tr>
                    </thead>
                    <tbody>${ordersHtml}</tbody>
                </table>
            `;
            container.appendChild(entry);
        });

    } catch (error) {
        console.error('Error loading bulk cost data:', error);
        container.innerHTML = '<div class="bulk-cost-loading">Błąd ładowania danych</div>';
    }
}

/**
 * Distribute total cost evenly for a specific SR in bulk modal
 */
function distributeBulkCost(srId) {
    const totalInput = document.querySelector(`.bulk-total-cost[data-sr-id="${srId}"]`);
    const costInputs = document.querySelectorAll(`.bulk-order-cost[data-sr-id="${srId}"]`);
    if (!totalInput || costInputs.length === 0) return;

    const total = parseFloat(totalInput.value) || 0;
    const perOrder = total / costInputs.length;
    const rounded = Math.floor(perOrder * 100) / 100;
    const remainder = Math.round((total - rounded * costInputs.length) * 100) / 100;

    costInputs.forEach((input, i) => {
        input.value = (i === 0 ? (rounded + remainder) : rounded).toFixed(2);
    });
}

/**
 * Close bulk cost modal
 */
function closeBulkCostModal() {
    const modal = document.getElementById('bulkCostModal');
    if (!modal || !modal.classList.contains('active')) return;
    modal.classList.add('closing');
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
    }, 350);
}

/**
 * Submit bulk cost form — sends PUT for each SR
 */
async function submitBulkCosts(e) {
    e.preventDefault();

    const entries = document.querySelectorAll('.bulk-cost-entry');
    if (entries.length === 0) return;

    const submitBtn = document.querySelector('#bulkCostForm .sr-save-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Zapisywanie...';
    }

    let successCount = 0;
    let errorCount = 0;

    for (const entry of entries) {
        const srId = entry.dataset.srId;
        const costInputs = entry.querySelectorAll('.bulk-order-cost');

        const orderCosts = [];
        costInputs.forEach(input => {
            orderCosts.push({
                order_id: parseInt(input.dataset.orderId),
                shipping_cost: parseFloat(input.value) || 0
            });
        });

        try {
            const response = await fetch(`/admin/orders/shipping-requests/${srId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ order_costs: orderCosts })
            });

            if (response.ok) {
                successCount++;
                entry.classList.add('bulk-cost-entry-saved');
            } else {
                errorCount++;
                entry.classList.add('bulk-cost-entry-error');
            }
        } catch (error) {
            errorCount++;
            entry.classList.add('bulk-cost-entry-error');
        }
    }

    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Zapisz wszystkie';
    }

    if (errorCount === 0) {
        closeBulkCostModal();
        window.location.reload();
    } else {
        alert(`Zapisano ${successCount}/${successCount + errorCount} zleceń. ${errorCount} z błędem.`);
    }
}

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
            if (window.Toast) {
                window.Toast.show(errorMsg, 'error');
            } else {
                alert(errorMsg);
            }
        }
    } catch (error) {
        console.error('Error creating WMS session:', error);
        const errorMsg = 'Błąd podczas tworzenia sesji WMS';
        if (window.Toast) {
            window.Toast.show(errorMsg, 'error');
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
        hiddenProducts.style.display = 'block';
        button.textContent = 'Zwiń';
        button.classList.add('expanded');
    } else {
        hiddenProducts.style.display = 'none';
        // Restore original text with count
        const hiddenCount = hiddenProducts.querySelectorAll('.order-product-item').length;
        button.textContent = `+${hiddenCount} więcej...`;
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

// Current shipping request data
let currentShippingRequest = null;

/**
 * Open shipping request edit modal
 * @param {number} shippingRequestId - ShippingRequest ID
 */
async function openShippingRequestModal(shippingRequestId) {
    const modal = document.getElementById('editShippingRequestModal');
    if (!modal) return;

    try {
        // Load shipping request data
        const response = await fetch(`/admin/orders/shipping-requests/${shippingRequestId}`);
        if (!response.ok) {
            throw new Error('Nie udało się załadować danych zlecenia');
        }

        const data = await response.json();
        currentShippingRequest = data;

        // Fill modal with data
        document.getElementById('srModalId').value = data.id;
        document.getElementById('srModalNumber').textContent = data.request_number;

        // Set total cost
        const totalCost = data.calculated_shipping_cost || 0;
        document.getElementById('srTotalCost').value = totalCost > 0 ? totalCost.toFixed(2) : '';

        // Render orders table
        renderOrdersTable(data.orders);

        // Render address preview
        renderAddressPreview(data);

        // Shipping section: show only if courier or tracking exist
        const shippingSection = document.getElementById('srShippingSection');
        const shippingReadMode = document.getElementById('srShippingReadMode');
        const shippingEditMode = document.getElementById('srShippingEditMode');
        const hasCourier = !!data.courier;
        const hasTracking = !!data.tracking_number;
        const courierNames = {
            'inpost': 'InPost', 'dpd': 'DPD', 'dhl': 'DHL', 'ups': 'UPS',
            'fedex': 'FedEx', 'gls': 'GLS', 'pocztex': 'Pocztex',
            'orlen': 'Orlen Paczka', 'other': 'Inny'
        };
        const parcelNames = { 'A': 'A - Mały', 'B': 'B - Średni', 'C': 'C - Duży' };

        if (shippingSection) {
            if (hasCourier || hasTracking) {
                shippingSection.style.display = '';
                // Fill read mode texts
                document.getElementById('srShippingCourierText').textContent = courierNames[data.courier] || data.courier || '—';
                document.getElementById('srShippingTrackingText').textContent = data.tracking_number || '—';
                // Parcel size
                const parcelRow = document.getElementById('srShippingParcelRow');
                if (data.parcel_size) {
                    parcelRow.style.display = '';
                    document.getElementById('srShippingParcelText').textContent = parcelNames[data.parcel_size] || data.parcel_size;
                } else {
                    parcelRow.style.display = 'none';
                }
                // Show read mode, hide edit mode
                shippingReadMode.style.display = '';
                shippingEditMode.style.display = 'none';
            } else {
                shippingSection.style.display = 'none';
            }
        }

        // Fill edit mode fields (courier, tracking, parcel_size)
        const courierSelect = document.getElementById('srCourier');
        if (courierSelect) courierSelect.value = data.courier || '';
        const trackingInput = document.getElementById('srTracking');
        if (trackingInput) trackingInput.value = data.tracking_number || '';

        // Handle parcel size field visibility and value
        const parcelSizeGroup = document.getElementById('srParcelSizeGroup');
        const parcelSizeSelect = document.getElementById('srParcelSize');
        if (parcelSizeGroup && parcelSizeSelect) {
            if (data.address_type === 'pickup_point') {
                parcelSizeGroup.style.display = 'block';
                parcelSizeSelect.value = data.parcel_size || '';
            } else {
                parcelSizeGroup.style.display = 'none';
                parcelSizeSelect.value = '';
            }
        }

        // Show modal
        modal.classList.add('active');

    } catch (error) {
        console.error('Error loading shipping request:', error);
        alert('Błąd podczas ładowania danych zlecenia');
    }
}

/**
 * Close shipping request modal with animation
 */
function closeShippingRequestModal() {
    const modal = document.getElementById('editShippingRequestModal');
    if (!modal || !modal.classList.contains('active')) return;

    // Add closing class to trigger exit animation
    modal.classList.add('closing');

    // Wait for animation to complete (350ms as defined in modals.css)
    setTimeout(() => {
        modal.classList.remove('active', 'closing');
        currentShippingRequest = null;
    }, 350);
}

/**
 * Toggle shipping details between read and edit mode
 */
function toggleShippingEdit() {
    const readMode = document.getElementById('srShippingReadMode');
    const editMode = document.getElementById('srShippingEditMode');
    const editBtn = document.getElementById('srShippingEditBtn');
    if (!readMode || !editMode) return;

    const isEditing = editMode.style.display !== 'none';
    if (isEditing) {
        // Switch to read mode
        readMode.style.display = '';
        editMode.style.display = 'none';
        if (editBtn) editBtn.classList.remove('active');
    } else {
        // Switch to edit mode
        readMode.style.display = 'none';
        editMode.style.display = '';
        if (editBtn) editBtn.classList.add('active');
    }
}

/**
 * Render orders table in modal
 */
function renderOrdersTable(orders) {
    const tbody = document.getElementById('srOrdersTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    orders.forEach(order => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <a href="/admin/orders/${order.id}" target="_blank" class="sr-order-link">
                    ${order.order_number}
                </a>
            </td>
            <td class="text-right">${order.total_amount.toFixed(2)} PLN</td>
            <td>
                <div class="sr-cost-input">
                    <input type="number"
                           class="form-input order-shipping-cost"
                           data-order-id="${order.id}"
                           step="0.01"
                           min="0"
                           value="${order.shipping_cost ? order.shipping_cost.toFixed(2) : ''}"
                           placeholder="0.00"
                           oninput="updateTotalShippingCost()">
                    <span class="currency">PLN</span>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

/**
 * Update total shipping cost when individual order costs change
 */
function updateTotalShippingCost() {
    const orderInputs = document.querySelectorAll('.order-shipping-cost');
    let total = 0;

    orderInputs.forEach(input => {
        const value = parseFloat(input.value) || 0;
        total += value;
    });

    const totalCostInput = document.getElementById('srTotalCost');
    if (totalCostInput) {
        totalCostInput.value = total > 0 ? total.toFixed(2) : '';
    }
}

/**
 * Render address preview
 */
function renderAddressPreview(data) {
    const container = document.getElementById('srAddressPreview');
    if (!container) return;

    let html = '';

    if (data.address_type === 'pickup_point') {
        html = `
            <div class="address-type-badge pickup">
                <svg width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5 8 5.961 14.154 3.5 8.186 1.113zM15 4.239l-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                </svg>
                Paczkomat / Punkt odbioru
            </div>
        `;
        if (data.pickup_courier) html += `<div><strong>${data.pickup_courier}</strong></div>`;
        if (data.pickup_point_id) html += `<div class="pickup-id">${data.pickup_point_id}</div>`;
        if (data.pickup_address) html += `<div>${data.pickup_address}</div>`;
        if (data.pickup_postal_code || data.pickup_city) {
            html += `<div>${data.pickup_postal_code || ''} ${data.pickup_city || ''}</div>`;
        }
    } else {
        if (data.shipping_name) html += `<div><strong>${data.shipping_name}</strong></div>`;
        if (data.shipping_address) html += `<div>${data.shipping_address}</div>`;
        if (data.shipping_postal_code || data.shipping_city) {
            html += `<div>${data.shipping_postal_code || ''} ${data.shipping_city || ''}</div>`;
        }
        if (data.shipping_voivodeship) {
            html += `<div class="text-muted">woj. ${data.shipping_voivodeship}</div>`;
        }
    }

    container.innerHTML = html || '<span class="text-muted">Brak adresu</span>';
}

/**
 * Distribute total shipping cost equally among orders
 */
function distributeShippingCost() {
    const totalCostInput = document.getElementById('srTotalCost');
    const totalCost = parseFloat(totalCostInput.value) || 0;

    if (totalCost <= 0) {
        alert('Wprowadź całkowity koszt wysyłki');
        return;
    }

    const orderInputs = document.querySelectorAll('.order-shipping-cost');
    const ordersCount = orderInputs.length;

    if (ordersCount === 0) return;

    // Calculate base cost per order (rounded down to 2 decimal places)
    const baseCost = Math.floor((totalCost / ordersCount) * 100) / 100;

    // Calculate remainder
    const remainder = Math.round((totalCost - (baseCost * ordersCount)) * 100) / 100;

    orderInputs.forEach((input, index) => {
        // Add remainder to the last order
        const cost = index === ordersCount - 1 ? baseCost + remainder : baseCost;
        input.value = cost.toFixed(2);
    });
}

/**
 * Cancel shipping request
 */
async function cancelShippingRequest() {
    if (!currentShippingRequest) return;

    if (!confirm(`Czy na pewno anulować zlecenie ${currentShippingRequest.request_number}?\n\nWszystkie zamówienia zostaną odłączone od tego zlecenia i wrócą do puli dostępnych zamówień klienta.`)) {
        return;
    }

    try {
        const response = await fetch(`/admin/orders/shipping-requests/${currentShippingRequest.id}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        const data = await response.json();
        if (data.success) {
            closeShippingRequestModal();
            window.location.reload();
        } else {
            alert(data.message || data.error || 'Błąd podczas anulowania zlecenia');
        }
    } catch (error) {
        console.error('Error canceling shipping request:', error);
        alert('Błąd podczas anulowania zlecenia');
    }
}

// Form submit handler and event listeners
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('editShippingRequestForm');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            if (!currentShippingRequest) return;

            // Collect order shipping costs
            const orderCosts = [];
            document.querySelectorAll('.order-shipping-cost').forEach(input => {
                orderCosts.push({
                    order_id: parseInt(input.dataset.orderId),
                    shipping_cost: parseFloat(input.value) || 0
                });
            });

            const formData = {
                order_costs: orderCosts
            };

            // Only include shipping fields if edit mode is active
            const shippingEditMode = document.getElementById('srShippingEditMode');
            if (shippingEditMode && shippingEditMode.style.display !== 'none') {
                formData.courier = document.getElementById('srCourier').value;
                formData.tracking_number = document.getElementById('srTracking').value;
                formData.parcel_size = document.getElementById('srParcelSize')?.value || null;
            }

            try {
                const response = await fetch(`/admin/orders/shipping-requests/${currentShippingRequest.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify(formData)
                });

                if (response.ok) {
                    closeShippingRequestModal();
                    window.location.reload();
                } else {
                    const data = await response.json();
                    alert(data.error || 'Błąd podczas zapisywania zmian');
                }
            } catch (error) {
                console.error('Error saving shipping request:', error);
                alert('Błąd podczas zapisywania zmian');
            }
        });
    }

    // Close modal on Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeShippingRequestModal();
            closeBulkCostModal();
        }
    });

    // Close modal when clicking outside
    const modal = document.getElementById('editShippingRequestModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeShippingRequestModal();
            }
        });
    }

    // ============================================
    // BULK TOOLBAR EVENT LISTENERS
    // ============================================

    // Bulk cost button
    const bulkCostBtn = document.querySelector('.btn-bulk[data-action="bulk-cost"]');
    if (bulkCostBtn) {
        bulkCostBtn.addEventListener('click', openBulkCostModal);
    }

    // Bulk cost form submit
    const bulkCostForm = document.getElementById('bulkCostForm');
    if (bulkCostForm) {
        bulkCostForm.addEventListener('submit', submitBulkCosts);
    }

    // Merge button
    const mergeBtn = document.querySelector('.btn-bulk[data-action="merge"]');
    if (mergeBtn) {
        mergeBtn.addEventListener('click', bulkMergeRequests);
    }

    // WMS button
    const wmsBtn = document.querySelector('.btn-bulk[data-action="wms"]');
    if (wmsBtn) {
        wmsBtn.addEventListener('click', bulkGoToWMS);
    }

    // Delete button
    const deleteBtn = document.querySelector('.btn-bulk[data-action="delete"]');
    if (deleteBtn) {
        deleteBtn.addEventListener('click', bulkDeleteRequests);
    }

    // Close bulk cost modal when clicking outside
    const bulkCostModal = document.getElementById('bulkCostModal');
    if (bulkCostModal) {
        bulkCostModal.addEventListener('click', function(e) {
            if (e.target === bulkCostModal) {
                closeBulkCostModal();
            }
        });
    }
});
