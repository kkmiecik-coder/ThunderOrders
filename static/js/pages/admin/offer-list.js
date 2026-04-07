/**
 * Offer Pages - Tab Switching & Settings Logic
 * Handles horizontal tab navigation and custom select dropdowns
 */

document.addEventListener('DOMContentLoaded', function() {
    initializeOfferTabs();
    initializeSettingsTabs(); // Left sidebar tabs in settings panel
    initializeCustomSelects();
    initializeAutoIncreaseForm();
    initializeDeleteForm();
    initializePaymentReminders();
});

/**
 * Initialize tab switching functionality
 */
function initializeOfferTabs() {
    const tabButtons = document.querySelectorAll('.offer-tab-button');
    const tabPanels = document.querySelectorAll('.offer-tab-panel');

    if (tabButtons.length === 0) return;

    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const targetTab = this.getAttribute('data-tab');

            // Remove active class from all buttons and panels
            tabButtons.forEach(btn => btn.classList.remove('offer-tab-active'));
            tabPanels.forEach(panel => panel.classList.remove('offer-tab-active'));

            // Add active class to clicked button and corresponding panel
            this.classList.add('offer-tab-active');
            const targetPanel = document.getElementById(targetTab);
            if (targetPanel) {
                targetPanel.classList.add('offer-tab-active');
            }

            // Save active tab to localStorage
            localStorage.setItem('offerActiveTab', targetTab);
        });
    });

    // Restore previously selected tab
    const savedTab = localStorage.getItem('offerActiveTab');
    if (savedTab) {
        const button = document.querySelector(`.offer-tab-button[data-tab="${savedTab}"]`);
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
                    window.location.href = data.redirect || '/admin/offers';
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
    if (window.Toast && typeof window.Toast.show === 'function') {
        window.Toast.show(message, type);
    } else {
        alert(message);
    }
}

/**
 * Initialize Payment Reminders Settings Tab
 */
function initializePaymentReminders() {
    const addBeforeBtn = document.getElementById('addBeforeDeadlineBtn');
    const addAfterBtn = document.getElementById('addAfterOrderBtn');

    if (!addBeforeBtn && !addAfterBtn) return;

    if (addBeforeBtn) {
        addBeforeBtn.addEventListener('click', function() {
            const input = document.getElementById('beforeDeadlineHours');
            addReminderRule('before_deadline', input, 'beforeDeadlineRules');
        });
    }

    if (addAfterBtn) {
        addAfterBtn.addEventListener('click', function() {
            const input = document.getElementById('afterOrderHours');
            addReminderRule('after_order_placed', input, 'afterOrderRules');
        });
    }

    document.querySelectorAll('.btn-remove-rule').forEach(btn => {
        btn.addEventListener('click', function() {
            deleteReminderRule(this.dataset.id, this.closest('.reminder-rule-row'));
        });
    });
}

async function addReminderRule(reminderType, input, listId) {
    const hours = parseInt(input.value, 10);
    if (!hours || hours < 1) {
        showToast('Podaj prawidłową liczbę godzin (min. 1).', 'error');
        return;
    }

    try {
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;
        const response = await fetch('/admin/offers/settings/payment-reminders/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ reminder_type: reminderType, hours: hours })
        });

        const data = await response.json();
        if (data.success) {
            const list = document.getElementById(listId);
            const textPrefix = reminderType === 'before_deadline'
                ? `${hours}h przed terminem płatności`
                : `${hours}h po złożeniu zamówienia`;

            const row = document.createElement('div');
            row.className = 'reminder-rule-row';
            row.dataset.id = data.rule.id;
            row.innerHTML = `
                <span class="reminder-rule-text">${textPrefix}</span>
                <button type="button" class="btn-remove-rule" data-id="${data.rule.id}" title="Usuń">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M4.646 4.646a.5.5 0 01.708 0L8 7.293l2.646-2.647a.5.5 0 01.708.708L8.707 8l2.647 2.646a.5.5 0 01-.708.708L8 8.707l-2.646 2.647a.5.5 0 01-.708-.708L7.293 8 4.646 5.354a.5.5 0 010-.708z"/>
                    </svg>
                </button>
            `;
            row.querySelector('.btn-remove-rule').addEventListener('click', function() {
                deleteReminderRule(this.dataset.id, row);
            });
            list.appendChild(row);

            input.value = '';
            showToast('Przypomnienie dodane.', 'success');
        } else {
            showToast(data.error || 'Wystąpił błąd.', 'error');
        }
    } catch (error) {
        console.error('Error adding rule:', error);
        showToast('Błąd połączenia z serwerem.', 'error');
    }
}

async function deleteReminderRule(ruleId, rowElement) {
    try {
        const csrfToken = document.querySelector('input[name="csrf_token"]').value;
        const response = await fetch('/admin/offers/settings/payment-reminders/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ rule_id: parseInt(ruleId, 10) })
        });

        const data = await response.json();
        if (data.success) {
            rowElement.remove();
            showToast('Przypomnienie usunięte.', 'success');
        } else {
            showToast(data.error || 'Wystąpił błąd.', 'error');
        }
    } catch (error) {
        console.error('Error deleting rule:', error);
        showToast('Błąd połączenia z serwerem.', 'error');
    }
}
