/**
 * Exclusive Pages - Tab Switching & Settings Logic
 * Handles horizontal tab navigation and custom select dropdowns
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeExclusiveTabs();
    initializeSettingsTabs(); // Left sidebar tabs in settings panel
    initializeCustomSelects();
    initializeAutoIncreaseForm();
    initializeDeleteForm();
});

/**
 * Initialize tab switching functionality
 */
function initializeExclusiveTabs() {
    const tabButtons = document.querySelectorAll('.exclusive-tab-button');
    const tabPanels = document.querySelectorAll('.exclusive-tab-panel');

    if (tabButtons.length === 0) return;

    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and panels
            tabButtons.forEach(btn => btn.classList.remove('exclusive-tab-active'));
            tabPanels.forEach(panel => panel.classList.remove('exclusive-tab-active'));

            // Add active class to clicked button and corresponding panel
            this.classList.add('exclusive-tab-active');
            const targetPanel = document.getElementById(targetTab);
            if (targetPanel) {
                targetPanel.classList.add('exclusive-tab-active');
            }

            // Save active tab to localStorage
            localStorage.setItem('exclusiveActiveTab', targetTab);
        });
    });

    // Restore previously selected tab
    const savedTab = localStorage.getItem('exclusiveActiveTab');
    if (savedTab) {
        const button = document.querySelector(`.exclusive-tab-button[data-tab="${savedTab}"]`);
        if (button) {
            button.click();
        }
    }
}

/**
 * Initialize settings tabs (left sidebar in settings panel)
 */
function initializeSettingsTabs() {
    const settingsTabButtons = document.querySelectorAll('.settings-tab');
    const settingsTabPanels = document.querySelectorAll('.tab-panel');

    if (settingsTabButtons.length === 0) return;

    settingsTabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and panels
            settingsTabButtons.forEach(btn => btn.classList.remove('active'));
            settingsTabPanels.forEach(panel => panel.classList.remove('active'));

            // Add active class to clicked button and corresponding panel
            this.classList.add('active');
            const targetPanel = document.getElementById(`tab-${targetTab}`);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });
}

/**
 * Initialize custom select dropdowns for status selection
 */
function initializeCustomSelects() {
    const customSelects = document.querySelectorAll('.custom-select');

    customSelects.forEach(select => {
        const trigger = select.querySelector('.custom-select-trigger');
        const dropdown = select.querySelector('.custom-select-dropdown');
        const options = select.querySelectorAll('.custom-select-option');
        const hiddenInput = select.parentElement.querySelector('input[type="hidden"]');

        if (!trigger || !dropdown) return;

        // Toggle dropdown
        trigger.addEventListener('click', function(e) {
            e.stopPropagation();

            // Close other dropdowns
            document.querySelectorAll('.custom-select-dropdown.active').forEach(otherDropdown => {
                if (otherDropdown !== dropdown) {
                    otherDropdown.classList.remove('active');
                }
            });

            dropdown.classList.toggle('active');
        });

        // Handle option selection
        options.forEach(option => {
            option.addEventListener('click', function(e) {
                e.stopPropagation();
                const value = this.getAttribute('data-value');
                const label = this.innerHTML;

                // Update trigger display
                const valueSpan = trigger.querySelector('.custom-select-value');
                if (valueSpan) {
                    valueSpan.innerHTML = label;
                }

                // Update hidden input
                if (hiddenInput) {
                    hiddenInput.value = value;
                }

                // Close dropdown
                dropdown.classList.remove('active');
            });
        });
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.custom-select')) {
            document.querySelectorAll('.custom-select-dropdown.active').forEach(dropdown => {
                dropdown.classList.remove('active');
            });
        }
    });

    // Close dropdowns on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.custom-select-dropdown.active').forEach(dropdown => {
                dropdown.classList.remove('active');
            });
        }
    });
}

/**
 * Initialize Auto-Increase Form Logic
 * Enable save button only when changes are detected
 */
function initializeAutoIncreaseForm() {
    const form = document.getElementById('auto-increase-form');
    if (!form) return;

    const saveBtn = document.getElementById('save_auto_increase_btn');
    const enabledCheckbox = document.getElementById('auto_increase_enabled');
    const productThreshold = document.getElementById('auto_increase_product_threshold');
    const setThreshold = document.getElementById('auto_increase_set_threshold');
    const amount = document.getElementById('auto_increase_amount');

    // Store initial values
    const initialValues = {
        enabled: enabledCheckbox.checked,
        product_threshold: productThreshold.value,
        set_threshold: setThreshold.value,
        amount: amount.value
    };

    // Function to check for changes
    function checkForChanges() {
        const currentValues = {
            enabled: enabledCheckbox.checked,
            product_threshold: productThreshold.value,
            set_threshold: setThreshold.value,
            amount: amount.value
        };

        const hasChanges = JSON.stringify(initialValues) !== JSON.stringify(currentValues);
        saveBtn.disabled = !hasChanges;
    }

    // Add event listeners
    enabledCheckbox.addEventListener('change', checkForChanges);
    productThreshold.addEventListener('input', checkForChanges);
    setThreshold.addEventListener('input', checkForChanges);
    amount.addEventListener('input', checkForChanges);

    // Handle form submission
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        // Disable button during submission
        saveBtn.disabled = true;
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner"></span> Zapisywanie...';

        // Prepare form data
        const formData = new FormData();
        formData.append('csrf_token', form.querySelector('input[name="csrf_token"]').value);
        formData.append('auto_increase_enabled', enabledCheckbox.checked ? 'true' : 'false');
        formData.append('auto_increase_product_threshold', productThreshold.value);
        formData.append('auto_increase_set_threshold', setThreshold.value);
        formData.append('auto_increase_amount', amount.value);

        // Submit via AJAX
        fetch(form.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Update initial values
                initialValues.enabled = enabledCheckbox.checked;
                initialValues.product_threshold = productThreshold.value;
                initialValues.set_threshold = setThreshold.value;
                initialValues.amount = amount.value;

                // Show success message
                showToast('Ustawienia auto-zwiększania zostały zapisane.', 'success');

                // Reset button
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = true;
            } else {
                throw new Error(data.error || 'Wystąpił błąd podczas zapisywania.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(error.message || 'Wystąpił błąd podczas zapisywania.', 'error');
            saveBtn.innerHTML = originalText;
            checkForChanges(); // Re-enable button if there are still changes
        });
    });
}

/**
 * Initialize Delete Form - AJAX submission with toast
 */
function initializeDeleteForm() {
    const deleteForm = document.getElementById('deleteForm');
    if (!deleteForm) return;

    deleteForm.addEventListener('submit', function(e) {
        e.preventDefault();

        const submitBtn = deleteForm.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Usuwanie...';

        fetch(deleteForm.action, {
            method: 'POST',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: new FormData(deleteForm)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Show toast
                showToast(data.message || 'Strona została usunięta.', 'success');

                // Close modal
                closeDeleteModal();

                // Redirect after a short delay
                setTimeout(() => {
                    window.location.href = data.redirect || '/admin/exclusive';
                }, 500);
            } else {
                throw new Error(data.error || 'Wystąpił błąd podczas usuwania.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(error.message || 'Wystąpił błąd podczas usuwania.', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        });
    });
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    // Reuse global toast function if available
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback: simple alert
        alert(message);
    }
}
