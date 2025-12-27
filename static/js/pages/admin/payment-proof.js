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
 */
async function approvePaymentProof(orderId) {
    if (!confirm('Czy na pewno zaakceptować dowód wpłaty?\n\nKwota wpłaty zostanie automatycznie ustawiona na wartość zamówienia (bez wysyłki).')) {
        return;
    }

    try {
        const response = await fetch(`/admin/orders/${orderId}/approve-payment-proof`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        });

        if (response.ok) {
            window.location.reload();
        } else {
            alert('Błąd podczas akceptacji dowodu wpłaty');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Błąd podczas akceptacji dowodu wpłaty');
    }
}

/**
 * Open reject payment proof modal
 */
function openRejectPaymentProofModal(orderId) {
    const modal = document.getElementById('rejectPaymentProofModal');
    const form = document.getElementById('rejectPaymentProofForm');

    if (modal && form) {
        form.dataset.orderId = orderId;
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
                    body: JSON.stringify({ rejection_reason: rejectionReason })
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
    }
});
