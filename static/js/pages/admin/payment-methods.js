// ============================================
// PAYMENT METHODS SETTINGS FUNCTIONS
// ============================================

/**
 * Toggle visibility of payment method fields based on method type
 */
function togglePaymentMethodFields(prefix) {
    const methodType = document.getElementById(prefix + 'MethodType').value;
    const recipientField = document.getElementById(prefix + '-field-recipient');
    const codeField = document.getElementById(prefix + '-field-code');

    if (methodType === 'transfer') {
        // Przelew: pokaż odbiorcę i kod (SWIFT)
        recipientField.style.display = 'block';
        codeField.style.display = 'block';
    } else if (methodType === 'instant') {
        // BLIK: ukryj odbiorcę i kod
        recipientField.style.display = 'none';
        codeField.style.display = 'none';
    } else if (methodType === 'online') {
        // Online: ukryj odbiorcę, pokaż kod (Revolut)
        recipientField.style.display = 'none';
        codeField.style.display = 'block';
    } else {
        // Other: pokaż wszystko
        recipientField.style.display = 'block';
        codeField.style.display = 'block';
    }
}

/**
 * Podgląd wybranego logo
 */
function previewLogo(input, prefix, type) {
    const file = input.files[0];
    if (!file) return;

    const preview = document.getElementById(prefix + '-logo-' + type + '-preview');
    const img = document.getElementById(prefix + '-logo-' + type + '-img');
    const selectLabel = document.getElementById(prefix + '-logo-' + type + '-select');

    const reader = new FileReader();
    reader.onload = function(e) {
        img.src = e.target.result;
        preview.style.display = 'flex';
        selectLabel.style.display = 'none';
    };
    reader.readAsDataURL(file);
}

/**
 * Usuń podgląd logo (i oznacz do usunięcia na backendzie)
 */
function removeLogoPreview(prefix, type) {
    const preview = document.getElementById(prefix + '-logo-' + type + '-preview');
    const img = document.getElementById(prefix + '-logo-' + type + '-img');
    const selectLabel = document.getElementById(prefix + '-logo-' + type + '-select');
    const fileInput = selectLabel.querySelector('input[type="file"]');

    preview.style.display = 'none';
    img.src = '';
    selectLabel.style.display = 'flex';
    fileInput.value = '';

    // W trybie edycji — oznacz logo do usunięcia na backendzie
    if (prefix === 'edit') {
        const removeField = document.getElementById('edit-remove-logo-' + type);
        if (removeField) removeField.value = '1';
    }
}

/**
 * Resetuj pola logo w modalu
 */
function resetLogoFields(prefix) {
    ['light', 'dark'].forEach(function(type) {
        const preview = document.getElementById(prefix + '-logo-' + type + '-preview');
        const img = document.getElementById(prefix + '-logo-' + type + '-img');
        const selectLabel = document.getElementById(prefix + '-logo-' + type + '-select');
        const fileInput = selectLabel ? selectLabel.querySelector('input[type="file"]') : null;

        if (preview) preview.style.display = 'none';
        if (img) img.src = '';
        if (selectLabel) selectLabel.style.display = 'flex';
        if (fileInput) fileInput.value = '';

        if (prefix === 'edit') {
            const removeField = document.getElementById('edit-remove-logo-' + type);
            if (removeField) removeField.value = '0';
        }
    });
}

/**
 * Open create payment method modal
 */
function openCreatePaymentMethodModal() {
    const modal = document.getElementById('createPaymentMethodModal');
    if (modal) {
        document.getElementById('createPaymentMethodForm').reset();
        resetLogoFields('create');
        modal.classList.add('active');
        togglePaymentMethodFields('create');
        document.getElementById('createName').focus();
    }
}

/**
 * Close create payment method modal
 */
function closeCreatePaymentMethodModal() {
    const modal = document.getElementById('createPaymentMethodModal');
    if (modal) {
        modal.classList.remove('active');
        document.getElementById('createPaymentMethodForm').reset();
    }
}

/**
 * Open edit payment method modal with data from method object
 */
function openEditPaymentMethodModal(methodData) {
    const modal = document.getElementById('editPaymentMethodModal');
    const form = document.getElementById('editPaymentMethodForm');

    if (modal && form) {
        form.action = '/admin/orders/payment-methods/' + methodData.id + '/edit';
        document.getElementById('editName').value = methodData.name || '';
        document.getElementById('editMethodType').value = methodData.method_type || 'other';
        document.getElementById('editRecipient').value = methodData.recipient || '';
        document.getElementById('editAccountNumber').value = methodData.account_number || '';
        document.getElementById('editCode').value = methodData.code || '';
        document.getElementById('editTransferTitle').value = methodData.transfer_title || '';
        document.getElementById('editAdditionalInfo').value = methodData.additional_info || '';
        document.getElementById('editIsActive').checked = methodData.is_active;

        // Resetuj pola logo i wypełnij istniejącymi
        resetLogoFields('edit');

        // Pokaż istniejące logo light
        if (methodData.logo_light_url) {
            var lightImg = document.getElementById('edit-logo-light-img');
            var lightPreview = document.getElementById('edit-logo-light-preview');
            var lightSelect = document.getElementById('edit-logo-light-select');
            lightImg.src = methodData.logo_light_url;
            lightPreview.style.display = 'flex';
            lightSelect.style.display = 'none';
        }

        // Pokaż istniejące logo dark
        if (methodData.logo_dark_url) {
            var darkImg = document.getElementById('edit-logo-dark-img');
            var darkPreview = document.getElementById('edit-logo-dark-preview');
            var darkSelect = document.getElementById('edit-logo-dark-select');
            darkImg.src = methodData.logo_dark_url;
            darkPreview.style.display = 'flex';
            darkSelect.style.display = 'none';
        }

        togglePaymentMethodFields('edit');
        modal.classList.add('active');
        document.getElementById('editName').focus();
    }
}

/**
 * Close edit payment method modal
 */
function closeEditPaymentMethodModal() {
    const modal = document.getElementById('editPaymentMethodModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// Delete payment method
function deletePaymentMethod(id, name) {
    if (!confirm('Czy na pewno usunąć metodę płatności "' + name + '"?')) {
        return;
    }

    const formData = new FormData();
    formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

    fetch('/admin/orders/payment-methods/' + id + '/delete', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            refreshPaymentMethodsList();
            showFlashMessage('Metoda płatności została usunięta', 'success');
        } else {
            showFlashMessage(data.error || 'Wystąpił błąd', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showFlashMessage('Wystąpił błąd podczas usuwania metody płatności', 'error');
    });
}

// Close on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeCreatePaymentMethodModal();
        closeEditPaymentMethodModal();
    }
});

// ============================================
// AJAX FORM SUBMISSIONS
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Create form submit handler
    const createForm = document.getElementById('createPaymentMethodForm');
    if (createForm) {
        createForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(createForm);

            fetch(createForm.action, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeCreatePaymentMethodModal();
                    refreshPaymentMethodsList();
                    showFlashMessage('Metoda płatności została dodana', 'success');
                } else {
                    showFlashMessage(data.error || 'Wystąpił błąd', 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showFlashMessage('Wystąpił błąd podczas dodawania metody płatności', 'error');
            });
        });
    }

    // Edit form submit handler
    const editForm = document.getElementById('editPaymentMethodForm');
    if (editForm) {
        editForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(editForm);

            fetch(editForm.action, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    closeEditPaymentMethodModal();
                    refreshPaymentMethodsList();
                    showFlashMessage('Metoda płatności została zaktualizowana', 'success');
                } else {
                    showFlashMessage(data.error || 'Wystąpił błąd', 'error');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showFlashMessage('Wystąpił błąd podczas aktualizacji metody płatności', 'error');
            });
        });
    }

    // Initialize field toggle for create modal
    togglePaymentMethodFields('create');
});

/**
 * Refresh payment methods list via AJAX
 */
function refreshPaymentMethodsList() {
    fetch('/admin/orders/payment-methods/list')
        .then(response => response.text())
        .then(html => {
            const listContainer = document.querySelector('.payment-methods-list');
            if (listContainer) {
                listContainer.innerHTML = html;
                // Re-initialize drag & drop
                setupPaymentMethodDragAndDrop();
            }
        })
        .catch(error => {
            console.error('Error refreshing list:', error);
            showFlashMessage('Nie udało się odświeżyć listy', 'error');
        });
}

/**
 * Show flash message (toast notification)
 */
function showFlashMessage(message, type) {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        alert(message);
    }
}

// ============================================
// DRAG & DROP - PAYMENT METHODS
// ============================================

let draggedPaymentMethod = null;

document.addEventListener('DOMContentLoaded', function() {
    const paymentMethodsList = document.querySelector('.payment-methods-list');
    if (!paymentMethodsList) return;

    setupPaymentMethodDragAndDrop();
});

function setupPaymentMethodDragAndDrop() {
    const items = document.querySelectorAll('.payment-method-list-item');

    items.forEach(item => {
        item.addEventListener('dragstart', handlePaymentMethodDragStart);
        item.addEventListener('dragover', handlePaymentMethodDragOver);
        item.addEventListener('drop', handlePaymentMethodDrop);
        item.addEventListener('dragend', handlePaymentMethodDragEnd);
    });
}

function handlePaymentMethodDragStart(e) {
    draggedPaymentMethod = this;
    this.style.opacity = '0.5';
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
}

function handlePaymentMethodDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';

    // Visual feedback
    this.style.borderTop = '2px solid var(--purple-300)';
    return false;
}

function handlePaymentMethodDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }

    // Remove border
    this.style.borderTop = '';

    if (draggedPaymentMethod !== this) {
        // Get all items
        const items = Array.from(document.querySelectorAll('.payment-method-list-item'));
        const draggedIndex = items.indexOf(draggedPaymentMethod);
        const targetIndex = items.indexOf(this);

        // Reorder DOM
        if (draggedIndex < targetIndex) {
            this.parentNode.insertBefore(draggedPaymentMethod, this.nextSibling);
        } else {
            this.parentNode.insertBefore(draggedPaymentMethod, this);
        }

        // Save new order to backend
        savePaymentMethodsOrder();
    }

    return false;
}

function handlePaymentMethodDragEnd(e) {
    this.style.opacity = '1';

    // Remove all borders
    const items = document.querySelectorAll('.payment-method-list-item');
    items.forEach(item => {
        item.style.borderTop = '';
    });
}

function savePaymentMethodsOrder() {
    const items = document.querySelectorAll('.payment-method-list-item');
    const order = [];

    items.forEach((item, index) => {
        order.push({
            id: parseInt(item.dataset.methodId),
            sort_order: index
        });
    });

    // Send to backend
    fetch('/admin/orders/payment-methods/reorder', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('input[name="csrf_token"]').value
        },
        body: JSON.stringify({ order: order })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log('Payment methods order saved');
        } else {
            console.error('Failed to save order');
        }
    })
    .catch(error => {
        console.error('Error saving order:', error);
    });
}
