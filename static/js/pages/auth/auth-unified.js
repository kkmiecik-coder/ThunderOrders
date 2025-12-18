/**
 * ThunderOrders - Unified Auth Page JavaScript
 * Handles multi-step forms, animations, validation, and code input
 */

document.addEventListener('DOMContentLoaded', function() {
    initFloatingLabels();
    initPasswordToggles();
    initPasswordValidation();
    initFieldValidation();
    initPhoneInput();
    initCodeInputs();
    initResendButton();
    initFormSubmission();
});

/* ============================================
   Floating Labels
   ============================================ */
function initFloatingLabels() {
    document.querySelectorAll('.auth-input').forEach(input => {
        // Check on page load if input has value
        if (input.value) {
            input.classList.add('has-value');
        }

        // Check on input
        input.addEventListener('input', function() {
            this.classList.toggle('has-value', this.value.length > 0);
        });

        // Handle autofill detection
        input.addEventListener('animationstart', function(e) {
            if (e.animationName === 'onAutoFillStart') {
                this.classList.add('has-value');
            }
        });
    });
}

/* ============================================
   Password Toggle
   ============================================ */
function initPasswordToggles() {
    document.querySelectorAll('.password-toggle-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const wrapper = this.closest('.password-toggle-wrapper');
            const input = wrapper.querySelector('.auth-input');
            const eyeOpen = this.querySelector('.eye-open');
            const eyeClosed = this.querySelector('.eye-closed');

            if (input.type === 'password') {
                input.type = 'text';
                eyeOpen.style.display = 'none';
                eyeClosed.style.display = 'block';
                this.classList.add('active');
            } else {
                input.type = 'password';
                eyeOpen.style.display = 'block';
                eyeClosed.style.display = 'none';
                this.classList.remove('active');
            }
        });
    });
}

/* ============================================
   Password Validation
   ============================================ */
function initPasswordValidation() {
    const passwordInput = document.getElementById('password-input');
    const confirmInput = document.getElementById('password-confirm-input');
    if (!passwordInput) return;

    const requirements = {
        length: document.getElementById('req-length'),
        uppercase: document.getElementById('req-uppercase'),
        lowercase: document.getElementById('req-lowercase'),
        number: document.getElementById('req-number')
    };

    // Skip if no requirements container
    if (!requirements.length) return;

    passwordInput.addEventListener('input', function() {
        const password = this.value;

        // Check all requirements
        const checks = {
            length: password.length >= 8,
            uppercase: /[A-Z]/.test(password),
            lowercase: /[a-z]/.test(password),
            number: /\d/.test(password)
        };

        // Update requirement indicators
        updateRequirement(requirements.length, checks.length);
        updateRequirement(requirements.uppercase, checks.uppercase);
        updateRequirement(requirements.lowercase, checks.lowercase);
        updateRequirement(requirements.number, checks.number);

        // Check if all requirements met for input validation state
        const allValid = checks.length && checks.uppercase && checks.lowercase && checks.number;
        setInputValidationState(passwordInput, password.length > 0 ? allValid : null);

        // Re-validate confirm password if it has a value
        if (confirmInput && confirmInput.value.length > 0) {
            validatePasswordConfirm();
        }
    });

    // Password confirm validation
    if (confirmInput) {
        confirmInput.addEventListener('input', validatePasswordConfirm);
    }

    function validatePasswordConfirm() {
        if (!confirmInput || !passwordInput) return;
        const password = passwordInput.value;
        const confirm = confirmInput.value;

        if (confirm.length === 0) {
            setInputValidationState(confirmInput, null);
            return;
        }

        setInputValidationState(confirmInput, password === confirm);
    }

    function updateRequirement(element, isValid) {
        if (!element) return;
        element.setAttribute('data-valid', isValid.toString());
    }
}

/* ============================================
   Field Validation (Name, Email)
   ============================================ */
function initFieldValidation() {
    // First name validation (min 2 chars)
    const firstNameInput = document.getElementById('first_name');
    if (firstNameInput) {
        firstNameInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (value.length === 0) {
                setInputValidationState(this, null);
            } else {
                setInputValidationState(this, value.length >= 2);
            }
        });
        // Also validate on blur
        firstNameInput.addEventListener('blur', function() {
            const value = this.value.trim();
            if (value.length > 0 && value.length < 2) {
                setInputValidationState(this, false);
            }
        });
    }

    // Last name validation (min 2 chars)
    const lastNameInput = document.getElementById('last_name');
    if (lastNameInput) {
        lastNameInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (value.length === 0) {
                setInputValidationState(this, null);
            } else {
                setInputValidationState(this, value.length >= 2);
            }
        });
        lastNameInput.addEventListener('blur', function() {
            const value = this.value.trim();
            if (value.length > 0 && value.length < 2) {
                setInputValidationState(this, false);
            }
        });
    }

    // Email validation (contains @ and .)
    // - Valid (green) shows immediately while typing
    // - Invalid (red) shows only on blur (focus loss)
    const emailInput = document.getElementById('email');
    if (emailInput) {
        // On input: only show valid state (green), never invalid
        emailInput.addEventListener('input', function() {
            const value = this.value.trim();
            if (value.length === 0) {
                setInputValidationState(this, null);
            } else {
                const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
                // Only set valid state (green), remove state if invalid (don't show red yet)
                setInputValidationState(this, isValid ? true : null);
            }
        });

        // On blur: show invalid state (red) if not valid
        emailInput.addEventListener('blur', function() {
            const value = this.value.trim();
            if (value.length === 0) {
                setInputValidationState(this, null);
            } else {
                const isValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
                setInputValidationState(this, isValid);
            }
        });
    }
}

/* ============================================
   Phone Input (digits only, min 9)
   ============================================ */
function initPhoneInput() {
    const phoneInput = document.getElementById('phone');
    if (!phoneInput) return;

    // Prevent non-digit input
    phoneInput.addEventListener('keypress', function(e) {
        // Allow: backspace, delete, tab, escape, enter
        if ([8, 9, 27, 13, 46].includes(e.keyCode)) {
            return;
        }
        // Allow: Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X
        if ((e.ctrlKey || e.metaKey) && [65, 67, 86, 88].includes(e.keyCode)) {
            return;
        }
        // Block non-digit keys
        if (!/^\d$/.test(e.key)) {
            e.preventDefault();
        }
    });

    // Clean pasted content
    phoneInput.addEventListener('paste', function(e) {
        e.preventDefault();
        const pastedText = (e.clipboardData || window.clipboardData).getData('text');
        const digitsOnly = pastedText.replace(/\D/g, '');

        // Insert at cursor position
        const start = this.selectionStart;
        const end = this.selectionEnd;
        const currentValue = this.value;
        this.value = currentValue.substring(0, start) + digitsOnly + currentValue.substring(end);

        // Trigger validation
        this.dispatchEvent(new Event('input'));
    });

    // Remove any non-digits on input (for mobile browsers that may bypass keypress)
    phoneInput.addEventListener('input', function() {
        const digitsOnly = this.value.replace(/\D/g, '');
        if (this.value !== digitsOnly) {
            const cursorPos = this.selectionStart - (this.value.length - digitsOnly.length);
            this.value = digitsOnly;
            this.setSelectionRange(cursorPos, cursorPos);
        }

        // Validate: phone is optional, but if filled must be at least 9 digits
        if (digitsOnly.length === 0) {
            setInputValidationState(this, null); // Empty is OK (optional field)
        } else {
            setInputValidationState(this, digitsOnly.length >= 9);
        }
    });
}

/* ============================================
   Input Validation State Helper
   ============================================ */
function setInputValidationState(input, isValid) {
    if (!input) return;

    // Find the input group container
    const inputGroup = input.closest('.auth-input-group');

    // Remove previous states
    input.classList.remove('input-valid', 'input-invalid');
    if (inputGroup) {
        inputGroup.classList.remove('validation-valid', 'validation-invalid');
    }

    // Apply new state
    if (isValid === true) {
        input.classList.add('input-valid');
        if (inputGroup) inputGroup.classList.add('validation-valid');
    } else if (isValid === false) {
        input.classList.add('input-invalid');
        if (inputGroup) inputGroup.classList.add('validation-invalid');
    }
    // If isValid is null, no classes are added (neutral state)
}

/* ============================================
   Code Inputs (6-digit verification)
   ============================================ */
function initCodeInputs() {
    const inputs = document.querySelectorAll('.code-input');
    const form = document.getElementById('verification-form');

    if (!inputs.length || !form) return;

    inputs.forEach((input, index) => {
        // Handle input - auto advance to next field
        input.addEventListener('input', function(e) {
            let value = e.target.value;

            // Only allow digits
            if (!/^\d*$/.test(value)) {
                e.target.value = '';
                return;
            }

            // If more than one digit (e.g., from paste), take only first
            if (value.length > 1) {
                e.target.value = value[0];
                value = value[0];
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
                    setTimeout(() => {
                        const submitBtn = form.querySelector('.auth-submit');
                        if (submitBtn) submitBtn.classList.add('loading');
                        form.submit();
                    }, 150);
                }
            }

            // Clear error state
            clearCodeError();
        });

        // Handle keydown for navigation
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Backspace') {
                if (input.value === '' && index > 0) {
                    inputs[index - 1].focus();
                    inputs[index - 1].value = '';
                }
            }

            // Arrow key navigation
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

                // Focus appropriate input
                const lastIndex = Math.min(pastedData.length, inputs.length) - 1;
                if (lastIndex < inputs.length - 1) {
                    inputs[lastIndex + 1].focus();
                } else {
                    inputs[lastIndex].focus();
                }

                // Auto-submit if 6 digits pasted
                if (pastedData.length === 6) {
                    setTimeout(() => {
                        const submitBtn = form.querySelector('.auth-submit');
                        if (submitBtn) submitBtn.classList.add('loading');
                        form.submit();
                    }, 150);
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
        setTimeout(() => inputs[0].focus(), 100);
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

/* ============================================
   Resend Code Button
   ============================================ */
function initResendButton() {
    const resendBtn = document.getElementById('resend-btn');
    if (!resendBtn) return;

    resendBtn.addEventListener('click', async function() {
        if (this.disabled) return;

        const token = this.dataset.token;
        this.disabled = true;
        const originalText = this.textContent;
        this.textContent = 'Wysylanie...';

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
                    this.textContent = originalText;
                }
            }
        } catch (error) {
            showNotification('Wystapil blad. Sprobuj ponownie.', 'error');
            this.disabled = false;
            this.textContent = originalText;
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
            resendText.innerHTML = `Wyslij kod ponownie za <span id="countdown" class="countdown">${remaining}</span>s`;
            remaining--;
            setTimeout(updateCountdown, 1000);
        } else {
            resendText.textContent = 'Nie otrzymales kodu?';
            resendBtn.disabled = false;
            resendBtn.classList.remove('disabled');
            resendBtn.textContent = 'Wyslij ponownie';
        }
    }

    updateCountdown();
}

// Make initCountdown globally available
window.initCountdown = initCountdown;

/* ============================================
   Form Submission with Loading State
   ============================================ */
function initFormSubmission() {
    const forms = document.querySelectorAll('.auth-form');

    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('.auth-submit');
            if (submitBtn && !submitBtn.classList.contains('loading')) {
                submitBtn.classList.add('loading');
            }
        });
    });
}

/* ============================================
   Utility Functions
   ============================================ */

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

    // Remove existing notifications
    document.querySelectorAll('.auth-notification').forEach(n => n.remove());

    // Create notification element
    const notification = document.createElement('div');
    notification.className = `auth-notification auth-notification-${type}`;
    notification.innerHTML = `
        <span class="notification-icon">${getNotificationIcon(type)}</span>
        <span class="notification-message">${message}</span>
        <button class="notification-close" onclick="this.parentElement.remove()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    `;

    // Add styles
    Object.assign(notification.style, {
        position: 'fixed',
        top: '20px',
        right: '20px',
        padding: '14px 20px',
        paddingRight: '48px',
        borderRadius: '12px',
        color: 'white',
        fontWeight: '500',
        fontSize: '0.9rem',
        zIndex: '9999',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        boxShadow: '0 8px 30px rgba(0, 0, 0, 0.2)',
        animation: 'slideInRight 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
        backgroundColor: type === 'success' ? '#4CAF50' :
                        type === 'error' ? '#F44336' :
                        type === 'warning' ? '#FF9800' : '#2196F3'
    });

    document.body.appendChild(notification);

    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-in forwards';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

/**
 * Get notification icon based on type
 */
function getNotificationIcon(type) {
    const icons = {
        success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="m9 12 2 2 4-4"></path></svg>',
        error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
        warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
        info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
    };
    return icons[type] || icons.info;
}

// Add notification animation styles
if (!document.getElementById('auth-notification-styles')) {
    const style = document.createElement('style');
    style.id = 'auth-notification-styles';
    style.textContent = `
        @keyframes slideInRight {
            from { transform: translateX(120%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOutRight {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(120%); opacity: 0; }
        }
        .notification-close {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: white;
            opacity: 0.7;
            cursor: pointer;
            padding: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: opacity 0.2s ease;
        }
        .notification-close:hover {
            opacity: 1;
        }
        .notification-icon {
            display: flex;
            align-items: center;
        }

        @media (max-width: 480px) {
            .auth-notification {
                left: 16px !important;
                right: 16px !important;
                top: 16px !important;
            }
        }
    `;
    document.head.appendChild(style);
}
