/**
 * Offer Pages - Tab Switching & Settings Logic
 * Handles horizontal tab navigation and custom select dropdowns
 */

/**
 * Sortowanie tabeli stron sprzedaży — odwzorowanie mechanizmu ze stock-orders.
 * Zawężone do tabeli klikniętego nagłówka (obie zakładki są w DOM jednocześnie).
 * Stan sortowania trzymany per <table> w data-sort-column / data-sort-dir.
 */
const OFFER_NUMERIC_COLUMNS = new Set(['created', 'starts', 'ends', 'deadline']);
const OFFER_STATUS_PRIORITY = { active: 0, paused: 1, scheduled: 2, draft: 3, ended: 4 };

function sortOfferTable(column, thEl) {
    const table = thEl.closest('table');
    if (!table) return;
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));

    // Toggle kierunku; stan per tabela
    let dir = 'asc';
    if (table.dataset.sortColumn === column) {
        dir = table.dataset.sortDir === 'asc' ? 'desc' : 'asc';
    }
    table.dataset.sortColumn = column;
    table.dataset.sortDir = dir;

    // Wskaźniki tylko w tej tabeli
    table.querySelectorAll('th.sortable').forEach(h => {
        h.classList.remove('sorted-asc', 'sorted-desc');
        if (h.dataset.column === column) {
            h.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
        }
    });

    const key = column;
    const isNumeric = OFFER_NUMERIC_COLUMNS.has(column);
    const isStatus = column === 'status';

    rows.sort((a, b) => {
        let av = a.dataset[key] || '';
        let bv = b.dataset[key] || '';
        if (isStatus) {
            av = OFFER_STATUS_PRIORITY[av] ?? 99;
            bv = OFFER_STATUS_PRIORITY[bv] ?? 99;
        } else if (isNumeric) {
            av = parseFloat(av) || 0;
            bv = parseFloat(bv) || 0;
        } else {
            av = av.toLowerCase();
            bv = bv.toLowerCase();
        }
        if (av < bv) return dir === 'asc' ? -1 : 1;
        if (av > bv) return dir === 'asc' ? 1 : -1;
        return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
}

document.addEventListener('DOMContentLoaded', function() {
    initializeOfferTabs();
    initializeSettingsTabs(); // Left sidebar tabs in settings panel
    initializeCustomSelects();
    initializeAutoIncreaseForm();
    initializeDeleteForm();
    initializePaymentReminders();
    initializeOfferSearch();
    initializeBulkActions();
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
            list.prepend(row);

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

/**
 * Live-filtr listy stron sprzedaży po nazwie.
 * Chowa/pokazuje już wyrenderowane karty mobile i wiersze tabeli.
 * Guard: jeśli na stronie nie ma pola szukajki, nic nie robi.
 */
function initializeOfferSearch() {
    const input = document.getElementById('offerSearchInput');
    if (!input) return;

    const emptyMessage = document.getElementById('offerSearchEmpty');
    const containers = document.querySelectorAll('.offer-cards-mobile, .table-container');
    const items = document.querySelectorAll('[data-search-name]');

    // lowercase + usunięcie znaków diakrytycznych (m.in. polskich ogonków),
    // żeby "lacie" znajdowało "Łacie"
    const normalize = (str) => (str || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/\p{Diacritic}/gu, '')
        .trim();

    input.addEventListener('input', function() {
        const query = normalize(input.value);
        // Liczy węzły DOM, nie strony — każda strona ma 2 wpisy (karta + wiersz).
        // Do logiki braku wyników liczy się tylko 0 vs >0, więc to wystarcza.
        let visibleNodeCount = 0;

        items.forEach(item => {
            const name = normalize(item.getAttribute('data-search-name'));
            const matches = query === '' || name.includes(query);
            item.classList.toggle('is-hidden', !matches);
            if (matches) visibleNodeCount++;
        });

        const noResults = query !== '' && visibleNodeCount === 0;
        containers.forEach(c => c.classList.toggle('is-hidden', noResults));

        if (emptyMessage) {
            emptyMessage.classList.toggle('is-hidden', !noResults);
            if (noResults) {
                emptyMessage.textContent = `Brak stron pasujących do „${input.value.trim()}"`;
            }
        }
    });
}

/**
 * Edycja masowa stron sprzedaży: checkboxy, pływający pasek, akcje.
 * Guard: jeśli na stronie nie ma paska (#bulkToolbar), nic nie robi.
 */
function initializeBulkActions() {
    const bulkToolbar = document.getElementById('bulkToolbar');
    if (!bulkToolbar) return;

    // Dwie zakładki → dwa master-checkboxy (#selectAll-current / #selectAll-closed).
    // Operujemy po klasie, nie po id.
    const selectAllBoxes = Array.from(document.querySelectorAll('.offer-select-all'));
    const selectedCount = document.getElementById('selectedCount');

    function getCsrfToken() {
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }

    // Tylko widoczne checkboxy (uwzględnia szukajkę chowającą wiersze klasą .is-hidden)
    function getVisibleCheckboxes() {
        return Array.from(document.querySelectorAll('.offer-checkbox'))
            .filter(cb => cb.offsetParent !== null);
    }

    function getSelected() {
        return getVisibleCheckboxes().filter(cb => cb.checked);
    }

    function getSelectedIds() {
        return getSelected().map(cb => cb.value);
    }

    function syncRowHighlight(cb) {
        const row = cb.closest('tr');
        if (row) row.classList.toggle('row-selected', cb.checked);
        const card = cb.closest('.offer-card');
        if (card) card.classList.toggle('card-selected', cb.checked);
    }

    function updateToolbar() {
        const selected = getSelected();
        const count = selected.length;

        if (count > 0) {
            bulkToolbar.classList.remove('hidden');
            selectedCount.textContent = `${count} zaznaczonych`;
        } else {
            bulkToolbar.classList.add('hidden');
        }

        if (selectAllBoxes.length) {
            const visible = getVisibleCheckboxes();
            const allChecked = visible.length > 0 && visible.every(cb => cb.checked);
            const someChecked = visible.some(cb => cb.checked);
            selectAllBoxes.forEach(box => {
                box.checked = allChecked;
                box.indeterminate = someChecked && !allChecked;
            });
        }

        updateButtonAvailability(selected);
    }

    // Polityka „zablokuj całą akcję" — lustro reguł backendu
    function updateButtonAvailability(selected) {
        const anyFullyClosed = selected.some(cb => cb.dataset.fullyClosed === '1');
        const allActiveOrPaused = selected.length > 0 &&
            selected.every(cb => cb.dataset.status === 'active' || cb.dataset.status === 'paused');
        const anyActive = selected.some(cb => cb.dataset.status === 'active');
        const allEnded = selected.length > 0 && selected.every(cb => cb.dataset.status === 'ended');

        setBtn('activate', !anyFullyClosed, 'Nie można aktywować — w zaznaczeniu jest strona całkowicie zamknięta.');
        setBtn('set-dates', !anyFullyClosed, 'Nie można ustawić dat — w zaznaczeniu jest strona całkowicie zamknięta.');
        setBtn('close', allActiveOrPaused, 'Zamknąć można tylko strony aktywne lub wstrzymane.');
        setBtn('close-complete', allEnded && !anyFullyClosed, 'Całkowicie zamknąć można tylko strony o statusie „Zakończona", które nie są jeszcze zamknięte.');
        setBtn('delete', !anyActive, 'Nie można usunąć aktywnej strony.');
    }

    function setBtn(action, enabled, reasonIfDisabled) {
        const btn = bulkToolbar.querySelector(`.btn-bulk[data-action="${action}"]`);
        if (!btn) return;
        btn.classList.toggle('is-disabled', !enabled);
        btn.title = enabled ? '' : reasonIfDisabled;
    }

    selectAllBoxes.forEach(box => {
        box.addEventListener('change', function() {
            getVisibleCheckboxes().forEach(cb => {
                cb.checked = this.checked;
                syncRowHighlight(cb);
            });
            updateToolbar();
        });
    });

    document.querySelectorAll('.offer-checkbox').forEach(cb => {
        cb.addEventListener('change', function() {
            syncRowHighlight(this);
            updateToolbar();
        });
    });

    // Odśwież pasek po filtrowaniu szukajką — zaznaczenia w ukrytych wierszach
    // przestają się liczyć (licznik, select-all i dostępność przycisków na bieżąco).
    const bulkSearchInput = document.getElementById('offerSearchInput');
    if (bulkSearchInput) {
        bulkSearchInput.addEventListener('input', updateToolbar);
    }

    // Zmiana zakładki: wyczyść zaznaczenie z poprzedniej zakładki, by pasek
    // akcji masowych nie operował na ukrytych (innej zakładki) stronach.
    document.querySelectorAll('.offer-tab-button').forEach(tabBtn => {
        tabBtn.addEventListener('click', function() {
            document.querySelectorAll('.offer-checkbox').forEach(cb => {
                cb.checked = false;
                syncRowHighlight(cb);
            });
            updateToolbar();
        });
    });

    // ---- Dropdown „Ustaw" + modal daty ----
    let bulkDateField = null;

    function setupBulkSetDropdown() {
        const wrapper = bulkToolbar.querySelector('.bulk-set-wrapper');
        const trigger = bulkToolbar.querySelector('.btn-bulk[data-action="set-dates"]');
        const dropdown = document.getElementById('bulkSetDropdown');
        if (!wrapper || !trigger || !dropdown) return;

        trigger.addEventListener('click', function(e) {
            e.stopPropagation();
            if (trigger.classList.contains('is-disabled')) return;
            dropdown.classList.toggle('show');
            wrapper.classList.toggle('open');
        });

        dropdown.querySelectorAll('.bulk-set-option').forEach(opt => {
            opt.addEventListener('click', function() {
                const field = this.dataset.field;
                dropdown.classList.remove('show');
                wrapper.classList.remove('open');
                openBulkDateModal(field);
            });
        });

        document.addEventListener('click', function(e) {
            if (!wrapper.contains(e.target)) {
                dropdown.classList.remove('show');
                wrapper.classList.remove('open');
            }
        });
    }

    function openBulkDateModal(field) {
        bulkDateField = field;
        const modal = document.getElementById('bulkDateModal');
        const title = document.getElementById('bulkDateTitle');
        const countEl = document.getElementById('bulkDateCount');
        const input = document.getElementById('bulkDateInput');

        title.textContent = field === 'starts_at' ? 'Ustaw datę rozpoczęcia' : 'Ustaw datę zakończenia';
        countEl.textContent = getSelectedIds().length;
        input.value = '';
        modal.classList.add('active');
    }

    window.closeBulkDateModal = function() {
        const modal = document.getElementById('bulkDateModal');
        modal.classList.add('closing');
        setTimeout(() => modal.classList.remove('active', 'closing'), 350);
        bulkDateField = null;
    };

    document.getElementById('bulkDateApply').addEventListener('click', function() {
        const input = document.getElementById('bulkDateInput');
        const value = input.value;
        const ids = getSelectedIds();

        if (!value) {
            showToast('Wybierz datę.', 'error');
            return;
        }
        if (ids.length === 0) {
            window.closeBulkDateModal();
            return;
        }

        fetch('/admin/offers/bulk/set-dates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ page_ids: ids, field: bulkDateField, value: value })
        })
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                showToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                showToast(result.error || 'Błąd ustawiania daty.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk set-dates error:', err);
            showToast('Wystąpił błąd.', 'error');
        });
    });

    document.getElementById('bulkDateModal').addEventListener('click', function(e) {
        if (e.target === this) window.closeBulkDateModal();
    });

    // ---- Akcje: Aktywuj / Zamknij / Usuń + modal potwierdzenia ----
    let bulkConfirmCallback = null;

    function setupBulkButtons() {
        bulkToolbar.querySelectorAll('.btn-bulk').forEach(btn => {
            btn.addEventListener('click', function() {
                const action = this.dataset.action;
                if (this.classList.contains('is-disabled')) return;
                if (action === 'set-dates') return; // obsłużone przez dropdown

                const ids = getSelectedIds();
                if (ids.length === 0) return;

                switch (action) {
                    case 'report':
                        bulkReport(ids, this);
                        break;
                    case 'activate':
                        bulkStatus(ids, 'publish', 'Aktywowano');
                        break;
                    case 'close':
                        openBulkConfirm(
                            'Zakończ sprzedaż',
                            `Zakończyć sprzedaż na ${ids.length} stronach? Zmienią status na „Zakończona".`,
                            'Zakończ sprzedaż',
                            false,
                            () => bulkStatus(ids, 'end', 'Zakończono')
                        );
                        break;
                    case 'close-complete':
                        if (typeof window.openBulkCloseModal === 'function') {
                            window.openBulkCloseModal(ids);
                        }
                        break;
                    case 'delete':
                        openBulkConfirm(
                            'Usuń strony',
                            `Usunąć ${ids.length} stron? Tej operacji nie można cofnąć.`,
                            'Usuń',
                            true,
                            () => bulkDelete(ids)
                        );
                        break;
                }
            });
        });
    }

    function bulkStatus(ids, backendAction, verb) {
        fetch('/admin/offers/bulk/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ page_ids: ids, action: backendAction })
        })
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                showToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                showToast(result.error || `Błąd: ${verb.toLowerCase()} nie powiodło się.`, 'error');
            }
        })
        .catch(err => {
            console.error('bulk status error:', err);
            showToast('Wystąpił błąd.', 'error');
        });
    }

    function bulkDelete(ids) {
        fetch('/admin/offers/bulk/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ page_ids: ids })
        })
        .then(r => r.json())
        .then(result => {
            if (result.success) {
                showToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                showToast(result.error || 'Błąd usuwania.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk delete error:', err);
            showToast('Wystąpił błąd.', 'error');
        });
    }

    function bulkReport(ids, btn) {
        const textEl = btn.querySelector('.btn-bulk-text');
        const originalText = textEl ? textEl.textContent : null;
        btn.classList.add('is-disabled');
        if (textEl) textEl.textContent = 'Generuję...';

        fetch('/admin/offers/bulk/report', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ page_ids: ids })
        })
        .then(async (response) => {
            const ct = response.headers.get('content-type') || '';
            if (response.ok && ct.includes('spreadsheetml')) {
                const blob = await response.blob();
                const disposition = response.headers.get('content-disposition') || '';
                const match = disposition.match(/filename="?([^"]+)"?/);
                const filename = match ? match[1] : 'raport_zbiorczy_ofert.xlsx';
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
                showToast('Raport zbiorowy pobrany.', 'success');
            } else {
                const result = await response.json().catch(() => ({}));
                showToast(result.error || 'Błąd generowania raportu.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk report error:', err);
            showToast('Wystąpił błąd.', 'error');
        })
        .finally(() => {
            btn.classList.remove('is-disabled');
            if (textEl && originalText !== null) textEl.textContent = originalText;
        });
    }

    function openBulkConfirm(title, text, okLabel, danger, onConfirm) {
        const modal = document.getElementById('bulkConfirmModal');
        document.getElementById('bulkConfirmTitle').textContent = title;
        document.getElementById('bulkConfirmText').textContent = text;
        const okBtn = document.getElementById('bulkConfirmOk');
        okBtn.textContent = okLabel;
        okBtn.classList.toggle('btn-danger', !!danger);
        bulkConfirmCallback = onConfirm;
        modal.classList.add('active');
    }

    window.closeBulkConfirmModal = function() {
        const modal = document.getElementById('bulkConfirmModal');
        modal.classList.add('closing');
        setTimeout(() => modal.classList.remove('active', 'closing'), 350);
        bulkConfirmCallback = null;
    };

    document.getElementById('bulkConfirmOk').addEventListener('click', function() {
        const cb = bulkConfirmCallback;
        window.closeBulkConfirmModal();
        if (typeof cb === 'function') cb();
    });

    document.getElementById('bulkConfirmModal').addEventListener('click', function(e) {
        if (e.target === this) window.closeBulkConfirmModal();
    });

    // Escape zamyka nowe modale
    document.addEventListener('keydown', function(e) {
        if (e.key !== 'Escape') return;
        const dateModal = document.getElementById('bulkDateModal');
        const confirmModal = document.getElementById('bulkConfirmModal');
        if (dateModal && dateModal.classList.contains('active')) window.closeBulkDateModal();
        if (confirmModal && confirmModal.classList.contains('active')) window.closeBulkConfirmModal();
    });

    // Inicjalizacja
    setupBulkSetDropdown();
    setupBulkButtons();
    updateToolbar();
}
