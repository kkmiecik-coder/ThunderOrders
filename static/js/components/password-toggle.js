/**
 * Password Toggle Component
 * Adds show/hide functionality to password inputs
 * Supports browser autofill (Safari Keychain, Chrome, etc.)
 *
 * NOTE: Safari security prevents reading autofilled password values via JavaScript.
 * When toggling type from 'password' to 'text', Safari clears the autofilled value.
 * This is a known Safari security feature and cannot be bypassed.
 *
 * Workaround: We show a warning to the user when they try to reveal an autofilled password.
 */

document.addEventListener('DOMContentLoaded', function() {
    initPasswordToggles();
    initAutofillDetection();
});

/**
 * Initialize password toggle buttons for all password inputs
 */
function initPasswordToggles() {
    // If wrappers already exist, just init the toggle behavior
    const existingToggles = document.querySelectorAll('.password-toggle-btn');
    existingToggles.forEach(btn => {
        // Remove old listeners to avoid duplicates
        btn.removeEventListener('click', handleToggleClick);
        btn.addEventListener('click', handleToggleClick);
    });

    // For inputs without wrapper, add it dynamically
    document.querySelectorAll('input[type="password"]:not(.toggle-initialized)').forEach(input => {
        // Skip if parent is already a wrapper
        if (input.parentElement.classList.contains('password-toggle-wrapper')) {
            input.classList.add('toggle-initialized');
            return;
        }

        // Create wrapper if needed and input is marked for toggle
        if (input.classList.contains('with-toggle')) {
            wrapPasswordInput(input);
        }
    });
}

/**
 * Initialize autofill detection for all auth inputs
 * Safari and other browsers don't always fire 'input' event on autofill
 */
function initAutofillDetection() {
    const authInputs = document.querySelectorAll('.auth-input');

    authInputs.forEach(input => {
        // Check immediately for autofilled values
        checkAndUpdateLabel(input);

        // Mark input as potentially autofilled for later reference
        input.dataset.wasAutofilled = 'false';

        // Use animation event to detect autofill (works in most browsers)
        input.addEventListener('animationstart', function(e) {
            if (e.animationName === 'onAutoFillStart' || e.animationName.includes('autofill')) {
                input.dataset.wasAutofilled = 'true';
                checkAndUpdateLabel(input);
            }
        });

        // Polling fallback for Safari - check periodically for first few seconds
        let checkCount = 0;
        const maxChecks = 20; // Check for 2 seconds
        const checkInterval = setInterval(function() {
            checkAndUpdateLabel(input);

            // Detect autofill by checking if the input has the autofill pseudo-class
            try {
                if (input.matches(':-webkit-autofill')) {
                    input.dataset.wasAutofilled = 'true';
                }
            } catch (e) {}

            checkCount++;
            if (checkCount >= maxChecks) {
                clearInterval(checkInterval);
            }
        }, 100);

        // Also check on focus/blur
        input.addEventListener('focus', function() {
            checkAndUpdateLabel(input);
        });

        input.addEventListener('blur', function() {
            checkAndUpdateLabel(input);
        });

        // Check on any change event
        input.addEventListener('change', function() {
            // User manually typed - no longer consider it autofilled
            input.dataset.wasAutofilled = 'false';
            checkAndUpdateLabel(input);
        });

        // On manual input, mark as not autofilled
        input.addEventListener('input', function() {
            input.dataset.wasAutofilled = 'false';
        });
    });

    // Global check after a short delay (covers most autofill scenarios)
    setTimeout(function() {
        authInputs.forEach(input => checkAndUpdateLabel(input));
    }, 100);

    setTimeout(function() {
        authInputs.forEach(input => checkAndUpdateLabel(input));
    }, 500);

    setTimeout(function() {
        authInputs.forEach(input => checkAndUpdateLabel(input));
    }, 1000);
}

/**
 * Check if input has value and update the floating label accordingly
 * @param {HTMLInputElement} input - The input element to check
 */
function checkAndUpdateLabel(input) {
    // Check if input has value (works for autofill)
    const hasValue = input.value && input.value.length > 0;

    // Also check for autofill pseudo-class (Chrome/Safari)
    let isAutofilled = false;
    try {
        isAutofilled = input.matches(':-webkit-autofill');
    } catch (e) {
        // Ignore if browser doesn't support this pseudo-class
    }

    if (hasValue || isAutofilled) {
        input.classList.add('has-value');
    } else {
        input.classList.remove('has-value');
    }
}

/**
 * Wrap password input with toggle button
 * @param {HTMLInputElement} input - Password input element
 */
function wrapPasswordInput(input) {
    const wrapper = document.createElement('div');
    wrapper.className = 'password-toggle-wrapper';

    // Insert wrapper before input
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    // Create toggle button
    const toggleBtn = document.createElement('button');
    toggleBtn.type = 'button';
    toggleBtn.className = 'password-toggle-btn';
    toggleBtn.setAttribute('tabindex', '-1');
    toggleBtn.innerHTML = getEyeIcon(false);
    toggleBtn.addEventListener('click', handleToggleClick);

    wrapper.appendChild(toggleBtn);
    input.classList.add('toggle-initialized');
}

/**
 * Handle toggle button click
 * @param {Event} e - Click event
 */
function handleToggleClick(e) {
    e.preventDefault();
    e.stopPropagation();

    const btn = e.currentTarget;
    const wrapper = btn.closest('.password-toggle-wrapper');
    const input = wrapper.querySelector('input');

    if (!input) return;

    // Check if this was autofilled by Safari
    const wasAutofilled = input.dataset.wasAutofilled === 'true';
    let isCurrentlyAutofilled = false;
    try {
        isCurrentlyAutofilled = input.matches(':-webkit-autofill');
    } catch (e) {}

    // Store current value before type change
    const currentValue = input.value;
    const currentType = input.type;

    if (currentType === 'password') {
        // Trying to show password
        input.type = 'text';

        // Check if Safari cleared the autofill value
        if ((wasAutofilled || isCurrentlyAutofilled) && input.value === '' && currentValue !== '') {
            // Safari cleared the autofill - restore type and show message
            input.type = 'password';

            // Show toast notification if available
            if (typeof showToast === 'function') {
                showToast('Ze względów bezpieczeństwa Safari nie pozwala na odkrycie automatycznie uzupełnionego hasła. Wpisz hasło ręcznie, aby móc je zobaczyć.', 'warning');
            } else {
                // Fallback alert
                alert('Ze względów bezpieczeństwa Safari nie pozwala na odkrycie automatycznie uzupełnionego hasła. Wpisz hasło ręcznie, aby móc je zobaczyć.');
            }
            return;
        }

        btn.innerHTML = getEyeIcon(true);
        btn.classList.add('active');
    } else {
        // Hide password
        input.type = 'password';
        btn.innerHTML = getEyeIcon(false);
        btn.classList.remove('active');
    }

    // Update label state
    checkAndUpdateLabel(input);

    // Keep focus on input
    input.focus();
}

/**
 * Get eye icon SVG
 * @param {boolean} visible - Whether password is visible (eye-off) or hidden (eye)
 * @returns {string} SVG icon HTML
 */
function getEyeIcon(visible) {
    if (visible) {
        // Eye-off icon (password is visible, click to hide)
        return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
            <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>`;
    } else {
        // Eye icon (password is hidden, click to show)
        return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
            <circle cx="12" cy="12" r="3"></circle>
        </svg>`;
    }
}
