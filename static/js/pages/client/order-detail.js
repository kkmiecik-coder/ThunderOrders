/**
 * Client Order Detail - Enhanced Interactions
 */

document.addEventListener('DOMContentLoaded', function() {
    // Auto-scroll timeline to bottom (newest messages first, but scroll to see form)
    const timeline = document.getElementById('timeline');
    if (timeline && timeline.children.length > 0) {
        // Timeline is already in reverse order (newest first), no need to scroll
    }

    // Handle comment form submission
    const commentForm = document.querySelector('.comment-form');
    if (commentForm) {
        commentForm.addEventListener('htmx:afterRequest', function(event) {
            if (event.detail.successful) {
                // Clear the textarea after successful submission
                const textarea = commentForm.querySelector('textarea');
                if (textarea) {
                    textarea.value = '';
                }

                // Show success message
                showToast('Wiadomość została wysłana', 'success');
            } else {
                showToast('Wystąpił błąd podczas wysyłania wiadomości', 'error');
            }
        });
    }

    // Add smooth scroll to timeline when new message is added
    if (timeline) {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    // Scroll to top to see new message (since it's prepended)
                    timeline.scrollTo({ top: 0, behavior: 'smooth' });
                }
            });
        });

        observer.observe(timeline, { childList: true });
    }

    // Enhance back link with keyboard shortcut
    document.addEventListener('keydown', function(e) {
        // Alt + Left Arrow = Go back
        if (e.altKey && e.key === 'ArrowLeft') {
            const backLink = document.querySelector('.back-link');
            if (backLink) {
                window.location.href = backLink.href;
            }
        }
    });

    // Add loading state to tracking button
    const trackingBtn = document.querySelector('.tracking-info .btn-primary');
    if (trackingBtn) {
        trackingBtn.addEventListener('click', function() {
            this.style.opacity = '0.6';
        });
    }
});

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Check if toast system exists
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback to console
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}

// ============================================
// PAYMENT PROOF - CLIENT FUNCTIONS
// ============================================

/**
 * Open payment proof upload modal
 */
function openPaymentProofModal() {
    const modal = document.getElementById('paymentProofModal');
    if (modal) {
        // Get order number from the page
        const orderNumberElement = document.querySelector('.payment-info-box code');
        const orderNumber = orderNumberElement ? orderNumberElement.textContent.trim() : '';

        modal.classList.add('active');
        loadPaymentMethodsInfo(orderNumber);
    }
}

/**
 * Close payment proof upload modal
 */
function closePaymentProofModal() {
    const modal = document.getElementById('paymentProofModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Load active payment methods from API
 * @param {string} orderNumber - The order number to replace placeholder with
 */
async function loadPaymentMethodsInfo(orderNumber = '') {
    const container = document.getElementById('paymentMethodsInfo');
    if (!container) return;

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
                        onclick="selectPaymentMethod(${index}, ${methods.length})"
                        data-method-index="${index}">
                    ${method.name}
                </button>
            `;
        });

        html += '</div>';
        html += '<div class="payment-method-details-container">';

        methods.forEach((method, index) => {
            // Replace [NUMER ZAMÓWIENIA] placeholder with actual order number
            let detailsText = method.details;
            if (orderNumber) {
                detailsText = detailsText.replace(/\[NUMER ZAMÓWIENIA\]/g, orderNumber);
            }

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
function selectPaymentMethod(index, totalMethods) {
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
        const methodName = selectedButton.textContent.trim();
        const hiddenInput = document.getElementById('selectedPaymentMethodName');
        if (hiddenInput) {
            hiddenInput.value = methodName;
        }
    }
    if (selectedDetails) selectedDetails.classList.add('active');
}

// Auto-open modal jeśli URL ma ?action=upload_payment
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('action') === 'upload_payment') {
        openPaymentProofModal();
    }
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closePaymentProofModal();
    }
});
