/**
 * Orders Settings JavaScript
 * Handles order status management
 * Modals styled according to modals.css (overlay + modal pattern)
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Orders settings JS loaded');

    // ==========================================
    // TAB SWITCHING
    // ==========================================
    const tabs = document.querySelectorAll('.settings-tab');
    const panels = document.querySelectorAll('.tab-panel');

    tabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const targetTab = this.dataset.tab;

            // Remove active from all tabs and panels
            tabs.forEach(t => t.classList.remove('active'));
            panels.forEach(p => p.classList.remove('active'));

            // Add active to clicked tab and corresponding panel
            this.classList.add('active');
            const targetPanel = document.getElementById(`tab-${targetTab}`);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });

    // ==========================================
    // COLOR PICKER SYNCHRONIZATION
    // ==========================================

    /**
     * Synchronize color picker with HEX input and preview
     */
    function setupColorPicker(colorPickerId, hexInputId, previewId) {
        const colorPicker = document.getElementById(colorPickerId);
        const hexInput = document.getElementById(hexInputId);
        const preview = document.getElementById(previewId);

        if (!colorPicker || !hexInput || !preview) return;

        // Update HEX input and preview when color picker changes
        colorPicker.addEventListener('input', function() {
            const color = this.value.toUpperCase();
            hexInput.value = color;
            preview.style.backgroundColor = color;
        });

        // Update color picker and preview when HEX input changes
        hexInput.addEventListener('input', function() {
            let hex = this.value.trim();

            // Add # if missing
            if (!hex.startsWith('#')) {
                hex = '#' + hex;
            }

            // Validate HEX format
            const hexRegex = /^#[0-9A-Fa-f]{6}$/;
            if (hexRegex.test(hex)) {
                colorPicker.value = hex;
                preview.style.backgroundColor = hex;
                this.value = hex.toUpperCase();
            }
        });

        // Convert to uppercase on blur
        hexInput.addEventListener('blur', function() {
            this.value = this.value.toUpperCase();
        });
    }

    // Setup color picker for status modal
    setupColorPicker('status-badge-color', 'status-badge-color-hex', 'status-color-preview');

    // ==========================================
    // STATUS MANAGEMENT
    // ==========================================

    initializeStatusManagement();

    function initializeStatusManagement() {
        const statusModal = document.getElementById('status-modal');
        const statusForm = document.getElementById('status-form');
        const statusIdInput = document.getElementById('status-id');
        const statusModalTitle = document.getElementById('status-modal-title');

        if (!statusModal) {
            console.log('Status modal not found on this page, skipping status management initialization');
            return; // Only returns from this function, not the entire DOMContentLoaded
        }

        console.log('Status management initialized');

        /**
         * Open status modal
         */
        async function openStatusModal(statusId = null) {
            console.log('Opening status modal, ID:', statusId);

            // Reset form
            statusForm.reset();
            clearStatusFormErrors();

            if (statusId) {
                // Edit mode - fetch status data from server
                statusModalTitle.textContent = 'Edytuj status';
                statusIdInput.value = statusId;

                try {
                    const response = await fetch(`/api/orders/statuses/${statusId}`);
                    const data = await response.json();

                    if (response.ok) {
                        // Fill form with fetched data
                        document.getElementById('status-name').value = data.name;
                        document.getElementById('status-badge-color').value = data.badge_color;
                        document.getElementById('status-badge-color-hex').value = data.badge_color;
                        document.getElementById('status-color-preview').style.backgroundColor = data.badge_color;
                        document.getElementById('status-active').checked = data.is_active;
                    } else {
                        window.showToast('Błąd podczas pobierania danych statusu', 'error');
                    }
                } catch (error) {
                    console.error('Error fetching status:', error);
                    window.showToast('Błąd podczas pobierania danych statusu', 'error');
                }
            } else {
                // Add mode
                statusModalTitle.textContent = 'Dodaj status';
                statusIdInput.value = '';
                // Reset color picker to default
                document.getElementById('status-badge-color').value = '#6B7280';
                document.getElementById('status-badge-color-hex').value = '#6B7280';
                document.getElementById('status-color-preview').style.backgroundColor = '#6B7280';
            }

            // Show modal
            statusModal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        /**
         * Close status modal
         */
        function closeStatusModal() {
            statusModal.classList.add('closing');
            setTimeout(() => {
                statusModal.classList.remove('active', 'closing');
                document.body.style.overflow = '';
                clearStatusFormErrors();
            }, 350);
        }

        /**
         * Clear form errors
         */
        function clearStatusFormErrors() {
            const errorElements = statusForm.querySelectorAll('.form-error');
            errorElements.forEach(el => el.textContent = '');
        }

        /**
         * Display form errors
         */
        function displayStatusFormErrors(errors) {
            clearStatusFormErrors();
            Object.keys(errors).forEach(field => {
                const errorElement = document.getElementById(`error-status-${field}`);
                if (errorElement) {
                    errorElement.textContent = errors[field];
                }
            });
        }

        /**
         * Refresh status list from server
         */
        async function refreshStatusList() {
            try {
                const response = await fetch('/admin/orders/settings');
                const html = await response.text();

                // Parse HTML and extract statuses list
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newStatusesList = doc.querySelector('.statuses-list');

                if (newStatusesList) {
                    // Replace old list with new one
                    const oldStatusesList = document.querySelector('.statuses-list');
                    oldStatusesList.innerHTML = newStatusesList.innerHTML;

                    // Reinitialize drag & drop for new elements
                    initDragAndDrop();
                }
            } catch (error) {
                console.error('Error refreshing status list:', error);
                window.showToast('Błąd podczas odświeżania listy', 'error');
            }
        }

        /**
         * Submit status form
         */
        statusForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('Status form submitted');

            const formData = new FormData(this);
            const statusId = statusIdInput.value;

            // Determine endpoint
            let url;
            if (statusId) {
                // Edit
                url = `/admin/orders/statuses/${statusId}/edit`;
            } else {
                // Create
                url = '/admin/orders/statuses/create';
            }

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    closeStatusModal();
                    // Refresh only the status list
                    await refreshStatusList();
                } else {
                    if (data.errors) {
                        displayStatusFormErrors(data.errors);
                    } else {
                        window.showToast(data.message || 'Wystąpił błąd', 'error');
                    }
                }
            } catch (error) {
                console.error('Error submitting status:', error);
                window.showToast('Błąd podczas zapisywania statusu', 'error');
            }
        });

        // Close modal on overlay click (when clicking directly on overlay, not content)
        statusModal.addEventListener('click', function(e) {
            if (e.target === statusModal) {
                closeStatusModal();
            }
        });

        // Close modal on X button click
        document.getElementById('close-status-modal').addEventListener('click', closeStatusModal);

        // Close modal on Cancel button click
        document.getElementById('cancel-status-btn').addEventListener('click', closeStatusModal);

        // ==========================================
        // GLOBAL FUNCTIONS (called from HTML onclick)
        // ==========================================

        /**
         * Add new status
         */
        window.addStatus = function() {
            openStatusModal();
        };

        /**
         * Edit status
         */
        window.editStatus = function(statusId) {
            openStatusModal(statusId);
        };

        /**
         * Delete status - first check usage, then delete or show migration modal
         */
        window.deleteStatus = function(statusId) {
            (async () => {
                try {
                    // First check if status is in use
                    const checkResponse = await fetch(`/admin/orders/statuses/${statusId}/check-usage`);
                    const checkData = await checkResponse.json();

                    if (checkData.can_delete_directly) {
                        // No orders using this status - confirm and delete
                        if (!confirm('Czy na pewno chcesz usunąć ten status?')) {
                            return;
                        }
                        await performStatusDeletion(statusId);
                    } else {
                        // Status is in use - show migration modal
                        openMigrationModal('status', statusId, checkData);
                    }
                } catch (error) {
                    console.error('Error checking status usage:', error);
                    window.showToast('Błąd podczas sprawdzania użycia statusu', 'error');
                }
            })();
        };

        /**
         * Perform actual status deletion
         */
        async function performStatusDeletion(statusId) {
            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]').value;

                const response = await fetch(`/admin/orders/statuses/${statusId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    await refreshStatusList();
                } else {
                    window.showToast(data.message || 'Błąd podczas usuwania statusu', 'error');
                }
            } catch (error) {
                console.error('Error deleting status:', error);
                window.showToast(error.message || 'Błąd podczas usuwania statusu', 'error');
            }
        }
    } // End of initializeStatusManagement

    // ==========================================
    // DRAG & DROP REORDERING
    // ==========================================

    let draggedElement = null;
    let draggedAfterElement = null;

    /**
     * Initialize drag & drop for status list items
     */
    function initDragAndDrop() {
        const statusItems = document.querySelectorAll('.status-list-item[draggable="true"]');

        statusItems.forEach(item => {
            // Dragstart - rozpoczęcie przeciągania
            item.addEventListener('dragstart', function(e) {
                draggedElement = this;
                this.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/html', this.innerHTML);
            });

            // Dragend - zakończenie przeciągania
            item.addEventListener('dragend', function(e) {
                this.classList.remove('dragging');

                // Remove drag-over class from all items
                statusItems.forEach(item => {
                    item.classList.remove('drag-over');
                });

                // Save new order if position changed
                if (draggedElement && draggedAfterElement !== draggedElement) {
                    saveNewOrder();
                }

                draggedElement = null;
                draggedAfterElement = null;
            });

            // Dragover - element nad którym przesuwa się przeciągany element
            item.addEventListener('dragover', function(e) {
                if (e.preventDefault) {
                    e.preventDefault(); // Allows drop
                }
                e.dataTransfer.dropEffect = 'move';

                if (this === draggedElement) {
                    return;
                }

                // Remove drag-over from all
                statusItems.forEach(item => {
                    item.classList.remove('drag-over');
                });

                // Add drag-over to current
                this.classList.add('drag-over');

                return false;
            });

            // Drop - upuszczenie elementu
            item.addEventListener('drop', function(e) {
                if (e.stopPropagation) {
                    e.stopPropagation(); // Stops some browsers from redirecting
                }

                if (draggedElement !== this) {
                    // Get the container
                    const container = this.parentNode;

                    // Insert dragged element before this element
                    container.insertBefore(draggedElement, this);

                    draggedAfterElement = this;
                }

                return false;
            });

            // Dragleave - opuszczenie obszaru elementu
            item.addEventListener('dragleave', function(e) {
                this.classList.remove('drag-over');
            });
        });
    }

    /**
     * Save new order to backend
     */
    async function saveNewOrder() {
        const statusItems = document.querySelectorAll('.status-list-item[data-status-id]');
        const newOrder = [];

        statusItems.forEach((item, index) => {
            const statusId = parseInt(item.dataset.statusId);
            newOrder.push({
                id: statusId,
                sort_order: index
            });
        });

        console.log('Saving new order:', newOrder);

        try {
            // Get CSRF token from form
            const csrfToken = document.querySelector('input[name="csrf_token"]').value;

            const response = await fetch('/admin/orders/statuses/reorder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ statuses: newOrder })
            });

            const data = await response.json();

            if (data.success) {
                window.showToast('Kolejność statusów została zaktualizowana', 'success');
            } else {
                window.showToast(data.message || 'Błąd podczas zapisywania kolejności', 'error');
                // Reload page to restore correct order
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            }
        } catch (error) {
            console.error('Error saving order:', error);
            window.showToast('Błąd podczas zapisywania kolejności', 'error');
            // Reload page to restore correct order
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        }
    }

    // Initialize drag & drop on page load
    initDragAndDrop();

    // ==========================================
    // WMS STATUS MANAGEMENT
    // ==========================================

    const wmsStatusModal = document.getElementById('wms-status-modal');
    const wmsStatusForm = document.getElementById('wms-status-form');
    const wmsStatusIdInput = document.getElementById('wms-status-id');
    const wmsStatusModalTitle = document.getElementById('wms-status-modal-title');

    // Setup color picker for WMS status modal
    setupColorPicker('wms-status-badge-color', 'wms-status-badge-color-hex', 'wms-status-color-preview');

    if (wmsStatusModal) {
        /**
         * Open WMS status modal
         */
        async function openWmsStatusModal(wmsStatusId = null) {
            console.log('Opening WMS status modal, ID:', wmsStatusId);

            // Reset form
            wmsStatusForm.reset();
            clearWmsStatusFormErrors();

            if (wmsStatusId) {
                // Edit mode - fetch WMS status data from server
                wmsStatusModalTitle.textContent = 'Edytuj status WMS';
                wmsStatusIdInput.value = wmsStatusId;

                try {
                    const response = await fetch(`/api/orders/wms-statuses/${wmsStatusId}`);
                    const data = await response.json();

                    if (response.ok) {
                        // Fill form with fetched data
                        document.getElementById('wms-status-name').value = data.name;
                        document.getElementById('wms-status-badge-color').value = data.badge_color;
                        document.getElementById('wms-status-badge-color-hex').value = data.badge_color;
                        document.getElementById('wms-status-color-preview').style.backgroundColor = data.badge_color;
                        document.getElementById('wms-status-is-picked').checked = data.is_picked;
                        document.getElementById('wms-status-is-default').checked = data.is_default;
                        document.getElementById('wms-status-active').checked = data.is_active;
                    } else {
                        window.showToast('Błąd podczas pobierania danych statusu WMS', 'error');
                    }
                } catch (error) {
                    console.error('Error fetching WMS status:', error);
                    window.showToast('Błąd podczas pobierania danych statusu WMS', 'error');
                }
            } else {
                // Add mode
                wmsStatusModalTitle.textContent = 'Dodaj status WMS';
                wmsStatusIdInput.value = '';
                // Reset color picker to default
                document.getElementById('wms-status-badge-color').value = '#6B7280';
                document.getElementById('wms-status-badge-color-hex').value = '#6B7280';
                document.getElementById('wms-status-color-preview').style.backgroundColor = '#6B7280';
            }

            // Show modal
            wmsStatusModal.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        /**
         * Close WMS status modal
         */
        function closeWmsStatusModal() {
            wmsStatusModal.classList.add('closing');
            setTimeout(() => {
                wmsStatusModal.classList.remove('active', 'closing');
                document.body.style.overflow = '';
                clearWmsStatusFormErrors();
            }, 350);
        }

        /**
         * Clear WMS form errors
         */
        function clearWmsStatusFormErrors() {
            const errorElements = wmsStatusForm.querySelectorAll('.form-error');
            errorElements.forEach(el => el.textContent = '');
        }

        /**
         * Display WMS form errors
         */
        function displayWmsStatusFormErrors(errors) {
            clearWmsStatusFormErrors();
            Object.keys(errors).forEach(field => {
                const errorElement = document.getElementById(`error-wms-status-${field}`);
                if (errorElement) {
                    errorElement.textContent = errors[field];
                }
            });
        }

        /**
         * Refresh WMS status list from server
         */
        async function refreshWmsStatusList() {
            try {
                const response = await fetch('/admin/orders/settings');
                const html = await response.text();

                // Parse HTML and extract WMS statuses list
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const newWmsStatusesList = doc.querySelector('.wms-statuses-list');

                if (newWmsStatusesList) {
                    // Replace old list with new one
                    const oldWmsStatusesList = document.querySelector('.wms-statuses-list');
                    oldWmsStatusesList.innerHTML = newWmsStatusesList.innerHTML;

                    // Reinitialize drag & drop for new elements
                    initWmsDragAndDrop();
                }
            } catch (error) {
                console.error('Error refreshing WMS status list:', error);
                window.showToast('Błąd podczas odświeżania listy', 'error');
            }
        }

        /**
         * Submit WMS status form
         */
        wmsStatusForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('WMS Status form submitted');

            const formData = new FormData(this);
            const wmsStatusId = wmsStatusIdInput.value;

            // Determine endpoint
            let url;
            if (wmsStatusId) {
                // Edit
                url = `/admin/orders/wms-statuses/${wmsStatusId}/update`;
            } else {
                // Create
                url = '/admin/orders/wms-statuses/create';
            }

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    closeWmsStatusModal();
                    // Refresh only the WMS status list
                    await refreshWmsStatusList();
                } else {
                    if (data.errors) {
                        displayWmsStatusFormErrors(data.errors);
                    } else {
                        window.showToast(data.message || 'Wystąpił błąd', 'error');
                    }
                }
            } catch (error) {
                console.error('Error submitting WMS status:', error);
                window.showToast('Błąd podczas zapisywania statusu WMS', 'error');
            }
        });

        // Close modal on overlay click (when clicking directly on overlay, not content)
        wmsStatusModal.addEventListener('click', function(e) {
            if (e.target === wmsStatusModal) {
                closeWmsStatusModal();
            }
        });

        // Close modal on X button click
        document.getElementById('close-wms-status-modal').addEventListener('click', closeWmsStatusModal);

        // Close modal on Cancel button click
        document.getElementById('cancel-wms-status-btn').addEventListener('click', closeWmsStatusModal);

        // ==========================================
        // WMS GLOBAL FUNCTIONS (called from HTML onclick)
        // ==========================================

        /**
         * Add new WMS status
         */
        window.addWmsStatus = function() {
            openWmsStatusModal();
        };

        /**
         * Edit WMS status
         */
        window.editWmsStatus = function(wmsStatusId) {
            openWmsStatusModal(wmsStatusId);
        };

        /**
         * Delete WMS status - first check usage, then delete or show migration modal
         */
        window.deleteWmsStatus = function(wmsStatusId) {
            (async () => {
                try {
                    // First check if status is in use
                    const checkResponse = await fetch(`/admin/orders/wms-statuses/${wmsStatusId}/check-usage`);
                    const checkData = await checkResponse.json();

                    if (checkData.can_delete_directly) {
                        // No items using this status - confirm and delete
                        if (!confirm('Czy na pewno chcesz usunąć ten status WMS?')) {
                            return;
                        }
                        await performWmsStatusDeletion(wmsStatusId);
                    } else {
                        // Status is in use - show migration modal
                        openMigrationModal('wms', wmsStatusId, checkData);
                    }
                } catch (error) {
                    console.error('Error checking WMS status usage:', error);
                    window.showToast('Błąd podczas sprawdzania użycia statusu WMS', 'error');
                }
            })();
        };

        /**
         * Perform actual WMS status deletion
         */
        async function performWmsStatusDeletion(wmsStatusId) {
            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]').value;

                const response = await fetch(`/admin/orders/wms-statuses/${wmsStatusId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    await refreshWmsStatusList();
                } else {
                    window.showToast(data.message || 'Błąd podczas usuwania statusu WMS', 'error');
                }
            } catch (error) {
                console.error('Error deleting WMS status:', error);
                window.showToast(error.message || 'Błąd podczas usuwania statusu WMS', 'error');
            }
        }

        // ==========================================
        // WMS DRAG & DROP REORDERING
        // ==========================================

        let wmsDraggedElement = null;
        let wmsDraggedAfterElement = null;

        /**
         * Initialize drag & drop for WMS status list items
         */
        function initWmsDragAndDrop() {
            const wmsStatusItems = document.querySelectorAll('.wms-status-item[draggable="true"]');

            wmsStatusItems.forEach(item => {
                item.addEventListener('dragstart', function(e) {
                    wmsDraggedElement = this;
                    this.classList.add('dragging');
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/html', this.innerHTML);
                });

                item.addEventListener('dragend', function(e) {
                    this.classList.remove('dragging');

                    wmsStatusItems.forEach(item => {
                        item.classList.remove('drag-over');
                    });

                    if (wmsDraggedElement && wmsDraggedAfterElement !== wmsDraggedElement) {
                        saveWmsNewOrder();
                    }

                    wmsDraggedElement = null;
                    wmsDraggedAfterElement = null;
                });

                item.addEventListener('dragover', function(e) {
                    if (e.preventDefault) {
                        e.preventDefault();
                    }
                    e.dataTransfer.dropEffect = 'move';

                    if (this === wmsDraggedElement) {
                        return;
                    }

                    wmsStatusItems.forEach(item => {
                        item.classList.remove('drag-over');
                    });

                    this.classList.add('drag-over');

                    return false;
                });

                item.addEventListener('drop', function(e) {
                    if (e.stopPropagation) {
                        e.stopPropagation();
                    }

                    if (wmsDraggedElement !== this) {
                        const container = this.parentNode;
                        container.insertBefore(wmsDraggedElement, this);
                        wmsDraggedAfterElement = this;
                    }

                    return false;
                });

                item.addEventListener('dragleave', function(e) {
                    this.classList.remove('drag-over');
                });
            });
        }

        /**
         * Save new WMS order to backend
         */
        async function saveWmsNewOrder() {
            const wmsStatusItems = document.querySelectorAll('.wms-status-item[data-wms-status-id]');
            const newOrder = [];

            wmsStatusItems.forEach((item, index) => {
                const wmsStatusId = parseInt(item.dataset.wmsStatusId);
                newOrder.push({
                    id: wmsStatusId,
                    sort_order: index
                });
            });

            console.log('Saving new WMS order:', newOrder);

            try {
                const csrfToken = document.querySelector('input[name="csrf_token"]').value;

                const response = await fetch('/admin/orders/wms-statuses/reorder', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify({ statuses: newOrder })
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast('Kolejność statusów WMS została zaktualizowana', 'success');
                } else {
                    window.showToast(data.message || 'Błąd podczas zapisywania kolejności', 'error');
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                }
            } catch (error) {
                console.error('Error saving WMS order:', error);
                window.showToast('Błąd podczas zapisywania kolejności', 'error');
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            }
        }

        // Initialize WMS drag & drop on page load
        initWmsDragAndDrop();
    }

    // ==========================================
    // MIGRATION MODAL
    // ==========================================

    const migrationModal = document.getElementById('migration-modal');
    const migrationStatusId = document.getElementById('migration-status-id');
    const migrationType = document.getElementById('migration-type');
    const migrationStatusName = document.getElementById('migration-status-name');
    const migrationCount = document.getElementById('migration-count');
    const migrationTargetSelect = document.getElementById('migration-target-status');

    /**
     * Open migration modal with status info
     */
    function openMigrationModal(type, statusId, data) {
        // Store data
        migrationStatusId.value = statusId;
        migrationType.value = type;

        // Update modal title
        const modalTitle = document.getElementById('migration-modal-title');
        if (type === 'status') {
            modalTitle.textContent = 'Usuń status zamówienia';
            migrationCount.textContent = `${data.orders_count} zamówieniach`;
        } else {
            modalTitle.textContent = 'Usuń status WMS';
            migrationCount.textContent = `${data.items_count} pozycjach zamówień`;
        }

        // Set status name
        migrationStatusName.textContent = data.status_name;

        // Populate target status dropdown
        migrationTargetSelect.innerHTML = '<option value="">-- Wybierz status --</option>';
        data.available_statuses.forEach(status => {
            const option = document.createElement('option');
            option.value = status.slug;
            option.textContent = status.name;
            option.style.backgroundColor = status.badge_color;
            migrationTargetSelect.appendChild(option);
        });

        // Show modal
        migrationModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    /**
     * Close migration modal
     */
    function closeMigrationModal() {
        migrationModal.classList.add('closing');
        setTimeout(() => {
            migrationModal.classList.remove('active', 'closing');
            document.body.style.overflow = '';
            migrationTargetSelect.value = '';
        }, 350);
    }

    /**
     * Perform migration and delete status
     */
    async function performMigration() {
        const statusId = migrationStatusId.value;
        const type = migrationType.value;
        const newStatus = migrationTargetSelect.value;

        if (!newStatus) {
            window.showToast('Wybierz status zastępczy', 'error');
            return;
        }

        try {
            const csrfToken = document.querySelector('input[name="csrf_token"]').value;
            const url = type === 'status'
                ? `/admin/orders/statuses/${statusId}/migrate`
                : `/admin/orders/wms-statuses/${statusId}/migrate`;

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ new_status: newStatus })
            });

            const data = await response.json();

            if (data.success) {
                window.showToast(data.message, 'success');
                closeMigrationModal();

                // Reload page to refresh lists
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            } else {
                window.showToast(data.message || 'Błąd podczas migracji', 'error');
            }
        } catch (error) {
            console.error('Error performing migration:', error);
            window.showToast('Błąd podczas migracji', 'error');
        }
    }

    // Event listeners for migration modal
    if (migrationModal) {
        // Close modal on overlay click (when clicking directly on overlay, not content)
        migrationModal.addEventListener('click', function(e) {
            if (e.target === migrationModal) {
                closeMigrationModal();
            }
        });
        document.getElementById('close-migration-modal').addEventListener('click', closeMigrationModal);
        document.getElementById('cancel-migration-btn').addEventListener('click', closeMigrationModal);
        document.getElementById('confirm-migration-btn').addEventListener('click', performMigration);
    }
});
