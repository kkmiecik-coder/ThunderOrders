/**
 * Shipping Requests - Client Page JavaScript
 * Handles wizard modal, order selection, and CRUD operations
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize
    initCreateRequestModal();
    initUploadProofModal();
    initCancelButtons();
});

// ================================
// CREATE REQUEST MODAL (WIZARD)
// ================================

let currentStep = 1;
let selectedOrders = [];

function initCreateRequestModal() {
    const modal = document.getElementById('create-request-modal');
    const openBtns = document.querySelectorAll('#create-request-btn, #create-request-btn-empty');
    const closeBtn = document.getElementById('close-create-modal');
    const cancelBtn = document.getElementById('cancel-create-btn');
    const backBtn = document.getElementById('wizard-back-btn');
    const nextBtn = document.getElementById('wizard-next-btn');
    const submitBtn = document.getElementById('wizard-submit-btn');
    const addressSelect = document.getElementById('address-select');

    // Open modal
    openBtns.forEach(btn => {
        if (btn) {
            btn.addEventListener('click', function() {
                openCreateModal();
            });
        }
    });

    // Close modal
    if (closeBtn) closeBtn.addEventListener('click', closeCreateModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeCreateModal);

    // Click outside to close
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeCreateModal();
            }
        });
    }

    // Back button
    if (backBtn) {
        backBtn.addEventListener('click', function() {
            goToStep(1);
        });
    }

    // Next button
    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            goToStep(2);
        });
    }

    // Submit button
    if (submitBtn) {
        submitBtn.addEventListener('click', submitShippingRequest);
    }

    // Address select change
    if (addressSelect) {
        addressSelect.addEventListener('change', updateAddressPreview);
        // Trigger on load if there's a default
        if (addressSelect.value) {
            updateAddressPreview();
        }
    }
}

function openCreateModal() {
    const modal = document.getElementById('create-request-modal');
    if (!modal) return;

    // Reset wizard
    currentStep = 1;
    selectedOrders = [];
    goToStep(1);

    // Load available orders
    loadAvailableOrders();

    // Show modal
    modal.classList.add('active');
}

function closeCreateModal() {
    const modal = document.getElementById('create-request-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function goToStep(step) {
    currentStep = step;

    // Update step indicators
    document.querySelectorAll('.wizard-step').forEach(el => {
        const stepNum = parseInt(el.dataset.step);
        el.classList.remove('active', 'completed');
        if (stepNum < step) {
            el.classList.add('completed');
        } else if (stepNum === step) {
            el.classList.add('active');
        }
    });

    // Show/hide step content
    document.querySelectorAll('.wizard-content').forEach(el => {
        el.style.display = 'none';
    });
    const stepContent = document.getElementById(`wizard-step-${step}`);
    if (stepContent) {
        stepContent.style.display = 'block';
    }

    // Update buttons
    const backBtn = document.getElementById('wizard-back-btn');
    const nextBtn = document.getElementById('wizard-next-btn');
    const submitBtn = document.getElementById('wizard-submit-btn');
    const cancelBtn = document.getElementById('cancel-create-btn');

    if (step === 1) {
        if (backBtn) backBtn.style.display = 'none';
        if (nextBtn) nextBtn.style.display = 'inline-flex';
        if (submitBtn) submitBtn.style.display = 'none';
        if (cancelBtn) cancelBtn.style.display = 'inline-flex';
        updateNextButtonState();
    } else if (step === 2) {
        if (backBtn) backBtn.style.display = 'inline-flex';
        if (nextBtn) nextBtn.style.display = 'none';
        if (submitBtn) submitBtn.style.display = 'inline-flex';
        if (cancelBtn) cancelBtn.style.display = 'none';
        updateSubmitButtonState();
    }
}

function loadAvailableOrders() {
    const container = document.getElementById('orders-selection');
    const noOrdersMsg = document.getElementById('no-orders-message');

    if (!container) return;

    // Show loading
    container.innerHTML = `
        <div class="loading-spinner">
            <div class="spinner"></div>
            <span>Ładowanie zamówień...</span>
        </div>
    `;
    if (noOrdersMsg) noOrdersMsg.style.display = 'none';

    // Fetch available orders
    fetch('/client/shipping/requests/available-orders')
        .then(response => response.json())
        .then(data => {
            if (data.orders && data.orders.length > 0) {
                renderOrderCards(data.orders);
            } else {
                container.innerHTML = '';
                if (noOrdersMsg) noOrdersMsg.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error loading orders:', error);
            container.innerHTML = '<div class="error-message">Błąd podczas ładowania zamówień</div>';
        });
}

function renderOrderCards(orders) {
    const container = document.getElementById('orders-selection');
    if (!container) return;

    // Render as table
    container.innerHTML = `
        <table class="orders-select-table">
            <thead>
                <tr>
                    <th class="col-checkbox"></th>
                    <th class="col-number">Numer</th>
                    <th class="col-items">Produkty</th>
                    <th class="col-amount">Kwota</th>
                </tr>
            </thead>
            <tbody>
                ${orders.map(order => `
                    <tr class="order-row ${selectedOrders.includes(order.id) ? 'selected' : ''}" data-order-id="${order.id}" onclick="toggleOrderSelection(${order.id})">
                        <td class="col-checkbox">
                            <input type="checkbox" class="order-checkbox" id="order-${order.id}" ${selectedOrders.includes(order.id) ? 'checked' : ''}>
                        </td>
                        <td class="col-number">
                            <span class="order-number">${order.order_number}</span>
                            <span class="order-date">${order.created_at}</span>
                        </td>
                        <td class="col-items">
                            <div class="items-list">
                                ${renderOrderItems(order.items, order.id)}
                            </div>
                        </td>
                        <td class="col-amount">
                            <span class="amount-value">${order.total_amount.toFixed(2)} zł</span>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderOrderItems(items, orderId) {
    const visibleItems = items.slice(0, 3);
    const hiddenItems = items.slice(3);

    let html = visibleItems.map(item => `
        <div class="item-row">
            <div class="item-thumb-wrapper">
                <img src="${item.image_url}" alt="" class="item-thumb" loading="lazy">
                ${item.quantity > 1 ? `<span class="item-qty-badge">${item.quantity}</span>` : ''}
            </div>
            <div class="item-details">
                <span class="item-name" title="${item.name}">${item.quantity}× ${truncateText(item.name, 30)}</span>
                <span class="item-price">${item.price.toFixed(2)} zł/szt</span>
            </div>
        </div>
    `).join('');

    if (hiddenItems.length > 0) {
        html += `
            <div class="items-hidden" id="hiddenItems-modal-${orderId}" style="display: none;">
                ${hiddenItems.map(item => `
                    <div class="item-row">
                        <div class="item-thumb-wrapper">
                            <img src="${item.image_url}" alt="" class="item-thumb" loading="lazy">
                            ${item.quantity > 1 ? `<span class="item-qty-badge">${item.quantity}</span>` : ''}
                        </div>
                        <div class="item-details">
                            <span class="item-name" title="${item.name}">${item.quantity}× ${truncateText(item.name, 30)}</span>
                            <span class="item-price">${item.price.toFixed(2)} zł/szt</span>
                        </div>
                    </div>
                `).join('')}
            </div>
            <button type="button" class="items-toggle-btn" onclick="event.stopPropagation(); toggleModalOrderItems(${orderId}, ${items.length})">
                <span class="toggle-text">W sumie ${items.length} produktów - pokaż pozostałe</span>
            </button>
        `;
    }

    return html;
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function toggleModalOrderItems(orderId, totalItems) {
    const hiddenDiv = document.getElementById(`hiddenItems-modal-${orderId}`);
    const toggleBtn = hiddenDiv.parentElement.querySelector('.items-toggle-btn .toggle-text');

    if (hiddenDiv.style.display === 'none') {
        hiddenDiv.style.display = 'flex';
        toggleBtn.textContent = 'Zwiń produkty';
    } else {
        hiddenDiv.style.display = 'none';
        toggleBtn.textContent = `W sumie ${totalItems} produktów - pokaż pozostałe`;
    }
}

function toggleOrderSelection(orderId) {
    const index = selectedOrders.indexOf(orderId);
    const row = document.querySelector(`.order-row[data-order-id="${orderId}"]`);
    const checkbox = document.getElementById(`order-${orderId}`);

    if (index > -1) {
        selectedOrders.splice(index, 1);
        if (row) row.classList.remove('selected');
        if (checkbox) checkbox.checked = false;
    } else {
        selectedOrders.push(orderId);
        if (row) row.classList.add('selected');
        if (checkbox) checkbox.checked = true;
    }

    updateNextButtonState();
}

function updateNextButtonState() {
    const nextBtn = document.getElementById('wizard-next-btn');
    if (nextBtn) {
        nextBtn.disabled = selectedOrders.length === 0;
    }
}

function updateAddressPreview() {
    const select = document.getElementById('address-select');
    const preview = document.getElementById('address-preview');

    if (!select || !preview) return;

    const option = select.options[select.selectedIndex];

    if (option && option.value) {
        const addressType = option.dataset.type;

        let previewHtml = '';

        if (addressType === 'pickup_point') {
            const courier = option.dataset.courier;
            const pointId = option.dataset.pointId;
            const pickupAddress = option.dataset.pickupAddress;
            const pickupPostal = option.dataset.pickupPostal;
            const pickupCity = option.dataset.pickupCity;

            previewHtml = `
                <div class="address-preview-content">
                    <div class="address-preview-icon">
                        <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5 8 5.961 14.154 3.5 8.186 1.113zM15 4.239l-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
                        </svg>
                    </div>
                    <div class="address-preview-details">
                        ${courier ? `<div class="preview-row"><span class="preview-label">Kurier:</span><span class="preview-value">${courier}</span></div>` : ''}
                        ${pointId ? `<div class="preview-row"><span class="preview-label">Kod punktu:</span><span class="preview-value preview-value-highlight">${pointId}</span></div>` : ''}
                        ${pickupAddress ? `<div class="preview-row"><span class="preview-label">Adres:</span><span class="preview-value">${pickupAddress}</span></div>` : ''}
                        ${(pickupPostal || pickupCity) ? `<div class="preview-row"><span class="preview-label">Miasto:</span><span class="preview-value">${pickupPostal} ${pickupCity}</span></div>` : ''}
                    </div>
                </div>
            `;
        } else {
            const shippingName = option.dataset.shippingName;
            const shippingAddress = option.dataset.shippingAddress;
            const shippingPostal = option.dataset.shippingPostal;
            const shippingCity = option.dataset.shippingCity;
            const shippingVoivodeship = option.dataset.shippingVoivodeship;

            previewHtml = `
                <div class="address-preview-content">
                    <div class="address-preview-icon">
                        <svg width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                            <path d="M8.354 1.146a.5.5 0 0 0-.708 0l-6 6A.5.5 0 0 0 1.5 7.5v7a.5.5 0 0 0 .5.5h4.5a.5.5 0 0 0 .5-.5v-4h2v4a.5.5 0 0 0 .5.5H14a.5.5 0 0 0 .5-.5v-7a.5.5 0 0 0-.146-.354L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.354 1.146zM2.5 14V7.707l5.5-5.5 5.5 5.5V14H10v-4a.5.5 0 0 0-.5-.5h-3a.5.5 0 0 0-.5.5v4H2.5z"/>
                        </svg>
                    </div>
                    <div class="address-preview-details">
                        ${shippingName ? `<div class="preview-row"><span class="preview-label">Odbiorca:</span><span class="preview-value">${shippingName}</span></div>` : ''}
                        ${shippingAddress ? `<div class="preview-row"><span class="preview-label">Adres:</span><span class="preview-value">${shippingAddress}</span></div>` : ''}
                        ${(shippingPostal || shippingCity) ? `<div class="preview-row"><span class="preview-label">Miasto:</span><span class="preview-value">${shippingPostal} ${shippingCity}</span></div>` : ''}
                        ${shippingVoivodeship ? `<div class="preview-row"><span class="preview-label">Województwo:</span><span class="preview-value">${shippingVoivodeship}</span></div>` : ''}
                    </div>
                </div>
            `;
        }

        preview.innerHTML = previewHtml;
    } else {
        preview.innerHTML = `
            <div class="address-preview-empty">
                Wybierz adres, aby zobaczyć podgląd
            </div>
        `;
    }

    updateSubmitButtonState();
}

function updateSubmitButtonState() {
    const submitBtn = document.getElementById('wizard-submit-btn');
    const addressSelect = document.getElementById('address-select');

    if (submitBtn && addressSelect) {
        submitBtn.disabled = !addressSelect.value || selectedOrders.length === 0;
    }
}

function submitShippingRequest() {
    const addressSelect = document.getElementById('address-select');
    const submitBtn = document.getElementById('wizard-submit-btn');

    if (!addressSelect || !addressSelect.value) {
        showToast('Wybierz adres dostawy', 'error');
        return;
    }

    if (selectedOrders.length === 0) {
        showToast('Wybierz przynajmniej jedno zamówienie', 'error');
        return;
    }

    // Disable button
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<div class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></div> Tworzenie...';
    }

    // Submit request
    fetch('/client/shipping/requests/create', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
        },
        body: JSON.stringify({
            order_ids: selectedOrders,
            address_id: parseInt(addressSelect.value)
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Zlecenie wysyłki zostało utworzone', 'success');
            closeCreateModal();
            // Reload page to refresh the list
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            showToast(data.error || 'Błąd podczas tworzenia zlecenia', 'error');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Zleć wysyłkę';
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Błąd podczas tworzenia zlecenia', 'error');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Zleć wysyłkę';
        }
    });
}

// ================================
// UPLOAD PROOF MODAL
// ================================

function initUploadProofModal() {
    const modal = document.getElementById('upload-proof-modal');
    const closeBtn = document.getElementById('close-upload-modal');
    const cancelBtn = document.getElementById('cancel-upload-btn');
    const form = document.getElementById('upload-proof-form');

    // Open modal via buttons
    document.querySelectorAll('.upload-proof-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const requestId = this.dataset.requestId;
            const requestNumber = this.dataset.requestNumber || '';
            const shippingCost = this.dataset.shippingCost || '';
            openUploadModal(requestId, requestNumber, shippingCost);
        });
    });

    // Close modal
    if (closeBtn) closeBtn.addEventListener('click', closeUploadModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeUploadModal);

    // Click outside to close
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeUploadModal();
            }
        });
    }

    // Form submit
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            submitPaymentProof();
        });
    }
}

function openUploadModal(requestId, requestNumber, shippingCost) {
    const modal = document.getElementById('upload-proof-modal');
    const requestIdInput = document.getElementById('upload-request-id');

    if (requestIdInput) requestIdInput.value = requestId;

    // Fill payment info box
    const paymentInfoBox = document.getElementById('paymentInfoBox');
    if (paymentInfoBox) {
        const costDisplay = shippingCost ? `${shippingCost} PLN` : 'Oczekuje na wycenę';
        paymentInfoBox.innerHTML = `
            <h3>Płatność za wysyłkę</h3>
            <p><strong>Numer zlecenia:</strong> <code>${requestNumber}</code></p>
            <p><strong>Kwota:</strong> ${costDisplay}</p>
            <p><strong>Tytuł przelewu:</strong> <code>${requestNumber}</code></p>
        `;
    }

    // Load payment methods
    loadPaymentMethodsInfo(requestNumber);

    if (modal) modal.classList.add('active');
}

/**
 * Load active payment methods from API
 */
async function loadPaymentMethodsInfo(requestNumber) {
    const container = document.getElementById('paymentMethodsInfo');
    if (!container) return;

    container.innerHTML = '<p class="text-muted">Ładowanie metod płatności...</p>';

    try {
        const response = await fetch('/api/payment-methods/active');
        const methods = await response.json();

        if (methods.length === 0) {
            container.innerHTML = '<p class="text-muted">Brak dostępnych metod płatności</p>';
            return;
        }

        let html = '<h3 class="payment-methods-heading">Wybierz metodę płatności:</h3>';
        html += '<div class="payment-method-buttons">';

        methods.forEach((method, index) => {
            html += `
                <button type="button"
                        class="payment-method-button ${index === 0 ? 'active' : ''}"
                        onclick="selectPaymentMethod(${index}, '${method.name.replace(/'/g, "\\'")}')"
                        data-method-index="${index}">
                    ${method.name}
                </button>
            `;
        });

        html += '</div>';
        html += '<div class="payment-method-details-container">';

        methods.forEach((method, index) => {
            // Replace [NUMER ZAMÓWIENIA] placeholder with request number
            let detailsText = method.details || '';
            detailsText = detailsText.replace(/\[NUMER ZAMÓWIENIA\]/g, requestNumber);

            html += `
                <div class="payment-method-details ${index === 0 ? 'active' : ''}"
                     data-details-index="${index}">
                    <pre>${detailsText}</pre>
                </div>
            `;
        });

        html += '</div>';

        container.innerHTML = html;

        // Set default payment method (first one) in hidden field
        if (methods.length > 0) {
            const hiddenInput = document.getElementById('selectedPaymentMethodName');
            if (hiddenInput) {
                hiddenInput.value = methods[0].name;
            }
        }
    } catch (error) {
        console.error('Error loading payment methods:', error);
        container.innerHTML = '<p class="text-danger">Błąd ładowania metod płatności</p>';
    }
}

/**
 * Select payment method and show its details
 */
function selectPaymentMethod(index, methodName) {
    // Deactivate all buttons and details
    document.querySelectorAll('.payment-method-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.payment-method-details').forEach(details => {
        details.classList.remove('active');
    });

    // Activate selected button and details
    const selectedButton = document.querySelector(`[data-method-index="${index}"]`);
    const selectedDetails = document.querySelector(`[data-details-index="${index}"]`);

    if (selectedButton) {
        selectedButton.classList.add('active');

        // Update hidden field with selected payment method name
        const hiddenInput = document.getElementById('selectedPaymentMethodName');
        if (hiddenInput) {
            hiddenInput.value = methodName;
        }
    }
    if (selectedDetails) selectedDetails.classList.add('active');
}

function closeUploadModal() {
    const modal = document.getElementById('upload-proof-modal');
    const form = document.getElementById('upload-proof-form');

    if (modal) modal.classList.remove('active');
    if (form) form.reset();
}

function submitPaymentProof() {
    const form = document.getElementById('upload-proof-form');
    const submitBtn = document.querySelector('.modal-footer button[type="submit"]');

    if (!form) return;

    const formData = new FormData(form);

    // Disable button
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Wgrywanie...';
    }

    fetch('/client/shipping/requests/upload-proof', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Dowód wpłaty został wgrany', 'success');
            closeUploadModal();
            location.reload();
        } else {
            showToast(data.error || 'Błąd podczas wgrywania', 'error');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = 'Wgraj dowód';
            }
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Błąd podczas wgrywania', 'error');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Wgraj dowód';
        }
    });
}

// ================================
// CANCEL REQUEST
// ================================

function initCancelButtons() {
    document.querySelectorAll('.cancel-request-btn').forEach(btn => {
        btn.addEventListener('click', function(e) {
            // Ignore click if button is disabled
            if (this.disabled) {
                e.preventDefault();
                return;
            }
            const requestId = this.dataset.requestId;
            cancelRequest(requestId);
        });
    });
}

function cancelRequest(requestId) {
    if (!confirm('Czy na pewno chcesz anulować to zlecenie wysyłki?\n\nZamówienia przypisane do tego zlecenia wrócą do puli i będą dostępne do ponownego zlecenia wysyłki.')) {
        return;
    }

    fetch(`/client/shipping/requests/${requestId}/cancel`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Zlecenie zostało anulowane', 'success');
            // Reload page to refresh the list
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            showToast(data.error || 'Błąd podczas anulowania', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('Błąd podczas anulowania', 'error');
    });
}

// ================================
// REFRESH REQUESTS LIST
// ================================

function refreshRequestsList() {
    fetch('/client/shipping/requests/list')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                renderRequestsTable(data.requests);
                // Re-initialize event listeners
                initUploadProofModal();
                initCancelButtons();
            }
        })
        .catch(error => {
            console.error('Error refreshing requests list:', error);
        });
}

function renderRequestsTable(requests) {
    const tableContainer = document.querySelector('.table-container');
    if (!tableContainer) return;

    if (requests.length === 0) {
        // Show empty state
        tableContainer.innerHTML = `
            <div class="empty-state">
                <svg width="64" height="64" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M0 3.5A1.5 1.5 0 0 1 1.5 2h9A1.5 1.5 0 0 1 12 3.5V5h1.02a1.5 1.5 0 0 1 1.17.563l1.481 1.85a1.5 1.5 0 0 1 .329.938V10.5a1.5 1.5 0 0 1-1.5 1.5H14a2 2 0 1 1-4 0H5a2 2 0 1 1-3.998-.085A1.5 1.5 0 0 1 0 10.5v-7zm1.294 7.456A1.999 1.999 0 0 1 4.732 11h5.536a2.01 2.01 0 0 1 .732-.732V3.5a.5.5 0 0 0-.5-.5h-9a.5.5 0 0 0-.5.5v7a.5.5 0 0 0 .294.456zM12 10a2 2 0 0 1 1.732 1h.768a.5.5 0 0 0 .5-.5V8.35a.5.5 0 0 0-.11-.312l-1.48-1.85A.5.5 0 0 0 13.02 6H12v4zm-9 1a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm9 0a1 1 0 1 0 0 2 1 1 0 0 0 0-2z"/>
                </svg>
                <h3>Brak zleceń wysyłki</h3>
                <p>Nie masz jeszcze żadnych zleceń wysyłki</p>
                <button type="button" class="btn btn-primary" id="create-request-btn-empty">Zleć pierwszą wysyłkę</button>
            </div>
        `;
        // Re-attach empty state button
        const emptyBtn = document.getElementById('create-request-btn-empty');
        if (emptyBtn) {
            emptyBtn.addEventListener('click', openCreateModal);
        }
        return;
    }

    // Render table
    tableContainer.innerHTML = `
        <table class="requests-table">
            <thead>
                <tr>
                    <th class="col-number">Numer zlecenia</th>
                    <th class="col-orders">Zamówienia</th>
                    <th class="col-address">Adres dostawy</th>
                    <th class="col-cost text-right">Koszt</th>
                    <th class="col-tracking">Nr przesyłki</th>
                    <th class="col-status">Status</th>
                    <th class="col-date">Data</th>
                    <th class="col-actions">Akcje</th>
                </tr>
            </thead>
            <tbody>
                ${requests.map(req => renderRequestRow(req)).join('')}
            </tbody>
        </table>
    `;
}

function renderRequestRow(req) {
    // Render orders badges
    const ordersBadges = req.orders.map(order =>
        `<a href="/client/orders/${order.id}" class="order-badge" title="${order.order_number}">${order.order_number}</a>`
    ).join('');
    const ordersMore = req.orders_count > 3 ? `<span class="orders-more">+${req.orders_count - 3}</span>` : '';

    // Render address icon
    const addressIcon = req.address_type === 'pickup_point'
        ? `<svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
            <path d="M8.186 1.113a.5.5 0 0 0-.372 0L1.846 3.5 8 5.961 14.154 3.5 8.186 1.113zM15 4.239l-6.5 2.6v7.922l6.5-2.6V4.24zM7.5 14.762V6.838L1 4.239v7.923l6.5 2.6zM7.443.184a1.5 1.5 0 0 1 1.114 0l7.129 2.852A.5.5 0 0 1 16 3.5v8.662a1 1 0 0 1-.629.928l-7.185 2.874a.5.5 0 0 1-.372 0L.63 13.09a1 1 0 0 1-.63-.928V3.5a.5.5 0 0 1 .314-.464L7.443.184z"/>
           </svg>`
        : `<svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
            <path d="M8.354 1.146a.5.5 0 0 0-.708 0l-6 6A.5.5 0 0 0 1.5 7.5v7a.5.5 0 0 0 .5.5h4.5a.5.5 0 0 0 .5-.5v-4h2v4a.5.5 0 0 0 .5.5H14a.5.5 0 0 0 .5-.5v-7a.5.5 0 0 0-.146-.354L13 5.793V2.5a.5.5 0 0 0-.5-.5h-1a.5.5 0 0 0-.5.5v1.293L8.354 1.146zM2.5 14V7.707l5.5-5.5 5.5 5.5V14H10v-4a.5.5 0 0 0-.5-.5h-3a.5.5 0 0 0-.5.5v4H2.5z"/>
           </svg>`;

    // Render cost
    const costHtml = req.total_shipping_cost
        ? `<span class="cost-value">${req.total_shipping_cost.toFixed(2)} zł</span>`
        : `<span class="cost-pending">Oczekuje</span>`;

    // Render tracking
    let trackingHtml = '<span class="tracking-pending">—</span>';
    if (req.tracking_number) {
        if (req.tracking_url) {
            trackingHtml = `<span class="tracking-number"><a href="${req.tracking_url}" target="_blank" title="Śledź przesyłkę">${req.tracking_number}</a></span>`;
        } else {
            trackingHtml = `<span class="tracking-number">${req.tracking_number}</span>`;
        }
    }

    // Render actions
    let actionsHtml = '';

    if (req.can_upload_payment_proof) {
        const shippingCostStr = req.total_shipping_cost ? req.total_shipping_cost.toFixed(2) : '';
        actionsHtml += `
            <button type="button" class="btn btn-sm btn-secondary upload-proof-btn"
                    data-request-id="${req.id}"
                    data-request-number="${req.request_number}"
                    data-shipping-cost="${shippingCostStr}"
                    title="Wgraj dowód wpłaty">
                <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/>
                    <path d="M7.646 1.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1-.708.708L8.5 2.707V11.5a.5.5 0 0 1-1 0V2.707L5.354 4.854a.5.5 0 1 1-.708-.708l3-3z"/>
                </svg>
            </button>
        `;
    }

    if (req.has_payment_proof) {
        let proofIcon = '';
        if (req.payment_proof_status === 'pending') {
            proofIcon = `<svg width="14" height="14" fill="#F59E0B" viewBox="0 0 16 16">
                <path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/>
                <path d="M8 4a.5.5 0 0 1 .5.5v3h3a.5.5 0 0 1 0 1h-3.5a.5.5 0 0 1-.5-.5v-3.5A.5.5 0 0 1 8 4z"/>
            </svg>`;
        } else if (req.payment_proof_status === 'approved') {
            proofIcon = `<svg width="14" height="14" fill="#10B981" viewBox="0 0 16 16">
                <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zm-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>
            </svg>`;
        } else if (req.payment_proof_status === 'rejected') {
            proofIcon = `<svg width="14" height="14" fill="#EF4444" viewBox="0 0 16 16">
                <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM5.354 4.646a.5.5 0 1 0-.708.708L7.293 8l-2.647 2.646a.5.5 0 0 0 .708.708L8 8.707l2.646 2.647a.5.5 0 0 0 .708-.708L8.707 8l2.647-2.646a.5.5 0 0 0-.708-.708L8 7.293 5.354 4.646z"/>
            </svg>`;
        }
        actionsHtml += `<span class="proof-status-icon proof-status-${req.payment_proof_status}" title="Dowód wpłaty: ${req.payment_proof_status}">${proofIcon}</span>`;
    }

    if (req.can_cancel) {
        actionsHtml += `
            <button type="button" class="btn btn-sm btn-danger cancel-request-btn" data-request-id="${req.id}" title="Anuluj zlecenie">
                <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                    <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                </svg>
            </button>
        `;
    }

    return `
        <tr data-request-id="${req.id}">
            <td class="col-number" data-label="Numer">
                <span class="request-number">${req.request_number}</span>
            </td>
            <td class="col-orders" data-label="Zamówienia">
                <div class="orders-badges">
                    ${ordersBadges}
                    ${ordersMore}
                </div>
            </td>
            <td class="col-address" data-label="Adres">
                <div class="address-cell">
                    <span class="address-icon" title="${req.address_type === 'pickup_point' ? 'Paczkomat' : 'Adres domowy'}">
                        ${addressIcon}
                    </span>
                    <span class="address-text" title="${req.full_address}">${req.short_address}</span>
                </div>
            </td>
            <td class="col-cost text-right" data-label="Koszt">
                ${costHtml}
            </td>
            <td class="col-tracking" data-label="Nr przesyłki">
                ${trackingHtml}
            </td>
            <td class="col-status" data-label="Status">
                <span class="badge status-badge" style="background-color: ${req.status_badge_color}; color: #fff;">
                    ${req.status_display_name}
                </span>
            </td>
            <td class="col-date" data-label="Data">
                ${req.created_at}
            </td>
            <td class="col-actions" data-label="Akcje">
                <div class="actions-group">
                    ${actionsHtml}
                </div>
            </td>
        </tr>
    `;
}

// Toast notifications - use global showToast from main.js
// No local definition needed
