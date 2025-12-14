/**
 * Orders List - Admin Panel
 * Handles checkboxes, bulk actions toolbar, delete confirmations
 */

(function() {
    'use strict';

    // ====================
    // CHECKBOX MANAGEMENT
    // ====================

    const selectAllCheckbox = document.getElementById('selectAll');
    const orderCheckboxes = document.querySelectorAll('.order-checkbox');
    const bulkToolbar = document.getElementById('bulkToolbar');
    const selectedCountSpan = document.getElementById('selectedCount');

    /**
     * Update bulk toolbar visibility and count
     */
    function updateBulkToolbar() {
        const checkedBoxes = document.querySelectorAll('.order-checkbox:checked');
        const count = checkedBoxes.length;

        if (count > 0) {
            bulkToolbar.classList.remove('hidden');
            selectedCountSpan.textContent = `${count} zaznaczonych`;
        } else {
            bulkToolbar.classList.add('hidden');
        }
    }

    /**
     * Get array of selected order IDs
     */
    function getSelectedOrderIds() {
        const checkedBoxes = document.querySelectorAll('.order-checkbox:checked');
        return Array.from(checkedBoxes).map(cb => cb.value);
    }

    // Select All checkbox handler
    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener('change', function() {
            const isChecked = this.checked;
            orderCheckboxes.forEach(checkbox => {
                checkbox.checked = isChecked;
            });
            updateBulkToolbar();
        });
    }

    // Individual checkbox handlers
    orderCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            // Update "Select All" checkbox state
            if (selectAllCheckbox) {
                const allChecked = Array.from(orderCheckboxes).every(cb => cb.checked);
                const someChecked = Array.from(orderCheckboxes).some(cb => cb.checked);

                selectAllCheckbox.checked = allChecked;
                selectAllCheckbox.indeterminate = someChecked && !allChecked;
            }

            updateBulkToolbar();
        });
    });

    // ====================
    // BULK ACTIONS
    // ====================

    const bulkActionButtons = document.querySelectorAll('.btn-bulk');

    bulkActionButtons.forEach(button => {
        button.addEventListener('click', function() {
            const action = this.dataset.action;
            const selectedIds = getSelectedOrderIds();

            if (selectedIds.length === 0) {
                alert('Zaznacz przynajmniej jedno zamówienie');
                return;
            }

            switch(action) {
                case 'status':
                    handleBulkStatusChange(selectedIds);
                    break;
                case 'export':
                    handleBulkExport(selectedIds);
                    break;
                case 'wms':
                    handleGoToWMS(selectedIds);
                    break;
                case 'delete':
                    handleBulkDelete(selectedIds);
                    break;
                default:
                    console.log('Unknown action:', action);
            }
        });
    });

    /**
     * Handle bulk status change
     */
    function handleBulkStatusChange(orderIds) {
        // TODO: Implement status change modal
        // For now, just show alert
        alert(`Zmiana statusu dla ${orderIds.length} zamówień (funkcja w budowie)`);
        console.log('Change status for orders:', orderIds);
    }

    /**
     * Handle bulk export to CSV
     */
    function handleBulkExport(orderIds) {
        // Create download link with order IDs as query params
        const idsParam = orderIds.join(',');
        const exportUrl = `/admin/orders/export?ids=${idsParam}`;

        window.location.href = exportUrl;
    }

    /**
     * Handle "Zabierz do WMS" action
     */
    function handleGoToWMS(orderIds) {
        const idsParam = orderIds.join(',');
        const wmsUrl = `/admin/orders/wms?order_ids=${idsParam}`;

        window.location.href = wmsUrl;
    }

    /**
     * Handle bulk delete
     */
    function handleBulkDelete(orderIds) {
        const count = orderIds.length;
        const confirmation = confirm(
            `Czy na pewno chcesz usunąć ${count} zamówień?\n\n` +
            'Ta operacja jest nieodwracalna!'
        );

        if (!confirmation) {
            return;
        }

        // Send delete requests for each order
        Promise.all(orderIds.map(id => deleteOrder(id)))
            .then(results => {
                const successCount = results.filter(r => r.success).length;
                alert(`Usunięto ${successCount} z ${count} zamówień`);

                // Reload page to reflect changes
                window.location.reload();
            })
            .catch(error => {
                console.error('Bulk delete error:', error);
                alert('Wystąpił błąd podczas usuwania zamówień');
            });
    }

    /**
     * Delete single order (returns Promise)
     */
    function deleteOrder(orderId) {
        return fetch(`/admin/orders/${orderId}/delete`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            return { orderId, success: data.success };
        })
        .catch(error => {
            console.error(`Error deleting order ${orderId}:`, error);
            return { orderId, success: false };
        });
    }

    // ====================
    // SINGLE ORDER DELETE
    // ====================

    const deleteButtons = document.querySelectorAll('.btn-delete');

    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            const orderId = this.dataset.orderId;
            const orderNumber = this.dataset.orderNumber;

            confirmDeleteOrder(orderId, orderNumber);
        });
    });

    /**
     * Confirm and delete single order
     */
    window.confirmDeleteOrder = function(orderId, orderNumber) {
        const confirmation = confirm(
            `Czy na pewno chcesz usunąć zamówienie ${orderNumber}?\n\n` +
            'Ta operacja jest nieodwracalna!'
        );

        if (!confirmation) {
            return;
        }

        deleteOrder(orderId)
            .then(result => {
                if (result.success) {
                    // Remove row from table with animation
                    const row = document.querySelector(`tr[data-order-id="${orderId}"]`);
                    if (row) {
                        row.style.opacity = '0';
                        row.style.transition = 'opacity 0.3s';
                        setTimeout(() => {
                            row.remove();

                            // If no more rows, reload page to show empty state
                            const remainingRows = document.querySelectorAll('.orders-table tbody tr');
                            if (remainingRows.length === 0) {
                                window.location.reload();
                            }
                        }, 300);
                    }

                    // Show success message
                    showToast(`Zamówienie ${orderNumber} zostało usunięte`, 'success');
                } else {
                    showToast('Nie udało się usunąć zamówienia', 'error');
                }
            });
    };

    // ====================
    // PER PAGE SELECTOR
    // ====================

    window.changePerPage = function(perPage) {
        const url = new URL(window.location.href);
        url.searchParams.set('per_page', perPage);
        url.searchParams.set('page', '1'); // Reset to first page when changing per_page
        window.location.href = url.toString();
    };

    // ====================
    // FILTERS TOGGLE
    // ====================

    window.toggleFilters = function() {
        const filtersPanel = document.getElementById('filtersPanel');
        const chevron = filtersPanel.querySelector('.chevron');
        const filtersContent = filtersPanel.querySelector('.filters-content');

        filtersContent.classList.toggle('expanded');
        chevron.classList.toggle('rotated');
    };

    // ====================
    // UTILITY FUNCTIONS
    // ====================

    /**
     * Get CSRF token from meta tag or cookie
     */
    function getCSRFToken() {
        // Try meta tag first
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }

        // Fallback: Try to get from form
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) {
            return csrfInput.value;
        }

        return '';
    }

    /**
     * Show toast notification
     */
    function showToast(message, type = 'info') {
        // Check if global toast function exists
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            // Fallback to alert
            alert(message);
        }
    }

    // Initialize on load
    updateBulkToolbar();

    // ====================
    // ADD ORDER MODAL
    // ====================

    const addOrderBtn = document.getElementById('addOrderBtn');
    const addOrderModal = document.getElementById('addOrderModal');
    const newClientBtn = document.getElementById('newClientBtn');
    const newClientModal = document.getElementById('newClientModal');
    const clientSearchInput = document.getElementById('clientSearchInput');
    const clientSearchResults = document.getElementById('clientSearchResults');
    const newClientForm = document.getElementById('newClientForm');

    let searchTimeout = null;

    /**
     * Open Add Order Modal
     */
    if (addOrderBtn) {
        addOrderBtn.addEventListener('click', function() {
            openAddOrderModal();
        });
    }

    window.openAddOrderModal = function() {
        if (addOrderModal) {
            addOrderModal.classList.add('active');
            if (clientSearchInput) {
                clientSearchInput.value = '';
                clientSearchInput.focus();
            }
            if (clientSearchResults) {
                clientSearchResults.innerHTML = '';
            }
        }
    };

    window.closeAddOrderModal = function() {
        if (addOrderModal) {
            addOrderModal.classList.remove('active');
        }
    };

    /**
     * Open New Client Modal
     */
    if (newClientBtn) {
        newClientBtn.addEventListener('click', function() {
            closeAddOrderModal();
            openNewClientModal();
        });
    }

    window.openNewClientModal = function() {
        if (newClientModal) {
            newClientModal.classList.add('active');
            const firstInput = newClientModal.querySelector('input[name="first_name"]');
            if (firstInput) {
                firstInput.focus();
            }
        }
    };

    window.closeNewClientModal = function() {
        if (newClientModal) {
            newClientModal.classList.remove('active');
            if (newClientForm) {
                newClientForm.reset();
            }
        }
    };

    /**
     * Close modal on backdrop click
     */
    [addOrderModal, newClientModal].forEach(modal => {
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    this.classList.remove('active');
                }
            });
        }
    });

    /**
     * Close modals on ESC key
     */
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeAddOrderModal();
            closeNewClientModal();
        }
    });

    /**
     * Client Search
     */
    if (clientSearchInput) {
        clientSearchInput.addEventListener('input', function() {
            const query = this.value.trim();

            // Clear previous timeout
            if (searchTimeout) {
                clearTimeout(searchTimeout);
            }

            // Clear results if query is too short
            if (query.length < 3) {
                if (clientSearchResults) {
                    clientSearchResults.innerHTML = '<div class="search-empty-state">Wpisz min. 3 znaki, aby wyszukać</div>';
                }
                return;
            }

            // Debounce search
            searchTimeout = setTimeout(() => {
                searchClients(query);
            }, 300);
        });
    }

    /**
     * Search clients via API
     */
    function searchClients(query) {
        if (clientSearchResults) {
            clientSearchResults.innerHTML = '<div class="search-empty-state">Szukam...</div>';
        }

        fetch(`/api/clients/search?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                displaySearchResults(data.clients || []);
            })
            .catch(error => {
                console.error('Search error:', error);
                if (clientSearchResults) {
                    clientSearchResults.innerHTML = '<div class="search-empty-state">Błąd wyszukiwania</div>';
                }
            });
    }

    /**
     * Display search results
     */
    function displaySearchResults(clients) {
        if (!clientSearchResults) return;

        if (clients.length === 0) {
            clientSearchResults.innerHTML = `
                <div class="search-empty-state">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"></circle>
                        <path d="m21 21-4.35-4.35"></path>
                    </svg>
                    <p>Nie znaleziono klientów</p>
                </div>
            `;
            return;
        }

        const html = clients.map(client => `
            <div class="client-search-item" onclick="selectClient(${client.id})">
                <div class="client-info">
                    <span class="client-name">${escapeHtml(client.full_name)}</span>
                    <span class="client-email">${escapeHtml(client.email)}</span>
                </div>
                <button type="button" class="client-select-btn">Wybierz</button>
            </div>
        `).join('');

        clientSearchResults.innerHTML = html;
    }

    /**
     * Select client and redirect to create order page
     */
    window.selectClient = function(clientId) {
        // Redirect to order creation page with selected client
        window.location.href = `/admin/orders/create?client_id=${clientId}`;
    };

    /**
     * Handle new client form submission
     */
    if (newClientForm) {
        newClientForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData(this);
            const data = {
                first_name: formData.get('first_name'),
                last_name: formData.get('last_name'),
                email: formData.get('email'),
                phone: formData.get('phone') || ''
            };

            // Disable submit button
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = 'Tworzę...';
            }

            fetch('/api/clients/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify(data)
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    // Redirect to order creation with new client
                    window.location.href = `/admin/orders/create?client_id=${result.client_id}`;
                } else {
                    alert(result.error || 'Nie udało się utworzyć klienta');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = `
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M12 5v14M5 12h14"/>
                            </svg>
                            Utwórz i przejdź do zamówienia
                        `;
                    }
                }
            })
            .catch(error => {
                console.error('Create client error:', error);
                alert('Wystąpił błąd podczas tworzenia klienta');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 5v14M5 12h14"/>
                        </svg>
                        Utwórz i przejdź do zamówienia
                    `;
                }
            });
        });
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
})();
