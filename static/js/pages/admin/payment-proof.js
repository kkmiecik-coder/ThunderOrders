// ============================================
// ADMIN PAYMENT PROOF FUNCTIONS
// ============================================

/**
 * Get CSRF token from the page
 */
function getCSRFToken() {
    return document.querySelector('input[name="csrf_token"]')?.value ||
           document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

/**
 * Approve payment proof
 * @param {number} orderId - Order ID
 * @param {string} proofType - 'order' or 'shipping'
 */
async function approvePaymentProof(orderId, proofType = 'order') {
    const proofLabel = proofType === 'order' ? 'za zamówienie' : 'za dostawę';
    const confirmMessage = proofType === 'order'
        ? 'Czy na pewno zaakceptować dowód wpłaty za zamówienie?\n\nKwota wpłaty zostanie automatycznie ustawiona na wartość zamówienia (bez wysyłki).'
        : 'Czy na pewno zaakceptować dowód wpłaty za dostawę?';

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const response = await fetch(`/admin/orders/${orderId}/approve-payment-proof`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ proof_type: proofType })
        });

        if (response.ok) {
            window.location.reload();
        } else {
            alert(`Błąd podczas akceptacji dowodu wpłaty ${proofLabel}`);
        }
    } catch (error) {
        console.error('Error:', error);
        alert(`Błąd podczas akceptacji dowodu wpłaty ${proofLabel}`);
    }
}

/**
 * Open reject payment proof modal
 * @param {number} orderId - Order ID
 * @param {string} proofType - 'order' or 'shipping'
 */
function openRejectPaymentProofModal(orderId, proofType = 'order') {
    const modal = document.getElementById('rejectPaymentProofModal');
    const form = document.getElementById('rejectPaymentProofForm');

    if (modal && form) {
        form.dataset.orderId = orderId;
        form.dataset.proofType = proofType;
        modal.classList.add('active');
        document.getElementById('rejectionReason').focus();
    }
}

/**
 * Close reject payment proof modal
 */
function closeRejectPaymentProofModal() {
    const modal = document.getElementById('rejectPaymentProofModal');
    if (modal) {
        modal.classList.remove('active');
        document.getElementById('rejectPaymentProofForm').reset();
    }
}

// Form submit handler
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('rejectPaymentProofForm');
    if (form) {
        form.addEventListener('submit', async function(e) {
            e.preventDefault();

            const orderId = form.dataset.orderId;
            const proofType = form.dataset.proofType || 'order';
            const rejectionReason = document.getElementById('rejectionReason').value.trim();

            if (!rejectionReason) {
                alert('Podaj powód odrzucenia');
                return;
            }

            try {
                const response = await fetch(`/admin/orders/${orderId}/reject-payment-proof`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        rejection_reason: rejectionReason,
                        proof_type: proofType
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    closeRejectPaymentProofModal();
                    window.location.reload();
                } else {
                    alert(data.error || 'Błąd podczas odrzucania dowodu wpłaty');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Błąd podczas odrzucania dowodu wpłaty');
            }
        });
    }
});

// Close on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeRejectPaymentProofModal();
        closeRejectShippingPaymentProofModal();
    }
});

// ============================================
// SHIPPING PAYMENT PROOF FUNCTIONS (ShippingRequest)
// ============================================

/**
 * Approve shipping payment proof (for ShippingRequest)
 * @param {number} shippingRequestId - ShippingRequest ID
 */
async function approveShippingPaymentProof(shippingRequestId) {
    if (!confirm('Czy na pewno zaakceptować dowód wpłaty za wysyłkę?\n\nAkceptacja dotyczy całego zlecenia wysyłki i wszystkich zamówień w nim zawartych.')) {
        return;
    }

    try {
        const response = await fetch(`/admin/shipping-requests/${shippingRequestId}/approve-payment-proof`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json();
            alert(data.error || 'Błąd podczas akceptacji dowodu wpłaty za wysyłkę');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Błąd podczas akceptacji dowodu wpłaty za wysyłkę');
    }
}

/**
 * Open reject shipping payment proof modal
 * @param {number} shippingRequestId - ShippingRequest ID
 */
function openRejectShippingPaymentProofModal(shippingRequestId) {
    const modal = document.getElementById('rejectShippingPaymentProofModal');
    const form = document.getElementById('rejectShippingPaymentProofForm');

    if (modal && form) {
        form.dataset.shippingRequestId = shippingRequestId;
        modal.classList.add('active');
        document.getElementById('shippingRejectionReason').focus();
    }
}

/**
 * Close reject shipping payment proof modal
 */
function closeRejectShippingPaymentProofModal() {
    const modal = document.getElementById('rejectShippingPaymentProofModal');
    if (modal) {
        modal.classList.remove('active');
        const form = document.getElementById('rejectShippingPaymentProofForm');
        if (form) form.reset();
    }
}

// Shipping payment proof form submit handler
document.addEventListener('DOMContentLoaded', function() {
    const shippingForm = document.getElementById('rejectShippingPaymentProofForm');
    if (shippingForm) {
        shippingForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const shippingRequestId = shippingForm.dataset.shippingRequestId;
            const rejectionReason = document.getElementById('shippingRejectionReason').value.trim();

            if (!rejectionReason) {
                alert('Podaj powód odrzucenia');
                return;
            }

            try {
                const response = await fetch(`/admin/shipping-requests/${shippingRequestId}/reject-payment-proof`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify({
                        rejection_reason: rejectionReason
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    closeRejectShippingPaymentProofModal();
                    window.location.reload();
                } else {
                    alert(data.error || 'Błąd podczas odrzucania dowodu wpłaty za wysyłkę');
                }
            } catch (error) {
                console.error('Error:', error);
                alert('Błąd podczas odrzucania dowodu wpłaty za wysyłkę');
            }
        });
    }
});
