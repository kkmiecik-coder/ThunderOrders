// ============================================
// ADMIN SHIPPING REQUESTS MANAGEMENT
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

        // Load statuses and set current
        await loadShippingRequestStatuses(data.status);

        // Set courier and tracking
        const courierSelect = document.getElementById('srCourier');
        if (courierSelect) {
            courierSelect.value = data.courier || '';
        }
        document.getElementById('srTracking').value = data.tracking_number || '';

        // Set total cost
        const totalCost = data.calculated_shipping_cost || 0;
        document.getElementById('srTotalCost').value = totalCost > 0 ? totalCost.toFixed(2) : '';

        // Render orders table
        renderOrdersTable(data.orders);

        // Render address preview
        renderAddressPreview(data);

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
 * Close shipping request modal
 */
function closeShippingRequestModal() {
    const modal = document.getElementById('editShippingRequestModal');
    if (modal) {
        modal.classList.remove('active');
        currentShippingRequest = null;
    }
}

/**
 * Load shipping request statuses into select
 */
async function loadShippingRequestStatuses(currentStatus) {
    const select = document.getElementById('srStatus');
    if (!select) return;

    try {
        const response = await fetch('/admin/orders/shipping-request-statuses/list');
        if (!response.ok) throw new Error('Failed to load statuses');

        const statuses = await response.json();
        select.innerHTML = '';

        statuses.forEach(status => {
            const option = document.createElement('option');
            option.value = status.slug;
            option.textContent = status.name;
            if (status.slug === currentStatus) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading statuses:', error);
        // Fallback - keep current status
        select.innerHTML = `<option value="${currentStatus}" selected>${currentStatus}</option>`;
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

        if (response.ok) {
            closeShippingRequestModal();
            window.location.reload();
        } else {
            const data = await response.json();
            alert(data.error || 'Błąd podczas anulowania zlecenia');
        }
    } catch (error) {
        console.error('Error canceling shipping request:', error);
        alert('Błąd podczas anulowania zlecenia');
    }
}

// Form submit handler
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
                status: document.getElementById('srStatus').value,
                courier: document.getElementById('srCourier').value,
                tracking_number: document.getElementById('srTracking').value,
                parcel_size: document.getElementById('srParcelSize')?.value || null,
                order_costs: orderCosts
            };

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
});
