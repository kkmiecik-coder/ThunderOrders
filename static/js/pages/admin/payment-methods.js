// ============================================
// PAYMENT METHODS SETTINGS FUNCTIONS
// ============================================

/**
 * Open create payment method modal
 */
function openCreatePaymentMethodModal() {
    const modal = document.getElementById('createPaymentMethodModal');
    if (modal) {
        // Reset form
        document.getElementById('createPaymentMethodForm').reset();
        modal.classList.add('active');
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
 * Open edit payment method modal
 */
function openEditPaymentMethodModal(id, name, details, isActive) {
    const modal = document.getElementById('editPaymentMethodModal');
    const form = document.getElementById('editPaymentMethodForm');

    if (modal && form) {
        form.action = `/admin/orders/payment-methods/${id}/edit`;
        document.getElementById('editName').value = name;
        document.getElementById('editDetails').value = details;
        document.getElementById('editIsActive').checked = isActive;

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
    if (!confirm(`Czy na pewno usunąć metodę płatności "${name}"?`)) {
        return;
    }

    const formData = new FormData();
    formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

    fetch(`/admin/orders/payment-methods/${id}/delete`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Refresh payment methods list
            refreshPaymentMethodsList();

            // Show success message
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
                    // Close modal
                    closeCreatePaymentMethodModal();

                    // Refresh payment methods list
                    refreshPaymentMethodsList();

                    // Show success message
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
                    // Close modal
                    closeEditPaymentMethodModal();

                    // Refresh payment methods list
                    refreshPaymentMethodsList();

                    // Show success message
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
    // Jeśli istnieje globalny system toast, użyj go
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback - prosty alert
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

    // Dodaj event listenery do wszystkich elementów
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
