/**
 * Verification Code Page JavaScript
 * Handles 6-digit code input, auto-focus, paste handling, and resend functionality
 */

document.addEventListener('DOMContentLoaded', function() {
    initCodeInputs();
    initResendButton();
});

/**
 * Initialize code input fields with auto-focus and navigation
 */
function initCodeInputs() {
    const inputs = document.querySelectorAll('.code-input');
    const form = document.getElementById('verification-form');

    inputs.forEach((input, index) => {
        // Handle input - auto advance to next field
        input.addEventListener('input', function(e) {
            const value = e.target.value;

            // Only allow digits
            if (!/^\d*$/.test(value)) {
                e.target.value = '';
                return;
            }

            // If digit entered, move to next input
            if (value.length === 1 && index < inputs.length - 1) {
                inputs[index + 1].focus();
            }

            // Auto-submit when all 6 digits are entered
            if (index === inputs.length - 1 && value.length === 1) {
                const allFilled = Array.from(inputs).every(inp => inp.value.length === 1);
                if (allFilled) {
                    // Small delay to show the last digit before submit
                    setTimeout(() => form.submit(), 100);
                }
            }

            // Clear error state
            clearCodeError();
        });

        // Handle backspace - go to previous field
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Backspace') {
                if (input.value === '' && index > 0) {
                    inputs[index - 1].focus();
                    inputs[index - 1].value = '';
                }
            }

            // Handle arrow keys
            if (e.key === 'ArrowLeft' && index > 0) {
                e.preventDefault();
                inputs[index - 1].focus();
            }
            if (e.key === 'ArrowRight' && index < inputs.length - 1) {
                e.preventDefault();
                inputs[index + 1].focus();
            }
        });

        // Handle paste - distribute digits across inputs
        input.addEventListener('paste', function(e) {
            e.preventDefault();
            const pastedData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);

            if (pastedData.length > 0) {
                pastedData.split('').forEach((digit, i) => {
                    if (inputs[i]) {
                        inputs[i].value = digit;
                    }
                });

                // Focus last filled input or the next empty one
                const lastIndex = Math.min(pastedData.length, inputs.length) - 1;
                if (lastIndex < inputs.length - 1) {
                    inputs[lastIndex + 1].focus();
                } else {
                    inputs[lastIndex].focus();
                }

                // Auto-submit if 6 digits pasted
                if (pastedData.length === 6) {
                    setTimeout(() => form.submit(), 100);
                }
            }
        });

        // Select all text on focus
        input.addEventListener('focus', function() {
            this.select();
        });
    });

    // Focus first input on page load
    if (inputs[0]) {
        inputs[0].focus();
    }
}

/**
 * Clear code input error state
 */
function clearCodeError() {
    const errorDiv = document.querySelector('.code-error');
    if (errorDiv) {
        errorDiv.style.display = 'none';
    }
}

/**
 * Initialize resend button with AJAX functionality
 */
function initResendButton() {
    const resendBtn = document.getElementById('resend-btn');
    if (!resendBtn) return;

    resendBtn.addEventListener('click', async function() {
        if (this.disabled) return;

        const token = this.dataset.token;
        this.disabled = true;
        this.textContent = 'Wysyłanie...';

        try {
            const response = await fetch(`/auth/resend-code/${token}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                }
            });

            const data = await response.json();

            if (data.success) {
                showNotification(data.message, 'success');
                initCountdown(data.seconds_remaining);
            } else {
                showNotification(data.error, 'error');

                if (data.seconds_remaining) {
                    initCountdown(data.seconds_remaining);
                } else {
                    this.disabled = false;
                    this.textContent = 'Wyślij ponownie';
                }
            }
        } catch (error) {
            showNotification('Wystąpił błąd. Spróbuj ponownie.', 'error');
            this.disabled = false;
            this.textContent = 'Wyślij ponownie';
        }
    });
}

/**
 * Initialize countdown timer for resend button
 * @param {number} seconds - Starting seconds for countdown
 */
function initCountdown(seconds) {
    const resendBtn = document.getElementById('resend-btn');
    const resendText = document.getElementById('resend-text');

    if (!resendBtn || !resendText) return;

    resendBtn.disabled = true;
    resendBtn.classList.add('disabled');

    let remaining = seconds;

    function updateCountdown() {
        if (remaining > 0) {
            resendText.innerHTML = `Wyślij kod ponownie za <span id="countdown">${remaining}</span>s`;
            remaining--;
            setTimeout(updateCountdown, 1000);
        } else {
            resendText.textContent = 'Nie otrzymałeś kodu?';
            resendBtn.disabled = false;
            resendBtn.classList.remove('disabled');
            resendBtn.textContent = 'Wyślij ponownie';
        }
    }

    updateCountdown();
}

/**
 * Get CSRF token from meta tag or form
 * @returns {string} CSRF token
 */
function getCSRFToken() {
    // Try meta tag first
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }

    // Try hidden input in form
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    if (csrfInput) {
        return csrfInput.value;
    }

    return '';
}

/**
 * Show notification toast
 * @param {string} message - Message to display
 * @param {string} type - Type of notification (success, error, warning, info)
 */
function showNotification(message, type = 'info') {
    // Check if global toast function exists
    if (typeof showToast === 'function') {
        showToast(message, type);
        return;
    }

    // Fallback: Create simple notification
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;

    // Style the notification
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '12px 24px',
        borderRadius: '8px',
        color: 'white',
        fontWeight: '500',
        zIndex: '9999',
        animation: 'slideIn 0.3s ease-out',
        backgroundColor: type === 'success' ? '#4CAF50' :
                        type === 'error' ? '#F44336' :
                        type === 'warning' ? '#FFC107' : '#2196F3'
    });

    document.body.appendChild(notification);

    // Remove after 4 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// Add animation keyframes if not already present
if (!document.getElementById('notification-styles')) {
    const style = document.createElement('style');
    style.id = 'notification-styles';
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
    `;
    document.head.appendChild(style);
}
