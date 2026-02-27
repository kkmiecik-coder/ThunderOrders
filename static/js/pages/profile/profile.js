/**
 * Profile Page - Change Password (AJAX inline validation)
 */
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('changePasswordForm');
    if (!form) return;

    const fields = ['current_password', 'new_password', 'confirm_password'];
    const submitBtn = document.getElementById('changePasswordBtn');
    const newPasswordInput = document.getElementById('new_password');
    const confirmPasswordInput = document.getElementById('confirm_password');

    // Password requirements elements
    const requirements = {
        length: document.getElementById('req-length'),
        uppercase: document.getElementById('req-uppercase'),
        lowercase: document.getElementById('req-lowercase'),
        number: document.getElementById('req-number')
    };

    // Track if all password requirements are met
    var allRequirementsMet = false;

    // Live password requirements validation
    if (newPasswordInput && requirements.length) {
        newPasswordInput.addEventListener('input', function() {
            var password = this.value;

            var checks = {
                length: password.length >= 8,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /\d/.test(password)
            };

            updateRequirement(requirements.length, checks.length);
            updateRequirement(requirements.uppercase, checks.uppercase);
            updateRequirement(requirements.lowercase, checks.lowercase);
            updateRequirement(requirements.number, checks.number);

            allRequirementsMet = checks.length && checks.uppercase && checks.lowercase && checks.number;

            // Clear field error when typing
            clearFieldError('new_password');

            // Re-validate confirm if it has a value
            if (confirmPasswordInput && confirmPasswordInput.value.length > 0) {
                validateConfirmMatch();
            }
        });
    }

    // Confirm password live match check
    if (confirmPasswordInput) {
        confirmPasswordInput.addEventListener('input', function() {
            clearFieldError('confirm_password');
            if (this.value.length > 0) {
                validateConfirmMatch();
            }
        });
    }

    function validateConfirmMatch() {
        if (!confirmPasswordInput || !newPasswordInput) return;
        var match = newPasswordInput.value === confirmPasswordInput.value;
        if (!match && confirmPasswordInput.value.length > 0) {
            showFieldError('confirm_password', 'Hasła nie są identyczne.');
        } else {
            clearFieldError('confirm_password');
        }
    }

    // Clear error when user starts typing (current password)
    var currentPasswordInput = document.getElementById('current_password');
    if (currentPasswordInput) {
        currentPasswordInput.addEventListener('input', function() {
            clearFieldError('current_password');
        });
    }

    function updateRequirement(element, isValid) {
        if (!element) return;
        element.setAttribute('data-valid', isValid.toString());
    }

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        clearAllErrors();

        // Client-side validation
        var currentPassword = document.getElementById('current_password').value;
        var newPassword = newPasswordInput.value;
        var confirmPassword = confirmPasswordInput.value;
        var hasClientErrors = false;

        if (!currentPassword) {
            showFieldError('current_password', 'Obecne hasło jest wymagane.');
            hasClientErrors = true;
        }

        if (!newPassword) {
            showFieldError('new_password', 'Nowe hasło jest wymagane.');
            hasClientErrors = true;
        } else if (!allRequirementsMet) {
            showFieldError('new_password', 'Nowe hasło nie spełnia wszystkich wymagań.');
            hasClientErrors = true;
        }

        if (newPassword && newPassword !== confirmPassword) {
            showFieldError('confirm_password', 'Hasła nie są identyczne.');
            hasClientErrors = true;
        }

        if (hasClientErrors) return;

        // Disable button during request
        submitBtn.disabled = true;
        submitBtn.textContent = 'Zmienianie...';

        var csrfToken = form.querySelector('[name="csrf_token"]').value;

        fetch(form.action, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': csrfToken
            },
            body: new FormData(form)
        })
        .then(function(response) {
            return response.json().then(function(data) {
                return { ok: response.ok, data: data };
            });
        })
        .then(function(result) {
            if (result.data.success) {
                // Reset form and requirements
                form.reset();
                allRequirementsMet = false;
                updateRequirement(requirements.length, false);
                updateRequirement(requirements.uppercase, false);
                updateRequirement(requirements.lowercase, false);
                updateRequirement(requirements.number, false);

                if (typeof window.showToast === 'function') {
                    window.showToast(result.data.message, 'success');
                }
            } else if (result.data.field_errors) {
                // Show per-field errors
                Object.keys(result.data.field_errors).forEach(function(field) {
                    showFieldError(field, result.data.field_errors[field]);
                });
            } else if (result.data.message) {
                if (typeof window.showToast === 'function') {
                    window.showToast(result.data.message, 'error');
                }
            }
        })
        .catch(function() {
            if (typeof window.showToast === 'function') {
                window.showToast('Wystąpił błąd połączenia.', 'error');
            }
        })
        .finally(function() {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Zmień hasło';
        });
    });

    function showFieldError(fieldName, message) {
        var errorSpan = document.getElementById('error-' + fieldName);
        var input = document.getElementById(fieldName);
        if (errorSpan) {
            errorSpan.textContent = message;
            errorSpan.classList.add('visible');
        }
        if (input) {
            input.classList.add('input-error');
        }
    }

    function clearFieldError(fieldName) {
        var errorSpan = document.getElementById('error-' + fieldName);
        var input = document.getElementById(fieldName);
        if (errorSpan) {
            errorSpan.textContent = '';
            errorSpan.classList.remove('visible');
        }
        if (input) {
            input.classList.remove('input-error');
        }
    }

    function clearAllErrors() {
        fields.forEach(function(name) {
            clearFieldError(name);
        });
    }
});
