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
        button.addEventListener('click', function(e) {
            const action = this.dataset.action;
            const selectedIds = getSelectedOrderIds();

            if (selectedIds.length === 0) {
                alert('Zaznacz przynajmniej jedno zamówienie');
                return;
            }

            // Prevent event from bubbling to document (for dropdown close handler)
            if (action === 'status') {
                e.stopPropagation();
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
     * Handle bulk status change - toggles dropdown
     */
    function handleBulkStatusChange(orderIds) {
        const wrapper = document.querySelector('.bulk-status-wrapper');
        const dropdown = document.getElementById('bulkStatusDropdown');

        if (!dropdown) {
            console.error('Bulk status dropdown not found');
            return;
        }

        // Toggle dropdown
        const isOpen = dropdown.classList.contains('show');

        if (isOpen) {
            closeBulkStatusDropdown();
        } else {
            // Store order IDs for later use
            dropdown.dataset.orderIds = JSON.stringify(orderIds);

            // Open dropdown
            dropdown.classList.add('show');
            if (wrapper) wrapper.classList.add('open');
        }
    }

    /**
     * Close bulk status dropdown
     */
    function closeBulkStatusDropdown() {
        const wrapper = document.querySelector('.bulk-status-wrapper');
        const dropdown = document.getElementById('bulkStatusDropdown');

        if (dropdown) dropdown.classList.remove('show');
        if (wrapper) wrapper.classList.remove('open');
    }

    /**
     * Handle status option click
     */
    function setupBulkStatusDropdown() {
        const dropdown = document.getElementById('bulkStatusDropdown');
        if (!dropdown) return;

        const options = dropdown.querySelectorAll('.bulk-status-option');

        options.forEach(option => {
            option.addEventListener('click', function() {
                const newStatus = this.dataset.status;
                const orderIds = JSON.parse(dropdown.dataset.orderIds || '[]');

                if (orderIds.length === 0 || !newStatus) {
                    showToast('Brak wybranych zamówień lub statusu', 'error');
                    return;
                }

                // Close dropdown
                closeBulkStatusDropdown();

                // Show loading toast
                showToast(`Zmieniam status ${orderIds.length} zamówień...`, 'info');

                // Send request
                fetch('/admin/orders/bulk/status', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify({
                        order_ids: orderIds,
                        status: newStatus
                    })
                })
                .then(response => response.json())
                .then(result => {
                    if (result.success) {
                        showToast(result.message, 'success');
                        // Reload page to show updated statuses
                        window.location.reload();
                    } else {
                        showToast(result.message || 'Błąd podczas zmiany statusu', 'error');
                    }
                })
                .catch(error => {
                    console.error('Bulk status change error:', error);
                    showToast('Wystąpił błąd podczas zmiany statusu', 'error');
                });
            });
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            const wrapper = document.querySelector('.bulk-status-wrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                closeBulkStatusDropdown();
            }
        });
    }

    // Initialize dropdown on page load
    setupBulkStatusDropdown();

    /**
     * Handle bulk export to XLSX
     */
    function handleBulkExport(orderIds) {
        // Create download link with order IDs as query params
        const idsParam = orderIds.join(',');
        const exportUrl = `/admin/orders/export?ids=${idsParam}`;

        showToast(`Eksportuję ${orderIds.length} zamówień do Excel...`, 'info');
        window.location.href = exportUrl;
    }

    /**
     * Handle "Zabierz do WMS" action
     */
    function handleGoToWMS(orderIds) {
        showToast(`Tworzę sesję WMS dla ${orderIds.length} zamówień...`, 'info');

        fetch('/admin/orders/wms/create-session', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ order_ids: orderIds })
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                if (result.warnings && result.warnings.length > 0) {
                    showToast(result.message + ' (pominięto: ' + result.warnings.length + ')', 'warning');
                }
                window.location.href = result.redirect_url;
            } else {
                let msg = result.message || 'Błąd tworzenia sesji WMS';
                if (result.errors && result.errors.length > 0) {
                    msg += ':\n' + result.errors.join('\n');
                }
                showToast(msg, 'error');
            }
        })
        .catch(error => {
            console.error('WMS create session error:', error);
            showToast('Wystąpił błąd podczas tworzenia sesji WMS', 'error');
        });
    }

    /**
     * Handle bulk delete - opens confirmation modal
     */
    function handleBulkDelete(orderIds) {
        const modal = document.getElementById('bulkDeleteModal');
        const countSpan = document.getElementById('bulkDeleteCount');
        const ordersList = document.getElementById('bulkDeleteOrdersList');

        if (!modal) {
            // Fallback to confirm dialog
            const count = orderIds.length;
            const confirmation = confirm(
                `Czy na pewno chcesz usunąć ${count} zamówień?\n\n` +
                'Ta operacja jest nieodwracalna!'
            );

            if (confirmation) {
                executeBulkDelete(orderIds);
            }
            return;
        }

        // Update count in modal
        if (countSpan) {
            countSpan.textContent = orderIds.length;
        }

        // Store selected IDs in modal for later use
        modal.dataset.orderIds = JSON.stringify(orderIds);

        // Fetch order details for the list
        fetch('/api/orders/bulk/info', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ order_ids: orderIds })
        })
        .then(response => response.json())
        .then(result => {
            if (result.success && ordersList) {
                const ordersHtml = result.orders.map(order => `
                    <div class="bulk-delete-order-item">
                        <span class="order-number">${escapeHtml(order.order_number)}</span>
                        <span class="order-customer">${escapeHtml(order.customer_name)}</span>
                        <span class="badge" style="background-color: ${order.status_color}; color: #fff;">${escapeHtml(order.status)}</span>
                    </div>
                `).join('');
                ordersList.innerHTML = ordersHtml;
            }
        })
        .catch(error => {
            console.error('Error fetching orders info:', error);
            if (ordersList) {
                ordersList.innerHTML = '<p>Nie udało się załadować listy zamówień</p>';
            }
        });

        // Open modal
        modal.classList.add('active');
    }

    /**
     * Close bulk delete modal
     */
    window.closeBulkDeleteModal = function() {
        const modal = document.getElementById('bulkDeleteModal');
        if (modal) {
            modal.classList.add('closing');
            setTimeout(() => {
                modal.classList.remove('active', 'closing');
            }, 350);
        }
    };

    /**
     * Confirm bulk delete
     */
    window.confirmBulkDelete = function() {
        const modal = document.getElementById('bulkDeleteModal');

        if (!modal) return;

        const orderIds = JSON.parse(modal.dataset.orderIds || '[]');

        if (orderIds.length === 0) {
            showToast('Brak wybranych zamówień', 'error');
            return;
        }

        executeBulkDelete(orderIds);
    };

    /**
     * Execute bulk delete request
     */
    function executeBulkDelete(orderIds) {
        const modal = document.getElementById('bulkDeleteModal');
        const confirmBtn = document.getElementById('bulkDeleteConfirmBtn');

        // Show loading state
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<svg class="spinner" width="16" height="16" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" stroke-dasharray="60" stroke-linecap="round"/></svg> Usuwam...';
        }

        // Send request
        fetch('/admin/orders/bulk/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ order_ids: orderIds })
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                showToast(result.message, 'success');
                if (modal) {
                    closeBulkDeleteModal();
                }
                // Reload page to show changes
                window.location.reload();
            } else {
                showToast(result.message || 'Błąd podczas usuwania', 'error');
                resetDeleteButton();
            }
        })
        .catch(error => {
            console.error('Bulk delete error:', error);
            showToast('Wystąpił błąd podczas usuwania zamówień', 'error');
            resetDeleteButton();
        });
    }

    /**
     * Reset delete button to initial state
     */
    function resetDeleteButton() {
        const confirmBtn = document.getElementById('bulkDeleteConfirmBtn');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg> Usuń zamówienia';
        }
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
        filtersPanel.classList.toggle('expanded');
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
    const bulkStatusModal = document.getElementById('bulkStatusModal');
    const bulkDeleteModal = document.getElementById('bulkDeleteModal');

    [addOrderModal, newClientModal, bulkStatusModal, bulkDeleteModal].forEach(modal => {
        if (modal) {
            modal.addEventListener('click', function(e) {
                if (e.target === this) {
                    this.classList.add('closing');
                    setTimeout(() => {
                        this.classList.remove('active', 'closing');
                    }, 350);
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
            closeBulkStatusModal();
            closeBulkDeleteModal();
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
     * Select client and create order immediately
     */
    window.selectClient = function(clientId) {
        // Show loading state in modal
        if (clientSearchResults) {
            clientSearchResults.innerHTML = '<div class="search-empty-state">Tworzę zamówienie...</div>';
        }

        // Create order via API and redirect to order detail page
        fetch('/api/orders/create-for-client', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken()
            },
            body: JSON.stringify({ client_id: clientId })
        })
        .then(response => response.json())
        .then(result => {
            if (result.success) {
                // Redirect to order detail page
                window.location.href = result.redirect_url;
            } else {
                alert(result.message || 'Nie udało się utworzyć zamówienia');
                closeAddOrderModal();
            }
        })
        .catch(error => {
            console.error('Create order error:', error);
            alert('Wystąpił błąd podczas tworzenia zamówienia');
            closeAddOrderModal();
        });
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
                submitBtn.innerHTML = 'Tworzę klienta...';
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
                    // Update button to show order creation
                    if (submitBtn) {
                        submitBtn.innerHTML = 'Tworzę zamówienie...';
                    }

                    // Now create order for this client
                    return fetch('/api/orders/create-for-client', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCSRFToken()
                        },
                        body: JSON.stringify({ client_id: result.client_id })
                    });
                } else {
                    throw new Error(result.error || 'Nie udało się utworzyć klienta');
                }
            })
            .then(response => response.json())
            .then(orderResult => {
                if (orderResult.success) {
                    // Redirect to order detail page
                    window.location.href = orderResult.redirect_url;
                } else {
                    throw new Error(orderResult.message || 'Nie udało się utworzyć zamówienia');
                }
            })
            .catch(error => {
                console.error('Create client/order error:', error);
                alert(error.message || 'Wystąpił błąd');
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

    // ====================
    // ITEMS TOGGLE
    // ====================

    /**
     * Toggle visibility of hidden order items
     */
    window.toggleOrderItems = function(orderId, totalItems) {
        const hiddenItems = document.getElementById(`hiddenItems-${orderId}`);
        const toggleBtn = hiddenItems?.parentElement.querySelector('.items-toggle-btn .toggle-text');

        if (!hiddenItems || !toggleBtn) return;

        const isHidden = hiddenItems.style.display === 'none';

        if (isHidden) {
            hiddenItems.style.display = 'flex';
            toggleBtn.textContent = 'Ukryj pozostałe';
        } else {
            hiddenItems.style.display = 'none';
            toggleBtn.textContent = `W sumie ${totalItems} przedmiotów - pokaż pozostałe`;
        }
    };

    // ====================
    // PRODUCT FILTER
    // ====================

    const productFilterSearch = document.getElementById('productFilterSearch');
    const productSearchResults = document.getElementById('productSearchResults');
    const selectedProductsContainer = document.getElementById('selectedProducts');
    const productsHiddenInput = document.getElementById('productsHiddenInput');

    // Store for selected products (id -> product data)
    let selectedProducts = new Map();
    let productSearchTimeout = null;

    // Initialize selected products from URL param
    function initSelectedProducts() {
        const productsParam = productsHiddenInput?.value;
        if (!productsParam || !productsParam.trim()) return;

        const productIds = productsParam.split(',').map(id => id.trim()).filter(id => id);
        if (productIds.length === 0) return;

        // Fetch product details for each ID
        productIds.forEach(id => {
            fetch(`/api/products/search?q=${id}&limit=1`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.products && data.products.length > 0) {
                        const product = data.products.find(p => p.id == id);
                        if (product) {
                            selectedProducts.set(product.id, product);
                            renderSelectedProducts();
                        }
                    }
                })
                .catch(err => console.error('Error fetching product:', err));
        });
    }

    // Product search input handler
    if (productFilterSearch) {
        productFilterSearch.addEventListener('input', function() {
            const query = this.value.trim();

            if (productSearchTimeout) {
                clearTimeout(productSearchTimeout);
            }

            if (query.length < 2) {
                hideProductSearchResults();
                return;
            }

            productSearchTimeout = setTimeout(() => {
                searchProducts(query);
            }, 300);
        });

        // Hide results when clicking outside
        document.addEventListener('click', function(e) {
            if (!productFilterSearch.contains(e.target) &&
                !productSearchResults.contains(e.target)) {
                hideProductSearchResults();
            }
        });

        // Handle focus - show popular/recent products immediately
        productFilterSearch.addEventListener('focus', function() {
            const query = this.value.trim();
            if (query.length >= 2) {
                searchProducts(query);
            } else {
                // Show some products on focus even without typing
                searchProducts('');
            }
        });
    }

    /**
     * Search products via API
     */
    function searchProducts(query) {
        if (!productSearchResults) return;

        productSearchResults.innerHTML = '<div class="product-search-loading">Szukam...</div>';
        productSearchResults.classList.add('active');

        fetch(`/api/products/search?q=${encodeURIComponent(query)}&limit=10`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayProductSearchResults(data.products || []);
                } else {
                    productSearchResults.innerHTML = '<div class="product-search-empty">Błąd wyszukiwania</div>';
                }
            })
            .catch(error => {
                console.error('Product search error:', error);
                productSearchResults.innerHTML = '<div class="product-search-empty">Błąd wyszukiwania</div>';
            });
    }

    // Placeholder SVG for products without images
    const PLACEHOLDER_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'%3E%3Crect width='48' height='48' fill='%23f0f0f0'/%3E%3Cpath d='M24 14a6 6 0 1 0 0 12 6 6 0 0 0 0-12zm0 10a4 4 0 1 1 0-8 4 4 0 0 1 0 8z' fill='%23ccc'/%3E%3Cpath d='M14 34v-4l6-6 4 4 8-8 6 6v8z' fill='%23ccc'/%3E%3C/svg%3E";

    /**
     * Display product search results
     */
    function displayProductSearchResults(products) {
        if (!productSearchResults) return;

        // Filter out already selected products
        const filteredProducts = products.filter(p => !selectedProducts.has(p.id));

        if (filteredProducts.length === 0) {
            productSearchResults.innerHTML = '<div class="product-search-empty">Brak wyników</div>';
            return;
        }

        const html = filteredProducts.map(product => {
            const imageUrl = product.image_url || PLACEHOLDER_IMAGE;
            const price = product.price ? `${product.price.toFixed(2)} PLN` : '';
            const sku = product.sku ? `SKU: ${product.sku}` : '';

            return `
                <div class="product-search-item" onclick="selectProduct(${product.id}, '${escapeHtml(product.name)}', '${escapeHtml(imageUrl)}', '${escapeHtml(sku)}')">
                    <img class="product-search-thumb" src="${escapeHtml(imageUrl)}" alt="" onerror="this.src='${PLACEHOLDER_IMAGE}'">
                    <div class="product-search-info">
                        <div class="product-search-name">${escapeHtml(product.name)}</div>
                        <div class="product-search-sku">${escapeHtml(sku)}</div>
                    </div>
                    <div class="product-search-price">${price}</div>
                </div>
            `;
        }).join('');

        productSearchResults.innerHTML = html;
    }

    /**
     * Hide product search results
     */
    function hideProductSearchResults() {
        if (productSearchResults) {
            productSearchResults.classList.remove('active');
        }
    }

    /**
     * Select a product from search results
     */
    window.selectProduct = function(id, name, imageUrl, sku) {
        if (selectedProducts.has(id)) return;

        selectedProducts.set(id, { id, name, image_url: imageUrl, sku });
        renderSelectedProducts();
        updateProductsHiddenInput();
        hideProductSearchResults();

        if (productFilterSearch) {
            productFilterSearch.value = '';
        }
    };

    /**
     * Remove a selected product
     */
    window.removeSelectedProduct = function(id) {
        selectedProducts.delete(id);
        renderSelectedProducts();
        updateProductsHiddenInput();
    };

    /**
     * Render selected products chips
     */
    function renderSelectedProducts() {
        if (!selectedProductsContainer) return;

        if (selectedProducts.size === 0) {
            selectedProductsContainer.innerHTML = '';
            return;
        }

        const html = Array.from(selectedProducts.values()).map(product => {
            const imageUrl = product.image_url || PLACEHOLDER_IMAGE;
            return `
                <div class="selected-product-chip">
                    <img src="${escapeHtml(imageUrl)}" alt="" onerror="this.src='${PLACEHOLDER_IMAGE}'">
                    <span>${escapeHtml(product.name)}</span>
                    <button type="button" class="selected-product-remove" onclick="removeSelectedProduct(${product.id})" title="Usuń">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
            `;
        }).join('');

        selectedProductsContainer.innerHTML = html;
    }

    /**
     * Update hidden input with selected product IDs
     */
    function updateProductsHiddenInput() {
        if (!productsHiddenInput) return;

        const ids = Array.from(selectedProducts.keys()).join(',');
        productsHiddenInput.value = ids;
    }

    // Initialize on page load
    initSelectedProducts();
})();
