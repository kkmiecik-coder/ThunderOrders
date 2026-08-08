/**
 * Stock Orders - Proxy & Poland tabs
 * Handles sorting, filtering, modals, and order management
 */

/**
 * Paski akcji masowych (wspólny komponent BulkToolbar).
 * Strona ma trzy paski; każdy jest renderowany warunkowo (aktywna zakładka),
 * więc init() może zwrócić null — stąd guardy przy każdym użyciu.
 */
let paskToOrder = null;
let paskAkcji = null;
let paskArchiwum = null;

document.addEventListener('DOMContentLoaded', function () {
    paskToOrder = BulkToolbar.init('toOrderBulkToolbar');
    paskAkcji = BulkToolbar.init('bulkActionsModal');
    paskArchiwum = BulkToolbar.init('archiwumBulkToolbar');
});

/**
 * Sortowanie i filtrowanie zakładek jest SERWEROWE (parametry ?sort/?dir oraz
 * pola filtrów w formularzu GET) — lista jest paginowana, więc układanie
 * i chowanie wierszy w przeglądarce obejmowałoby tylko bieżącą stronę.
 * Nagłówki kolumn to linki generowane w stock_orders_macros.html.
 */






// ============================================
// Unified Checkbox & Select All Functions
// ============================================

function _toggleSelectAll(tab, selectAllCheckbox) {
    const config = TAB_CONFIG[tab];
    const table = document.getElementById(config.tableId);
    if (!table) return;
    const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');

    visibleRows.forEach(row => {
        const cb = row.querySelector(`.${config.checkboxClass}`);
        if (cb) {
            cb.checked = selectAllCheckbox.checked;
            row.classList.toggle('selected', selectAllCheckbox.checked);
        }
    });

    updateBulkActionsModal();
}

function toggleSelectAll(selectAllCheckbox) { _toggleSelectAll('proxy', selectAllCheckbox); }
function toggleSelectAllPoland(selectAllCheckbox) { _toggleSelectAll('polska', selectAllCheckbox); }

function _handleCheckboxChange(tab) {
    const checkbox = event.target;
    const row = checkbox.closest('tr');
    row.classList.toggle('selected', checkbox.checked);

    _updateSelectAllState(tab);
    updateBulkActionsModal();
}

function handleCheckboxChange() { _handleCheckboxChange('proxy'); }
function handleCheckboxChangePoland() { _handleCheckboxChange('polska'); }

function _updateSelectAllState(tab) {
    const config = TAB_CONFIG[tab];
    const selectAll = document.getElementById(config.selectAllId);
    if (!selectAll) return;

    const table = document.getElementById(config.tableId);
    if (!table) return;
    const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');
    const checkboxes = Array.from(visibleRows).map(row => row.querySelector(`.${config.checkboxClass}`)).filter(cb => cb);

    const allChecked = checkboxes.length > 0 && checkboxes.every(cb => cb.checked);
    const someChecked = checkboxes.some(cb => cb.checked);

    selectAll.checked = allChecked;
    selectAll.indeterminate = someChecked && !allChecked;
}

function updateSelectAllState() { _updateSelectAllState('proxy'); }
function updateSelectAllStatePoland() { _updateSelectAllState('polska'); }

// ============================================
// Unified Status Dropdown Functions
// ============================================

function _toggleStatusDropdown(tab, orderId) {
    const config = TAB_CONFIG[tab];
    const prefix = config.statusDropdownPrefix;
    const dropdownId = `${prefix}-${orderId}`;

    const allDropdowns = document.querySelectorAll(`[id^="${prefix}-"]`);
    allDropdowns.forEach(d => {
        if (d.id !== dropdownId) d.style.display = 'none';
    });

    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;

    const fnName = tab === 'proxy' ? 'toggleStatusDropdown' : 'togglePolandStatusDropdown';
    const button = document.querySelector(`[onclick="${fnName}(${orderId})"]`);
    if (!button) return;

    if (dropdown.style.display === 'none' || !dropdown.style.display) {
        if (dropdown.parentElement !== document.body) {
            document.body.appendChild(dropdown);
        }

        const rect = button.getBoundingClientRect();
        const dropdownHeight = 280;
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;

        let top = (rect.bottom + dropdownHeight > viewportHeight) ? rect.top - dropdownHeight - 4 : rect.bottom + 4;
        let left = rect.left;
        if (left + 180 > viewportWidth) left = viewportWidth - 180 - 16;

        dropdown.style.position = 'fixed';
        dropdown.style.top = `${top}px`;
        dropdown.style.left = `${left}px`;
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

function toggleStatusDropdown(orderId) { _toggleStatusDropdown('proxy', orderId); }
function togglePolandStatusDropdown(orderId) { _toggleStatusDropdown('polska', orderId); }

// ============================================
// Unified Status Change Function
// ============================================

function _changeOrderStatus(tab, orderId, newStatus) {
    const config = TAB_CONFIG[tab];

    const dropdown = document.getElementById(`${config.statusDropdownPrefix}-${orderId}`);
    if (dropdown) dropdown.style.display = 'none';

    fetch(config.statusEndpoint(orderId), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
        body: JSON.stringify({ status: newStatus })
    })
    .then(handleFetchResponse)
    .then(data => {
        if (!data) return;
        if (data.success) {
            const row = document.getElementById(`${config.rowIdPrefix}-${orderId}`);
            if (row) {
                const button = row.querySelector('.status-badge-button');
                if (button) {
                    button.className = `status-badge-button badge-${newStatus}`;
                    button.childNodes[0].textContent = (config.statusLabels[newStatus] || newStatus) + ' ';
                }
                row.dataset.status = newStatus;

                // Update date display
                const now = new Date();
                const formattedDate = `${String(now.getDate()).padStart(2,'0')}.${String(now.getMonth()+1).padStart(2,'0')}.${now.getFullYear()} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;

                if (config.dateUpdateSelector) {
                    const dateEl = row.querySelector(config.dateUpdateSelector);
                    if (dateEl) {
                        dateEl.textContent = formattedDate;
                        dateEl.style.transition = 'background-color 0.3s';
                        dateEl.style.backgroundColor = 'rgba(249, 115, 22, 0.15)';
                        setTimeout(() => { dateEl.style.backgroundColor = ''; }, 1000);
                    }
                } else if (config.dateUpdateCellIndex !== null) {
                    const cells = row.querySelectorAll('td');
                    const cell = cells[config.dateUpdateCellIndex];
                    if (cell) {
                        cell.textContent = formattedDate;
                        cell.className = 'text-muted';
                        cell.style.transition = 'background-color 0.3s';
                        cell.style.backgroundColor = 'rgba(90, 24, 154, 0.15)';
                        setTimeout(() => { cell.style.backgroundColor = ''; }, 1000);
                    }
                }

                row.dataset.statusChanged = Math.floor(now.getTime() / 1000);
            }

            if (typeof window.showToast === 'function') {
                window.showToast(data.message || 'Status zamówienia zmieniony', 'success');
            }

            // Powiadomienie o wysłanych emailach do klientów
            if (data.emails_sent > 0 && typeof window.showToast === 'function') {
                const emailMsg = data.emails_sent === 1
                    ? 'Wysłano email do klienta o zmianie statusu zamówienia'
                    : `Wysłano email do ${data.emails_sent} klientów o zmianie statusu zamówienia`;
                window.showToast(emailMsg, 'info');
            }
        } else {
            if (typeof window.showToast === 'function') window.showToast('Błąd: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Status change error:', error);
        if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd podczas zmiany statusu', 'error');
    });
}

function changeOrderStatus(orderId, newStatus) { _changeOrderStatus('proxy', orderId, newStatus); }
function changePolandOrderStatus(orderId, newStatus) { _changeOrderStatus('polska', orderId, newStatus); }

// ============================================
// Unified Delete Functions
// ============================================

function _deleteOrder(tab, orderId) {
    const config = TAB_CONFIG[tab];
    const label = tab === 'polska' ? 'POLSKA' : '';
    if (!confirm(`Czy na pewno chcesz usunąć to zamówienie${label ? ' ' + label : ''}?\n\nTa operacja jest nieodwracalna.`)) return;

    fetch(config.deleteEndpoint(orderId), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
    })
    .then(handleFetchResponse)
    .then(data => {
        if (!data) return;
        if (data.success) {
            if (typeof window.showToast === 'function') window.showToast(`Zamówienie${label ? ' ' + label : ''} zostało usunięte`, 'success');
            setTimeout(() => { window.location.reload(); }, 500);
        } else {
            if (typeof window.showToast === 'function') window.showToast('Błąd: ' + data.error, 'error');
        }
    })
    .catch(error => {
        console.error('Delete error:', error);
        if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd podczas usuwania zamówienia', 'error');
    });
}

function deleteOrder(orderId) { _deleteOrder('proxy', orderId); }
function deletePolandOrder(orderId) { _deleteOrder('polska', orderId); }

function _bulkDeleteOrders(tab) {
    const config = TAB_CONFIG[tab];
    const label = tab === 'polska' ? ' POLSKA' : '';
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    if (!confirm(`Czy na pewno chcesz usunąć ${orderIds.length} zamówień${label}?\n\nTa operacja jest nieodwracalna.`)) return;

    let completed = 0, errors = 0;

    orderIds.forEach(orderId => {
        fetch(config.deleteEndpoint(orderId), {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() }
        })
        .then(handleFetchResponse)
        .then(data => {
            if (!data) return;
            completed++;
            if (!data.success) errors++;
            if (completed === orderIds.length) {
                if (errors === 0) {
                    if (typeof window.showToast === 'function') window.showToast(`Usunięto ${orderIds.length} zamówień`, 'success');
                } else {
                    if (typeof window.showToast === 'function') window.showToast(`Usunięto ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                }
                setTimeout(() => { window.location.reload(); }, 500);
            }
        })
        .catch(error => {
            console.error('Bulk delete error:', error);
            errors++; completed++;
            if (completed === orderIds.length) setTimeout(() => { window.location.reload(); }, 500);
        });
    });
}

function bulkDeleteOrders() { _bulkDeleteOrders('proxy'); }
function bulkDeletePolandOrders() { _bulkDeleteOrders('polska'); }

// ============================================
// Unified Bulk Move Function
// ============================================

function _bulkMove(targetTab) {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    const targetLabel = targetTab.toUpperCase();
    if (!confirm(`Czy na pewno chcesz przenieść ${orderIds.length} zamówień do zakładki ${targetLabel}?`)) return;

    let completed = 0, errors = 0;
    const successfulMoves = [];
    const direction = targetTab === 'polska' ? '50px' : '-50px';

    orderIds.forEach(orderId => {
        fetch(`/admin/products/proxy-orders/${orderId}/move`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ order_type: targetTab })
        })
        .then(handleFetchResponse)
        .then(data => {
            if (!data) return;
            completed++;
            if (data.success) {
                successfulMoves.push(orderId);
                const row = document.getElementById(`order-row-${orderId}`);
                if (row) {
                    row.style.transition = 'opacity 0.3s, transform 0.3s';
                    row.style.opacity = '0';
                    row.style.transform = `translateX(${direction})`;
                }
            } else {
                errors++;
            }

            if (completed === orderIds.length) {
                const modal = document.getElementById('bulkActionsModal');
                if (modal) modal.classList.remove('visible');

                const fromTab = targetTab === 'polska' ? 'proxy' : 'polska';
                updateTabBadges(fromTab, targetTab, successfulMoves.length);
                updateSelectAllState();

                if (errors === 0) {
                    if (typeof window.showToast === 'function') window.showToast(`Przeniesiono ${successfulMoves.length} zamówień do zakładki ${targetLabel}`, 'success');
                } else {
                    if (typeof window.showToast === 'function') window.showToast(`Przeniesiono ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                }

                setTimeout(() => {
                    successfulMoves.forEach(id => {
                        const row = document.getElementById(`order-row-${id}`);
                        if (row) row.remove();
                    });
                    const tbody = document.querySelector('.data-table tbody');
                    if (tbody && tbody.children.length === 0) showEmptyState();
                }, 350);
            }
        })
        .catch(error => {
            console.error('Bulk move error:', error);
            errors++; completed++;
        });
    });
}

function bulkMoveToPolska() { _bulkMove('polska'); }
function bulkMoveToProxy() { _bulkMove('proxy'); }

// Zamykanie rozwijanych list zmiany statusu przy kliknięciu obok.
// (Listę wielokrotnego wyboru w filtrach obsługuje js/components/server-filters.js.)
document.addEventListener('click', function(event) {
    if (!event.target.closest('.status-dropdown-wrapper') && !event.target.closest('.status-dropdown')) {
        document.querySelectorAll('.status-dropdown, [id^="poland-status-dropdown-"]').forEach(d => {
            d.style.display = 'none';
        });
    }
});

// ============================================
// Checkbox & Bulk Actions Functions
// ============================================

/**
 * Update bulk actions modal visibility
 */
function updateBulkActionsModal() {
    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
    const config = TAB_CONFIG[activeTab];
    const checkboxClass = config ? config.checkboxClass : 'order-checkbox';
    const checkedBoxes = document.querySelectorAll(`.${checkboxClass}:checked`);
    if (!paskAkcji) return;

    paskAkcji.update(checkedBoxes.length);
    if (checkedBoxes.length === 0) {
        hideBulkStatusDropdown();
    }
}

/**
 * Get selected order IDs
 */
function getSelectedOrderIds() {
    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
    const config = TAB_CONFIG[activeTab];
    const checkboxClass = config ? config.checkboxClass : 'order-checkbox';
    return Array.from(document.querySelectorAll(`.${checkboxClass}:checked`)).map(cb => cb.value);
}

/**
 * Open bulk status change dropdown
 */
function openBulkStatusChange() {
    const dropdown = document.getElementById('bulkStatusDropdown');
    if (dropdown.style.display === 'none') {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

/**
 * Hide bulk status dropdown
 */
function hideBulkStatusDropdown() {
    const dropdown = document.getElementById('bulkStatusDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

/**
 * Apply bulk status change
 */
function applyBulkStatus(newStatus) {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) return;

    const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';

    const statusLabelsProxy = {
        'zamowiono': 'Zamówiono',
        'dostarczone_do_proxy': 'Dostarczone do Proxy',
        'anulowane': 'Anulowane'
    };
    const statusLabelsPoland = {
        'zamowione': 'Zamówione',
        'urzad_celny': 'Urząd celny',
        'dostarczone_gom': 'Dostarczone GOM',
        'anulowane': 'Anulowane'
    };
    const statusLabels = activeTab === 'polska' ? statusLabelsPoland : statusLabelsProxy;
    const rowPrefix = activeTab === 'polska' ? 'poland-order-row' : 'order-row';

    let completed = 0;
    let errors = 0;
    let totalEmailsSent = 0;

    orderIds.forEach(orderId => {
        const endpoint = activeTab === 'polska'
            ? `/admin/products/poland-orders/${orderId}/status`
            : `/admin/products/proxy-orders/${orderId}/status`;

        fetch(endpoint, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() },
            body: JSON.stringify({ status: newStatus })
        })
        .then(handleFetchResponse)
        .then(data => {
            if (!data) return;
            completed++;

            if (data.success) {
                totalEmailsSent += (data.emails_sent || 0);

                const row = document.getElementById(`${rowPrefix}-${orderId}`);

                if (row) {
                    const button = row.querySelector('.status-badge-button');
                    if (button) {
                        button.className = `status-badge-button badge-${newStatus}`;
                        button.childNodes[0].textContent = (statusLabels[newStatus] || newStatus) + ' ';
                    }
                    row.dataset.status = newStatus;

                    const checkbox = row.querySelector('.order-checkbox');
                    if (checkbox) {
                        checkbox.checked = false;
                        row.classList.remove('selected');
                    }
                }
            } else {
                errors++;
            }

            if (completed === orderIds.length) {
                hideBulkStatusDropdown();
                updateBulkActionsModal();
                _updateSelectAllState(activeTab);

                if (errors === 0) {
                    if (typeof window.showToast === 'function') {
                        window.showToast(`Status ${orderIds.length} zamówień został zmieniony`, 'success');
                    }
                } else {
                    if (typeof window.showToast === 'function') {
                        window.showToast(`Zmieniono status ${completed - errors} zamówień, ${errors} błędów`, 'warning');
                    }
                }

                // Powiadomienie o wysłanych emailach do klientów
                if (totalEmailsSent > 0 && typeof window.showToast === 'function') {
                    const emailMsg = totalEmailsSent === 1
                        ? 'Wysłano email do klienta o zmianie statusu zamówienia'
                        : `Wysłano email do ${totalEmailsSent} klientów o zmianie statusu zamówienia`;
                    window.showToast(emailMsg, 'info');
                }
            }
        })
        .catch(error => {
            console.error('Bulk status change error:', error);
            errors++;
            completed++;
        });
    });
}

/**
 * Update tab badges after moving orders
 */
function updateTabBadges(fromTab, toTab, count) {
    const proxyBadge = document.getElementById('proxyCountBadge');
    const polskaBadge = document.getElementById('polskaCountBadge');

    if (fromTab === 'proxy' && proxyBadge) {
        let currentCount = parseInt(proxyBadge.textContent) || 0;
        let newCount = Math.max(0, currentCount - count);
        proxyBadge.textContent = newCount;
        proxyBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (fromTab === 'polska' && polskaBadge) {
        let currentCount = parseInt(polskaBadge.textContent) || 0;
        let newCount = Math.max(0, currentCount - count);
        polskaBadge.textContent = newCount;
        polskaBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (toTab === 'proxy' && proxyBadge) {
        let currentCount = parseInt(proxyBadge.textContent) || 0;
        let newCount = currentCount + count;
        proxyBadge.textContent = newCount;
        proxyBadge.style.display = newCount > 0 ? '' : 'none';
    }

    if (toTab === 'polska' && polskaBadge) {
        let currentCount = parseInt(polskaBadge.textContent) || 0;
        let newCount = currentCount + count;
        polskaBadge.textContent = newCount;
        polskaBadge.style.display = newCount > 0 ? '' : 'none';
    }
}

// Close bulk status dropdown when clicking outside
document.addEventListener('click', function(event) {
    if (!event.target.closest('.bulk-action-status') && !event.target.closest('.bulk-status-dropdown')) {
        hideBulkStatusDropdown();
    }
});

/**
 * Re-position dropdowns on scroll (for fixed position)
 */
const tableResponsive = document.querySelector('.table-responsive');
if (tableResponsive) {
    tableResponsive.addEventListener('scroll', function() {
        // Close all dropdowns on scroll
        document.querySelectorAll('.status-dropdown, [id^="poland-status-dropdown-"]').forEach(d => {
            d.style.display = 'none';
        });
    });
}

/**
 * Toggle hidden products in Poland tab
 */
function togglePolandProducts(toggleEl) {
    const container = toggleEl.closest('.poland-products-cell') || toggleEl.closest('.products-cell');
    const hiddenItems = container.querySelectorAll('.poland-product-hidden');
    const isExpanded = toggleEl.dataset.expanded === 'true';

    hiddenItems.forEach(item => {
        item.style.display = isExpanded ? 'none' : '';
    });

    if (isExpanded) {
        toggleEl.textContent = `Pokaż więcej (${hiddenItems.length})`;
        toggleEl.dataset.expanded = 'false';
    } else {
        toggleEl.textContent = 'Pokaż mniej';
        toggleEl.dataset.expanded = 'true';
    }
}

/**
 * Show empty state when table becomes empty
 */
function showEmptyState() {
    // Hide the filters section
    const filtersSection = document.querySelector('.orders-filters');
    if (filtersSection) {
        filtersSection.style.display = 'none';
    }

    const tableResponsive = document.querySelector('.table-responsive');
    if (tableResponsive) {
        tableResponsive.remove();
    }

    const ordersList = document.querySelector('.orders-list');
    if (ordersList) {
        const activeTab = (window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.activeTab) || 'proxy';
        let emptyStateHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
                    <line x1="1" y1="10" x2="23" y2="10"></line>
                </svg>
                <h3>Brak zamówień</h3>
        `;

        if (activeTab === 'proxy') {
            emptyStateHTML += `
                <p>Nie znaleziono żadnych zamówień dla kategorii PROXY</p>
            `;
        } else {
            emptyStateHTML += `
                <p>Zamówienia pojawią się tutaj po zmianie statusu na "Dostarczone GOM" w zakładce PROXY</p>
                <a href="${(window.STOCK_ORDERS_CONFIG && window.STOCK_ORDERS_CONFIG.proxyTabUrl) || '/admin/products/stock-orders?tab=proxy'}" class="btn btn-primary">
                    Przejdź do PROXY
                </a>
            `;
        }

        emptyStateHTML += '</div>';
        ordersList.innerHTML = emptyStateHTML;
    }
}

// ============================================
// DO ZAMÓWIENIA Tab Functions
// ============================================

/**
 * Toggle select all products in DO ZAMÓWIENIA tab
 */
function toggleSelectAllToOrder(checkbox) {
    const checkboxes = document.querySelectorAll('.to-order-checkbox');
    checkboxes.forEach(cb => {
        const row = cb.closest('tr');
        const isVisible = row.style.display !== 'none';
        if (isVisible) {
            cb.checked = checkbox.checked;
            if (checkbox.checked) {
                row.classList.add('selected');
            } else {
                row.classList.remove('selected');
            }
        }
    });
    handleToOrderCheckboxChange();
}

/**
 * Handle checkbox change in DO ZAMÓWIENIA tab
 */
function handleToOrderCheckboxChange() {
    const allCheckboxes = document.querySelectorAll('.to-order-checkbox');
    const visibleCheckboxes = [...allCheckboxes].filter(cb => cb.closest('tr').style.display !== 'none');
    const visibleChecked = visibleCheckboxes.filter(cb => cb.checked);

    // Count all checked (visible + hidden) for toolbar
    const totalChecked = document.querySelectorAll('.to-order-checkbox:checked').length;
    if (paskToOrder) paskToOrder.update(totalChecked);

    // Update select all checkbox state based on visible rows only
    const selectAllCheckbox = document.getElementById('selectAllToOrder');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = visibleCheckboxes.length > 0 && visibleChecked.length === visibleCheckboxes.length;
        selectAllCheckbox.indeterminate = visibleChecked.length > 0 && visibleChecked.length < visibleCheckboxes.length;
    }
}

/**
 * Clear selection in DO ZAMÓWIENIA tab
 */
function clearToOrderSelection() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = false;
        cb.closest('tr').classList.remove('selected');
    });
    const selectAllCheckbox = document.getElementById('selectAllToOrder');
    if (selectAllCheckbox) {
        selectAllCheckbox.checked = false;
        selectAllCheckbox.indeterminate = false;
    }
    if (paskToOrder) paskToOrder.hide();
}

/**
 * Suppliers data for the modal dropdown
 */

// suppliersData is declared in the HTML template (Jinja2 data bridge)

// Zamknij modal grupowy po kliknięciu na overlay
(function() {
    const groupModal = document.getElementById('groupOrderModal');
    if (groupModal) {
        groupModal.addEventListener('click', function(e) {
            if (e.target === groupModal) {
                closeGroupOrderModal();
            }
        });
    }
})();

// Podświetlanie zaznaczonych wierszy w tabeli DO ZAMÓWIENIA
document.querySelectorAll('.to-order-checkbox').forEach(box => {
    box.addEventListener('change', function() {
        const row = this.closest('tr');
        if (this.checked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
});

/**
 * Otwórz modal zamówienia grupowego z walidacją typów płatności
 */
function openOrderProductsModal() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox:checked');
    if (checkboxes.length === 0) {
        if (typeof window.showToast === 'function') {
            window.showToast('Zaznacz produkty do zamówienia', 'warning');
        }
        return;
    }

    // Sprawdź typy płatności (Proxy vs Polska)
    const paymentTypes = new Set();
    checkboxes.forEach(box => {
        paymentTypes.add(box.dataset.paymentType);
    });

    // WALIDACJA: NIE można mieszać Proxy + Polska
    if (paymentTypes.size > 1) {
        if (typeof window.showToast === 'function') {
            window.showToast('Nie można złożyć zamówienia grupowego łączącego produkty Proxy i Polska. Zaznacz produkty tylko jednego typu.', 'error');
        } else {
            alert('Nie można złożyć zamówienia grupowego łączącego produkty Proxy i Polska. Zaznacz produkty tylko jednego typu.');
        }
        return;
    }

    const orderType = Array.from(paymentTypes)[0]; // 'proxy' lub 'polska'
    const orderTypeLabel = orderType === 'proxy' ? 'Proxy' : 'Polska';

    // Uzupełnij dane w modalu
    document.getElementById('groupOrderCount').textContent = checkboxes.length;
    document.getElementById('groupOrderType').textContent = orderTypeLabel;

    // Wypełnij tabelę produktów
    const tbody = document.getElementById('groupOrderTableBody');
    tbody.innerHTML = '';
    let total = 0;
    let totalOriginal = 0;
    let totalCurrency = null;

    checkboxes.forEach(checkbox => {
        const row = checkbox.closest('tr');
        const productName = row.dataset.productName;
        const toOrder = parseInt(row.dataset.toOrder);
        const purchasePrice = parseFloat(row.dataset.purchasePrice) || 0;
        const purchaseOriginal = parseFloat(row.dataset.purchaseOriginal) || 0;
        const purchaseCurrency = row.dataset.purchaseCurrency || 'PLN';

        const rowTotal = toOrder * purchasePrice;
        total += rowTotal;

        if (purchaseCurrency !== 'PLN' && purchaseOriginal > 0) {
            totalOriginal += toOrder * purchaseOriginal;
            totalCurrency = purchaseCurrency;
        }

        const unitCell = buildPriceCell(purchasePrice, purchaseOriginal, purchaseCurrency);
        const sumCell = buildPriceCell(rowTotal, toOrder * purchaseOriginal, purchaseCurrency);

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(productName)}</td>
            <td class="text-center">${toOrder}</td>
            <td class="text-right">${unitCell}</td>
            <td class="text-right font-semibold">${sumCell}</td>
        `;
        tbody.appendChild(tr);
    });

    const totalCell = buildPriceCell(total, totalOriginal, totalCurrency);
    document.getElementById('groupOrderTotal').innerHTML = totalCell;

    // Pokaż modal
    document.getElementById('groupOrderModal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

/**
 * Zamknij modal zamówienia grupowego
 */
function closeGroupOrderModal() {
    const modal = document.getElementById('groupOrderModal');
    if (modal) {
        modal.classList.add('closing');
        setTimeout(() => {
            modal.classList.remove('active');
            modal.classList.remove('closing');
            document.body.style.overflow = '';
            document.getElementById('groupOrderNote').value = '';
        }, 350);
    }
}

/**
 * Potwierdź i utwórz zamówienie grupowe
 */
function confirmGroupOrder() {
    const checkboxes = document.querySelectorAll('.to-order-checkbox:checked');
    if (checkboxes.length === 0) return;

    const note = document.getElementById('groupOrderNote').value.trim();
    const orderType = checkboxes[0].dataset.paymentType;

    // Zbierz dane produktów
    const products = [];
    checkboxes.forEach(checkbox => {
        const row = checkbox.closest('tr');
        products.push({
            product_id: parseInt(checkbox.value),
            supplier_id: row.dataset.supplierId ? parseInt(row.dataset.supplierId) : null,
            quantity: parseInt(row.dataset.toOrder),
            unit_price: parseFloat(row.dataset.purchasePrice) || 0
        });
    });

    // Wyłącz przycisk
    const btn = document.getElementById('btnConfirmGroupOrder');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-small"></span> Tworzenie...';

    // AJAX: Utwórz zamówienie grupowe
    fetch('/admin/products/api/create-group-proxy-order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
            products: products,
            order_type: orderType,
            note: note
        })
    })
    .then(handleFetchResponse)
    .then(data => {
        if (!data) return;
        if (data.success) {
            closeGroupOrderModal();
            if (typeof window.showToast === 'function') {
                window.showToast(`Zamówienie grupowe utworzone! Numer: ${data.order_number}`, 'success');
            }
            // Przekieruj do odpowiedniej zakładki
            setTimeout(() => {
                window.location.href = `/admin/products/stock-orders?tab=${orderType}`;
            }, 1000);
        } else {
            if (typeof window.showToast === 'function') {
                window.showToast('Błąd: ' + (data.error || 'Nieznany błąd'), 'error');
            }
            btn.disabled = false;
            btn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"></path>
                    <line x1="3" y1="6" x2="21" y2="6"></line>
                    <path d="M16 10a4 4 0 01-8 0"></path>
                </svg>
                Potwierdź zamówienie
            `;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (typeof window.showToast === 'function') {
            window.showToast('Wystąpił błąd podczas tworzenia zamówienia', 'error');
        }
        btn.disabled = false;
        btn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"></path>
                <line x1="3" y1="6" x2="21" y2="6"></line>
                <path d="M16 10a4 4 0 01-8 0"></path>
            </svg>
            Potwierdź zamówienie
        `;
    });
}

// ============================================
// ARCHIWUM — Archive / Unarchive Poland Orders
// ============================================

function toggleSelectAllArchiwum(selectAllCheckbox) {
    _toggleSelectAll('archiwum', selectAllCheckbox);
}

function handleCheckboxChangeArchiwum() {
    _updateSelectAllState('archiwum');
    updateArchiwumBulkToolbar();
}

function updateArchiwumBulkToolbar() {
    const checkedBoxes = document.querySelectorAll('.archiwum-checkbox:checked');
    if (!paskArchiwum) return;

    paskArchiwum.update(checkedBoxes.length);
}

function getSelectedArchiwumIds() {
    return Array.from(document.querySelectorAll('.archiwum-checkbox:checked')).map(cb => cb.value);
}

function bulkArchivePolandOrders() {
    const orderIds = getSelectedOrderIds();
    if (orderIds.length === 0) {
        if (typeof window.showToast === 'function') window.showToast('Zaznacz zamówienia do archiwizacji', 'warning');
        return;
    }

    if (!confirm(`Czy na pewno chcesz przenieść ${orderIds.length} zamówień do archiwum?`)) return;

    fetch('/admin/products/poland-orders/bulk-archive', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ order_ids: orderIds.map(Number), archive: true })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            if (typeof window.showToast === 'function') window.showToast(data.error || 'Błąd archiwizacji', 'error');
        }
    })
    .catch(err => {
        console.error('Error:', err);
        if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
    });
}

function bulkUnarchivePolandOrders() {
    const orderIds = getSelectedArchiwumIds();
    if (orderIds.length === 0) {
        if (typeof window.showToast === 'function') window.showToast('Zaznacz zamówienia do przywrócenia', 'warning');
        return;
    }

    if (!confirm(`Czy na pewno chcesz przywrócić ${orderIds.length} zamówień z archiwum?`)) return;

    fetch('/admin/products/poland-orders/bulk-archive', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({ order_ids: orderIds.map(Number), archive: false })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            if (typeof window.showToast === 'function') window.showToast(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            if (typeof window.showToast === 'function') window.showToast(data.error || 'Błąd przywracania', 'error');
        }
    })
    .catch(err => {
        console.error('Error:', err);
        if (typeof window.showToast === 'function') window.showToast('Wystąpił błąd', 'error');
    });
}

// Archiwum filter wrapper functions
