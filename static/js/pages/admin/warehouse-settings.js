/**
 * Warehouse Settings JavaScript
 * Handles tab switching and SKU preview
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('Warehouse settings JS loaded');

    // Tab switching
    const tabs = document.querySelectorAll('.settings-tab');
    const panels = document.querySelectorAll('.tab-panel');

    // Check URL parameter for active tab
    const urlParams = new URLSearchParams(window.location.search);
    const activeTab = urlParams.get('tab');

    // Activate tab from URL parameter if present
    if (activeTab) {
        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));

        const targetTabBtn = document.querySelector(`.settings-tab[data-tab="${activeTab}"]`);
        const targetPanel = document.getElementById(`tab-${activeTab}`);

        if (targetTabBtn && targetPanel) {
            targetTabBtn.classList.add('active');
            targetPanel.classList.add('active');

            // Initialize Tag Management if tags tab is active
            if (activeTab === 'tags') {
                initializeTagManagement();
            }

            // Initialize Series Management if series tab is active
            if (activeTab === 'series') {
                initializeSeriesManagement();
            }

            // Initialize Manufacturers Management if manufacturers tab is active
            if (activeTab === 'manufacturers') {
                initializeManufacturersManagement();
            }

            // Initialize Supplier Management if suppliers tab is active
            if (activeTab === 'suppliers') {
                initializeSupplierManagement();
            }
        }
    }

    // Form actions visibility control
    const formActions = document.querySelector('.form-actions');
    const tabsWithoutForm = ['categories', 'tags', 'series', 'manufacturers', 'suppliers'];

    function toggleFormActions(tabName) {
        if (formActions) {
            if (tabsWithoutForm.includes(tabName)) {
                formActions.style.display = 'none';
            } else {
                formActions.style.display = 'flex';
            }
        }
    }

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

            // Update hidden input with active tab
            const activeTabInput = document.getElementById('active-tab-input');
            if (activeTabInput) {
                activeTabInput.value = targetTab;
            }

            // Toggle form actions visibility
            toggleFormActions(targetTab);

            // Initialize Tag Management when Tags tab is clicked
            if (targetTab === 'tags') {
                console.log('Tags tab activated, initializing Tag Management...');
                initializeTagManagement();
            }

            // Initialize Series Management when Series tab is clicked
            if (targetTab === 'series') {
                console.log('Series tab activated, initializing Series Management...');
                initializeSeriesManagement();
            }

            // Initialize Manufacturers Management when Manufacturers tab is clicked
            if (targetTab === 'manufacturers') {
                console.log('Manufacturers tab activated, initializing Manufacturers Management...');
                initializeManufacturersManagement();
            }

            // Initialize Supplier Management when Suppliers tab is clicked
            if (targetTab === 'suppliers') {
                console.log('Suppliers tab activated, initializing Supplier Management...');
                initializeSupplierManagement();
            }
        });
    });

    // Initial form actions visibility on page load
    if (activeTab) {
        toggleFormActions(activeTab);
    } else {
        // Default first tab is 'categories'
        toggleFormActions('categories');
    }

    // Refresh currency rates button
    const refreshRatesBtn = document.getElementById('refresh-rates');
    if (refreshRatesBtn) {
        refreshRatesBtn.addEventListener('click', async function() {
            this.disabled = true;
            this.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="animate-spin"><path fill-rule="evenodd" d="M8 3a5 5 0 104.546 2.914.5.5 0 00-.908-.417A4 4 0 118 4v1H4.5a.5.5 0 000 1h4A.5.5 0 009 5.5v-4a.5.5 0 00-1 0V3z"/></svg> Odświeżanie...';

            try {
                const response = await fetch('/api/refresh-currency-rates', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value
                    }
                });

                const data = await response.json();

                if (data.success) {
                    // Update rate inputs
                    document.getElementById('currency_krw_rate').value = data.rates.KRW;
                    document.getElementById('currency_usd_rate').value = data.rates.USD;

                    // Show success message
                    window.showToast('Kursy walut zostały zaktualizowane', 'success');

                    // Update last update time
                    const lastUpdateEl = document.querySelector('.rates-updated strong');
                    if (lastUpdateEl) {
                        lastUpdateEl.textContent = new Date().toLocaleString('pl-PL');
                    }
                } else {
                    window.showToast('Nie udało się pobrać kursów walut', 'error');
                }
            } catch (error) {
                console.error('Error refreshing rates:', error);
                window.showToast('Błąd podczas pobierania kursów', 'error');
            } finally {
                this.disabled = false;
                this.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path fill-rule="evenodd" d="M8 3a5 5 0 104.546 2.914.5.5 0 00-.908-.417A4 4 0 118 4v1H4.5a.5.5 0 000 1h4A.5.5 0 009 5.5v-4a.5.5 0 00-1 0V3z"/></svg> Odśwież kursy teraz';
            }
        });
    }

    /**
     * Category Management
     */
    const categoryModal = document.getElementById('category-modal');
    const categoryOverlay = document.getElementById('category-modal-overlay');
    const categoryForm = document.getElementById('category-form');
    const categoryIdInput = document.getElementById('category-id');
    const modalTitle = document.getElementById('category-modal-title');

    // Check if elements exist
    if (!categoryModal || !categoryOverlay) {
        console.error('Category modal elements not found');
        return;
    }

    // Open modal for adding category
    const addCategoryBtn = document.getElementById('add-category-btn');
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', function() {
            openCategoryModal();
        });
    }

    // Open modal for editing category
    document.querySelectorAll('.category-edit').forEach(btn => {
        btn.addEventListener('click', async function() {
            const categoryId = this.dataset.categoryId;
            await openCategoryModal(categoryId);
        });
    });

    // Delete category
    document.querySelectorAll('.category-delete').forEach(btn => {
        btn.addEventListener('click', async function() {
            const categoryId = this.dataset.categoryId;

            if (confirm('Czy na pewno chcesz usunąć tę kategorię?')) {
                await deleteCategory(categoryId);
            }
        });
    });

    // Close modal buttons
    document.getElementById('close-category-modal')?.addEventListener('click', closeCategoryModal);
    document.getElementById('cancel-category-btn')?.addEventListener('click', closeCategoryModal);

    // Close modal on overlay click
    categoryOverlay?.addEventListener('click', closeCategoryModal);

    // Submit form
    categoryForm?.addEventListener('submit', async function(e) {
        e.preventDefault();
        await saveCategoryForm();
    });

    /**
     * Populate parent dropdown with all categories
     */
    function populateParentDropdown(excludeId = null) {
        const parentSelect = document.getElementById('category-parent');
        const categories = Array.from(document.querySelectorAll('.category-item'));

        parentSelect.innerHTML = '<option value="0">-- Brak (kategoria główna) --</option>';

        categories.forEach(item => {
            const categoryId = parseInt(item.dataset.categoryId);
            const categoryName = item.querySelector('.category-name')?.textContent || '';

            // Exclude current category if editing
            if (!excludeId || categoryId !== excludeId) {
                const option = document.createElement('option');
                option.value = categoryId;
                option.textContent = categoryName;
                parentSelect.appendChild(option);
            }
        });
    }

    /**
     * Open category modal
     */
    async function openCategoryModal(categoryId = null) {
        // Reset form
        categoryForm.reset();
        clearFormErrors();

        if (categoryId) {
            // Edit mode
            modalTitle.textContent = 'Edytuj kategorię';
            categoryIdInput.value = categoryId;

            // Load category data
            try {
                const response = await fetch(`/admin/products/categories/${categoryId}`);
                const data = await response.json();

                if (data.success) {
                    document.getElementById('category-name').value = data.category.name;
                    document.getElementById('category-active').checked = data.category.is_active;

                    // Update parent dropdown with filtered options
                    const parentSelect = document.getElementById('category-parent');
                    parentSelect.innerHTML = '<option value="0">-- Brak (kategoria główna) --</option>';
                    data.parent_choices.forEach(choice => {
                        const option = document.createElement('option');
                        option.value = choice.value;
                        option.textContent = choice.label;
                        parentSelect.appendChild(option);
                    });
                    parentSelect.value = data.category.parent_id;
                }
            } catch (error) {
                console.error('Error loading category:', error);
                window.showToast('Błąd podczas ładowania kategorii', 'error');
                return;
            }
        } else {
            // Add mode
            modalTitle.textContent = 'Dodaj kategorię';
            categoryIdInput.value = '';

            // Populate parent dropdown with all categories
            populateParentDropdown();
        }

        // Show modal and overlay
        categoryOverlay.classList.add('active');
        categoryModal.style.display = 'block';
    }

    /**
     * Close category modal
     */
    function closeCategoryModal() {
        categoryOverlay.classList.remove('active');
        categoryModal.style.display = 'none';
        categoryForm.reset();
        clearFormErrors();
    }

    /**
     * Save category form
     */
    async function saveCategoryForm() {
        const categoryId = categoryIdInput.value;
        const url = categoryId
            ? `/admin/products/categories/${categoryId}/edit`
            : '/admin/products/categories/create';

        const formData = new FormData(categoryForm);

        try {
            const response = await fetch(url, {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.success) {
                window.showToast(data.message, 'success');
                closeCategoryModal();
                // Reload page but stay on categories tab
                setTimeout(() => {
                    window.location.href = window.location.pathname + '?tab=categories';
                }, 300);
            } else {
                // Show validation errors
                if (data.errors) {
                    Object.keys(data.errors).forEach(field => {
                        const errorEl = document.getElementById(`error-${field}`);
                        if (errorEl) {
                            errorEl.textContent = data.errors[field];
                            errorEl.style.display = 'block';
                        }
                    });
                } else {
                    window.showToast(data.message || 'Błąd podczas zapisywania kategorii', 'error');
                }
            }
        } catch (error) {
            console.error('Error saving category:', error);
            window.showToast('Błąd podczas zapisywania kategorii', 'error');
        }
    }

    /**
     * Delete category
     */
    async function deleteCategory(categoryId) {
        try {
            const response = await fetch(`/admin/products/categories/${categoryId}`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value
                }
            });

            const data = await response.json();

            if (data.success) {
                window.showToast(data.message, 'success');
                // Remove category from DOM
                const categoryItem = document.querySelector(`.category-item[data-category-id="${categoryId}"]`);
                if (categoryItem) {
                    categoryItem.remove();
                }
            } else {
                window.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('Error deleting category:', error);
            window.showToast('Błąd podczas usuwania kategorii', 'error');
        }
    }

    /**
     * Clear form errors
     */
    function clearFormErrors() {
        document.querySelectorAll('.form-error').forEach(el => {
            el.textContent = '';
            el.style.display = 'none';
        });
    }

    /**
     * Tag Management - Initialize when Tags tab is activated
     */
    let tagManagementInitialized = false;

    function initializeTagManagement() {
        if (tagManagementInitialized) {
            console.log('Tag Management already initialized, skipping...');
            return;
        }

        console.log('Initializing Tag Management...');

        const tagModal = document.getElementById('tag-modal');
        const tagOverlay = document.getElementById('tag-modal-overlay');
        const tagForm = document.getElementById('tag-form');
        const tagIdInput = document.getElementById('tag-id');
        const tagModalTitle = document.getElementById('tag-modal-title');

        console.log('Tag modal:', tagModal);
        console.log('Tag overlay:', tagOverlay);
        console.log('Tag form:', tagForm);
        console.log('Add tag button:', document.getElementById('add-tag-btn'));

        // Check if elements exist
        if (!tagModal || !tagOverlay) {
            console.error('Tag modal elements not found - modal:', tagModal, 'overlay:', tagOverlay);
            return; // Exit early if modal doesn't exist
        }

        tagManagementInitialized = true;
        console.log('Tag Management initialized successfully');

        // Tag modal exists, setup event listeners
        // Open modal for adding tag
        const addTagBtn = document.getElementById('add-tag-btn');
        if (addTagBtn) {
            addTagBtn.addEventListener('click', function() {
                console.log('Add tag button clicked');
                openTagModal();
            });
        }

        // Open modal for editing tag
        document.querySelectorAll('.tag-edit').forEach(btn => {
            btn.addEventListener('click', async function() {
                const tagId = this.dataset.tagId;
                await openTagModal(tagId);
            });
        });

        // Delete tag
        document.querySelectorAll('.tag-delete').forEach(btn => {
            btn.addEventListener('click', async function() {
                const tagId = this.dataset.tagId;

                if (confirm('Czy na pewno chcesz usunąć ten tag?')) {
                    await deleteTag(tagId);
                }
            });
        });

        // Close modal buttons
        document.getElementById('close-tag-modal')?.addEventListener('click', closeTagModal);
        document.getElementById('cancel-tag-btn')?.addEventListener('click', closeTagModal);

        // Close modal on overlay click
        tagOverlay?.addEventListener('click', closeTagModal);

        // Submit form
        tagForm?.addEventListener('submit', async function(e) {
            e.preventDefault();
            await saveTagForm();
        });

        /**
         * Open tag modal
         */
        async function openTagModal(tagId = null) {
            // Reset form
            tagForm.reset();
            clearTagFormErrors();

            if (tagId) {
                // Edit mode
                tagModalTitle.textContent = 'Edytuj tag';
                tagIdInput.value = tagId;

                // Load tag data
                try {
                    const response = await fetch(`/admin/products/tags/${tagId}`);
                    const data = await response.json();

                    if (data.success) {
                        document.getElementById('tag-name').value = data.tag.name;
                    }
                } catch (error) {
                    console.error('Error loading tag:', error);
                    window.showToast('Błąd podczas ładowania taga', 'error');
                    return;
                }
            } else {
                // Add mode
                tagModalTitle.textContent = 'Dodaj tag';
                tagIdInput.value = '';
            }

            // Show modal and overlay
            tagOverlay.classList.add('active');
            tagModal.style.display = 'block';
        }

        /**
         * Close tag modal
         */
        function closeTagModal() {
            tagOverlay.classList.remove('active');
            tagModal.style.display = 'none';
            tagForm.reset();
            clearTagFormErrors();
        }

        /**
         * Save tag form
         */
        async function saveTagForm() {
            const tagId = tagIdInput.value;
            const url = tagId
                ? `/admin/products/tags/${tagId}/edit`
                : '/admin/products/tags/create';

            const formData = new FormData(tagForm);

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    closeTagModal();

                    // Update tag list dynamically instead of reloading page
                    if (tagId) {
                        // Edit mode - update existing tag in DOM
                        const tagItem = document.querySelector(`.tag-item[data-tag-id="${tagId}"]`);
                        if (tagItem) {
                            tagItem.querySelector('.tag-name').textContent = data.tag.name;
                        }
                    } else {
                        // Create mode - add new tag to DOM
                        const tagsGrid = document.querySelector('.tags-grid');
                        const emptyState = tagsGrid.querySelector('.empty-state');

                        // Remove empty state if exists
                        if (emptyState) {
                            emptyState.remove();
                        }

                        // Create new tag element
                        const newTagHTML = `
                            <div class="tag-item" data-tag-id="${data.tag.id}">
                                <span class="tag-name">${data.tag.name}</span>
                                <div class="tag-actions">
                                    <button type="button" class="tag-action tag-edit" data-tag-id="${data.tag.id}">Edytuj</button>
                                    <button type="button" class="tag-action tag-delete" data-tag-id="${data.tag.id}">Usuń</button>
                                </div>
                            </div>
                        `;

                        tagsGrid.insertAdjacentHTML('beforeend', newTagHTML);

                        // Add event listeners to new tag buttons
                        const newTagItem = tagsGrid.querySelector(`.tag-item[data-tag-id="${data.tag.id}"]`);
                        newTagItem.querySelector('.tag-edit').addEventListener('click', async function() {
                            await openTagModal(data.tag.id);
                        });
                        newTagItem.querySelector('.tag-delete').addEventListener('click', async function() {
                            if (confirm('Czy na pewno chcesz usunąć ten tag?')) {
                                await deleteTag(data.tag.id);
                            }
                        });
                    }
                } else {
                    // Show validation errors
                    if (data.errors) {
                        Object.keys(data.errors).forEach(field => {
                            const errorEl = document.getElementById(`error-tag-${field}`);
                            if (errorEl) {
                                errorEl.textContent = data.errors[field];
                                errorEl.style.display = 'block';
                            }
                        });
                    } else {
                        window.showToast(data.message || 'Błąd podczas zapisywania taga', 'error');
                    }
                }
            } catch (error) {
                console.error('Error saving tag:', error);
                window.showToast('Błąd podczas zapisywania taga', 'error');
            }
        }

        /**
         * Delete tag
         */
        async function deleteTag(tagId) {
            try {
                const response = await fetch(`/admin/products/tags/${tagId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Remove tag from DOM
                    const tagItem = document.querySelector(`.tag-item[data-tag-id="${tagId}"]`);
                    if (tagItem) {
                        tagItem.remove();
                    }
                } else {
                    window.showToast(data.message, 'error');
                }
            } catch (error) {
                console.error('Error deleting tag:', error);
                window.showToast('Błąd podczas usuwania taga', 'error');
            }
        }

        /**
         * Clear form errors for tags
         */
        function clearTagFormErrors() {
            tagForm.querySelectorAll('.form-error').forEach(el => {
                el.textContent = '';
                el.style.display = 'none';
            });
        }
    } // End of initializeTagManagement function

    // ==========================================
    // SERIES MANAGEMENT
    // ==========================================

    let seriesManagementInitialized = false;

    function initializeSeriesManagement() {
        if (seriesManagementInitialized) {
            return;
        }

        seriesManagementInitialized = true;

        // Series management uses inline prompts like tags, not a modal
        // Add series button
        const addSeriesBtn = document.getElementById('add-series-btn');
        if (addSeriesBtn) {
            addSeriesBtn.addEventListener('click', function() {
                const seriesName = prompt('Wprowadź nazwę serii:');
                if (seriesName) {
                    createSeries(seriesName);
                }
            });
        }

        // Edit series
        document.querySelectorAll('.series-edit').forEach(btn => {
            btn.addEventListener('click', async function() {
                const seriesId = this.dataset.seriesId;
                const currentName = this.closest('.tag-item').querySelector('.tag-name').textContent;
                const newName = prompt('Wprowadź nową nazwę serii:', currentName);
                if (newName && newName !== currentName) {
                    await editSeries(seriesId, newName);
                }
            });
        });

        // Delete series
        document.querySelectorAll('.series-delete').forEach(btn => {
            btn.addEventListener('click', async function() {
                const seriesId = this.dataset.seriesId;
                if (confirm('Czy na pewno chcesz usunąć tę serię?')) {
                    await deleteSeries(seriesId);
                }
            });
        });

        async function createSeries(name) {
            try {
                const formData = new FormData();
                formData.append('name', name);
                formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

                const response = await fetch('/admin/products/series/create', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Add new series to the grid
                    const seriesGrid = document.querySelector('#tab-series .tags-grid');
                    const emptyState = seriesGrid.querySelector('.empty-state');
                    if (emptyState) {
                        emptyState.remove();
                    }

                    const newSeriesHTML = `
                        <div class="tag-item" data-series-id="${data.series.id}">
                            <span class="tag-name">${data.series.name}</span>
                            <div class="tag-actions">
                                <button type="button" class="tag-action series-edit" data-series-id="${data.series.id}">Edytuj</button>
                                <button type="button" class="tag-action series-delete" data-series-id="${data.series.id}">Usuń</button>
                            </div>
                        </div>
                    `;

                    seriesGrid.insertAdjacentHTML('beforeend', newSeriesHTML);

                    // Add event listeners to new series buttons
                    const newSeriesItem = seriesGrid.querySelector(`.tag-item[data-series-id="${data.series.id}"]`);
                    newSeriesItem.querySelector('.series-edit').addEventListener('click', async function() {
                        const currentName = this.closest('.tag-item').querySelector('.tag-name').textContent;
                        const newName = prompt('Wprowadź nową nazwę serii:', currentName);
                        if (newName && newName !== currentName) {
                            await editSeries(data.series.id, newName);
                        }
                    });
                    newSeriesItem.querySelector('.series-delete').addEventListener('click', async function() {
                        if (confirm('Czy na pewno chcesz usunąć tę serię?')) {
                            await deleteSeries(data.series.id);
                        }
                    });
                } else {
                    const errorMsg = data.errors?.name || data.message || 'Błąd podczas dodawania serii';
                    window.showToast(errorMsg, 'error');
                }
            } catch (error) {
                console.error('Error creating series:', error);
                window.showToast('Błąd podczas dodawania serii', 'error');
            }
        }

        async function editSeries(seriesId, newName) {
            try {
                const formData = new FormData();
                formData.append('name', newName);
                formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

                const response = await fetch(`/admin/products/series/${seriesId}/edit`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Update series name in DOM
                    const seriesItem = document.querySelector(`.tag-item[data-series-id="${seriesId}"]`);
                    if (seriesItem) {
                        seriesItem.querySelector('.tag-name').textContent = data.series.name;
                    }
                } else {
                    const errorMsg = data.errors?.name || data.message || 'Błąd podczas aktualizacji serii';
                    window.showToast(errorMsg, 'error');
                }
            } catch (error) {
                console.error('Error updating series:', error);
                window.showToast('Błąd podczas aktualizacji serii', 'error');
            }
        }

        async function deleteSeries(seriesId) {
            try {
                const response = await fetch(`/admin/products/series/${seriesId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Remove series from DOM
                    const seriesItem = document.querySelector(`.tag-item[data-series-id="${seriesId}"]`);
                    if (seriesItem) {
                        seriesItem.remove();
                    }

                    // Check if grid is empty and show empty state
                    const seriesGrid = document.querySelector('#tab-series .tags-grid');
                    if (seriesGrid && seriesGrid.children.length === 0) {
                        seriesGrid.innerHTML = '<div class="empty-state"><p>Brak serii produktowych. Dodaj pierwszą serię.</p></div>';
                    }
                } else {
                    window.showToast(data.message, 'error');
                }
            } catch (error) {
                console.error('Error deleting series:', error);
                window.showToast('Błąd podczas usuwania serii', 'error');
            }
        }
    } // End of initializeSeriesManagement function

    // ==========================================
    // MANUFACTURERS MANAGEMENT
    // ==========================================

    let manufacturersManagementInitialized = false;

    function initializeManufacturersManagement() {
        if (manufacturersManagementInitialized) {
            return;
        }

        manufacturersManagementInitialized = true;

        // Manufacturers management uses inline prompts like tags and series
        // Add manufacturer button
        const addManufacturerBtn = document.getElementById('add-manufacturer-btn');
        if (addManufacturerBtn) {
            addManufacturerBtn.addEventListener('click', function() {
                const manufacturerName = prompt('Wprowadź nazwę producenta:');
                if (manufacturerName) {
                    createManufacturer(manufacturerName);
                }
            });
        }

        // Edit manufacturer
        document.querySelectorAll('.manufacturer-edit').forEach(btn => {
            btn.addEventListener('click', async function() {
                const manufacturerId = this.dataset.manufacturerId;
                const currentName = this.closest('.tag-item').querySelector('.tag-name').textContent;
                const newName = prompt('Wprowadź nową nazwę producenta:', currentName);
                if (newName && newName !== currentName) {
                    await editManufacturer(manufacturerId, newName);
                }
            });
        });

        // Delete manufacturer
        document.querySelectorAll('.manufacturer-delete').forEach(btn => {
            btn.addEventListener('click', async function() {
                const manufacturerId = this.dataset.manufacturerId;
                if (confirm('Czy na pewno chcesz usunąć tego producenta?')) {
                    await deleteManufacturer(manufacturerId);
                }
            });
        });

        async function createManufacturer(name) {
            try {
                const formData = new FormData();
                formData.append('name', name);
                formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

                const response = await fetch('/admin/products/manufacturers/create', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Add new manufacturer to the grid
                    const manufacturersGrid = document.querySelector('#tab-manufacturers .tags-grid');
                    const emptyState = manufacturersGrid.querySelector('.empty-state');
                    if (emptyState) {
                        emptyState.remove();
                    }

                    const newManufacturerHTML = `
                        <div class="tag-item" data-manufacturer-id="${data.manufacturer.id}">
                            <span class="tag-name">${data.manufacturer.name}</span>
                            <div class="tag-actions">
                                <button type="button" class="tag-action manufacturer-edit" data-manufacturer-id="${data.manufacturer.id}">Edytuj</button>
                                <button type="button" class="tag-action manufacturer-delete" data-manufacturer-id="${data.manufacturer.id}">Usuń</button>
                            </div>
                        </div>
                    `;

                    manufacturersGrid.insertAdjacentHTML('beforeend', newManufacturerHTML);

                    // Add event listeners to new manufacturer buttons
                    const newManufacturerItem = manufacturersGrid.querySelector(`.tag-item[data-manufacturer-id="${data.manufacturer.id}"]`);
                    newManufacturerItem.querySelector('.manufacturer-edit').addEventListener('click', async function() {
                        const currentName = this.closest('.tag-item').querySelector('.tag-name').textContent;
                        const newName = prompt('Wprowadź nową nazwę producenta:', currentName);
                        if (newName && newName !== currentName) {
                            await editManufacturer(data.manufacturer.id, newName);
                        }
                    });
                    newManufacturerItem.querySelector('.manufacturer-delete').addEventListener('click', async function() {
                        if (confirm('Czy na pewno chcesz usunąć tego producenta?')) {
                            await deleteManufacturer(data.manufacturer.id);
                        }
                    });
                } else {
                    const errorMsg = data.errors?.name || data.message || 'Błąd podczas dodawania producenta';
                    window.showToast(errorMsg, 'error');
                }
            } catch (error) {
                console.error('Error creating manufacturer:', error);
                window.showToast('Błąd podczas dodawania producenta', 'error');
            }
        }

        async function editManufacturer(manufacturerId, newName) {
            try {
                const formData = new FormData();
                formData.append('name', newName);
                formData.append('csrf_token', document.querySelector('input[name="csrf_token"]').value);

                const response = await fetch(`/admin/products/manufacturers/${manufacturerId}/edit`, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Update manufacturer name in DOM
                    const manufacturerItem = document.querySelector(`.tag-item[data-manufacturer-id="${manufacturerId}"]`);
                    if (manufacturerItem) {
                        manufacturerItem.querySelector('.tag-name').textContent = data.manufacturer.name;
                    }
                } else {
                    const errorMsg = data.errors?.name || data.message || 'Błąd podczas aktualizacji producenta';
                    window.showToast(errorMsg, 'error');
                }
            } catch (error) {
                console.error('Error updating manufacturer:', error);
                window.showToast('Błąd podczas aktualizacji producenta', 'error');
            }
        }

        async function deleteManufacturer(manufacturerId) {
            try {
                const response = await fetch(`/admin/products/manufacturers/${manufacturerId}`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': document.querySelector('input[name="csrf_token"]')?.value
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    // Remove manufacturer from DOM
                    const manufacturerItem = document.querySelector(`.tag-item[data-manufacturer-id="${manufacturerId}"]`);
                    if (manufacturerItem) {
                        manufacturerItem.remove();
                    }

                    // Check if grid is empty and show empty state
                    const manufacturersGrid = document.querySelector('#tab-manufacturers .tags-grid');
                    if (manufacturersGrid && manufacturersGrid.children.length === 0) {
                        manufacturersGrid.innerHTML = '<div class="empty-state"><p>Brak producentów. Dodaj pierwszego producenta.</p></div>';
                    }
                } else {
                    window.showToast(data.message, 'error');
                }
            } catch (error) {
                console.error('Error deleting manufacturer:', error);
                window.showToast('Błąd podczas usuwania producenta', 'error');
            }
        }
    } // End of initializeManufacturersManagement function

    // ==========================================
    // SUPPLIER MANAGEMENT
    // ==========================================

    let supplierManagementInitialized = false;

    /**
     * Initialize Supplier Management (lazy loaded when tab is activated)
     */
    function initializeSupplierManagement() {
        if (supplierManagementInitialized) {
            console.log('Supplier Management already initialized, skipping...');
            return;
        }

        console.log('Initializing Supplier Management...');

        // Get modal elements
        const supplierModal = document.getElementById('supplier-modal');
        const supplierOverlay = document.getElementById('supplier-modal-overlay');
        const supplierForm = document.getElementById('supplier-form');
        const supplierIdInput = document.getElementById('supplier-id');
        const supplierModalTitle = document.getElementById('supplier-modal-title');
        const addSupplierBtn = document.getElementById('add-supplier-btn');
        const cancelSupplierBtn = document.getElementById('cancel-supplier-btn');
        const closeSupplierBtn = document.getElementById('close-supplier-modal');
        const saveSupplierBtn = document.getElementById('save-supplier-btn');

        if (!supplierModal || !supplierOverlay || !supplierForm) {
            console.error('Supplier modal elements not found');
            return;
        }

        console.log('Supplier modal elements found:', {
            modal: supplierModal,
            overlay: supplierOverlay,
            form: supplierForm
        });

        /**
         * Open supplier modal
         */
        function openSupplierModal(supplierId = null) {
            console.log('Opening supplier modal, ID:', supplierId);

            if (supplierId) {
                // Edit mode - fetch supplier data
                fetch(`/admin/products/suppliers/${supplierId}`)
                    .then(response => response.json())
                    .then(data => {
                        supplierModalTitle.textContent = 'Edytuj dostawcę';
                        supplierIdInput.value = supplierId;
                        document.getElementById('supplier-name').value = data.name || '';
                        document.getElementById('supplier-email').value = data.contact_email || '';
                        document.getElementById('supplier-phone').value = data.contact_phone || '';
                        document.getElementById('supplier-country').value = data.country || '';
                        document.getElementById('supplier-notes').value = data.notes || '';
                        document.getElementById('supplier-active').checked = data.is_active !== false;
                    })
                    .catch(error => {
                        console.error('Error fetching supplier:', error);
                        window.showToast('Błąd podczas ładowania danych dostawcy', 'error');
                    });
            } else {
                // Add mode
                supplierModalTitle.textContent = 'Dodaj dostawcę';
                supplierIdInput.value = '';
            }

            // Show modal and overlay
            supplierOverlay.classList.add('active');
            supplierModal.style.display = 'block';
        }

        /**
         * Close supplier modal
         */
        function closeSupplierModal() {
            supplierOverlay.classList.remove('active');
            supplierModal.style.display = 'none';
            supplierForm.reset();
            clearSupplierFormErrors();
        }

        /**
         * Save supplier form
         */
        async function saveSupplierForm() {
            const supplierId = supplierIdInput.value;
            const url = supplierId
                ? `/admin/products/suppliers/${supplierId}/edit`
                : '/admin/products/suppliers/create';

            const formData = new FormData(supplierForm);

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');
                    closeSupplierModal();

                    if (supplierId) {
                        // Edit mode - update existing supplier in table
                        const row = document.querySelector(`tr[data-supplier-id="${supplierId}"]`);
                        if (row) {
                            row.querySelector('td:nth-child(1)').textContent = data.supplier.name;
                            row.querySelector('td:nth-child(2)').textContent = data.supplier.country || '-';
                            row.querySelector('td:nth-child(3)').textContent = data.supplier.contact_email || '-';
                            row.querySelector('td:nth-child(4)').textContent = data.supplier.contact_phone || '-';
                            row.querySelector('td:nth-child(5)').innerHTML = data.supplier.is_active
                                ? '<span class="badge badge-success">Aktywny</span>'
                                : '<span class="badge badge-error">Nieaktywny</span>';
                        }
                    } else {
                        // Create mode - add new supplier to table
                        const tbody = document.querySelector('.suppliers-table tbody');
                        const emptyState = tbody.querySelector('.empty-state');

                        // Remove empty state if exists
                        if (emptyState) {
                            emptyState.remove();
                        }

                        const newRow = document.createElement('tr');
                        newRow.setAttribute('data-supplier-id', data.supplier.id);
                        newRow.innerHTML = `
                            <td>${data.supplier.name}</td>
                            <td>${data.supplier.country || '-'}</td>
                            <td>${data.supplier.contact_email || '-'}</td>
                            <td>${data.supplier.contact_phone || '-'}</td>
                            <td>
                                ${data.supplier.is_active
                                    ? '<span class="badge badge-success">Aktywny</span>'
                                    : '<span class="badge badge-error">Nieaktywny</span>'}
                            </td>
                            <td>
                                <button type="button" class="action-link supplier-edit" data-supplier-id="${data.supplier.id}">
                                    Edytuj
                                </button>
                                <button type="button" class="action-link supplier-delete" data-supplier-id="${data.supplier.id}">
                                    Usuń
                                </button>
                            </td>
                        `;
                        tbody.appendChild(newRow);

                        // Add event listeners to new buttons
                        const editBtn = newRow.querySelector('.supplier-edit');
                        const deleteBtn = newRow.querySelector('.supplier-delete');

                        editBtn.addEventListener('click', function() {
                            openSupplierModal(this.getAttribute('data-supplier-id'));
                        });

                        deleteBtn.addEventListener('click', function() {
                            deleteSupplier(this.getAttribute('data-supplier-id'));
                        });
                    }
                } else {
                    // Show validation errors
                    if (data.errors) {
                        Object.keys(data.errors).forEach(field => {
                            const input = supplierForm.querySelector(`[name="${field}"]`);
                            if (input) {
                                const errorDiv = input.parentElement.querySelector('.form-error') ||
                                    document.createElement('div');
                                errorDiv.className = 'form-error';
                                errorDiv.textContent = data.errors[field];
                                errorDiv.style.display = 'block';
                                if (!input.parentElement.querySelector('.form-error')) {
                                    input.parentElement.appendChild(errorDiv);
                                }
                            }
                        });
                    } else {
                        window.showToast(data.message, 'error');
                    }
                }
            } catch (error) {
                console.error('Error saving supplier:', error);
                window.showToast('Błąd podczas zapisywania dostawcy', 'error');
            }
        }

        /**
         * Delete supplier
         */
        async function deleteSupplier(supplierId) {
            if (!confirm('Czy na pewno chcesz usunąć tego dostawcę?')) {
                return;
            }

            try {
                const response = await fetch(`/admin/products/suppliers/${supplierId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name="csrf_token"]').value
                    }
                });

                const data = await response.json();

                if (data.success) {
                    window.showToast(data.message, 'success');

                    // Remove supplier from DOM
                    const row = document.querySelector(`tr[data-supplier-id="${supplierId}"]`);
                    if (row) {
                        row.remove();
                    }

                    // Check if table is empty and show empty state
                    const tbody = document.querySelector('.suppliers-table tbody');
                    if (tbody.querySelectorAll('tr').length === 0) {
                        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Brak dostawców</td></tr>';
                    }
                } else {
                    window.showToast(data.message, 'error');
                }
            } catch (error) {
                console.error('Error deleting supplier:', error);
                window.showToast('Błąd podczas usuwania dostawcy', 'error');
            }
        }

        /**
         * Clear form errors for suppliers
         */
        function clearSupplierFormErrors() {
            supplierForm.querySelectorAll('.form-error').forEach(el => {
                el.textContent = '';
                el.style.display = 'none';
            });
        }

        // Event listeners
        if (addSupplierBtn) {
            addSupplierBtn.addEventListener('click', () => openSupplierModal());
        }

        if (cancelSupplierBtn) {
            cancelSupplierBtn.addEventListener('click', closeSupplierModal);
        }

        if (closeSupplierBtn) {
            closeSupplierBtn.addEventListener('click', closeSupplierModal);
        }

        if (supplierOverlay) {
            supplierOverlay.addEventListener('click', closeSupplierModal);
        }

        if (supplierForm) {
            supplierForm.addEventListener('submit', function(e) {
                e.preventDefault();
                saveSupplierForm();
            });
        }

        // Edit buttons
        document.querySelectorAll('.supplier-edit').forEach(btn => {
            btn.addEventListener('click', function() {
                openSupplierModal(this.getAttribute('data-supplier-id'));
            });
        });

        // Delete buttons
        document.querySelectorAll('.supplier-delete').forEach(btn => {
            btn.addEventListener('click', function() {
                deleteSupplier(this.getAttribute('data-supplier-id'));
            });
        });

        supplierManagementInitialized = true;
        console.log('Supplier Management initialized successfully');
    } // End of initializeSupplierManagement function
});
