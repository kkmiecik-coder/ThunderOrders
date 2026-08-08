/**
 * Offer Pages - Tab Switching & Settings Logic
 * Handles horizontal tab navigation and custom select dropdowns
 */

/**
 * Sortowanie i filtrowanie listy stron sprzedaży są serwerowe (parametry
 * ?sort/?dir/?search), bo lista jest paginowana — sortowanie w przeglądarce
 * układałoby tylko 20 wierszy bieżącej strony. Nagłówki kolumn to zwykłe linki
 * generowane w _list_items.html.
 */

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
                notifyToast('Ustawienia auto-zwiększania zostały zapisane.', 'success');

                // Reset button
                saveBtn.innerHTML = originalText;
                saveBtn.disabled = true;
            } else {
                throw new Error(data.error || 'Wystąpił błąd podczas zapisywania.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            notifyToast(error.message || 'Wystąpił błąd podczas zapisywania.', 'error');
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
                notifyToast(data.message || 'Strona została usunięta.', 'success');

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
            notifyToast(error.message || 'Wystąpił błąd podczas usuwania.', 'error');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        });
    });
}

/**
 * Show toast notification.
 * Celowo nie nazywa się `showToast`, żeby nie nadpisywać globalnego
 * window.showToast z toast.js (plik nie jest w IIFE).
 */
function notifyToast(message, type = 'info') {
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
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
        notifyToast('Podaj prawidłową liczbę godzin (min. 1).', 'error');
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
            notifyToast('Przypomnienie dodane.', 'success');
        } else {
            notifyToast(data.error || 'Wystąpił błąd.', 'error');
        }
    } catch (error) {
        console.error('Error adding rule:', error);
        notifyToast('Błąd połączenia z serwerem.', 'error');
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
            notifyToast('Przypomnienie usunięte.', 'success');
        } else {
            notifyToast(data.error || 'Wystąpił błąd.', 'error');
        }
    } catch (error) {
        console.error('Error deleting rule:', error);
        notifyToast('Błąd połączenia z serwerem.', 'error');
    }
}

/**
 * Szukajka stron sprzedaży — filtr jest serwerowy (?search=), więc pole tylko
 * wysyła formularz. Wysyłka jest opóźniona (debounce), żeby zachować wrażenie
 * pisania „na żywo" bez przeładowania po każdym znaku.
 * Guard: jeśli na stronie nie ma pola szukajki, nic nie robi.
 */
function initializeOfferSearch() {
    const input = document.getElementById('offerSearchInput');
    if (!input) return;

    const form = input.form;
    if (!form) return;

    // Po przeładowaniu wracamy kursorem na koniec wpisanej frazy, żeby pisanie
    // dało się kontynuować bez klikania w pole.
    if (input.value) {
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    }

    let timer = null;
    input.addEventListener('input', function() {
        clearTimeout(timer);
        timer = setTimeout(() => form.submit(), 400);
    });

    // Enter wysyła od razu — bez czekania na debounce.
    form.addEventListener('submit', function() {
        clearTimeout(timer);
    });
}

/**
 * Edycja masowa stron sprzedaży: checkboxy, pływający pasek, akcje.
 * Guard: jeśli na stronie nie ma paska (#bulkToolbar), nic nie robi.
 */
function initializeBulkActions() {
    // Wspólny komponent paska (js/components/bulk-toolbar.js) — on odpowiada
    // za pokazywanie/ukrywanie i tekst licznika (z odmianą przez liczbę).
    const pasek = window.BulkToolbar ? window.BulkToolbar.init('bulkToolbar') : null;
    if (!pasek) return;

    // Element paska nadal potrzebny do wyszukiwania przycisków akcji w środku.
    const bulkToolbar = pasek.el;

    // Dwie zakładki → dwa master-checkboxy (#selectAll-current / #selectAll-closed).
    // Operujemy po klasie, nie po id.
    const selectAllBoxes = Array.from(document.querySelectorAll('.offer-select-all'));

    // Lista jest paginowana, więc zaznaczenie NIE może opierać się na wierszach
    // w DOM — te pokazują tylko bieżące 20. Serwer podaje identyfikatory i
    // metadane wszystkich stron pasujących do filtra, per zakładka.
    const selectionData = readSelectionData();
    const selectedIds = new Set();

    function readSelectionData() {
        const el = document.getElementById('offerSelectionData');
        if (!el) return { current: [], closed: [] };
        try {
            const parsed = JSON.parse(el.textContent);
            return { current: parsed.current || [], closed: parsed.closed || [] };
        } catch (e) {
            console.error('Nie udało się odczytać danych zaznaczenia:', e);
            return { current: [], closed: [] };
        }
    }

    function activeTabKey() {
        const panel = document.querySelector('.offer-tab-panel.offer-tab-active');
        return (panel && panel.dataset.tabKey) || 'current';
    }

    // Wpisy bieżącej zakładki: [{id, status, fullyClosed}]
    function tabEntries() {
        return selectionData[activeTabKey()] || [];
    }

    function selectedEntries() {
        return tabEntries().filter(entry => selectedIds.has(String(entry.id)));
    }

    function getCsrfToken() {
        const el = document.querySelector('input[name="csrf_token"]');
        return el ? el.value : '';
    }

    function getSelectedIds() {
        return selectedEntries().map(entry => String(entry.id));
    }

    function syncRowHighlight(cb) {
        const row = cb.closest('tr');
        if (row) row.classList.toggle('row-selected', cb.checked);
        const card = cb.closest('.offer-card');
        if (card) card.classList.toggle('card-selected', cb.checked);
    }

    // Przepisuje stan zaznaczenia na checkboxy widoczne na bieżącej stronie.
    function syncCheckboxesFromState() {
        document.querySelectorAll('.offer-checkbox').forEach(cb => {
            cb.checked = selectedIds.has(String(cb.value));
            syncRowHighlight(cb);
        });
    }

    // Zmiana strony paginacji to pełne przeładowanie, więc zaznaczenie musi
    // przeżyć poza DOM-em — inaczej przejście na stronę 2 kasowałoby wybór
    // zrobiony na stronie 1. sessionStorage: znika po zamknięciu karty.
    const SELECTION_STORAGE_KEY = 'offerBulkSelection';

    function restoreSelection() {
        let stored;
        try {
            stored = JSON.parse(sessionStorage.getItem(SELECTION_STORAGE_KEY) || 'null');
        } catch (e) {
            return;
        }
        if (!stored || stored.tab !== activeTabKey()) return;

        // Przecięcie z aktualnym wynikiem filtra — po zawężeniu szukajki
        // zaznaczenie nie może obejmować stron, których już nie widać.
        const allowed = new Set(tabEntries().map(entry => String(entry.id)));
        (stored.ids || []).forEach(id => {
            if (allowed.has(String(id))) selectedIds.add(String(id));
        });
    }

    function persistSelection() {
        try {
            sessionStorage.setItem(SELECTION_STORAGE_KEY, JSON.stringify({
                tab: activeTabKey(),
                ids: Array.from(selectedIds),
            }));
        } catch (e) {
            // Prywatny tryb przeglądarki może blokować zapis — zaznaczenie
            // wtedy po prostu nie przetrwa zmiany strony.
        }
    }

    function updateToolbar() {
        const selected = selectedEntries();
        const count = selected.length;

        persistSelection();
        pasek.update(count);

        if (selectAllBoxes.length) {
            const entries = tabEntries();
            const allChecked = entries.length > 0 &&
                entries.every(entry => selectedIds.has(String(entry.id)));
            selectAllBoxes.forEach(box => {
                box.checked = allChecked;
                box.indeterminate = count > 0 && !allChecked;
            });
        }

        updateButtonAvailability(selected);
    }

    // Polityka „zablokuj całą akcję" — lustro reguł backendu
    function updateButtonAvailability(selected) {
        const anyFullyClosed = selected.some(entry => entry.fullyClosed);
        const allActiveOrPaused = selected.length > 0 &&
            selected.every(entry => entry.status === 'active' || entry.status === 'paused');
        const anyActive = selected.some(entry => entry.status === 'active');
        const allEnded = selected.length > 0 && selected.every(entry => entry.status === 'ended');

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

    // „Zaznacz wszystkie" obejmuje CAŁĄ przefiltrowaną zakładkę, nie tylko
    // wiersze widoczne na bieżącej stronie paginacji.
    selectAllBoxes.forEach(box => {
        box.addEventListener('change', function() {
            const checked = this.checked;
            tabEntries().forEach(entry => {
                if (checked) {
                    selectedIds.add(String(entry.id));
                } else {
                    selectedIds.delete(String(entry.id));
                }
            });
            syncCheckboxesFromState();
            updateToolbar();
        });
    });

    document.querySelectorAll('.offer-checkbox').forEach(cb => {
        cb.addEventListener('change', function() {
            if (this.checked) {
                selectedIds.add(String(this.value));
            } else {
                selectedIds.delete(String(this.value));
            }
            syncRowHighlight(this);
            updateToolbar();
        });
    });

    // Zmiana zakładki: wyczyść zaznaczenie z poprzedniej zakładki, by pasek
    // akcji masowych nie operował na stronach z drugiej zakładki.
    document.querySelectorAll('.offer-tab-button').forEach(tabBtn => {
        tabBtn.addEventListener('click', function() {
            selectedIds.clear();
            syncCheckboxesFromState();
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
            notifyToast('Wybierz datę.', 'error');
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
                notifyToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                notifyToast(result.error || 'Błąd ustawiania daty.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk set-dates error:', err);
            notifyToast('Wystąpił błąd.', 'error');
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
                notifyToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                notifyToast(result.error || `Błąd: ${verb.toLowerCase()} nie powiodło się.`, 'error');
            }
        })
        .catch(err => {
            console.error('bulk status error:', err);
            notifyToast('Wystąpił błąd.', 'error');
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
                notifyToast(result.message, 'success');
                setTimeout(() => window.location.reload(), 500);
            } else {
                notifyToast(result.error || 'Błąd usuwania.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk delete error:', err);
            notifyToast('Wystąpił błąd.', 'error');
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
                notifyToast('Raport zbiorowy pobrany.', 'success');
            } else {
                const result = await response.json().catch(() => ({}));
                notifyToast(result.error || 'Błąd generowania raportu.', 'error');
            }
        })
        .catch(err => {
            console.error('bulk report error:', err);
            notifyToast('Wystąpił błąd.', 'error');
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
    restoreSelection();
    syncCheckboxesFromState();
    updateToolbar();
}
